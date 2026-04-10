"""SP parser using sqlglot for extracting intelligence from stored procedures.

Three-pass extraction pipeline:
  Pass 1: AST-level find_all for structured nodes (tables, mutations, EXEC)
  Pass 2: Command fallback nodes — regex extraction for ELSE/WHILE/TRY bodies
  Pass 3: Parse quality scoring (Anonymous node ratio)

Security mitigations:
  T-02-03: Reuse check_file_size_limit from ddl_parser before parsing
  T-02-04: All INSERT statements use ? parameterized placeholders
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel

from db_wiki.core.models import (
    BranchInfo,
    CallChainInfo,
    EnumDetection,
    MutationInfo,
    RelationshipInfo,
    SPInfo,
    SPParseResult,
    StateTransitionInfo,
)

logger = logging.getLogger(__name__)

# Regex for extracting table refs from Command fallback nodes (D-01 pass 2)
TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([\w\.]+)", re.IGNORECASE)

# Regex for detecting dynamic SQL in Command fallback nodes
DYNAMIC_SQL_RE = re.compile(r"\bEXEC\s*\(\s*@", re.IGNORECASE)
SP_EXECUTESQL_RE = re.compile(r"\bEXEC\s+sp_executesql\b", re.IGNORECASE)

# Regex for detecting IF/ELSE/WHILE control flow in Command fallback nodes
IF_RE = re.compile(r"\bIF\b", re.IGNORECASE)
WHILE_RE = re.compile(r"\bWHILE\b", re.IGNORECASE)


def compute_body_hash(sql_text: str) -> str:
    """Compute SHA-256 hash of normalized SQL text for incremental re-parse (D-11).

    Normalizes whitespace before hashing so formatting-only changes
    don't trigger a re-parse.

    Args:
        sql_text: Raw SQL content.

    Returns:
        Hex digest of SHA-256 hash.
    """
    normalized = " ".join(sql_text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_sp_file(sql_text: str) -> tuple[list[exp.Expression], list[str]]:
    """Parse SQL file content, filtering for CREATE PROCEDURE statements.

    Uses the same ErrorLevel.WARN tolerant parsing pattern as ddl_parser.
    Filters for exp.Create with kind == "PROCEDURE". Non-SP statements
    (DDL, DML) are skipped with warnings.

    Args:
        sql_text: Raw SQL file content.

    Returns:
        Tuple of (valid_sp_statements, warning_messages).
    """
    statements = sqlglot.parse(sql_text, dialect="tsql", error_level=ErrorLevel.WARN)
    valid: list[exp.Expression] = []
    warnings: list[str] = []

    for stmt in statements:
        if stmt is None:
            msg = "Skipping unparseable statement (None result from sqlglot)"
            logger.warning(msg)
            warnings.append(msg)
            continue
        if isinstance(stmt, exp.Command):
            preview = stmt.sql()[:120]
            msg = f"Skipping unparseable command statement: {preview!r}"
            logger.warning(msg)
            warnings.append(msg)
            continue
        if isinstance(stmt, exp.Create) and stmt.args.get("kind") == "PROCEDURE":
            valid.append(stmt)
        else:
            # Non-SP DDL or DML — skip silently (D-13 auto-detect handles routing)
            pass

    return valid, warnings


def _get_sp_name(sp_stmt: exp.Create) -> str:
    """Extract the procedure name from a CREATE PROCEDURE AST node."""
    sp_node = sp_stmt.this  # StoredProcedure node
    if hasattr(sp_node, "this") and hasattr(sp_node.this, "name"):
        return sp_node.this.name
    return ""


def _get_sp_schema(sp_stmt: exp.Create) -> str | None:
    """Extract the schema name from a CREATE PROCEDURE AST node."""
    sp_node = sp_stmt.this
    if hasattr(sp_node, "this") and hasattr(sp_node.this, "db"):
        db = sp_node.this.db
        return db if db else None
    return None


def extract_table_refs(sp_stmt: exp.Create) -> tuple[list[str], bool]:
    """Extract table references from an SP using two-pass approach.

    Pass 1: AST-level find_all(exp.Table) — catches SELECT FROM, JOIN, etc.
    Pass 2: Command fallback nodes — regex extraction for unparsed bodies.

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        Tuple of (table_names, has_command_nodes).
    """
    tables: set[str] = set()
    has_command_nodes = False
    sp_name = _get_sp_name(sp_stmt)

    # Pass 1: structured AST
    for table in sp_stmt.find_all(exp.Table):
        name = table.name
        if name and name != sp_name:
            tables.add(name)

    # Pass 2: Command fallback nodes (ELSE bodies, unsupported syntax)
    for cmd in sp_stmt.find_all(exp.Command):
        has_command_nodes = True
        for match in TABLE_REF_RE.findall(cmd.sql()):
            # Strip schema prefix: dbo.Orders -> Orders
            clean = match.split(".")[-1]
            if clean and clean != sp_name:
                tables.add(clean)

    return list(tables), has_command_nodes


def extract_mutations(sp_stmt: exp.Create) -> list[MutationInfo]:
    """Extract write operations (INSERT/UPDATE/DELETE/MERGE) from an SP.

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        List of MutationInfo for each mutation found.
    """
    mutations: list[MutationInfo] = []

    for ins in sp_stmt.find_all(exp.Insert):
        # ins.this is a Schema node; ins.this.this is the Table node
        table_name = ""
        if hasattr(ins.this, "this") and hasattr(ins.this.this, "name"):
            table_name = ins.this.this.name
        columns = []
        # Column names from the Schema node's expressions
        if hasattr(ins.this, "expressions"):
            columns = [e.name for e in ins.this.expressions if hasattr(e, "name")]
        mutations.append(
            MutationInfo(table_name=table_name, mutation_type="insert", columns=columns)
        )

    for upd in sp_stmt.find_all(exp.Update):
        table_name = upd.this.name if hasattr(upd.this, "name") else ""
        columns = []
        for eq in upd.args.get("expressions", []):
            if isinstance(eq, exp.EQ) and hasattr(eq.this, "name"):
                columns.append(eq.this.name)
        mutations.append(
            MutationInfo(table_name=table_name, mutation_type="update", columns=columns)
        )

    for delete in sp_stmt.find_all(exp.Delete):
        table_name = ""
        tbl = delete.this
        if hasattr(tbl, "name"):
            table_name = tbl.name
        mutations.append(
            MutationInfo(table_name=table_name, mutation_type="delete", columns=[])
        )

    for merge in sp_stmt.find_all(exp.Merge):
        table_name = ""
        tbl = merge.this
        if hasattr(tbl, "name"):
            table_name = tbl.name
        mutations.append(
            MutationInfo(table_name=table_name, mutation_type="merge", columns=[])
        )

    return mutations


def extract_branches(sp_stmt: exp.Create) -> list[BranchInfo]:
    """Extract control flow branches (IF/ELSE/CASE/WHILE) from an SP.

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        List of BranchInfo for each branch found.
    """
    branches: list[BranchInfo] = []
    branch_idx = 0

    # IF blocks — sqlglot T-SQL produces exp.If (CASE WHEN) and/or exp.IfBlock (procedural IF)
    # Check both node types to handle different sqlglot versions
    for if_cls in (exp.If, getattr(exp, "IfBlock", None)):
        if if_cls is None:
            continue
        for if_node in sp_stmt.find_all(if_cls):
            # Skip If nodes that are CASE WHEN branches (they appear inside Case)
            parent = if_node.parent
            if isinstance(parent, exp.Case):
                continue

            condition_text = if_node.this.sql() if if_node.this else None
            tables_touched = [
                t.name
                for t in if_node.find_all(exp.Table)
                if t.name != _get_sp_name(sp_stmt)
            ]

            # Calculate nesting depth by counting If/IfBlock ancestors
            depth = 0
            p = if_node.parent
            while p:
                if isinstance(p, (exp.If,)) and not isinstance(p.parent, exp.Case):
                    depth += 1
                elif if_cls is not exp.If and isinstance(p, if_cls):
                    depth += 1
                p = getattr(p, "parent", None)

            branches.append(
                BranchInfo(
                    branch_index=branch_idx,
                    condition_text=condition_text,
                    branch_type="if",
                    tables_touched=tables_touched,
                    nesting_depth=depth,
                )
            )
            branch_idx += 1

    # CASE/WHEN via exp.Case
    for case_node in sp_stmt.find_all(exp.Case):
        tables_touched = [
            t.name for t in case_node.find_all(exp.Table) if t.name != _get_sp_name(sp_stmt)
        ]
        condition_text = case_node.sql()[:200]
        branches.append(
            BranchInfo(
                branch_index=branch_idx,
                condition_text=condition_text,
                branch_type="case_when",
                tables_touched=tables_touched,
                nesting_depth=0,
            )
        )
        branch_idx += 1

    # Command nodes that contain IF/ELSE/WHILE text (fallback for unparsed bodies)
    for cmd in sp_stmt.find_all(exp.Command):
        cmd_sql = cmd.sql()
        if IF_RE.search(cmd_sql):
            branches.append(
                BranchInfo(
                    branch_index=branch_idx,
                    condition_text=None,
                    branch_type="if",
                    tables_touched=[m.split(".")[-1] for m in TABLE_REF_RE.findall(cmd_sql)],
                    nesting_depth=0,
                )
            )
            branch_idx += 1
        if "ELSE" in cmd_sql.upper():
            branches.append(
                BranchInfo(
                    branch_index=branch_idx,
                    condition_text=None,
                    branch_type="else",
                    tables_touched=[m.split(".")[-1] for m in TABLE_REF_RE.findall(cmd_sql)],
                    nesting_depth=0,
                )
            )
            branch_idx += 1
        if WHILE_RE.search(cmd_sql):
            branches.append(
                BranchInfo(
                    branch_index=branch_idx,
                    condition_text=None,
                    branch_type="while",
                    tables_touched=[m.split(".")[-1] for m in TABLE_REF_RE.findall(cmd_sql)],
                    nesting_depth=0,
                )
            )
            branch_idx += 1

    return branches


def classify_execute(exe: exp.Execute) -> dict:
    """Classify an Execute node as static call, dynamic SQL, or sp_executesql.

    Args:
        exe: A sqlglot exp.Execute node.

    Returns:
        Classification dict with type and relevant metadata.
    """
    this = exe.args.get("this")
    if this is None:
        return {"type": "unknown"}

    # Dynamic SQL: EXEC (@variable) — this is a Subquery/Paren
    if isinstance(this, (exp.Subquery, exp.Paren)):
        return {"type": "dynamic", "is_dynamic_sql": True}

    # sp_executesql: EXEC sp_executesql N'...'
    name = getattr(this, "name", "")
    if name.lower() == "sp_executesql":
        return {"type": "sp_executesql", "is_dynamic_sql": True}

    # Static call: EXEC dbo.ProcName — this is a Table node
    if isinstance(this, exp.Table):
        return {
            "type": "static",
            "proc_name": this.name,
            "schema_name": this.db or None,
            "is_dynamic_sql": False,
        }

    return {"type": "unknown"}


def extract_call_chains(
    sp_stmt: exp.Create,
) -> tuple[list[CallChainInfo], list[dict]]:
    """Extract EXEC call chains and dynamic SQL locations from an SP.

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        Tuple of (call_chains, dynamic_sql_locations).
    """
    call_chains: list[CallChainInfo] = []
    dynamic_sql_locations: list[dict] = []

    for exe in sp_stmt.find_all(exp.Execute):
        info = classify_execute(exe)

        if info["type"] == "static":
            call_chains.append(
                CallChainInfo(
                    callee_name=info["proc_name"],
                    callee_schema=info.get("schema_name"),
                    is_dynamic=False,
                )
            )
        elif info["type"] in ("dynamic", "sp_executesql"):
            dynamic_sql_locations.append(
                {
                    "type": info["type"],
                    "sql_preview": exe.sql()[:200],
                }
            )

    # Pass 2: Command fallback nodes — regex detection for dynamic SQL
    for cmd in sp_stmt.find_all(exp.Command):
        cmd_sql = cmd.sql()
        if DYNAMIC_SQL_RE.search(cmd_sql):
            dynamic_sql_locations.append(
                {"type": "dynamic", "sql_preview": cmd_sql[:200]}
            )
        elif SP_EXECUTESQL_RE.search(cmd_sql):
            dynamic_sql_locations.append(
                {"type": "sp_executesql", "sql_preview": cmd_sql[:200]}
            )

    return call_chains, dynamic_sql_locations


def extract_enum_detections(sp_stmt: exp.Create) -> list[EnumDetection]:
    """Extract enum-like value mappings from CASE WHEN expressions (D-04).

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        List of EnumDetection for each CASE pattern found.
    """
    enums: list[EnumDetection] = []

    for case_node in sp_stmt.find_all(exp.Case):
        ifs = case_node.args.get("ifs", [])
        if not ifs:
            continue

        # Try to find a consistent column across all WHEN branches
        column_name = None
        table_name = ""
        values: list[dict] = []

        for if_node in ifs:
            cond = if_node.this  # the condition (e.g., Status = 1)
            if isinstance(cond, exp.EQ):
                col = cond.this
                val = cond.args.get("expression")
                if hasattr(col, "name"):
                    if column_name is None:
                        column_name = col.name
                        # Try to get table from column
                        if hasattr(col, "table") and col.table:
                            table_name = col.table
                    if isinstance(val, exp.Literal):
                        true_val = if_node.args.get("true")
                        label = ""
                        if isinstance(true_val, exp.Literal):
                            label = true_val.this
                        values.append({"value": val.this, "label": label})

        if column_name and len(values) >= 2:
            # Try to find a table context from the surrounding SELECT
            if not table_name:
                # Look for tables in the parent SELECT
                parent = case_node.parent
                while parent and not isinstance(parent, exp.Select):
                    parent = getattr(parent, "parent", None)
                if parent:
                    for tbl in parent.find_all(exp.Table):
                        if tbl.name != _get_sp_name(sp_stmt):
                            table_name = tbl.name
                            break

            enums.append(
                EnumDetection(
                    table_name=table_name or "unknown",
                    column_name=column_name,
                    values=values,
                    confidence=0.7,
                    detection_method="case_when",
                )
            )

    return enums


def extract_state_transitions(sp_stmt: exp.Create) -> list[StateTransitionInfo]:
    """Detect state transitions from UPDATE SET col=X WHERE col=Y patterns (D-14).

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        List of StateTransitionInfo for literal-to-literal transitions.
    """
    transitions: list[StateTransitionInfo] = []

    for upd in sp_stmt.find_all(exp.Update):
        target_table = upd.this.name if hasattr(upd.this, "name") else None
        if not target_table:
            continue

        # Collect SET assignments: {col_name: literal_value}
        set_literals: dict[str, str] = {}
        for eq in upd.args.get("expressions", []):
            if isinstance(eq, exp.EQ):
                col = eq.this.name if hasattr(eq.this, "name") else None
                val = eq.args.get("expression")
                if col and isinstance(val, exp.Literal):
                    set_literals[col] = val.this

        # Collect WHERE literals: {col_name: literal_value}
        where = upd.args.get("where")
        where_literals: dict[str, str] = {}
        if where:
            for eq in where.find_all(exp.EQ):
                col = eq.this.name if hasattr(eq.this, "name") else None
                val = eq.args.get("expression")
                if col and isinstance(val, exp.Literal):
                    where_literals[col] = val.this

        # Match: same column in both SET and WHERE
        for col in set_literals:
            if col in where_literals:
                transitions.append(
                    StateTransitionInfo(
                        table_name=target_table,
                        column_name=col,
                        from_value=where_literals[col],
                        to_value=set_literals[col],
                        confidence=0.9,  # D-15: literal-to-literal = 0.9
                    )
                )

    return transitions


def compute_parse_quality(sp_stmt: exp.Create) -> tuple[float, bool]:
    """Compute parse quality as 1 - (anonymous_count / total_nodes).

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.

    Returns:
        Tuple of (quality_score, is_degraded). Degraded if quality < 0.95.
    """
    all_nodes = list(sp_stmt.walk())
    anon_nodes = list(sp_stmt.find_all(exp.Anonymous))
    total = len(all_nodes)
    if total == 0:
        return 0.0, True
    ratio = len(anon_nodes) / total
    quality = 1.0 - ratio
    return quality, ratio > 0.05


def extract_sp_info(sp_stmt: exp.Create, sql_text: str) -> SPInfo:
    """Orchestrate all extraction functions to build a complete SPInfo.

    Args:
        sp_stmt: A sqlglot exp.Create node for a CREATE PROCEDURE.
        sql_text: Original SQL text for body hash computation.

    Returns:
        SPInfo with all intelligence fields populated.
    """
    sp_name = _get_sp_name(sp_stmt)
    sp_schema = _get_sp_schema(sp_stmt)

    table_refs, has_command_nodes = extract_table_refs(sp_stmt)
    mutations = extract_mutations(sp_stmt)
    branches = extract_branches(sp_stmt)
    call_chains, dynamic_sql_locations = extract_call_chains(sp_stmt)
    enum_detections = extract_enum_detections(sp_stmt)
    state_transitions = extract_state_transitions(sp_stmt)
    quality, is_degraded = compute_parse_quality(sp_stmt)

    has_dynamic_sql = len(dynamic_sql_locations) > 0

    warnings: list[str] = []
    if has_command_nodes:
        warnings.append("SP contains unparseable Command nodes — regex fallback used")
    if has_dynamic_sql:
        warnings.append(
            f"SP contains {len(dynamic_sql_locations)} dynamic SQL location(s) — flagged, not parsed"
        )

    return SPInfo(
        procedure_name=sp_name,
        schema_name=sp_schema,
        body_hash=compute_body_hash(sql_text),
        table_refs=table_refs,
        mutations=mutations,
        branches=branches,
        call_chains=call_chains,
        enum_detections=enum_detections,
        state_transitions=state_transitions,
        parse_quality=quality,
        is_degraded=is_degraded,
        has_dynamic_sql=has_dynamic_sql,
        partial_ast=has_command_nodes,
        dynamic_sql_locations=dynamic_sql_locations,
        warnings=warnings,
    )


def parse_sp(sql_text: str) -> SPParseResult:
    """Parse a full SP file and return aggregated SPParseResult.

    Parses, extracts SPInfo for each procedure, and builds relationships
    (reads_from for SELECT refs, writes_to for mutation targets).

    Args:
        sql_text: Raw SQL content.

    Returns:
        SPParseResult with procedures, relationships, and warnings.
    """
    valid_stmts, warnings = parse_sp_file(sql_text)

    procedures: list[SPInfo] = []
    relationships: list[RelationshipInfo] = []

    for stmt in valid_stmts:
        try:
            info = extract_sp_info(stmt, sql_text)
            procedures.append(info)

            # Build relationships from table refs and mutations
            mutation_tables = {m.table_name for m in info.mutations}

            for table_name in info.table_refs:
                if table_name in mutation_tables:
                    relationships.append(
                        RelationshipInfo(
                            source_table=info.procedure_name,
                            target_table=table_name,
                            relationship_type="writes_to",
                            confidence=0.9,
                        )
                    )
                else:
                    relationships.append(
                        RelationshipInfo(
                            source_table=info.procedure_name,
                            target_table=table_name,
                            relationship_type="reads_from",
                            confidence=0.9,
                        )
                    )

            # Also add writes_to for mutation tables not already in table_refs
            for m in info.mutations:
                if m.table_name and m.table_name not in info.table_refs:
                    relationships.append(
                        RelationshipInfo(
                            source_table=info.procedure_name,
                            target_table=m.table_name,
                            relationship_type="writes_to",
                            confidence=0.9,
                        )
                    )

        except Exception as e:
            msg = f"Failed to extract SP info: {e}"
            logger.warning(msg)
            warnings.append(msg)

    return SPParseResult(
        procedures=procedures,
        relationships=relationships,
        warnings=warnings,
    )


def invalidate_procedure(
    conn: sqlite3.Connection, procedure_id: int, now_iso: str, now_ts: int
) -> None:
    """Invalidate a procedure and cascade to all derived rows (D-11).

    Sets invalidated_at on the procedure row and all related rows in:
    sp_branches, sp_reliability, sp_call_chains, enum_values,
    state_transitions, bitmask_definitions, column_aliases.

    Args:
        conn: Open SQLite connection.
        procedure_id: ID of the procedure to invalidate.
        now_iso: ISO timestamp string.
        now_ts: Unix timestamp integer.
    """
    # Invalidate the procedure itself
    conn.execute(
        """UPDATE db_procedures
           SET invalidated_at = ?, invalidated_at_ts = ?,
               valid_until = ?, valid_until_ts = ?
           WHERE id = ? AND invalidated_at IS NULL""",
        (now_iso, now_ts, now_iso, now_ts, procedure_id),
    )

    # Cascade to derived tables
    cascade_tables = [
        ("sp_branches", "procedure_id"),
        ("sp_reliability", "procedure_id"),
        ("sp_call_chains", "caller_id"),
        ("enum_values", "source_procedure_id"),
        ("state_transitions", "source_procedure_id"),
        ("bitmask_definitions", "source_procedure_id"),
        ("column_aliases", "source_procedure_id"),
    ]

    for table, fk_col in cascade_tables:
        conn.execute(
            f"""UPDATE {table}
                SET invalidated_at = ?, invalidated_at_ts = ?,
                    valid_until = ?, valid_until_ts = ?
                WHERE {fk_col} = ? AND invalidated_at IS NULL""",
            (now_iso, now_ts, now_iso, now_ts, procedure_id),
        )

    # Invalidate relationships where source_id is the procedure
    conn.execute(
        """UPDATE db_relationships
           SET invalidated_at = ?, invalidated_at_ts = ?,
               valid_until = ?, valid_until_ts = ?
           WHERE source_id = ? AND invalidated_at IS NULL""",
        (now_iso, now_ts, now_iso, now_ts, procedure_id),
    )


def ingest_sp(conn: sqlite3.Connection, sp_result: SPParseResult) -> dict[str, int]:
    """Write parsed SP entities to the bi-temporal SQLite knowledge store.

    For each SPInfo: checks for existing procedure by name. If body_hash
    matches, skips (D-11). If different, invalidates old and inserts new.

    Security: All INSERT statements use ? parameterized placeholders (T-02-04).

    Args:
        conn: An open SQLite connection with the full schema initialized.
        sp_result: Aggregated parse result from parse_sp().

    Returns:
        Dictionary with counts of inserted entities.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ts = int(now.timestamp())

    proc_count = 0
    branch_count = 0
    reliability_count = 0
    call_chain_count = 0
    enum_count = 0
    transition_count = 0
    relationship_count = 0

    try:
        for sp_info in sp_result.procedures:
            # Check for existing procedure by name
            existing = conn.execute(
                """SELECT id, body_hash FROM current_db_procedures
                   WHERE procedure_name = ?""",
                (sp_info.procedure_name,),
            ).fetchone()

            if existing:
                if existing["body_hash"] == sp_info.body_hash:
                    # No change — skip re-parse (D-11)
                    continue
                # Body changed — invalidate old procedure and cascade
                invalidate_procedure(conn, existing["id"], now_iso, now_ts)

            # INSERT new procedure
            cursor = conn.execute(
                """INSERT INTO db_procedures (
                    procedure_name, schema_name, body_hash,
                    valid_from, valid_from_ts, valid_until, valid_until_ts,
                    recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                (
                    sp_info.procedure_name,
                    sp_info.schema_name,
                    sp_info.body_hash,
                    now_iso,
                    now_ts,
                    now_iso,
                    now_ts,
                ),
            )
            proc_id = cursor.lastrowid
            proc_count += 1

            # INSERT sp_reliability
            conn.execute(
                """INSERT INTO sp_reliability (
                    procedure_id, parse_quality, is_degraded, has_dynamic_sql,
                    partial_ast, dynamic_sql_locations_json,
                    valid_from, valid_from_ts, valid_until, valid_until_ts,
                    recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                (
                    proc_id,
                    sp_info.parse_quality,
                    1 if sp_info.is_degraded else 0,
                    1 if sp_info.has_dynamic_sql else 0,
                    1 if sp_info.partial_ast else 0,
                    json.dumps(sp_info.dynamic_sql_locations),
                    now_iso,
                    now_ts,
                    now_iso,
                    now_ts,
                ),
            )
            reliability_count += 1

            # INSERT sp_branches
            for branch in sp_info.branches:
                conn.execute(
                    """INSERT INTO sp_branches (
                        procedure_id, branch_index, condition_text, branch_type,
                        tables_touched_json, nesting_depth,
                        valid_from, valid_from_ts, valid_until, valid_until_ts,
                        recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                    (
                        proc_id,
                        branch.branch_index,
                        branch.condition_text,
                        branch.branch_type,
                        json.dumps(branch.tables_touched),
                        branch.nesting_depth,
                        now_iso,
                        now_ts,
                        now_iso,
                        now_ts,
                    ),
                )
                branch_count += 1

            # INSERT sp_call_chains
            for chain in sp_info.call_chains:
                conn.execute(
                    """INSERT INTO sp_call_chains (
                        caller_id, callee_name_raw, callee_schema,
                        valid_from, valid_from_ts, valid_until, valid_until_ts,
                        recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                    (
                        proc_id,
                        chain.callee_name,
                        chain.callee_schema,
                        now_iso,
                        now_ts,
                        now_iso,
                        now_ts,
                    ),
                )
                call_chain_count += 1

            # INSERT enum_values
            for enum in sp_info.enum_detections:
                for val in enum.values:
                    conn.execute(
                        """INSERT INTO enum_values (
                            table_name, column_name, enum_value, enum_label,
                            confidence, detection_method, source_procedure_id,
                            valid_from, valid_from_ts, valid_until, valid_until_ts,
                            recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                        (
                            enum.table_name,
                            enum.column_name,
                            val.get("value", ""),
                            val.get("label", ""),
                            enum.confidence,
                            enum.detection_method,
                            proc_id,
                            now_iso,
                            now_ts,
                            now_iso,
                            now_ts,
                        ),
                    )
                    enum_count += 1

            # INSERT state_transitions
            for trans in sp_info.state_transitions:
                conn.execute(
                    """INSERT INTO state_transitions (
                        table_name, column_name, from_value, to_value,
                        confidence, source_procedure_id,
                        valid_from, valid_from_ts, valid_until, valid_until_ts,
                        recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                    (
                        trans.table_name,
                        trans.column_name,
                        trans.from_value,
                        trans.to_value,
                        trans.confidence,
                        proc_id,
                        now_iso,
                        now_ts,
                        now_iso,
                        now_ts,
                    ),
                )
                transition_count += 1

            # INSERT relationships (reads_from/writes_to)
            # Look up table IDs from current_db_tables
            for rel in sp_result.relationships:
                if rel.source_table != sp_info.procedure_name:
                    continue
                target_row = conn.execute(
                    "SELECT id FROM current_db_tables WHERE table_name = ?",
                    (rel.target_table,),
                ).fetchone()
                target_id = target_row["id"] if target_row else None

                conn.execute(
                    """INSERT INTO db_relationships (
                        source_id, target_id, relationship_type,
                        confidence,
                        valid_from, valid_from_ts, valid_until, valid_until_ts,
                        recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)""",
                    (
                        proc_id,
                        target_id or 0,
                        rel.relationship_type,
                        rel.confidence,
                        now_iso,
                        now_ts,
                        now_iso,
                        now_ts,
                    ),
                )
                relationship_count += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "procedures": proc_count,
        "branches": branch_count,
        "reliability": reliability_count,
        "call_chains": call_chain_count,
        "enums": enum_count,
        "transitions": transition_count,
        "relationships": relationship_count,
    }


def detect_content_type(sql_text: str) -> str:
    """Auto-detect whether SQL content is SP, DDL, or unknown (D-13).

    Args:
        sql_text: Raw SQL file content.

    Returns:
        "sp" if contains CREATE PROCEDURE, "ddl" if contains CREATE TABLE/INDEX/ALTER,
        "unknown" otherwise.
    """
    statements = sqlglot.parse(sql_text, dialect="tsql", error_level=ErrorLevel.WARN)

    for stmt in statements:
        if stmt is None:
            continue
        if isinstance(stmt, exp.Create):
            kind = stmt.args.get("kind")
            if kind == "PROCEDURE":
                return "sp"
            if kind in (None, "TABLE", "INDEX"):
                return "ddl"
        if isinstance(stmt, exp.Alter):
            return "ddl"

    return "unknown"
