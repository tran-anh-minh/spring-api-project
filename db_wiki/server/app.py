"""FastMCP server for db-wiki knowledge engine.

Provides MCP tools for ingesting DDL files and querying the knowledge store.
Connects to the knowledge store via lifespan context (MCP-01, MCP-02).

Security notes:
- T-03-02: file_path validated to exist and be a regular file before reading
- T-03-03: file size checked against config.ingest.max_file_size_mb limit
"""
import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

from db_wiki.core.config import load_config
from db_wiki.core.store import init_schema, open_store

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Typed lifespan context providing store access to MCP tools."""

    store_path: Path
    conn: sqlite3.Connection


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
    try:
        yield AppContext(store_path=store_path, conn=conn)
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
    except Exception as e:
        logger.exception("Ingest failed for %s", file_path)
        raise


@mcp.tool()
async def status(ctx: Context) -> str:
    """Show knowledge store status.

    Returns counts of tables, columns, and relationships currently in the store.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context
    try:
        tables = app_ctx.conn.execute("SELECT COUNT(*) FROM current_db_tables").fetchone()[0]
        columns = app_ctx.conn.execute("SELECT COUNT(*) FROM current_db_columns").fetchone()[0]
        procedures = app_ctx.conn.execute(
            "SELECT COUNT(*) FROM current_db_procedures"
        ).fetchone()[0]
        rels = app_ctx.conn.execute(
            "SELECT COUNT(*) FROM current_db_relationships"
        ).fetchone()[0]
        return (
            f"Knowledge store: {tables} tables, {columns} columns, "
            f"{procedures} procedures, {rels} relationships"
        )
    except Exception as e:
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
        lines.append(f"{indent}{edge_label}{node_name} (depth {r['depth']})")

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


def main() -> None:
    """Entry point for the db-wiki-mcp MCP server (stdio transport)."""
    mcp.run()
