"""FastMCP server for db-wiki knowledge engine.

Provides MCP tools for ingesting DDL files and querying the knowledge store.
Connects to the knowledge store via lifespan context (MCP-01, MCP-02).

Phase 4 tools (MCP-04, MCP-05): ask, explain, define_metric, state_machine,
branch_analysis, impact, coverage, data_quality, forensics, compare.

Security notes:
- T-03-02: file_path validated to exist and be a regular file before reading
- T-03-03: file size checked against config.ingest.max_file_size_mb limit
- T-04-10: ask tool validates SQL via sqlglot; execution gated by explicit execute param
- T-04-11: define_metric validates SQL fragment via sqlglot + keyword blacklist
- T-04-13: impact/forensics limit BFS depth to prevent DoS
"""
import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import anyio
from mcp.server.fastmcp import Context, FastMCP

from db_wiki.core.config import load_config
from db_wiki.core.store import init_schema, open_store

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Typed lifespan context providing store access to MCP tools."""

    store_path: Path
    conn: sqlite3.Connection
    pipeline: object | None = None  # QueryPipeline, lazy to avoid circular import


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Open the knowledge store connection for the duration of the server session.

    Loads config from the default .db-wiki directory, opens the SQLite store,
    and initialises the schema if needed. Yields an AppContext for tools to use.
    """
    config = load_config(Path(".db-wiki"))
    store_path = Path(config.storage.path).resolve()
    db_path = store_path / "knowledge.db"
    conn = open_store(db_path)
    init_schema(conn)

    # Phase 4: init query schema and pipeline
    from db_wiki.core.query_schema import init_query_schema
    from db_wiki.query.pipeline import QueryPipeline

    init_query_schema(conn)
    pipeline = QueryPipeline(conn, config)

    try:
        yield AppContext(store_path=store_path, conn=conn, pipeline=pipeline)
    finally:
        conn.close()


mcp = FastMCP("db-wiki", lifespan=app_lifespan)


@mcp.tool()
async def ingest(file_path: str, ctx: Context) -> str:
    """Ingest a DDL file into the knowledge store.

    Parses CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD CONSTRAINT
    statements from the specified SQL file and stores the extracted
    schema entities in the knowledge store.

    Args:
        file_path: Absolute or relative path to the .sql DDL file.

    Returns:
        Summary of ingested entities or an error message.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    # T-03-02: validate path before reading
    path = Path(file_path).resolve()
    if not path.exists():
        logger.error("File not found: %s", file_path)
        raise ValueError(f"File not found: {file_path}")
    if not path.is_file():
        logger.error("Not a file: %s", file_path)
        raise ValueError(f"Not a file: {file_path}")

    # T-03-03: enforce file size limit
    config = load_config(app_ctx.store_path)
    max_bytes = config.ingest.max_file_size_mb * 1024 * 1024
    file_size = path.stat().st_size
    if file_size > max_bytes:
        msg = (
            f"File too large "
            f"({file_size / 1024 / 1024:.1f}MB > {config.ingest.max_file_size_mb}MB limit)"
        )
        logger.error(msg)
        raise ValueError(msg)

    sql_text = path.read_text(encoding="utf-8")

    try:
        from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl

        result = parse_ddl(sql_text)
        counts = ingest_ddl(app_ctx.conn, result)

        summary = (
            f"Ingested {file_path}: "
            f"{counts.get('tables', 0)} tables, "
            f"{counts.get('columns', 0)} columns, "
            f"{counts.get('relationships', 0)} relationships, "
            f"{counts.get('indexes', 0)} indexes"
        )
        if result.warnings:
            summary += f"\nWarnings ({len(result.warnings)}):"
            for w in result.warnings[:5]:
                summary += f"\n  - {w}"
        return summary
    except ImportError:
        raise ImportError("DDL parser module not available. Ensure db_wiki.ingest is installed.")
    except Exception:
        logger.exception("Ingest failed for %s", file_path)
        raise


@mcp.tool()
async def status(ctx: Context) -> str:
    """Show knowledge store status including coverage, gaps, and growth trend (MCP-06).

    Returns counts of tables, columns, procedures, relationships, gap_count,
    conflict_count, coverage_pct, top gaps, and knowledge growth trend.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    def _query():
        conn = app_ctx.conn
        tables = conn.execute("SELECT COUNT(*) FROM current_db_tables").fetchone()[0]
        columns = conn.execute("SELECT COUNT(*) FROM current_db_columns").fetchone()[0]
        procedures = conn.execute("SELECT COUNT(*) FROM current_db_procedures").fetchone()[0]
        rels = conn.execute("SELECT COUNT(*) FROM current_db_relationships").fetchone()[0]

        # Coverage: tables with at least one description (proxy for confidence >= 0.5)
        tables_with_desc = conn.execute(
            "SELECT COUNT(*) FROM current_db_tables "
            "WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
        coverage_pct = (tables_with_desc / tables * 100) if tables > 0 else 0.0

        # Gap and conflict counts
        try:
            gap_count = conn.execute(
                "SELECT COUNT(*) FROM current_knowledge_gaps"
            ).fetchone()[0]
        except Exception:
            gap_count = 0

        try:
            conflict_count = conn.execute(
                "SELECT COUNT(*) FROM current_knowledge_gaps "
                "WHERE gap_type = 'conflict'"
            ).fetchone()[0]
        except Exception:
            conflict_count = 0

        # Top 5 unresolved gaps by severity
        try:
            top_gaps = conn.execute(
                "SELECT gap_type, entity_type, severity, description "
                "FROM current_knowledge_gaps "
                "ORDER BY severity DESC LIMIT 5"
            ).fetchall()
        except Exception:
            top_gaps = []

        # Knowledge growth: facts added in last 7 days vs previous 7 days
        try:
            recent_facts = conn.execute(
                "SELECT COUNT(*) FROM facts "
                "WHERE created_at >= datetime('now', '-7 days')"
            ).fetchone()[0]
            prev_facts = conn.execute(
                "SELECT COUNT(*) FROM facts "
                "WHERE created_at >= datetime('now', '-14 days') "
                "AND created_at < datetime('now', '-7 days')"
            ).fetchone()[0]
        except Exception:
            recent_facts = 0
            prev_facts = 0

        return (
            tables, columns, procedures, rels, coverage_pct,
            gap_count, conflict_count, top_gaps, recent_facts, prev_facts
        )

    try:
        (
            tables, columns, procedures, rels, coverage_pct,
            gap_count, conflict_count, top_gaps, recent_facts, prev_facts
        ) = await anyio.to_thread.run_sync(_query)

        lines = [
            "Knowledge Store Status",
            f"  Tables: {tables} | Columns: {columns} | Procedures: {procedures} | Relationships: {rels}",
            f"  Schema Coverage: {coverage_pct:.1f}%",
            f"  Open Gaps: {gap_count} | Conflicts: {conflict_count}",
        ]

        # Knowledge growth trend
        if recent_facts > 0 or prev_facts > 0:
            trend = "up" if recent_facts >= prev_facts else "down"
            lines.append(
                f"  Knowledge Growth: {recent_facts} facts (last 7d) vs {prev_facts} facts (prev 7d) [{trend}]"
            )

        # Top gaps
        if top_gaps:
            lines.append("  Top Gaps:")
            for g in top_gaps:
                gap_type, entity_type, severity, description = g
                sev_str = f"{severity:.2f}" if severity is not None else "?"
                desc_str = (description or "")[:60]
                lines.append(f"    [{gap_type}/{entity_type}] sev={sev_str} {desc_str}")

        return "\n".join(lines)
    except Exception:
        logger.exception("Status query failed")
        raise


@mcp.tool()
async def search(
    query: str,
    ctx: Context,
    limit: int = 10,
    fts_weight: float = 0.5,
) -> str:
    """Search the knowledge store for entities matching a query.

    Uses hybrid search combining FTS5 keyword matching and vector similarity.
    On first search, triggers on-demand embedding of all entities (D-09).

    Args:
        query: Natural language or keyword search query.
        limit: Maximum results to return (default 10).
        fts_weight: Weight for FTS5 keyword matching (0-1, default 0.5).
            Vector weight = 1 - fts_weight.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    from db_wiki.core.queries import lookup_entity_name
    from db_wiki.search.fts import sync_fts
    from db_wiki.search.hybrid import hybrid_search

    config = load_config(app_ctx.store_path)

    # Ensure FTS index is populated
    sync_fts(app_ctx.conn)

    vec_weight = 1.0 - fts_weight
    results = hybrid_search(
        app_ctx.conn,
        query,
        config.embedding,
        fts_weight=fts_weight,
        vec_weight=vec_weight,
        limit=limit,
    )

    if not results:
        return f"No results found for: {query}"

    # Format results with entity details
    lines = [f"Search results for '{query}' ({len(results)} matches):"]
    for entity_type, entity_id, score in results:
        name = lookup_entity_name(app_ctx.conn, entity_id)
        lines.append(f"  [{entity_type}] {name} (score: {score:.3f})")

    # D-10: Enrich with query engine suggestions when pipeline is available
    if app_ctx.pipeline is not None:
        try:
            from db_wiki.query.resolver import resolve_concepts

            resolved = resolve_concepts(app_ctx.conn, query, config.embedding, limit=1)
            if resolved:
                top = resolved[0]
                lines.append("")
                lines.append(f"Related queries: You can ask: 'show me {top.name} data'")
        except Exception:
            pass  # non-critical enhancement

    return "\n".join(lines)


@mcp.tool()
async def lineage(
    entity_name: str,
    ctx: Context,
    max_depth: int = 3,
    edge_types: str = "",
) -> str:
    """Trace data lineage from an entity through the relationship graph.

    Uses BFS traversal with configurable depth and edge type filtering (D-06).

    Args:
        entity_name: Name of the table or procedure to trace from.
        max_depth: How many relationship hops to follow (default 3).
        edge_types: Comma-separated relationship types to follow.
            Empty = all types. Options: fk_declared, fk_inferred,
            joins_with, reads_from, writes_to, feeds_into.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    from db_wiki.core.queries import find_entity_by_name, lookup_entity_name
    from db_wiki.graph.bfs import bfs_graph

    # Find entity ID by name using shared utility
    entity_id, entity_type = find_entity_by_name(app_ctx.conn, entity_name)

    if entity_id is None:
        return f"Entity not found: {entity_name}"

    # Parse edge types
    types_list = [t.strip() for t in edge_types.split(",") if t.strip()] or None

    results = bfs_graph(
        app_ctx.conn, entity_id, max_depth=max_depth, edge_types=types_list
    )

    if len(results) <= 1:
        return f"No relationships found for {entity_name}"

    # Format results using shared lookup
    lines = [f"Lineage from {entity_name} ({entity_type}, depth {max_depth}):"]
    for r in results:
        node_name = lookup_entity_name(app_ctx.conn, r["node_id"])
        indent = "  " * r["depth"]
        edge_label = f" --[{r['edge_type']}]--> " if r["edge_type"] else ""

        # D-10: Append L0 wiki summary when pipeline is available
        wiki_note = ""
        if app_ctx.pipeline is not None:
            try:
                from db_wiki.query.wiki import get_wiki_page

                l0 = get_wiki_page(app_ctx.conn, "table", r["node_id"], "L0")
                if l0:
                    wiki_note = f" — {l0}"
            except Exception:
                pass  # non-critical enhancement

        lines.append(f"{indent}{edge_label}{node_name} (depth {r['depth']}){wiki_note}")

    return "\n".join(lines)


@mcp.tool()
async def sp_info(procedure_name: str, ctx: Context) -> str:
    """Show detailed information about a stored procedure.

    Returns parse quality, branches, call chains, and table relationships.

    Args:
        procedure_name: Name of the stored procedure to inspect.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    row = app_ctx.conn.execute(
        "SELECT id, procedure_name, schema_name, description, body_hash "
        "FROM current_db_procedures WHERE procedure_name=?",
        (procedure_name,),
    ).fetchone()

    if not row:
        return f"Procedure not found: {procedure_name}"

    proc_id = row[0]
    lines = [
        f"Procedure: {row[1]}",
        f"Schema: {row[2] or 'dbo'}",
        f"Body hash: {row[4] or 'N/A'}",
    ]

    # Parse quality (D-03)
    rel_row = app_ctx.conn.execute(
        "SELECT parse_quality, is_degraded, has_dynamic_sql, partial_ast, has_cycle "
        "FROM current_sp_reliability WHERE procedure_id=?",
        (proc_id,),
    ).fetchone()
    if rel_row:
        lines.append(f"\nParse quality: {rel_row[0]:.2%}")
        if rel_row[1]:
            lines.append("  WARNING: Parse quality degraded (>5% anonymous nodes)")
        if rel_row[2]:
            lines.append("  Contains dynamic SQL")
        if rel_row[3]:
            lines.append("  Partial AST (Command fallback nodes present)")
        if rel_row[4]:
            lines.append("  Circular call chain detected")

    # Branches
    branches = app_ctx.conn.execute(
        "SELECT branch_type, condition_text, tables_touched_json, nesting_depth "
        "FROM current_sp_branches WHERE procedure_id=? ORDER BY branch_index",
        (proc_id,),
    ).fetchall()
    if branches:
        lines.append(f"\nBranches ({len(branches)}):")
        for b in branches:
            cond = f": {b[1]}" if b[1] else ""
            tables = b[2] or "[]"
            lines.append(f"  [{b[0]}] depth={b[3]}{cond} tables={tables}")

    # Call chains
    chains = app_ctx.conn.execute(
        "SELECT callee_name_raw, callee_schema, is_resolved "
        "FROM current_sp_call_chains WHERE caller_id=?",
        (proc_id,),
    ).fetchall()
    if chains:
        lines.append(f"\nCall chains ({len(chains)}):")
        for c in chains:
            resolved = "resolved" if c[2] else "unresolved"
            schema = f"{c[1]}." if c[1] else ""
            lines.append(f"  EXEC {schema}{c[0]} ({resolved})")

    # Relationships
    rels = app_ctx.conn.execute(
        "SELECT r.relationship_type, t.table_name "
        "FROM current_db_relationships r "
        "JOIN current_db_tables t ON r.target_id = t.id "
        "WHERE r.source_id=?",
        (proc_id,),
    ).fetchall()
    if rels:
        lines.append(f"\nRelationships ({len(rels)}):")
        for r in rels:
            lines.append(f"  {r[0]}: {r[1]}")

    return "\n".join(lines)


@mcp.tool()
async def discover(ctx: Context, max_gaps: int = 10) -> str:
    """Run a learning loop: detect knowledge gaps and investigate top N.

    Args:
        max_gaps: Maximum gaps to investigate in this run (default 10).

    Returns:
        Summary of gaps found, investigated, and facts updated.
    """
    import anyio

    app_ctx: AppContext = ctx.request_context.lifespan_context
    config = load_config(app_ctx.store_path)
    if max_gaps != config.learning.max_gaps_per_run:
        config.learning.max_gaps_per_run = max_gaps

    from db_wiki.learning.orchestrator import run_learning_loop

    summary = await anyio.to_thread.run_sync(
        lambda: run_learning_loop(app_ctx.conn, config)
    )
    return summary


@mcp.tool()
async def lint(ctx: Context) -> str:
    """Check knowledge store health and report issues (MCP-06).

    Checks for:
    - Orphan tables (no relationships)
    - Tables with no columns
    - Low-confidence stored procedures (parse quality < 0.3)
    - Stale unresolved gaps (> 30 days old)
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context
    conn = app_ctx.conn

    def _run_lint():
        issues = []

        # Check for orphan tables (no relationships)
        try:
            orphans = conn.execute(
                "SELECT t.table_name FROM current_db_tables t "
                "LEFT JOIN current_db_relationships r "
                "ON t.id = r.source_id OR t.id = r.target_id "
                "WHERE r.source_id IS NULL AND r.target_id IS NULL"
            ).fetchall()
            for o in orphans:
                issues.append(f"WARN: Orphan table '{o[0]}' — no relationships")
        except Exception:
            pass

        # Check for tables with no columns
        try:
            empty = conn.execute(
                "SELECT t.table_name FROM current_db_tables t "
                "LEFT JOIN current_db_columns c ON t.id = c.table_id "
                "WHERE c.id IS NULL"
            ).fetchall()
            for e in empty:
                issues.append(f"ERROR: Table '{e[0]}' has no columns")
        except Exception:
            pass

        # Check for SPs with low parse quality (< 0.3)
        try:
            low_quality = conn.execute(
                "SELECT p.procedure_name, r.parse_quality "
                "FROM current_sp_reliability r "
                "JOIN current_db_procedures p ON p.id = r.procedure_id "
                "WHERE r.parse_quality < 0.3"
            ).fetchall()
            for row in low_quality:
                issues.append(
                    f"WARN: Procedure '{row[0]}' has low parse quality ({row[1]:.0%})"
                )
        except Exception:
            pass

        # Check for stale gaps (> 30 days without resolution)
        try:
            stale = conn.execute(
                "SELECT COUNT(*) FROM current_knowledge_gaps "
                "WHERE created_at < datetime('now', '-30 days')"
            ).fetchone()[0]
            if stale > 0:
                issues.append(
                    f"WARN: {stale} gap(s) unresolved for more than 30 days"
                )
        except Exception:
            pass

        return issues

    issues = await anyio.to_thread.run_sync(_run_lint)
    if not issues:
        return "Knowledge store health: OK — no issues found."
    return "Knowledge store issues:\n" + "\n".join(issues)


@mcp.tool()
async def history(ctx: Context, limit: int = 20) -> str:
    """Show recent learning loop activity (MCP-06).

    Args:
        limit: Maximum number of history entries to return (default 20, max 100).
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    # T-05-13: cap limit to prevent DoS
    limit = min(limit, 100)

    def _query():
        conn = app_ctx.conn
        try:
            rows = conn.execute(
                "SELECT task_type, gap_type, result_type, created_at "
                "FROM agent_results "
                "ORDER BY created_at DESC "
                "LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            rows = []
        return rows

    rows = await anyio.to_thread.run_sync(_query)
    if not rows:
        return "No recent learning loop activity found."

    lines = [f"Recent Learning Loop Activity (last {len(rows)} entries):"]
    lines.append(f"{'Task Type':<20} {'Gap Type':<20} {'Result':<20} {'Date'}")
    lines.append("-" * 80)
    for task_type, gap_type, result_type, created_at in rows:
        lines.append(
            f"{(task_type or '-'):<20} {(gap_type or '-'):<20} "
            f"{(result_type or '-'):<20} {created_at or '-'}"
        )
    return "\n".join(lines)


@mcp.tool()
async def export_knowledge(
    ctx: Context,
    formats: str = "all",
    entity_name: str | None = None,
    entity_type: str = "table",
) -> str:
    """Export knowledge in multiple formats (MCP-06, EXPORT-03).

    Args:
        formats: Comma-separated formats or "all". Options: markdown, mermaid, json, ddl.
        entity_name: If specified, export only this entity. Default: all entities.
        entity_type: "table" or "procedure" (used with entity_name).
    """
    from db_wiki.export.runner import ALL_FORMATS, run_export

    app_ctx: AppContext = ctx.request_context.lifespan_context
    fmt_list = ALL_FORMATS if formats == "all" else [f.strip() for f in formats.split(",")]
    output_dir = Path(app_ctx.store_path) / "export"

    results = await anyio.to_thread.run_sync(
        lambda: run_export(app_ctx.conn, output_dir, fmt_list, entity_name, entity_type)
    )
    return (
        f"Exported {len(results)} files to {output_dir}:\n"
        + "\n".join(results.keys())
    )


@mcp.tool()
async def loop(ctx: Context, max_gaps: int = 10) -> str:
    """Trigger a learning loop run (MCP-06).

    Args:
        max_gaps: Maximum gaps to investigate in this run (default 10).

    Returns:
        Summary of gaps found, investigated, and facts updated.
    """
    from db_wiki.learning.orchestrator import run_learning_loop

    app_ctx: AppContext = ctx.request_context.lifespan_context
    config = load_config(app_ctx.store_path)
    if max_gaps != config.learning.max_gaps_per_run:
        config.learning.max_gaps_per_run = max_gaps

    summary = await anyio.to_thread.run_sync(
        lambda: run_learning_loop(app_ctx.conn, config)
    )
    return summary


@mcp.tool()
async def confirm(
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
    ctx: Context,
) -> str:
    """Confirm a fact as human-verified (sets confidence to 1.0).

    Args:
        entity_type: "table", "column", "procedure", "enum", etc.
        entity_name: Name of the entity (e.g., "Orders.Status").
        attribute: Which attribute to confirm (e.g., "enum_label", "description").
        value: The confirmed value.
    """
    import anyio

    app_ctx: AppContext = ctx.request_context.lifespan_context

    from db_wiki.learning.confirm import confirm_fact

    result = await anyio.to_thread.run_sync(
        lambda: confirm_fact(app_ctx.conn, entity_type, entity_name, attribute, value)
    )
    return result


@mcp.tool()
async def teach(
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
    ctx: Context,
) -> str:
    """Teach the system a new fact directly (human-injected knowledge).

    Adds the fact with confidence=1.0 and human_confirmed=True.

    Args:
        entity_type: "table", "column", "procedure", "enum", etc.
        entity_name: Name of the entity (e.g., "Orders.Status").
        attribute: Which attribute to set (e.g., "description", "enum_label").
        value: The value to teach.
    """
    import anyio

    app_ctx: AppContext = ctx.request_context.lifespan_context

    from db_wiki.learning.confirm import teach_fact

    result = await anyio.to_thread.run_sync(
        lambda: teach_fact(app_ctx.conn, entity_type, entity_name, attribute, value)
    )
    return result


# ---------------------------------------------------------------------------
# Skill: teach_knowledge — free-form human knowledge injection
# Skill: entity_history — bi-temporal timeline viewer
# ---------------------------------------------------------------------------


@mcp.tool()
async def teach_knowledge(entity: str, explanation: str, ctx: Context) -> str:
    """Inject free-form business rules or domain context for an entity.

    Stores the explanation in knowledge_facts with fact_type='human_teaching',
    confidence=1.0, and confirmed_by='human'. Use this when auto-discovery
    cannot capture tribal knowledge (e.g. "Orders.Status=5 means fraud hold").

    Args:
        entity: Entity name, e.g. "Orders" (table) or "Orders.Status" (column)
                or "usp_ProcessOrder" (procedure).
        explanation: Free-form explanation or business rule to record.
    """
    import json
    import time
    from datetime import datetime, timezone

    app_ctx: AppContext = ctx.request_context.lifespan_context

    def _insert():
        now_ts = int(time.time())
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        # Infer entity_type from entity string shape
        parts = entity.split(".")
        if len(parts) == 2:
            entity_type = "column"
        elif entity.lower().startswith(("usp_", "sp_", "proc_")):
            entity_type = "procedure"
        else:
            entity_type = "table"

        evidence = json.dumps({"explanation": explanation, "source": "human_teaching"})

        conn = app_ctx.conn
        cur = conn.execute(
            """INSERT INTO knowledge_facts
               (entity_type, entity_id, fact_type, attribute, value,
                confidence, confirmed_by, evidence_json,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, 'human_teaching', NULL, ?,
                       1.0, 'human', ?,
                       ?, ?, ?, ?)""",
            (entity_type, entity, explanation, evidence,
             now_iso, now_ts, now_iso, now_ts),
        )
        conn.commit()
        return cur.lastrowid

    fact_id = await anyio.to_thread.run_sync(_insert)
    return f"Taught: [{entity}] — fact recorded (id={fact_id}, confidence=1.0, confirmed_by=human)"


@mcp.tool()
async def entity_history(entity: str, ctx: Context) -> str:
    """Show the bi-temporal knowledge timeline for an entity.

    Queries knowledge_facts (ALL rows including superseded/invalidated),
    plus enum_values and state_transitions for the entity. Returns a
    timeline sorted by recorded_at showing what was believed, when learned,
    when invalidated, and what superseded it.

    Args:
        entity: Entity name, e.g. "Orders" or "Orders.Status".
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context

    def _query():
        conn = app_ctx.conn
        lines = [f"Knowledge Timeline: {entity}", ""]

        # --- knowledge_facts (all rows, including invalidated) ---
        try:
            rows = conn.execute(
                """SELECT id, fact_type, value, confidence, confirmed_by,
                          valid_from, valid_until, recorded_at, invalidated_at,
                          superseded_by_id
                   FROM knowledge_facts
                   WHERE entity_id = ?
                   ORDER BY recorded_at_ts ASC""",
                (entity,),
            ).fetchall()
        except Exception:
            rows = []

        if rows:
            lines.append("## Knowledge Facts")
            for row in rows:
                (fid, fact_type, value, confidence, confirmed_by,
                 valid_from, valid_until, recorded_at, invalidated_at,
                 superseded_by_id) = row
                status = "current"
                if invalidated_at:
                    status = f"invalidated {invalidated_at}"
                elif valid_until:
                    status = f"expired {valid_until}"
                elif superseded_by_id:
                    status = f"superseded by id={superseded_by_id}"
                conf_str = f"{confidence:.2f}" if confidence is not None else "?"
                lines.append(
                    f"  [{recorded_at}] id={fid} type={fact_type} "
                    f"conf={conf_str} by={confirmed_by or '-'} [{status}]"
                )
                lines.append(f"    {value[:120]}")
        else:
            lines.append("No knowledge_facts entries found for this entity.")

        # --- enum_values (table/column entities) ---
        parts = entity.split(".", 1)
        table_name = parts[0]
        column_name = parts[1] if len(parts) == 2 else None

        if column_name:
            try:
                ev_rows = conn.execute(
                    """SELECT enum_value, enum_label, confidence, detection_method,
                              valid_from, valid_until, recorded_at, invalidated_at
                       FROM enum_values
                       WHERE table_name = ? AND column_name = ?
                       ORDER BY recorded_at_ts ASC""",
                    (table_name, column_name),
                ).fetchall()
                if ev_rows:
                    lines.append("")
                    lines.append("## Enum Values")
                    for r in ev_rows:
                        status = "invalidated" if r[7] else ("expired" if r[5] else "current")
                        lines.append(
                            f"  [{r[6]}] value={r[0]} label={r[1] or '-'} "
                            f"conf={r[2]:.2f} method={r[3]} [{status}]"
                        )
            except Exception:
                pass

            try:
                st_rows = conn.execute(
                    """SELECT from_value, to_value, confidence,
                              valid_from, valid_until, recorded_at, invalidated_at
                       FROM state_transitions
                       WHERE table_name = ? AND column_name = ?
                       ORDER BY recorded_at_ts ASC""",
                    (table_name, column_name),
                ).fetchall()
                if st_rows:
                    lines.append("")
                    lines.append("## State Transitions")
                    for r in st_rows:
                        status = "invalidated" if r[6] else ("expired" if r[4] else "current")
                        lines.append(
                            f"  [{r[5]}] {r[0]} -> {r[1]} conf={r[2]:.2f} [{status}]"
                        )
            except Exception:
                pass

        return "\n".join(lines)

    return await anyio.to_thread.run_sync(_query)


@mcp.tool()
async def ask(question: str, ctx: Context, execute: bool = False) -> str:
    """Ask a natural language question and receive T-SQL.

    Set execute=True to run against live DB.

    Args:
        question: Natural language question about the database.
        execute: Whether to execute the generated SQL against live DB.
    """
    app: AppContext = ctx.request_context.lifespan_context
    if app.pipeline is None:
        return "Query pipeline not available."

    result = await anyio.to_thread.run_sync(
        lambda: app.pipeline.run(question, execute=execute)
    )

    if result.sql is None:
        return (
            "Could not generate SQL for this question. "
            "Try rephrasing or ensure LLM is configured for complex queries."
        )

    lines = [
        f"## Query: {question}",
        "",
        f"**Tier:** {result.tier}",
        f"**Attempts:** {result.attempts}",
        f"**From cache:** {result.from_cache}",
        "",
        "```sql",
        result.sql,
        "```",
    ]

    if result.validation_errors:
        lines.append("")
        lines.append(f"**Warnings:** {', '.join(result.validation_errors)}")

    if result.execution_result:
        lines.append("")
        lines.append("## Results")
        lines.append("")
        exec_r = result.execution_result
        if exec_r.get("error"):
            lines.append(f"**Error:** {exec_r['error']}")
        elif exec_r.get("rows"):
            cols = exec_r.get("columns", [])
            rows = exec_r["rows"]
            if cols:
                lines.append("| " + " | ".join(str(c) for c in cols) + " |")
                lines.append("| " + " | ".join("---" for _ in cols) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(v) for v in row) + " |")
            lines.append(f"\n*{len(rows)} row(s)*")
        else:
            lines.append("No rows returned.")

    return "\n".join(lines)


@mcp.tool()
async def explain(entity_name: str, ctx: Context, entity_type: str = "table") -> str:
    """Get detailed wiki explanation of a table or stored procedure.

    Args:
        entity_name: Name of the entity to explain.
        entity_type: "table" or "procedure" (default "table").
    """
    app: AppContext = ctx.request_context.lifespan_context

    from db_wiki.query.wiki import generate_wiki_markdown

    def _lookup_and_generate():
        if entity_type == "table":
            row = app.conn.execute(
                "SELECT id FROM current_db_tables WHERE table_name = ?",
                (entity_name,),
            ).fetchone()
        else:
            row = app.conn.execute(
                "SELECT id FROM current_db_procedures WHERE procedure_name = ?",
                (entity_name,),
            ).fetchone()
        if not row:
            return None
        return generate_wiki_markdown(app.conn, entity_type, row[0])

    result = await anyio.to_thread.run_sync(_lookup_and_generate)
    if result is None:
        return f"Entity '{entity_name}' not found."
    return result


@mcp.tool()
async def define_metric(
    name: str,
    sql_expression: str,
    source_tables: str,
    ctx: Context,
    description: str = "",
) -> str:
    """Define a business metric as a reusable SQL expression.

    Args:
        name: Metric name (e.g. "monthly_revenue").
        sql_expression: SQL fragment (e.g. "SUM(amount)").
        source_tables: Comma-separated table names.
        description: Optional description.
    """
    app: AppContext = ctx.request_context.lifespan_context

    from db_wiki.query.resolver import define_metric as _define_metric

    tables = [t.strip() for t in source_tables.split(",") if t.strip()]

    def _do():
        return _define_metric(app.conn, name, sql_expression, tables, description or None)

    try:
        metric_id = await anyio.to_thread.run_sync(_do)
        return f"Metric '{name}' defined successfully (id={metric_id})."
    except (ValueError, Exception) as e:
        return f"Error defining metric: {e}"


@mcp.tool()
async def state_machine(table_name: str, column_name: str, ctx: Context) -> str:
    """Generate a Mermaid state diagram for a column's state transitions.

    Args:
        table_name: Table containing the state column.
        column_name: Column that holds state values.
    """
    app: AppContext = ctx.request_context.lifespan_context

    def _generate():
        transitions = app.conn.execute(
            "SELECT from_value, to_value, source_procedure_id "
            "FROM current_state_transitions "
            "WHERE table_name = ? AND column_name = ?",
            (table_name, column_name),
        ).fetchall()
        if not transitions:
            return None

        # Get enum labels for richer display
        enums = app.conn.execute(
            "SELECT enum_value, enum_label FROM current_enum_values "
            "WHERE table_name = ? AND column_name = ?",
            (table_name, column_name),
        ).fetchall()
        label_map = {str(row[0]): row[1] for row in enums if row[1]}

        lines = ["stateDiagram-v2"]
        desc_lines = []
        for from_s, to_s, via in transitions:
            from_label = label_map.get(str(from_s), str(from_s))
            to_label = label_map.get(str(to_s), str(to_s))
            via_label = f": {via}" if via else ""
            lines.append(f"    {from_label} --> {to_label}{via_label}")
            desc_lines.append(
                f"- {from_label} -> {to_label}"
                + (f" (via {via})" if via else "")
            )

        mermaid = "```mermaid\n" + "\n".join(lines) + "\n```"
        desc = "\n".join(desc_lines)
        return f"{mermaid}\n\n**Transitions:**\n{desc}"

    result = await anyio.to_thread.run_sync(_generate)
    if result is None:
        return f"No state transitions found for {table_name}.{column_name}."
    return result


@mcp.tool()
async def branch_analysis(procedure_name: str, ctx: Context) -> str:
    """Analyze IF/ELSE branches in a stored procedure showing tables touched per branch.

    Args:
        procedure_name: Name of the stored procedure to analyze.
    """
    app: AppContext = ctx.request_context.lifespan_context

    def _analyze():
        row = app.conn.execute(
            "SELECT id FROM current_db_procedures WHERE procedure_name = ?",
            (procedure_name,),
        ).fetchone()
        if not row:
            return None
        proc_id = row[0]

        branches = app.conn.execute(
            "SELECT branch_type, condition_text, tables_touched_json, nesting_depth "
            "FROM current_sp_branches WHERE procedure_id = ? ORDER BY branch_index",
            (proc_id,),
        ).fetchall()

        if not branches:
            return f"## Branch Analysis: {procedure_name}\n\nNo branches found."

        lines = [f"## Branch Analysis: {procedure_name}", ""]
        for i, (btype, cond, tables_json, depth) in enumerate(branches, 1):
            lines.append(f"### Branch {i}: {cond or '(unconditional)'}")
            lines.append(f"- Type: {btype}")
            lines.append(f"- Nesting depth: {depth}")
            lines.append(f"- Tables: {tables_json or '[]'}")
            lines.append("")

        return "\n".join(lines)

    result = await anyio.to_thread.run_sync(_analyze)
    if result is None:
        return f"Procedure not found: {procedure_name}"
    return result


@mcp.tool()
async def impact(
    entity_name: str, ctx: Context, entity_type: str = "table", max_depth: int = 3
) -> str:
    """Analyze impact: show all entities affected by changes to the given entity.

    Args:
        entity_name: Name of the entity to analyze.
        entity_type: "table" or "procedure" (default "table").
        max_depth: BFS traversal depth (default 3, max 10).
    """
    app: AppContext = ctx.request_context.lifespan_context

    from db_wiki.core.queries import find_entity_by_name, lookup_entity_name
    from db_wiki.graph.bfs import bfs_graph

    # T-04-13: cap depth
    max_depth = min(max_depth, 10)

    entity_id, etype = find_entity_by_name(app.conn, entity_name)
    if entity_id is None:
        return f"Entity not found: {entity_name}"

    results = await anyio.to_thread.run_sync(
        lambda: bfs_graph(app.conn, entity_id, max_depth=max_depth)
    )

    if len(results) <= 1:
        return f"No downstream impact found for {entity_name}."

    lines = [
        f"## Impact Analysis: {entity_name}",
        "",
        f"Affected entities ({len(results) - 1}):",
        "",
        "| Entity | Depth | Relationship |",
        "|--------|-------|-------------|",
    ]
    for r in results:
        if r["node_id"] == entity_id:
            continue
        name = lookup_entity_name(app.conn, r["node_id"])
        lines.append(f"| {name} | {r['depth']} | {r.get('edge_type', '-')} |")

    return "\n".join(lines)


@mcp.tool()
async def coverage(ctx: Context) -> str:
    """Report knowledge coverage: % of tables with descriptions, relationships, and wiki pages."""
    app: AppContext = ctx.request_context.lifespan_context

    def _report():
        total_tables = app.conn.execute("SELECT COUNT(*) FROM current_db_tables").fetchone()[0]
        tables_with_desc = app.conn.execute(
            "SELECT COUNT(*) FROM current_db_tables WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
        tables_with_rels = app.conn.execute(
            "SELECT COUNT(DISTINCT source_id) FROM current_db_relationships"
        ).fetchone()[0]

        # Wiki pages
        try:
            tables_with_wiki = app.conn.execute(
                "SELECT COUNT(DISTINCT entity_id) FROM wiki_pages WHERE entity_type = 'table'"
            ).fetchone()[0]
        except Exception:
            tables_with_wiki = 0

        total_sps = app.conn.execute("SELECT COUNT(*) FROM current_db_procedures").fetchone()[0]
        sps_with_desc = app.conn.execute(
            "SELECT COUNT(*) FROM current_db_procedures WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
        total_rels = app.conn.execute("SELECT COUNT(*) FROM current_db_relationships").fetchone()[0]

        try:
            total_enums = app.conn.execute("SELECT COUNT(*) FROM current_enum_values").fetchone()[0]
        except Exception:
            total_enums = 0
        try:
            total_transitions = app.conn.execute("SELECT COUNT(*) FROM current_state_transitions").fetchone()[0]
        except Exception:
            total_transitions = 0

        def pct(n, d):
            return f"{n / d * 100:.0f}%" if d > 0 else "N/A"

        lines = [
            "## Knowledge Coverage",
            "",
            "| Metric | Count | Coverage |",
            "|--------|-------|----------|",
            f"| Tables | {total_tables} | - |",
            f"| Tables with descriptions | {tables_with_desc} | {pct(tables_with_desc, total_tables)} |",
            f"| Tables with relationships | {tables_with_rels} | {pct(tables_with_rels, total_tables)} |",
            f"| Tables with wiki pages | {tables_with_wiki} | {pct(tables_with_wiki, total_tables)} |",
            f"| Procedures | {total_sps} | - |",
            f"| Procedures with descriptions | {sps_with_desc} | {pct(sps_with_desc, total_sps)} |",
            f"| Relationships | {total_rels} | - |",
            f"| Enum values | {total_enums} | - |",
            f"| State transitions | {total_transitions} | - |",
        ]
        return "\n".join(lines)

    return await anyio.to_thread.run_sync(_report)


@mcp.tool()
async def data_quality(ctx: Context) -> str:
    """Report data quality issues: open gaps, low-confidence facts, stale knowledge."""
    app: AppContext = ctx.request_context.lifespan_context

    def _report():
        # Open gaps by severity
        try:
            gaps = app.conn.execute(
                "SELECT severity, COUNT(*) FROM knowledge_gaps "
                "WHERE status = 'open' GROUP BY severity ORDER BY severity"
            ).fetchall()
        except Exception:
            gaps = []

        total_gaps = sum(count for _, count in gaps)

        # Low confidence SPs
        try:
            low_conf = app.conn.execute(
                "SELECT COUNT(*) FROM current_sp_reliability WHERE parse_quality < 0.5"
            ).fetchone()[0]
        except Exception:
            low_conf = 0

        lines = [
            "## Data Quality Report",
            "",
            f"### Open Gaps ({total_gaps})",
            "",
        ]

        if gaps:
            lines.append("| Severity | Count |")
            lines.append("|----------|-------|")
            for sev, count in gaps:
                lines.append(f"| {sev} | {count} |")
        else:
            lines.append("No open gaps.")

        lines.extend([
            "",
            "### Low-Confidence Facts",
            "",
            f"- Procedures with parse quality < 50%: {low_conf}",
        ])

        return "\n".join(lines)

    return await anyio.to_thread.run_sync(_report)


@mcp.tool()
async def forensics(
    entity_name: str, ctx: Context, direction: str = "both", max_depth: int = 5
) -> str:
    """Trace data flow: show how data flows to/from an entity through SPs and tables.

    Args:
        entity_name: Entity to trace from.
        direction: "upstream", "downstream", or "both" (default "both").
        max_depth: BFS depth limit (default 5, max 10).
    """
    app: AppContext = ctx.request_context.lifespan_context

    from db_wiki.core.queries import find_entity_by_name, lookup_entity_name
    from db_wiki.graph.bfs import bfs_graph

    # T-04-13: cap depth
    max_depth = min(max_depth, 10)

    entity_id, etype = find_entity_by_name(app.conn, entity_name)
    if entity_id is None:
        return f"Entity not found: {entity_name}"

    data_flow_types = ["reads_from", "writes_to", "feeds_into"]
    results = await anyio.to_thread.run_sync(
        lambda: bfs_graph(
            app.conn, entity_id, max_depth=max_depth, edge_types=data_flow_types
        )
    )

    if len(results) <= 1:
        return f"No data flow found for {entity_name}."

    lines = [f"## Data Forensics: {entity_name}", ""]

    upstream = []
    downstream = []
    for r in results:
        if r["node_id"] == entity_id:
            continue
        edge = r.get("edge_type", "")
        if edge in ("reads_from",):
            upstream.append(r)
        elif edge in ("writes_to", "feeds_into"):
            downstream.append(r)
        else:
            upstream.append(r)
            downstream.append(r)

    if direction in ("upstream", "both") and upstream:
        lines.append("### Upstream")
        lines.append("")
        for r in upstream:
            name = lookup_entity_name(app.conn, r["node_id"])
            lines.append(f"- {name} (depth {r['depth']}, {r.get('edge_type', '-')})")
        lines.append("")

    if direction in ("downstream", "both") and downstream:
        lines.append("### Downstream")
        lines.append("")
        for r in downstream:
            name = lookup_entity_name(app.conn, r["node_id"])
            lines.append(f"- {name} (depth {r['depth']}, {r.get('edge_type', '-')})")
        lines.append("")

    if len(lines) <= 2:
        return f"No {direction} data flow found for {entity_name}."

    return "\n".join(lines)


@mcp.tool()
async def compare(entity_a: str, entity_b: str, ctx: Context) -> str:
    """Compare two entities side-by-side showing columns, relationships, and statistics.

    Args:
        entity_a: First entity name (table or procedure).
        entity_b: Second entity name (table or procedure).
    """
    app: AppContext = ctx.request_context.lifespan_context

    def _compare():
        def get_table_stats(name):
            row = app.conn.execute(
                "SELECT id, table_name, description FROM current_db_tables WHERE table_name = ?",
                (name,),
            ).fetchone()
            if not row:
                return None
            tid = row[0]
            col_count = app.conn.execute(
                "SELECT COUNT(*) FROM current_db_columns WHERE table_id = ?", (tid,)
            ).fetchone()[0]
            rel_count = app.conn.execute(
                "SELECT COUNT(*) FROM current_db_relationships WHERE source_id = ? OR target_id = ?",
                (tid, tid),
            ).fetchone()[0]
            try:
                enum_count = app.conn.execute(
                    "SELECT COUNT(*) FROM current_enum_values WHERE table_name = ?", (name,)
                ).fetchone()[0]
            except Exception:
                enum_count = 0
            cols = app.conn.execute(
                "SELECT column_name FROM current_db_columns WHERE table_id = ? ORDER BY id",
                (tid,),
            ).fetchall()
            col_names = {r[0] for r in cols}
            return {
                "type": "table",
                "description": row[2] or "-",
                "columns": col_count,
                "relationships": rel_count,
                "enums": enum_count,
                "column_names": col_names,
            }

        stats_a = get_table_stats(entity_a)
        stats_b = get_table_stats(entity_b)

        if not stats_a:
            return f"Entity '{entity_a}' not found."
        if not stats_b:
            return f"Entity '{entity_b}' not found."

        shared = stats_a["column_names"] & stats_b["column_names"]

        lines = [
            f"## Comparison: {entity_a} vs {entity_b}",
            "",
            f"| Property | {entity_a} | {entity_b} |",
            "|----------|" + "-" * (len(entity_a) + 2) + "|" + "-" * (len(entity_b) + 2) + "|",
            f"| Type | {stats_a['type']} | {stats_b['type']} |",
            f"| Description | {stats_a['description']} | {stats_b['description']} |",
            f"| Columns | {stats_a['columns']} | {stats_b['columns']} |",
            f"| Relationships | {stats_a['relationships']} | {stats_b['relationships']} |",
            f"| Enums | {stats_a['enums']} | {stats_b['enums']} |",
            f"| Shared columns | {len(shared)} | {len(shared)} |",
        ]

        if shared:
            lines.append("")
            lines.append(f"**Shared columns:** {', '.join(sorted(shared))}")

        return "\n".join(lines)

    result = await anyio.to_thread.run_sync(_compare)
    return result

def main() -> None:
    """Entry point for the db-wiki-mcp MCP server (stdio transport)."""
    mcp.run()
