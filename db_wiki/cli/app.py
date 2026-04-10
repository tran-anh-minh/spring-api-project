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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (natural language or keywords)"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results"),
    fts_weight: float = typer.Option(0.5, "--fts-weight", help="FTS5 keyword weight (0-1)"),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
) -> None:
    """Search the knowledge store for tables, procedures, and columns."""
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo("Error: No knowledge store. Run 'db-wiki init' first.", err=True)
        raise typer.Exit(code=1)

    from db_wiki.core.config import load_config
    from db_wiki.core.queries import lookup_entity_name
    from db_wiki.search.fts import sync_fts
    from db_wiki.search.hybrid import hybrid_search

    config = load_config(store_path)
    conn = open_store(db_path)
    try:
        init_schema(conn)
        sync_fts(conn)

        vec_weight = 1.0 - fts_weight
        results = hybrid_search(
            conn,
            query,
            config.embedding,
            fts_weight=fts_weight,
            vec_weight=vec_weight,
            limit=limit,
        )

        if not results:
            typer.echo(f"No results for: {query}")
            return

        if output_format == "json":
            import json

            typer.echo(
                json.dumps(
                    [{"type": r[0], "id": r[1], "score": r[2]} for r in results], indent=2
                )
            )
        else:
            typer.echo(f"Results for '{query}':")
            for entity_type, entity_id, score in results:
                name = lookup_entity_name(conn, entity_id)
                typer.echo(f"  [{entity_type}] {name} (score={score:.3f})")
    finally:
        conn.close()


@app.command()
def lineage(
    entity_name: str = typer.Argument(..., help="Table or procedure name"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
    max_depth: int = typer.Option(
        3, "--max-depth", "-d", help="Maximum traversal depth"
    ),
    edge_types: str = typer.Option(
        "", "--edge-types", "-e", help="Comma-separated: fk_declared,reads_from,..."
    ),
) -> None:
    """Trace data lineage from an entity through the relationship graph."""
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo("Error: No knowledge store. Run 'db-wiki init' first.", err=True)
        raise typer.Exit(code=1)

    from db_wiki.core.queries import find_entity_by_name, lookup_entity_name
    from db_wiki.graph.bfs import bfs_graph

    conn = open_store(db_path)
    try:
        init_schema(conn)

        entity_id, entity_type = find_entity_by_name(conn, entity_name)
        if entity_id is None:
            typer.echo(f"Entity not found: {entity_name}", err=True)
            raise typer.Exit(code=1)

        types_list = [t.strip() for t in edge_types.split(",") if t.strip()] or None

        results = bfs_graph(conn, entity_id, max_depth=max_depth, edge_types=types_list)

        if len(results) <= 1:
            typer.echo(f"No relationships found for {entity_name}")
            return

        typer.echo(f"Lineage from {entity_name} ({entity_type}, depth {max_depth}):")
        for r in results:
            node_name = lookup_entity_name(conn, r["node_id"])
            indent = "  " * r["depth"]
            edge_label = f" --[{r['edge_type']}]--> " if r["edge_type"] else ""
            typer.echo(f"{indent}{edge_label}{node_name} (depth {r['depth']})")
    finally:
        conn.close()


@app.command(name="sp-info")
def sp_info(
    procedure_name: str = typer.Argument(..., help="Stored procedure name"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """Show detailed information about a stored procedure."""
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo("Error: No knowledge store. Run 'db-wiki init' first.", err=True)
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)

    row = conn.execute(
        "SELECT id, procedure_name, schema_name, description, body_hash "
        "FROM current_db_procedures WHERE procedure_name=?",
        (procedure_name,),
    ).fetchone()

    if not row:
        typer.echo(f"Procedure not found: {procedure_name}", err=True)
        conn.close()
        raise typer.Exit(code=1)

    proc_id = row[0]
    typer.echo(f"Procedure: {row[1]}")
    typer.echo(f"Schema: {row[2] or 'dbo'}")
    typer.echo(f"Body hash: {row[4] or 'N/A'}")

    # Parse quality (D-03)
    rel_row = conn.execute(
        "SELECT parse_quality, is_degraded, has_dynamic_sql, partial_ast, has_cycle "
        "FROM current_sp_reliability WHERE procedure_id=?",
        (proc_id,),
    ).fetchone()
    if rel_row:
        typer.echo(f"\nParse quality: {rel_row[0]:.2%}")
        if rel_row[1]:
            typer.echo("  WARNING: Parse quality degraded (>5% anonymous nodes)")
        if rel_row[2]:
            typer.echo("  Contains dynamic SQL")
        if rel_row[3]:
            typer.echo("  Partial AST (Command fallback nodes present)")
        if rel_row[4]:
            typer.echo("  Circular call chain detected")

    # Branches
    branches = conn.execute(
        "SELECT branch_type, condition_text, tables_touched_json, nesting_depth "
        "FROM current_sp_branches WHERE procedure_id=? ORDER BY branch_index",
        (proc_id,),
    ).fetchall()
    if branches:
        typer.echo(f"\nBranches ({len(branches)}):")
        for b in branches:
            cond = f": {b[1]}" if b[1] else ""
            tables = b[2] or "[]"
            typer.echo(f"  [{b[0]}] depth={b[3]}{cond} tables={tables}")

    # Call chains
    chains = conn.execute(
        "SELECT callee_name_raw, callee_schema, is_resolved "
        "FROM current_sp_call_chains WHERE caller_id=?",
        (proc_id,),
    ).fetchall()
    if chains:
        typer.echo(f"\nCall chains ({len(chains)}):")
        for c in chains:
            resolved = "resolved" if c[2] else "unresolved"
            schema = f"{c[1]}." if c[1] else ""
            typer.echo(f"  EXEC {schema}{c[0]} ({resolved})")

    # Relationships
    rels = conn.execute(
        "SELECT r.relationship_type, t.table_name "
        "FROM current_db_relationships r "
        "JOIN current_db_tables t ON r.target_id = t.id "
        "WHERE r.source_id=?",
        (proc_id,),
    ).fetchall()
    if rels:
        typer.echo(f"\nRelationships ({len(rels)}):")
        for r in rels:
            typer.echo(f"  {r[0]}: {r[1]}")

    conn.close()


@app.command()
def discover(
    max_gaps: int = typer.Option(10, help="Maximum gaps to investigate"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", "-s", help="Path to the knowledge store"
    ),
) -> None:
    """Run the learning loop: detect knowledge gaps and investigate."""
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo("Error: No knowledge store. Run 'db-wiki init' first.", err=True)
        raise typer.Exit(code=1)

    config = load_config(store_path)
    if max_gaps != config.learning.max_gaps_per_run:
        config.learning.max_gaps_per_run = max_gaps

    conn = open_store(db_path)
    init_schema(conn)
    try:
        from db_wiki.learning.orchestrator import run_learning_loop

        summary = run_learning_loop(conn, config)
        typer.echo(summary)
    finally:
        conn.close()


@app.command()
def confirm(
    entity_type: str = typer.Argument(help="Entity type: table, column, procedure, enum"),
    entity_name: str = typer.Argument(help="Entity name (e.g., Orders.Status)"),
    attribute: str = typer.Argument(help="Attribute to confirm (e.g., enum_label)"),
    value: str = typer.Argument(help="The confirmed value"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", "-s", help="Path to the knowledge store"
    ),
) -> None:
    """Confirm a fact as human-verified (sets confidence to 1.0)."""
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo("Error: No knowledge store. Run 'db-wiki init' first.", err=True)
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)
    try:
        from db_wiki.learning.confirm import confirm_fact

        result = confirm_fact(conn, entity_type, entity_name, attribute, value)
        typer.echo(result)
    finally:
        conn.close()


@app.command()
def teach(
    entity_type: str = typer.Argument(help="Entity type: table, column, procedure, enum"),
    entity_name: str = typer.Argument(help="Entity name (e.g., Orders.Status)"),
    attribute: str = typer.Argument(help="Attribute to set (e.g., description)"),
    value: str = typer.Argument(help="The value to teach"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", "-s", help="Path to the knowledge store"
    ),
) -> None:
    """Teach the system a new fact (adds with confidence=1.0)."""
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo("Error: No knowledge store. Run 'db-wiki init' first.", err=True)
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)
    try:
        from db_wiki.learning.confirm import teach_fact

        result = teach_fact(conn, entity_type, entity_name, attribute, value)
        typer.echo(result)
    finally:
        conn.close()


def main() -> None:
    """Entry point for the db-wiki CLI."""
    app()
