"""Typer CLI for the db-wiki knowledge engine.

Commands:
  init           — Create .db-wiki/ directory with config.yaml and knowledge.db
  connect        — Register a live database connection string in config.yaml
  ingest         — Parse and ingest SQL files (DDL or SP) into the knowledge store
  ask            — Ask a natural language question and get SQL
  explain        — Generate wiki page for a table or procedure
  define-metric  — Define a named business metric (SQL expression)
  state-machine  — Show state transitions for a table column
  branch-analysis — Show branch analysis for a stored procedure
  impact         — Show entities affected by an entity (BFS traversal)
  coverage       — Show knowledge coverage statistics
  data-quality   — Show knowledge gaps and data quality issues
  forensics      — Trace data lineage (upstream/downstream)
  compare        — Compare two entities side by side

Security notes:
- T-03-01: store_path resolved to absolute with Path.resolve() to prevent
  path traversal via --store-path (e.g., --store-path ../../../etc)
- T-02-05: All user-supplied paths resolved before file operations
- T-04-14: ask --execute passes SQL through QueryPipeline validator (SELECT-only)
- T-04-15: define-metric validates SQL expression via sqlglot before storage
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
    from db_wiki.core.query_schema import init_query_schema
    init_query_schema(conn)
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
        yaml.dump(
            config.model_dump(exclude={"learning": {"llm_api_key"}}),
            f, default_flow_style=False,
        )

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
    from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl
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


def _open_store_with_query_schema(store_path: Path):
    """Open the knowledge store and ensure both base and query schemas are initialized.

    Returns (conn, config) tuple. Caller is responsible for closing conn.
    Raises typer.Exit(code=1) if the store does not exist.
    """
    db_path = store_path / "knowledge.db"
    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    from db_wiki.core.query_schema import init_query_schema

    config = load_config(store_path)
    conn = open_store(db_path)
    init_schema(conn)
    init_query_schema(conn)
    return conn, config


@app.command()
def ask(
    question: str = typer.Argument(help="Natural language question"),
    execute: bool = typer.Option(False, "--execute", "-e", help="Execute SQL against live DB"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    sql_only: bool = typer.Option(False, "--sql-only", "-s", help="Raw SQL only"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Store directory"
    ),
) -> None:
    """Ask a natural language question and receive generated SQL.

    Uses the Phase 4 QueryPipeline to classify, resolve, generate, and
    validate SQL. Optionally executes the SQL against the live database
    (requires --execute and a configured connection string).

    Security: T-04-14 — SQL validated via sqlglot qualify(); --execute
    requires explicit opt-in; executor rejects non-SELECT statements.
    """
    import json as json_mod

    from db_wiki.query.pipeline import QueryPipeline

    store_path = store_path.resolve()
    conn, config = _open_store_with_query_schema(store_path)
    try:
        pipeline = QueryPipeline(conn, config)
        result = pipeline.run(question, execute=execute)
    finally:
        conn.close()

    if sql_only:
        if result.sql:
            typer.echo(result.sql)
        else:
            typer.echo("-- No SQL generated", err=True)
            raise typer.Exit(code=1)
        return

    if json_output:
        output = {
            "question": result.question,
            "tier": result.tier,
            "sql": result.sql,
            "attempts": result.attempts,
            "from_cache": result.from_cache,
            "validation_errors": result.validation_errors,
            "execution_result": result.execution_result,
        }
        typer.echo(json_mod.dumps(output, indent=2))
        return

    # Rich output
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax
        from rich.table import Table

        console = Console()
        badge = f"[bold cyan]{result.tier}[/bold cyan]"
        cache_note = " (cached)" if result.from_cache else ""
        attempts_note = f"  attempts={result.attempts}{cache_note}"
        sql_text = result.sql or "-- No SQL generated"
        syntax = Syntax(sql_text, "sql", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title=f"SQL — {badge}", subtitle=attempts_note))

        if result.validation_errors:
            console.print(f"[yellow]Validation warnings:[/yellow] {'; '.join(result.validation_errors)}")

        if result.execution_result and result.execution_result.get("rows"):
            rows = result.execution_result["rows"]
            cols = result.execution_result.get("columns", [])
            tbl = Table(*cols, show_header=True)
            for row in rows[:50]:
                tbl.add_row(*[str(v) for v in row])
            console.print(tbl)

    except ImportError:
        # Fallback without rich
        typer.echo(f"Tier: {result.tier}  attempts={result.attempts}")
        typer.echo(result.sql or "-- No SQL generated")


@app.command()
def explain(
    entity_name: str = typer.Argument(help="Table or procedure name"),
    entity_type: str = typer.Option("table", "--type", "-t", help="Entity type: table or procedure"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Generate a wiki page for a table or stored procedure.

    Outputs L0/L1/L2 combined markdown documentation for the named entity.
    """
    import json as json_mod

    from db_wiki.core.queries import find_entity_by_name
    from db_wiki.query.wiki import generate_wiki_markdown

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        entity_id, found_type = find_entity_by_name(conn, entity_name)
        if entity_id is None:
            typer.echo(f"Entity not found: {entity_name}", err=True)
            raise typer.Exit(code=1)

        resolved_type = found_type or entity_type
        content = generate_wiki_markdown(conn, resolved_type, entity_id)
    finally:
        conn.close()

    if json_output:
        import json as json_mod
        typer.echo(json_mod.dumps({"entity": entity_name, "type": resolved_type, "content": content}, indent=2))
    else:
        typer.echo(content)


@app.command("define-metric")
def define_metric_cmd(
    name: str = typer.Argument(help="Metric name"),
    expression: str = typer.Argument(help="SQL expression"),
    tables: str = typer.Option("", "--tables", help="Comma-separated source tables"),
    description: str = typer.Option("", "--description", "-d", help="Metric description"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Define a named business metric (SQL expression).

    Stores the metric in the knowledge store for use by the query pipeline.
    The SQL expression is validated via sqlglot before storage.

    Security: T-04-15 — expression validated; dangerous DML/DDL keywords rejected.
    """
    from db_wiki.query.resolver import define_metric

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        source_tables = [t.strip() for t in tables.split(",") if t.strip()]
        metric_id = define_metric(
            conn,
            name=name,
            sql_fragment=expression,
            source_tables=source_tables,
            description=description or None,
        )
        typer.echo(f"Defined metric '{name}' (id={metric_id})")
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()


@app.command("state-machine")
def state_machine_cmd(
    table_name: str = typer.Argument(help="Table name"),
    column_name: str = typer.Argument(help="Column name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Show state machine transitions for a table column as a Mermaid diagram."""
    import json as json_mod

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        transitions = conn.execute(
            "SELECT from_value, to_value, confidence "
            "FROM current_state_transitions "
            "WHERE table_name = ? AND column_name = ? "
            "ORDER BY from_value, to_value",
            (table_name, column_name),
        ).fetchall()
    finally:
        conn.close()

    if not transitions:
        typer.echo(f"No state transitions found for {table_name}.{column_name}")
        return

    if json_output:
        rows = [
            {"from_value": r[0], "to_value": r[1], "confidence": r[2]}
            for r in transitions
        ]
        typer.echo(json_mod.dumps({"table": table_name, "column": column_name, "transitions": rows}, indent=2))
        return

    # Mermaid state diagram
    lines = ["stateDiagram-v2"]
    for from_val, to_val, _ in transitions:
        lines.append(f"    {from_val} --> {to_val}")
    typer.echo("\n".join(lines))


@app.command("branch-analysis")
def branch_analysis_cmd(
    procedure_name: str = typer.Argument(help="Stored procedure name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Show branch analysis for a stored procedure."""
    import json as json_mod

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        proc_row = conn.execute(
            "SELECT id, procedure_name, description FROM current_db_procedures WHERE procedure_name = ?",
            (procedure_name,),
        ).fetchone()

        if proc_row is None:
            typer.echo(f"Procedure not found: {procedure_name}", err=True)
            raise typer.Exit(code=1)

        proc_id = proc_row[0]
        branches = conn.execute(
            "SELECT branch_index, branch_type, condition_text, tables_touched_json, nesting_depth "
            "FROM current_sp_branches WHERE procedure_id = ? ORDER BY branch_index",
            (proc_id,),
        ).fetchall()

        reliability = conn.execute(
            "SELECT parse_quality, is_degraded, has_dynamic_sql "
            "FROM current_sp_reliability WHERE procedure_id = ?",
            (proc_id,),
        ).fetchone()
    finally:
        conn.close()

    if json_output:
        branch_list = [
            {
                "index": b[0],
                "type": b[1],
                "condition": b[2],
                "tables": b[3],
                "depth": b[4],
            }
            for b in branches
        ]
        output = {
            "procedure": procedure_name,
            "branch_count": len(branches),
            "branches": branch_list,
            "reliability": {
                "parse_quality": reliability[0] if reliability else None,
                "is_degraded": bool(reliability[1]) if reliability else None,
                "has_dynamic_sql": bool(reliability[2]) if reliability else None,
            },
        }
        typer.echo(json_mod.dumps(output, indent=2))
        return

    typer.echo(f"Branch Analysis: {procedure_name}")
    typer.echo(f"Total branches: {len(branches)}")

    if reliability:
        typer.echo(f"Parse quality: {reliability[0]:.2%}")
        if reliability[1]:
            typer.echo("  WARNING: Parse quality degraded")
        if reliability[2]:
            typer.echo("  Contains dynamic SQL")

    if branches:
        typer.echo("\nBranches:")
        for b in branches:
            cond = f": {b[2]}" if b[2] else ""
            typer.echo(f"  [{b[1]}] depth={b[4]}{cond}")
    else:
        typer.echo("No branches found.")


@app.command()
def impact(
    entity_name: str = typer.Argument(help="Entity to analyze"),
    entity_type: str = typer.Option("table", "--type", "-t", help="Entity type: table or procedure"),
    max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum BFS depth"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Show entities affected by an entity via BFS traversal of the relationship graph."""
    import json as json_mod

    from db_wiki.core.queries import find_entity_by_name, lookup_entity_name
    from db_wiki.graph.bfs import bfs_graph

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        entity_id, found_type = find_entity_by_name(conn, entity_name)
        if entity_id is None:
            typer.echo(f"Entity not found: {entity_name}", err=True)
            raise typer.Exit(code=1)

        bfs_results = bfs_graph(conn, entity_id, max_depth=max_depth)

        # Resolve names for all nodes
        rows = []
        for r in bfs_results[1:]:  # skip the start node itself
            node_name = lookup_entity_name(conn, r["node_id"])
            rows.append({
                "name": node_name,
                "node_id": r["node_id"],
                "depth": r["depth"],
                "relationship": r["edge_type"] or "",
            })
    finally:
        conn.close()

    if not rows:
        typer.echo(f"No affected entities found for {entity_name}")
        return

    if json_output:
        typer.echo(json_mod.dumps({"entity": entity_name, "affected": rows}, indent=2))
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        tbl = Table("Name", "Depth", "Relationship", show_header=True)
        for r in rows:
            tbl.add_row(r["name"], str(r["depth"]), r["relationship"])
        console.print(f"[bold]Impact of {entity_name}[/bold] (depth {max_depth}):")
        console.print(tbl)
    except ImportError:
        typer.echo(f"Impact of {entity_name} (depth {max_depth}):")
        for r in rows:
            typer.echo(f"  depth={r['depth']}  {r['relationship']}  {r['name']}")


@app.command()
def coverage(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Show knowledge coverage statistics for the knowledge store."""
    import json as json_mod

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        total_tables = conn.execute("SELECT COUNT(*) FROM current_db_tables").fetchone()[0]
        tables_with_desc = conn.execute(
            "SELECT COUNT(*) FROM current_db_tables WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
        tables_with_rels = conn.execute(
            "SELECT COUNT(DISTINCT source_id) FROM current_db_relationships "
            "WHERE source_id IN (SELECT id FROM current_db_tables)"
        ).fetchone()[0]
        tables_with_wiki = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM current_wiki_pages WHERE entity_type='table'"
        ).fetchone()[0]
        total_procs = conn.execute("SELECT COUNT(*) FROM current_db_procedures").fetchone()[0]
        procs_with_desc = conn.execute(
            "SELECT COUNT(*) FROM current_db_procedures WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
        total_cols = conn.execute("SELECT COUNT(*) FROM current_db_columns").fetchone()[0]
        cols_with_desc = conn.execute(
            "SELECT COUNT(*) FROM current_db_columns WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
    finally:
        conn.close()

    def pct(n: int, total: int) -> str:
        return f"{n}/{total} ({100*n//total if total else 0}%)"

    stats = {
        "tables": {
            "total": total_tables,
            "with_description": tables_with_desc,
            "with_relationships": tables_with_rels,
            "with_wiki": tables_with_wiki,
        },
        "procedures": {
            "total": total_procs,
            "with_description": procs_with_desc,
        },
        "columns": {
            "total": total_cols,
            "with_description": cols_with_desc,
        },
    }

    if json_output:
        typer.echo(json_mod.dumps(stats, indent=2))
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        tbl = Table("Category", "Metric", "Coverage", show_header=True)
        tbl.add_row("Tables", "Total", str(total_tables))
        tbl.add_row("Tables", "With description", pct(tables_with_desc, total_tables))
        tbl.add_row("Tables", "With relationships", pct(tables_with_rels, total_tables))
        tbl.add_row("Tables", "With wiki pages", pct(tables_with_wiki, total_tables))
        tbl.add_row("Procedures", "Total", str(total_procs))
        tbl.add_row("Procedures", "With description", pct(procs_with_desc, total_procs))
        tbl.add_row("Columns", "Total", str(total_cols))
        tbl.add_row("Columns", "With description", pct(cols_with_desc, total_cols))
        console.print("[bold]Knowledge Coverage[/bold]")
        console.print(tbl)
    except ImportError:
        typer.echo("Knowledge Coverage:")
        typer.echo(f"  Tables: {total_tables} total, {tables_with_desc} with description")
        typer.echo(f"  Procedures: {total_procs} total, {procs_with_desc} with description")
        typer.echo(f"  Columns: {total_cols} total, {cols_with_desc} with description")


@app.command("data-quality")
def data_quality_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Show knowledge gaps, low-confidence facts, and data quality issues."""
    import json as json_mod

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        # knowledge_gaps.severity is REAL (0.0-1.0): >0.7 = high, 0.4-0.7 = medium, <0.4 = low
        high_gaps = conn.execute(
            "SELECT COUNT(*) FROM current_knowledge_gaps WHERE severity >= 0.7"
        ).fetchone()[0]
        medium_gaps = conn.execute(
            "SELECT COUNT(*) FROM current_knowledge_gaps WHERE severity >= 0.4 AND severity < 0.7"
        ).fetchone()[0]
        low_gaps = conn.execute(
            "SELECT COUNT(*) FROM current_knowledge_gaps WHERE severity < 0.4"
        ).fetchone()[0]
        gaps_by_severity = {"high": high_gaps, "medium": medium_gaps, "low": low_gaps}

        gaps_sample = conn.execute(
            "SELECT gap_type, entity_type, severity, description "
            "FROM current_knowledge_gaps "
            "ORDER BY severity DESC "
            "LIMIT 20"
        ).fetchall()

        # Count low-confidence columns (no dedicated facts table — use columns with no description)
        # as a proxy for low-confidence coverage
        low_confidence_count = conn.execute(
            "SELECT COUNT(*) FROM current_db_columns "
            "WHERE description IS NULL OR description = ''"
        ).fetchone()[0]
    finally:
        conn.close()

    if json_output:
        output = {
            "gaps_by_severity": gaps_by_severity,
            "low_confidence_columns": low_confidence_count,
            "gaps_sample": [
                {"type": r[0], "entity_type": r[1], "severity": r[2], "description": r[3]}
                for r in gaps_sample
            ],
        }
        typer.echo(json_mod.dumps(output, indent=2))
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        console.print("[bold]Data Quality Report[/bold]")

        sev_tbl = Table("Severity", "Gap Count", show_header=True)
        for sev, cnt in gaps_by_severity.items():
            sev_tbl.add_row(sev, str(cnt))
        sev_tbl.add_row("columns without description", str(low_confidence_count))
        console.print(sev_tbl)

        if gaps_sample:
            gap_tbl = Table("Type", "Entity", "Severity", "Description", show_header=True)
            for r in gaps_sample:
                gap_tbl.add_row(r[0] or "", r[1] or "", f"{r[2]:.2f}" if r[2] is not None else "", (r[3] or "")[:60])
            console.print(gap_tbl)
    except ImportError:
        typer.echo("Data Quality Report:")
        for sev, cnt in gaps_by_severity.items():
            typer.echo(f"  {sev}: {cnt} gaps")
        typer.echo(f"  columns without description: {low_confidence_count}")


@app.command()
def forensics(
    entity_name: str = typer.Argument(help="Entity to trace"),
    direction: str = typer.Option("both", "--direction", help="upstream, downstream, or both"),
    max_depth: int = typer.Option(5, "--depth", "-d", help="Maximum BFS depth"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Trace data lineage (upstream/downstream) for an entity."""
    import json as json_mod

    from db_wiki.core.queries import find_entity_by_name, lookup_entity_name
    from db_wiki.graph.bfs import bfs_graph

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        entity_id, _found_type = find_entity_by_name(conn, entity_name)
        if entity_id is None:
            typer.echo(f"Entity not found: {entity_name}", err=True)
            raise typer.Exit(code=1)

        data_edge_types = ["reads_from", "writes_to", "feeds_into"]
        bfs_results = bfs_graph(
            conn,
            entity_id,
            max_depth=max_depth,
            edge_types=data_edge_types,
            bidirectional=(direction == "both"),
        )

        # Filter by direction
        rows = []
        for r in bfs_results[1:]:
            if direction == "upstream" and r["edge_type"] not in ("reads_from",):
                continue
            if direction == "downstream" and r["edge_type"] not in ("writes_to", "feeds_into"):
                continue
            node_name = lookup_entity_name(conn, r["node_id"])
            rows.append({
                "name": node_name,
                "depth": r["depth"],
                "edge_type": r["edge_type"] or "",
            })
    finally:
        conn.close()

    if json_output:
        typer.echo(json_mod.dumps({
            "entity": entity_name,
            "direction": direction,
            "flow": rows,
        }, indent=2))
        return

    typer.echo(f"Forensic trace for {entity_name} (direction={direction}, depth={max_depth}):")
    if not rows:
        typer.echo("  No data flow found.")
        return
    for r in rows:
        indent = "  " * r["depth"]
        typer.echo(f"{indent}--[{r['edge_type']}]--> {r['name']}")


@app.command()
def compare(
    entity_a: str = typer.Argument(help="First entity"),
    entity_b: str = typer.Argument(help="Second entity"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Compare two entities (tables or procedures) side by side."""
    import json as json_mod

    from db_wiki.core.queries import find_entity_by_name

    store_path = store_path.resolve()
    conn, _config = _open_store_with_query_schema(store_path)
    try:
        id_a, type_a = find_entity_by_name(conn, entity_a)
        if id_a is None:
            typer.echo(f"Entity not found: {entity_a}", err=True)
            raise typer.Exit(code=1)

        id_b, type_b = find_entity_by_name(conn, entity_b)
        if id_b is None:
            typer.echo(f"Entity not found: {entity_b}", err=True)
            raise typer.Exit(code=1)

        def _get_cols(eid: int, etype: str | None) -> set[str]:
            if etype == "table":
                rows = conn.execute(
                    "SELECT column_name FROM current_db_columns WHERE table_id = ?", (eid,)
                ).fetchall()
                return {r[0] for r in rows}
            return set()

        def _get_rel_count(eid: int) -> int:
            return conn.execute(
                "SELECT COUNT(*) FROM current_db_relationships WHERE source_id = ?", (eid,)
            ).fetchone()[0]

        cols_a = _get_cols(id_a, type_a)
        cols_b = _get_cols(id_b, type_b)
        shared_cols = cols_a & cols_b
        rels_a = _get_rel_count(id_a)
        rels_b = _get_rel_count(id_b)
    finally:
        conn.close()

    comparison = {
        "entity_a": {"name": entity_a, "type": type_a, "column_count": len(cols_a), "relationship_count": rels_a},
        "entity_b": {"name": entity_b, "type": type_b, "column_count": len(cols_b), "relationship_count": rels_b},
        "shared_columns": sorted(shared_cols),
        "shared_column_count": len(shared_cols),
    }

    if json_output:
        typer.echo(json_mod.dumps(comparison, indent=2))
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        tbl = Table("Metric", entity_a, entity_b, show_header=True)
        tbl.add_row("Type", type_a or "unknown", type_b or "unknown")
        tbl.add_row("Column count", str(len(cols_a)), str(len(cols_b)))
        tbl.add_row("Relationship count", str(rels_a), str(rels_b))
        tbl.add_row("Shared columns", str(len(shared_cols)), "")
        console.print(f"[bold]Comparison: {entity_a} vs {entity_b}[/bold]")
        console.print(tbl)
        if shared_cols:
            console.print(f"Shared columns: {', '.join(sorted(shared_cols))}")
    except ImportError:
        typer.echo(f"Comparison: {entity_a} vs {entity_b}")
        typer.echo(f"  {entity_a}: {len(cols_a)} columns, {rels_a} relationships")
        typer.echo(f"  {entity_b}: {len(cols_b)} columns, {rels_b} relationships")
        if shared_cols:
            typer.echo(f"  Shared: {', '.join(sorted(shared_cols))}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(8080, help="Port to listen on"),
    no_ui: bool = typer.Option(False, "--no-ui", help="Headless learning loop only (no web UI)"),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """Start web UI and background learning daemon in one process (D-04, CLI-05).

    Starts both the web graph UI (default http://127.0.0.1:8080) and a background
    learning scheduler. Use --no-ui for headless daemon-only mode.
    Stop with Ctrl+C.
    """
    import time

    from db_wiki.core.config import load_config
    from db_wiki.daemon.scheduler import DaemonScheduler

    # T-03-01: resolve to absolute path before any file operations
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    config = load_config(store_path)

    # Start background scheduler
    scheduler = DaemonScheduler(db_path, config)
    scheduler.start()
    typer.echo(
        f"Background learning daemon started "
        f"(fast={config.daemon.fast_interval_minutes}m)"
    )

    if not no_ui:
        import uvicorn

        from db_wiki.web.app import create_web_app

        web_app = create_web_app(db_path, config)
        typer.echo(f"Web UI: http://{host}:{port}")
        typer.echo("Press Ctrl+C to stop.")
        try:
            uvicorn.run(web_app, host=host, port=port, log_level="info")
        finally:
            scheduler.stop()
            typer.echo("Daemon stopped.")
    else:
        typer.echo("Headless mode — press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.stop()
            typer.echo("Daemon stopped.")


@app.command(name="status")
def status(
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """Show maturity dashboard: coverage, gaps, conflicts, and growth trend (EXPORT-01, D-10)."""
    # T-03-01: resolve to absolute path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)

    try:
        tables = conn.execute("SELECT COUNT(*) FROM current_db_tables").fetchone()[0]
        columns = conn.execute("SELECT COUNT(*) FROM current_db_columns").fetchone()[0]
        procedures = conn.execute("SELECT COUNT(*) FROM current_db_procedures").fetchone()[0]
        rels = conn.execute("SELECT COUNT(*) FROM current_db_relationships").fetchone()[0]

        # Coverage: tables with descriptions
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
                "SELECT COUNT(*) FROM current_knowledge_gaps WHERE gap_type = 'conflict'"
            ).fetchone()[0]
        except Exception:
            conflict_count = 0

        # Knowledge growth
        try:
            recent_facts = conn.execute(
                "SELECT COUNT(*) FROM facts WHERE created_at >= datetime('now', '-7 days')"
            ).fetchone()[0]
            prev_facts = conn.execute(
                "SELECT COUNT(*) FROM facts "
                "WHERE created_at >= datetime('now', '-14 days') "
                "AND created_at < datetime('now', '-7 days')"
            ).fetchone()[0]
        except Exception:
            recent_facts = 0
            prev_facts = 0

    finally:
        conn.close()

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        tbl = Table(title="DB Wiki — Knowledge Store Status", show_header=True)
        tbl.add_column("Metric", style="bold")
        tbl.add_column("Value")

        tbl.add_row("Tables", str(tables))
        tbl.add_row("Columns", str(columns))
        tbl.add_row("Procedures", str(procedures))
        tbl.add_row("Relationships", str(rels))
        tbl.add_row("Schema Coverage", f"{coverage_pct:.1f}%")
        tbl.add_row("Open Gaps", str(gap_count))
        tbl.add_row("Conflicts", str(conflict_count))

        if recent_facts > 0 or prev_facts > 0:
            trend = "up" if recent_facts >= prev_facts else "down"
            tbl.add_row(
                "Knowledge Growth",
                f"{recent_facts} facts (last 7d) vs {prev_facts} (prev 7d) [{trend}]",
            )

        console.print(tbl)
    except ImportError:
        typer.echo("DB Wiki — Knowledge Store Status")
        typer.echo(f"  Tables: {tables} | Columns: {columns} | Procedures: {procedures}")
        typer.echo(f"  Relationships: {rels}")
        typer.echo(f"  Schema Coverage: {coverage_pct:.1f}%")
        typer.echo(f"  Open Gaps: {gap_count} | Conflicts: {conflict_count}")


@app.command(name="export")
def export_cmd(
    entity_name: Optional[str] = typer.Argument(
        None, help="Entity name to export (omit for all)"
    ),
    format: str = typer.Option(
        "all", "--format", "-f", help="Format: markdown, mermaid, json, ddl, all"
    ),
    to_cross: bool = typer.Option(
        False, "--to-cross", help="Push patterns to cross-project store (D-07 explicit opt-in)"
    ),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """Export knowledge in multiple formats to .db-wiki/export/ (D-11, EXPORT-03).

    Supports markdown wiki pages, Mermaid ER diagrams, JSON schema, and annotated DDL.
    Use --to-cross to push patterns to the shared cross-project store (explicit opt-in per D-07).
    """
    from db_wiki.export.runner import ALL_FORMATS, run_export

    # T-03-01: resolve to absolute path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)

    try:
        if to_cross:
            from db_wiki.cross.export import push_patterns_to_cross

            db_name = store_path.parent.name or "default"
            counts = push_patterns_to_cross(conn, db_name)
            typer.echo(f"Pushed patterns to cross-project store: {counts}")
        else:
            fmt_list = ALL_FORMATS if format == "all" else [
                f.strip() for f in format.split(",")
            ]
            output_dir = store_path / "export"
            entity_type = "table"
            results = run_export(conn, output_dir, fmt_list, entity_name, entity_type)
            typer.echo(f"Exported {len(results)} files to {output_dir}")
            for path in results:
                typer.echo(f"  {path}")
    finally:
        conn.close()


@app.command(name="push-cross")
def push_cross(
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """Push patterns from this project's knowledge.db to ~/.db-wiki/cross.db (D-07, CROSS-01).

    Extracts naming conventions, enum values, schema shapes, and state machine
    templates, then writes them to the shared cross-project store.
    """
    from db_wiki.cross.export import push_patterns_to_cross

    # T-03-01: resolve to absolute path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)

    try:
        db_name = store_path.parent.name or "default"
        counts = push_patterns_to_cross(conn, db_name)
    finally:
        conn.close()

    total = sum(counts.values())
    typer.echo(f"Pushed {total} patterns to cross-project store:")
    for pattern_type, count in counts.items():
        typer.echo(f"  {pattern_type}: {count}")


@app.command(name="pull-cross")
def pull_cross(
    pattern_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by pattern type: naming, enum, schema_shape, state_machine"
    ),
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """List available cross-project patterns that could inform this project (D-09, CROSS-02).

    Reads patterns from ~/.db-wiki/cross.db and shows them with similarity-adjusted
    confidence scores.
    """
    from db_wiki.cross.reader import get_cross_patterns

    # T-03-01: resolve to absolute path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)

    try:
        patterns = get_cross_patterns(conn, pattern_type)
    finally:
        conn.close()

    if not patterns:
        typer.echo("No cross-project patterns found. Run 'db-wiki push-cross' on other projects first.")
        return

    typer.echo(f"Cross-project patterns ({len(patterns)} found):")
    for p in patterns:
        typer.echo(
            f"  [{p['pattern_type']}] {p['pattern_key']} "
            f"(source: {p['source_db']}, "
            f"confidence: {p['adjusted_confidence']:.2f}, "
            f"similarity: {p['similarity']:.2f})"
        )


@app.command(name="lint")
def lint_cmd(
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON report instead of formatted text"
    ),
) -> None:
    """Run a comprehensive knowledge health check (lint) on the store.

    Executes all gap detection rules and prints a health score (0-100),
    categorized issues, statistics, and actionable recommendations.
    """
    import json as _json

    from db_wiki.learning.gap_detector import run_lint_check

    # T-03-01: resolve to absolute path
    store_path = store_path.resolve()
    db_path = store_path / "knowledge.db"

    if not db_path.exists():
        typer.echo(
            f"Error: No knowledge store at {store_path}. Run 'db-wiki init' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    conn = open_store(db_path)
    init_schema(conn)

    try:
        report = run_lint_check(conn)
    finally:
        conn.close()

    if json_output:
        typer.echo(_json.dumps(report, indent=2))
        return

    typer.echo(f"Health Score: {report['health_score']}/100")
    typer.echo("")
    typer.echo("Statistics:")
    for key, val in report["stats"].items():
        typer.echo(f"  {key.replace('_', ' ').title()}: {val}")

    if report["issues"]:
        typer.echo("")
        typer.echo(f"Issues ({len(report['issues'])} total):")
        for issue in report["issues"]:
            typer.echo(
                f"  [{issue['severity'].upper()}] {issue['type']}: "
                f"{issue['entity']} — {issue['description']}"
            )
    else:
        typer.echo("")
        typer.echo("No issues found.")

    if report["recommendations"]:
        typer.echo("")
        typer.echo("Recommendations:")
        for rec in report["recommendations"]:
            typer.echo(f"  - {rec}")


# ---------------------------------------------------------------------------
# Phase 5 daemon command group (CLI-05 — discoverability stubs per D-04)
#
# IMPORTANT: These are intentional discoverability stubs, NOT incomplete
# implementations. D-04 specifies `db-wiki serve` as the combined web+learning
# command. There is no separate detached daemon process. These stubs exist so
# users who type `db-wiki daemon` are directed to `db-wiki serve`.
# ---------------------------------------------------------------------------

daemon_app = typer.Typer(
    help="Background learning daemon management. Use 'db-wiki serve' for the combined web+learning process."
)
app.add_typer(daemon_app, name="daemon")


@daemon_app.command()
def start(
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Path to the knowledge store directory"
    ),
) -> None:
    """Start background learning. Redirects to 'db-wiki serve --no-ui'."""
    typer.echo("The learning daemon runs as part of 'db-wiki serve'.")
    typer.echo("For headless learning (no web UI): db-wiki serve --no-ui")
    typer.echo("For web UI + learning:             db-wiki serve")
    raise typer.Exit(0)


@daemon_app.command()
def stop() -> None:
    """Stop background learning. Redirects to Ctrl+C on serve process."""
    typer.echo("The daemon runs inside 'db-wiki serve'. Stop it with Ctrl+C.")
    raise typer.Exit(0)


@daemon_app.command(name="status")
def daemon_status() -> None:
    """Show daemon status. Redirects to serve process."""
    typer.echo("The daemon runs inside 'db-wiki serve'. Check that process for status.")
    typer.echo("For knowledge store status: db-wiki status")
    raise typer.Exit(0)


def main() -> None:
    """Entry point for the db-wiki CLI."""
    app()
