"""DDL parser using sqlglot for extracting schema entities from SQL files.

Handles T-SQL DDL: CREATE TABLE, CREATE INDEX, ALTER TABLE ADD CONSTRAINT.
Uses tolerant parsing (D-04): bad statements are logged and skipped without
failing the entire file.

Security mitigations:
  T-02-01: File size check before passing to sqlglot (check_file_size_limit)
  T-02-02: Parameterized SQL (?) placeholders for all INSERT statements
  T-02-03: sqlglot parses SQL structurally — no SQL is ever executed
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel

from db_wiki.core.models import (
    ColumnInfo,
    ConstraintInfo,
    IndexInfo,
    ParseResult,
    RelationshipInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)


def check_file_size_limit(sql_text: str, max_mb: int = 50) -> None:
    """Reject SQL content larger than max_mb megabytes (T-02-01 mitigation).

    Args:
        sql_text: The SQL content to check.
        max_mb: Maximum allowed size in megabytes. Default 50.

    Raises:
        ValueError: If the file size exceeds the limit.
    """
    size_bytes = len(sql_text.encode("utf-8"))
    limit_bytes = max_mb * 1024 * 1024
    if size_bytes > limit_bytes:
        size_mb = size_bytes / (1024 * 1024)
        raise ValueError(
            f"File size {size_mb:.1f}MB exceeds limit of {max_mb}MB. "
            "Reduce file size or increase max_file_size_mb in config."
        )


def parse_ddl_file(sql_text: str) -> tuple[list[exp.Expression], list[str]]:
    """Parse SQL file content, skipping unparseable statements (D-04).

    Calls sqlglot.parse() with T-SQL dialect. Filters out None results and
    exp.Command nodes (sqlglot's fallback for unparseable syntax). Logs
    warnings for every skipped statement.

    Args:
        sql_text: Raw SQL file content.

    Returns:
        Tuple of (valid_statements, warning_messages).
    """
    # Use WARN level so sqlglot logs errors but doesn't raise — tolerant parsing (D-04)
    statements = sqlglot.parse(sql_text, dialect="tsql", error_level=ErrorLevel.WARN)
    valid: list[exp.Expression] = []
    warnings: list[str] = []

    # DDL statement types we handle; anything else is invalid/unparseable
    _valid_types = (exp.Create, exp.Alter)

    for stmt in statements:
        if stmt is None:
            msg = "Skipping unparseable statement (None result from sqlglot)"
            logger.warning(msg)
            warnings.append(msg)
            continue
        if isinstance(stmt, exp.Command):
            # sqlglot fallback for unparseable syntax — log and skip
            preview = stmt.sql()[:120]
            msg = f"Skipping unparseable command statement: {preview!r}"
            logger.warning(msg)
            warnings.append(msg)
            continue
        if not isinstance(stmt, _valid_types):
            # sqlglot parsed the invalid statement as some other node type (e.g., Alias)
            preview = stmt.sql()[:120]
            msg = f"Skipping unrecognized statement type {type(stmt).__name__}: {preview!r}"
            logger.warning(msg)
            warnings.append(msg)
            continue
        valid.append(stmt)

    return valid, warnings


def extract_create_table(stmt: exp.Create) -> TableInfo:
    """Extract table name, columns, and constraints from a CREATE TABLE AST node.

    Handles:
    - Schema-qualified table names (dbo.TableName)
    - Inline column constraints: PRIMARY KEY, NOT NULL, UNIQUE, DEFAULT
    - Table-level PRIMARY KEY and FOREIGN KEY constraints

    Args:
        stmt: A sqlglot exp.Create node for a CREATE TABLE statement.

    Returns:
        TableInfo with columns and constraints populated.
    """
    # stmt.this is a Schema node wrapping a Table node
    schema_node = stmt.this
    table_node = schema_node.this  # The actual Table node

    table_name = table_node.name
    schema_name = table_node.db if table_node.db else None

    columns: list[ColumnInfo] = []
    ordinal = 0

    for col_def in stmt.find_all(exp.ColumnDef):
        ordinal += 1
        col_name = col_def.name
        data_type = col_def.kind.sql(dialect="tsql") if col_def.kind else None

        is_nullable = True
        is_primary_key = False
        is_unique = False
        default_value = None

        for constraint in col_def.args.get("constraints", []):
            kind = constraint.kind
            if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                is_primary_key = True
            elif isinstance(kind, exp.NotNullColumnConstraint):
                is_nullable = False
            elif isinstance(kind, exp.UniqueColumnConstraint):
                is_unique = True
            elif isinstance(kind, exp.DefaultColumnConstraint):
                default_value = kind.this.sql() if kind.this else None

        columns.append(
            ColumnInfo(
                column_name=col_name,
                data_type=data_type,
                is_nullable=is_nullable,
                is_primary_key=is_primary_key,
                is_unique=is_unique,
                default_value=default_value,
                ordinal_position=ordinal,
            )
        )

    # Table-level constraints
    constraints: list[ConstraintInfo] = []

    for pk in stmt.find_all(exp.PrimaryKey):
        pk_cols = [expr.name for expr in pk.expressions]
        constraints.append(ConstraintInfo(constraint_type="PRIMARY KEY", columns=pk_cols))

    for fk in stmt.find_all(exp.ForeignKey):
        fk_cols = [ident.name for ident in fk.expressions]
        ref = fk.args.get("reference")
        ref_table = None
        ref_columns: list[str] = []
        if ref:
            # ref.this is a Schema node; ref.this.this is the Table node
            ref_schema = ref.this
            if hasattr(ref_schema, "this") and ref_schema.this:
                ref_table = ref_schema.this.name
            elif hasattr(ref_schema, "name"):
                ref_table = ref_schema.name
            # Ref columns are in ref_schema.expressions (identifiers)
            if hasattr(ref_schema, "expressions"):
                ref_columns = [e.name for e in ref_schema.expressions]

        constraints.append(
            ConstraintInfo(
                constraint_type="FOREIGN KEY",
                columns=fk_cols,
                ref_table=ref_table,
                ref_columns=ref_columns if ref_columns else None,
            )
        )

    return TableInfo(
        table_name=table_name,
        schema_name=schema_name,
        columns=columns,
        constraints=constraints,
    )


def extract_create_index(stmt: exp.Create) -> IndexInfo | None:
    """Extract index metadata from a CREATE [UNIQUE] INDEX AST node.

    Args:
        stmt: A sqlglot exp.Create node.

    Returns:
        IndexInfo if the statement is an index creation, None otherwise.
    """
    if stmt.args.get("kind") != "INDEX":
        return None

    index_node = stmt.this  # exp.Index node
    if not isinstance(index_node, exp.Index):
        return None

    # index_node.this is an Identifier with the index name
    index_name = index_node.this.name if index_node.this else ""

    # table info is in index_node.args["table"]
    table_node = index_node.args.get("table")
    table_name = table_node.name if table_node else ""
    schema_name = table_node.db if (table_node and table_node.db) else None

    # is_unique comes from stmt.args["unique"] (top-level Create node)
    # Note: index_node.args["unique"] is None even for UNIQUE indexes in sqlglot 30.x
    is_unique = bool(stmt.args.get("unique"))

    # Columns from the index parameters
    columns: list[str] = []
    params = index_node.args.get("params")
    if params:
        for ordered in params.args.get("columns", []):
            columns.append(ordered.name)

    return IndexInfo(
        index_name=index_name,
        table_name=table_name,
        schema_name=schema_name,
        is_unique=is_unique,
        columns=columns,
    )


def extract_alter_table_constraint(stmt: exp.Alter) -> list[RelationshipInfo]:
    """Extract FK relationships from ALTER TABLE ADD CONSTRAINT statements.

    Args:
        stmt: A sqlglot exp.AlterTable node.

    Returns:
        List of RelationshipInfo (one per FK constraint found).
    """
    relationships: list[RelationshipInfo] = []

    source_table = stmt.this.name if stmt.this else ""

    for action in stmt.args.get("actions", []):
        if not isinstance(action, exp.AddConstraint):
            continue
        for constraint_expr in action.args.get("expressions", []):
            # constraint_expr is exp.Constraint; its expressions contain FK nodes
            for fk in constraint_expr.find_all(exp.ForeignKey):
                fk_cols = [ident.name for ident in fk.expressions]
                ref = fk.args.get("reference")
                if not ref:
                    continue
                ref_schema = ref.this
                # ref_schema is Schema node: ref_schema.this = Table
                ref_table = None
                ref_cols: list[str] = []
                if hasattr(ref_schema, "this") and ref_schema.this:
                    ref_table = ref_schema.this.name
                if hasattr(ref_schema, "expressions"):
                    ref_cols = [e.name for e in ref_schema.expressions]

                source_col = fk_cols[0] if len(fk_cols) == 1 else None
                target_col = ref_cols[0] if len(ref_cols) == 1 else None

                relationships.append(
                    RelationshipInfo(
                        source_table=source_table,
                        target_table=ref_table or "",
                        relationship_type="fk_declared",
                        source_column=source_col,
                        target_column=target_col,
                        confidence=1.0,
                    )
                )

    return relationships


def parse_ddl(sql_text: str) -> ParseResult:
    """Parse a full DDL file and return aggregated ParseResult.

    Routes each statement to the appropriate extractor:
    - exp.Create with kind=None -> extract_create_table
    - exp.Create with kind=INDEX -> extract_create_index
    - exp.AlterTable -> extract_alter_table_constraint

    Also extracts FK relationships from inline table-level FOREIGN KEY
    constraints and adds them to the relationships list.

    Args:
        sql_text: Raw SQL content.

    Returns:
        ParseResult with tables, indexes, relationships, and warnings.
    """
    valid_stmts, warnings = parse_ddl_file(sql_text)

    tables: list[TableInfo] = []
    indexes: list[IndexInfo] = []
    relationships: list[RelationshipInfo] = []

    for stmt in valid_stmts:
        if isinstance(stmt, exp.Create):
            kind = stmt.args.get("kind")
            if kind == "INDEX":
                idx = extract_create_index(stmt)
                if idx:
                    indexes.append(idx)
            elif kind is None or kind == "TABLE":
                # It's a CREATE TABLE statement
                try:
                    table_info = extract_create_table(stmt)
                    tables.append(table_info)
                    # Extract FK relationships from inline table-level constraints
                    for constraint in table_info.constraints:
                        if constraint.constraint_type == "FOREIGN KEY" and constraint.ref_table:
                            source_col = (
                                constraint.columns[0] if len(constraint.columns) == 1 else None
                            )
                            target_col = (
                                constraint.ref_columns[0]
                                if constraint.ref_columns and len(constraint.ref_columns) == 1
                                else None
                            )
                            relationships.append(
                                RelationshipInfo(
                                    source_table=table_info.table_name,
                                    target_table=constraint.ref_table,
                                    relationship_type="fk_declared",
                                    source_column=source_col,
                                    target_column=target_col,
                                    confidence=1.0,
                                )
                            )
                except Exception as e:
                    msg = f"Failed to extract CREATE TABLE: {e}"
                    logger.warning(msg)
                    warnings.append(msg)

        elif isinstance(stmt, exp.Alter):
            try:
                rels = extract_alter_table_constraint(stmt)
                relationships.extend(rels)
            except Exception as e:
                msg = f"Failed to extract ALTER TABLE constraint: {e}"
                logger.warning(msg)
                warnings.append(msg)

    return ParseResult(
        tables=tables,
        indexes=indexes,
        relationships=relationships,
        warnings=warnings,
    )


def ingest_ddl(conn: sqlite3.Connection, parse_result: ParseResult) -> dict[str, int]:
    """Write parsed DDL entities to the bi-temporal SQLite knowledge store.

    Inserts all tables, columns, relationships, and indexes from the ParseResult
    into their respective tables with UTC bi-temporal timestamps.

    Security: All INSERT statements use ? parameterized placeholders (T-02-02).

    Args:
        conn: An open SQLite connection with the full schema initialized.
        parse_result: Aggregated parse result from parse_ddl().

    Returns:
        Dictionary with counts: {"tables": N, "columns": N, "relationships": N, "indexes": N}
    """
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ts = int(now.timestamp())

    table_counts = 0
    column_counts = 0
    relationship_counts = 0
    index_counts = 0

    # Map table_name -> inserted row id for FK linking
    table_id_map: dict[str, int] = {}

    try:
        for table_info in parse_result.tables:
            cursor = conn.execute(
                """
                INSERT INTO db_tables (
                    table_name, schema_name,
                    valid_from, valid_from_ts, valid_until, valid_until_ts,
                    recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                """,
                (
                    table_info.table_name,
                    table_info.schema_name,
                    now_iso,
                    now_ts,
                    now_iso,
                    now_ts,
                ),
            )
            table_id = cursor.lastrowid
            table_id_map[table_info.table_name] = table_id
            table_counts += 1

            for col in table_info.columns:
                conn.execute(
                    """
                    INSERT INTO db_columns (
                        table_id, column_name, data_type,
                        is_nullable, is_primary_key, is_unique, default_value,
                        ordinal_position,
                        valid_from, valid_from_ts, valid_until, valid_until_ts,
                        recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        table_id,
                        col.column_name,
                        col.data_type,
                        1 if col.is_nullable else 0,
                        1 if col.is_primary_key else 0,
                        1 if col.is_unique else 0,
                        col.default_value,
                        col.ordinal_position,
                        now_iso,
                        now_ts,
                        now_iso,
                        now_ts,
                    ),
                )
                column_counts += 1

        # Insert relationships (source_id/target_id are table row ids)
        for rel in parse_result.relationships:
            source_id = table_id_map.get(rel.source_table)
            target_id = table_id_map.get(rel.target_table)
            # Skip relationships where referenced tables were not ingested in this batch
            if source_id is None or target_id is None:
                logger.warning(
                    "Skipping relationship %s->%s: table not found in current batch",
                    rel.source_table,
                    rel.target_table,
                )
                continue
            conn.execute(
                """
                INSERT INTO db_relationships (
                    source_id, target_id, relationship_type,
                    source_column, target_column, confidence,
                    valid_from, valid_from_ts, valid_until, valid_until_ts,
                    recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                """,
                (
                    source_id,
                    target_id,
                    rel.relationship_type,
                    rel.source_column,
                    rel.target_column,
                    rel.confidence,
                    now_iso,
                    now_ts,
                    now_iso,
                    now_ts,
                ),
            )
            relationship_counts += 1

        # Insert indexes
        for idx in parse_result.indexes:
            parent_table_id = table_id_map.get(idx.table_name)
            if parent_table_id is None:
                logger.warning(
                    "Skipping index %s: table %s not found in current batch",
                    idx.index_name,
                    idx.table_name,
                )
                continue
            conn.execute(
                """
                INSERT INTO db_indexes (
                    table_id, index_name, is_unique, columns_json,
                    valid_from, valid_from_ts, valid_until, valid_until_ts,
                    recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                """,
                (
                    parent_table_id,
                    idx.index_name,
                    1 if idx.is_unique else 0,
                    json.dumps(idx.columns),
                    now_iso,
                    now_ts,
                    now_iso,
                    now_ts,
                ),
            )
            index_counts += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "tables": table_counts,
        "columns": column_counts,
        "relationships": relationship_counts,
        "indexes": index_counts,
    }
