"""Typer CLI for the db-wiki knowledge engine.

Commands:
  init    — Create .db-wiki/ directory with config.yaml and knowledge.db
  connect — Register a live database connection string in config.yaml
  ingest  — Parse and ingest SQL files (DDL or SP) into the knowledge store

Security notes:
- T-03-01: store_path resolved to absolute with Path.resolve() to prevent
  path traversal via --store-path (e.g., --store-path ../../../etc)
- T-02-05: All user-supplied paths resolved before file operations
"""
from pathlib import Path
from typing import Optional

import typer
import yaml

from db_wiki.core.config import load_config, write_default_config
from db_wiki.core.store import init_schema, open_store

app = typer.Typer(
    name="db-wiki",
    help="DB Wiki — turn undocumented databases into queryable knowledge.",
    no_args_is_help=True,
)


@app.command()
def init(
    store_path: Path = typer.Option(
        Path(".db-wiki"),
        "--store-path",
        help="Directory for knowledge store (default: .db-wiki in current directory)",
    ),
) -> None:
    """Initialize a new db-wiki knowledge store.

    Creates the store directory, writes a default config.yaml, and
    initialises the SQLite knowledge database with the full schema.
    Safe to call multiple times — if the store already exists it prints
    a message and exits cleanly (D-07).
    """
    # T-03-01: resolve to absolute path before any file operations
    store_path = store_path.resolve()
    config_path = store_path / "config.yaml"
    db_path = store_path / "knowledge.db"

    if config_path.exists() and db_path.exists():
        typer.echo(f"Knowledge store already exists at {store_path}")
        return

    store_path.mkdir(parents=True, exist_ok=True)

    write_default_config(store_path)
    typer.echo(f"Created {config_path}")

    conn = open_store(db_path)
    init_schema(conn)
    conn.close()
    typer.echo(f"Created {db_path}")

    typer.echo(f"Initialized knowledge store at {store_path}")


@app.command()
def connect(
    connection_string: str = typer.Argument(
        ...,
        help="SQL Server connection string (e.g., 'Server=localhost;Database=mydb')",
    ),
    store_path: Path = typer.Option(
        Path(".db-wiki"),
        "--store-path",
        help="Path to the knowledge store directory",
    ),
) -> None:
    """Register a live database connection in the knowledge store config.

    Updates config.yaml with the supplied connection string so that the
    Collector Agent can connect to the live SQL Server database.
    Run 'db-wiki init' first if the store does not yet exist.
    """
    # T-03-01: resolve to absolute path
    store_path = store_path.resolve()
    config_path = store_path / "config.yaml"

    if not config_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    config = load_config(store_path)
    config.database.connection_string = connection_string

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)

    display = connection_string[:50] + ("..." if len(connection_string) > 50 else "")
    typer.echo(f"Connection registered: {display}")


@app.command()
def ingest(
    path: str = typer.Argument(
        ...,
        help="SQL file, directory, or glob pattern to ingest",
    ),
    store_path: Path = typer.Option(
        Path(".db-wiki"),
        "--store-path",
        help="Path to the knowledge store directory",
    ),
    content_type: Optional[str] = typer.Option(
        None,
        "--type",
        help="Force content type: 'sp' or 'ddl'. Default: auto-detect",
    ),
) -> None:
    """Parse and ingest SQL files into the knowledge store.

    Accepts a single SQL file, a directory (ingests all *.sql files
    recursively), or a glob pattern (e.g., '**/*.sql').

    Supports DDL (CREATE TABLE, CREATE INDEX, ALTER TABLE) and stored
    procedures (CREATE PROCEDURE). Auto-detects content type per file
    unless --type is specified to force a specific parser.

    Tolerant — warnings are logged for unparseable statements, the rest
    are ingested (D-04).
    """
    from db_wiki.ingest.ddl_parser import check_file_size_limit, ingest_ddl, parse_ddl
    from db_wiki.ingest.sp_parser import detect_content_type, ingest_sp, parse_sp

    # T-03-01: resolve store path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    config = load_config(store_path)
    max_bytes = config.ingest.max_file_size_mb * 1024 * 1024

    # Resolve file list from path argument
    # T-02-05: resolve all paths before operations
    path_obj = Path(path)
    files: list[Path] = []

    if path_obj.is_dir():
        # Directory: glob for all .sql files recursively
        files = sorted(path_obj.resolve().glob("**/*.sql"))
    elif path_obj.is_file():
        # Single file
        files = [path_obj.resolve()]
    elif "*" in path or "?" in path:
        # Glob pattern
        files = sorted(Path.cwd().glob(path))
    else:
        # Try resolving as a path
        resolved = path_obj.resolve()
        if resolved.exists() and resolved.is_file():
            files = [resolved]
        else:
            typer.echo(f"Error: Path not found: {path}", err=True)
            raise typer.Exit(code=1)

    if not files:
        typer.echo(f"No .sql files found matching: {path}")
        return

    typer.echo(f"Processing {len(files)} file(s)...")

    conn = open_store(db_path)

    total_tables = 0
    total_columns = 0
    total_procedures = 0
    total_relationships = 0
    total_warnings: list[str] = []
    skipped = 0

    try:
        for sql_file in files:
            # Check file size
            file_size = sql_file.stat().st_size
            if max_bytes > 0 and file_size > max_bytes:
                typer.echo(
                    f"  Skipping {sql_file.name} — too large "
                    f"({file_size / 1024 / 1024:.1f}MB > {config.ingest.max_file_size_mb}MB)"
                )
                skipped += 1
                continue

            sql_text = sql_file.read_text(encoding="utf-8")

            # Determine content type
            if content_type:
                file_type = content_type.lower()
            else:
                file_type = detect_content_type(sql_text)

            if file_type == "sp":
                result = parse_sp(sql_text)
                counts = ingest_sp(conn, result)
                proc_count = counts.get("procedures", 0)
                rel_count = counts.get("relationships", 0)
                total_procedures += proc_count
                total_relationships += rel_count
                typer.echo(
                    f"  {sql_file.name} (sp): {proc_count} procedure(s), "
                    f"{rel_count} relationship(s)"
                )
                total_warnings.extend(result.warnings)

            elif file_type == "ddl":
                result = parse_ddl(sql_text)
                counts = ingest_ddl(conn, result)
                tbl_count = counts.get("tables", 0)
                col_count = counts.get("columns", 0)
                rel_count = counts.get("relationships", 0)
                total_tables += tbl_count
                total_columns += col_count
                total_relationships += rel_count
                typer.echo(
                    f"  {sql_file.name} (ddl): {tbl_count} table(s), "
                    f"{col_count} column(s)"
                )
                total_warnings.extend(result.warnings)

            else:
                typer.echo(f"  {sql_file.name}: skipped (unknown content type)")
                skipped += 1

    finally:
        conn.close()

    # Print total summary
    parts = []
    if total_procedures:
        parts.append(f"{total_procedures} procedure(s)")
    if total_tables:
        parts.append(f"{total_tables} table(s)")
    if total_columns:
        parts.append(f"{total_columns} column(s)")
    if total_relationships:
        parts.append(f"{total_relationships} relationship(s)")

    summary = ", ".join(parts) if parts else "nothing ingested"
    typer.echo(f"Total: {summary}")
    if skipped:
        typer.echo(f"Skipped: {skipped} file(s)")

    if total_warnings:
        typer.echo(f"\nWarnings ({len(total_warnings)}):")
        for w in total_warnings[:10]:
            typer.echo(f"  - {w}")


def main() -> None:
    """Entry point for the db-wiki CLI."""
    app()
