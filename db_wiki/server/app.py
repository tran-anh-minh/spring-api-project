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
        return f"Error: File not found: {file_path}"
    if not path.is_file():
        return f"Error: Not a file: {file_path}"

    # T-03-03: enforce file size limit
    config = load_config(app_ctx.store_path)
    max_bytes = config.ingest.max_file_size_mb * 1024 * 1024
    file_size = path.stat().st_size
    if file_size > max_bytes:
        return (
            f"Error: File too large "
            f"({file_size / 1024 / 1024:.1f}MB > {config.ingest.max_file_size_mb}MB limit)"
        )

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
        return "Error: DDL parser module not available. Ensure db_wiki.ingest is installed."
    except Exception as e:
        logger.exception("Ingest failed for %s", file_path)
        return f"Error during ingest: {e}"


@mcp.tool()
async def status(ctx: Context) -> str:
    """Show knowledge store status.

    Returns counts of tables, columns, and relationships currently in the store.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context
    try:
        tables = app_ctx.conn.execute("SELECT COUNT(*) FROM current_db_tables").fetchone()[0]
        columns = app_ctx.conn.execute("SELECT COUNT(*) FROM current_db_columns").fetchone()[0]
        rels = app_ctx.conn.execute(
            "SELECT COUNT(*) FROM current_db_relationships"
        ).fetchone()[0]
        return f"Knowledge store: {tables} tables, {columns} columns, {rels} relationships"
    except Exception as e:
        logger.exception("Status query failed")
        return f"Error reading store: {e}"


def main() -> None:
    """Entry point for the db-wiki-mcp MCP server (stdio transport)."""
    mcp.run()
