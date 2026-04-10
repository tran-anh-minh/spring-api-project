"""Typer CLI for the db-wiki knowledge engine.

Commands:
  init    — Create .db-wiki/ directory with config.yaml and knowledge.db
  connect — Register a live database connection string in config.yaml
  ingest  — Parse and ingest a DDL file into the knowledge store

Security notes:
- T-03-01: store_path resolved to absolute with Path.resolve() to prevent
  path traversal via --store-path (e.g., --store-path ../../../etc)
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
    file: Path = typer.Argument(
        ...,
        help="DDL file to ingest (.sql)",
    ),
    store_path: Path = typer.Option(
        Path(".db-wiki"),
        "--store-path",
        help="Path to the knowledge store directory",
    ),
) -> None:
    """Parse and ingest a DDL file into the knowledge store.

    Accepts SQL files containing CREATE TABLE, CREATE INDEX, and
    ALTER TABLE ADD CONSTRAINT statements. Tolerant — warnings are logged
    for unparseable statements, the rest are ingested (D-04).
    """
    # T-03-01: resolve store path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    # T-03-02: validate the input file
    file = file.resolve()
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    if not file.is_file():
        typer.echo(f"Error: Not a file: {file}", err=True)
        raise typer.Exit(code=1)

    # T-03-03: enforce file size limit
    config = load_config(store_path)
    max_bytes = config.ingest.max_file_size_mb * 1024 * 1024
    file_size = file.stat().st_size
    if file_size > max_bytes:
        typer.echo(
            f"Error: File too large "
            f"({file_size / 1024 / 1024:.1f}MB > {config.ingest.max_file_size_mb}MB limit)",
            err=True,
        )
        raise typer.Exit(code=1)

    sql_text = file.read_text(encoding="utf-8")

    try:
        from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl
    except ImportError:
        typer.echo("Error: DDL parser module not available.", err=True)
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    try:
        result = parse_ddl(sql_text)
        counts = ingest_ddl(conn, result)
    finally:
        conn.close()

    typer.echo(
        f"Ingested: {counts.get('tables', 0)} tables, "
        f"{counts.get('columns', 0)} columns, "
        f"{counts.get('relationships', 0)} relationships, "
        f"{counts.get('indexes', 0)} indexes"
    )

    if result.warnings:
        typer.echo(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings[:10]:
            typer.echo(f"  - {w}")


def main() -> None:
    """Entry point for the db-wiki CLI."""
    app()
