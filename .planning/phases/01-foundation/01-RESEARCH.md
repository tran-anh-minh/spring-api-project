# Phase 01: Foundation - Research

**Researched:** 2026-04-10
**Domain:** Python project scaffolding, SQLite bi-temporal schema, sqlglot DDL parsing, FastMCP server, Typer CLI, Pydantic config
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Single table with temporal columns — each entity table (db_tables, db_columns, etc.) has valid_from/valid_until/recorded_at/invalidated_at directly on rows. Bi-temporal views filter to "current" rows as mandatory access layer.
- **D-02:** Dual time format — both ISO timestamps (TEXT) and Unix epoch integers (INTEGER) for each temporal column. Epochs for indexing/comparisons, ISO for human readability. Example: `valid_from` (TEXT) + `valid_from_ts` (INTEGER).
- **D-03:** Parser handles CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD CONSTRAINT. Extracts tables, columns with types, inline constraints (PK, FK, NOT NULL, DEFAULT, UNIQUE), and indexes.
- **D-04:** Tolerant parsing — log warnings for unparseable statements, skip them, continue with the rest. Never fail an entire file because of one bad statement.
- **D-05:** Layered sub-packages mirroring the 5-layer architecture: `db_wiki/core/` (store, models), `db_wiki/ingest/` (parsers), `db_wiki/server/` (MCP), `db_wiki/cli/`.
- **D-06:** Two separate entry points: `db-wiki` for CLI (Typer) and `db-wiki-mcp` for MCP server (FastMCP stdio transport).
- **D-07:** Configurable store location with project-local default. `db-wiki init` creates `.db-wiki/` in current directory with `config.yaml` and `knowledge.db`. Overridable via `--store-path` flag or config setting.
- **D-08:** YAML configuration file at `.db-wiki/config.yaml` for storage, database connection, and future settings.

### Claude's Discretion

- Exact SQLite table schemas and column names
- View definitions for bi-temporal filtering
- Specific sqlglot API usage for DDL parsing
- Typer command group structure
- FastMCP skill registration patterns
- Pydantic model definitions for config validation

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-01 | Parse DDL files into tables, columns, constraints, and indexes | sqlglot `parse()` + T-SQL dialect + AST traversal patterns documented below |
| STORE-01 | SQLite database with bi-temporal model (valid_from/until + recorded_at/invalidated_at) for all facts | Bi-temporal schema design with dual ISO+epoch format per D-01/D-02 |
| STORE-02 | Bi-temporal views as mandatory access layer | SQLite CREATE VIEW pattern with WHERE valid_until IS NULL or > current time |
| STORE-03 | Core entity tables: db_tables, db_columns, db_procedures with descriptions and metadata | Schema design in Architecture Patterns section |
| STORE-04 | Relationship graph: db_relationships with typed edges | Schema design in Architecture Patterns section |
| MCP-01 | MCP server via FastMCP with stdio transport | FastMCP 1.27.0 patterns documented below |
| MCP-02 | Async-first skill design with job ID pattern | FastMCP async tool + lifespan context patterns documented below |
| CLI-01 | CLI interface (Typer) mirroring MCP skills | Typer 0.24.1 command group patterns documented below |
| CLI-02 | Setup commands: db-wiki init, db-wiki connect | Typer subcommand pattern with filesystem operations |
| CONFIG-02 | Configurable DB connection: works offline from SQL files | YAML config + optional db_connection section |
| CONFIG-03 | YAML configuration file (.db-wiki/config.yaml) | pydantic-settings BaseSettings + YamlConfigSettingsSource |
</phase_requirements>

---

## Summary

Phase 1 establishes the entire foundational layer of db-wiki: the Python package scaffold, SQLite bi-temporal schema, DDL parser (CREATE TABLE/INDEX/ALTER TABLE ADD CONSTRAINT), FastMCP server skeleton, Typer CLI skeleton, and YAML configuration system. All five areas have well-established, stable libraries with clear APIs — no novel integration challenges exist for this phase.

The key technical constraint is the bi-temporal schema design (D-01/D-02). Every entity table carries four temporal columns (valid_from, valid_from_ts, valid_until, valid_until_ts, recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts) and application code must only query through current-state views — never raw tables. This is a schema discipline problem, not a library problem. The planner must assign explicit tasks for creating the views and enforcing the access layer rule.

sqlglot has advanced significantly beyond the 25.x version mentioned in CLAUDE.md — the current version is 30.4.2. The core API (`parse()`, `parse_one()`, `exp.ColumnDef`, `find_all()`) is stable and backwards-compatible. The `exp.Command` fallback behavior (tolerant parsing for unparseable statements) has been stable across versions.

**Primary recommendation:** Build in wave order — (1) pyproject.toml + package scaffold, (2) SQLite schema + bi-temporal views, (3) DDL parser, (4) FastMCP skeleton, (5) Typer CLI, (6) YAML config. Each wave produces testable output before the next depends on it.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.4 (installed) | Runtime | sqlglot, sentence-transformers, MCP SDK all compatible. CLAUDE.md mandates 3.11+ minimum. |
| sqlglot | 30.4.2 (latest) | T-SQL DDL parsing | Only mature pure-Python SQL parser with full AST for T-SQL. `parse()` + T-SQL dialect handles all Phase 1 DDL targets. [VERIFIED: pip index versions] |
| mcp (FastMCP) | 1.27.0 (latest) | MCP server protocol | Anthropic's official Python SDK. FastMCP decorator API. stdio transport for Claude Code. [VERIFIED: pip index versions] |
| typer | 0.24.1 (latest) | CLI interface | Standard Python CLI with command groups. `app.add_typer()` for nested commands. [VERIFIED: pip index versions] |
| pydantic | 2.12.5 (latest) | Config validation | FastMCP requires Pydantic v2. BaseSettings for YAML config. [VERIFIED: pip index versions] |
| pyyaml | 6.x (latest) | YAML parsing | Required by pydantic-settings for YAML config source. Standard, stable. [ASSUMED - version, but pyyaml is the de-facto YAML library] |
| pydantic-settings | 2.x | YAML config loading | Official pydantic extension for settings management with YAML source support. [ASSUMED - check exact version] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlite3 | stdlib (bundled) | SQLite database | All DB operations. WAL mode for concurrent read access. |
| pytest | 9.0.3 (latest) | Unit testing | Standard. Phase 1 creates test infrastructure. [VERIFIED: pip index versions] |
| pytest-asyncio | 1.3.0 (latest) | Async test support | Required for testing async MCP tool handlers. [VERIFIED: pip index versions] |
| ruff | 0.15.10 (latest) | Linting + formatting | Replaces flake8/black/isort. Single tool. [VERIFIED: pip index versions] |
| uv | 0.8.4 (installed) | Package manager | Already installed. `uv run`, `uvx`, lockfile management. [VERIFIED: command -v uv] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pydantic-settings + pyyaml | pydantic-yaml | pydantic-settings is the official Pydantic extension, pydantic-yaml is a third-party lib. Use official approach. |
| typer | click | CLAUDE.md recommends click; typer is built on click and adds type hints + help generation with zero extra work. Typer is strictly better for new Python 3.11+ projects. CONTEXT.md decision implies Typer (discretion area). |
| sqlglot.parse() | sqlglot.parse_one() | `parse_one()` raises on multi-statement input. Always use `parse()` for SQL files which may contain many statements. |

### Installation

```bash
uv add sqlglot mcp typer pydantic pydantic-settings pyyaml
uv add --dev pytest pytest-asyncio ruff pyright
```

---

## Architecture Patterns

### Recommended Project Structure

```
db_wiki/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── store.py          # SQLite connection management, WAL mode setup
│   ├── schema.py         # CREATE TABLE statements, bi-temporal DDL
│   └── models.py         # Pydantic models for internal data structures
├── ingest/
│   ├── __init__.py
│   └── ddl_parser.py     # sqlglot DDL parsing, tolerant error handling
├── server/
│   ├── __init__.py
│   └── app.py            # FastMCP instance, tool registrations
└── cli/
    ├── __init__.py
    └── app.py            # Typer app, command groups
pyproject.toml
.db-wiki/                  # Created by `db-wiki init` (gitignored)
├── config.yaml
└── knowledge.db
tests/
├── conftest.py
├── test_ddl_parser.py
├── test_store.py
└── test_cli.py
```

### Pattern 1: sqlglot Tolerant DDL Parsing

**What:** Parse a SQL file with multiple statements, extract DDL, skip unparseable statements with warnings.

**When to use:** INGEST-01 — parsing user-supplied schema files

```python
# Source: https://github.com/tobymao/sqlglot/blob/main/posts/onboarding.md
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
import logging

logger = logging.getLogger(__name__)

def parse_ddl_file(sql_text: str) -> list[exp.Expression]:
    """Parse SQL file content, skipping unparseable statements (D-04)."""
    statements = sqlglot.parse(sql_text, dialect="tsql")
    result = []
    for stmt in statements:
        if stmt is None:
            continue
        if isinstance(stmt, exp.Command):
            # sqlglot fallback for unparseable syntax — log and skip
            logger.warning("Skipping unparseable statement: %s", stmt.sql()[:120])
            continue
        result.append(stmt)
    return result
```

### Pattern 2: Extracting Table/Column Info from CREATE TABLE AST

**What:** Walk a CREATE TABLE AST node to extract table name, column definitions, and inline constraints.

**When to use:** INGEST-01 — after parsing, before storing to SQLite

```python
# Source: https://github.com/tobymao/sqlglot/blob/main/posts/onboarding.md
from sqlglot import exp

def extract_create_table(stmt: exp.Create) -> dict:
    table_node = stmt.this  # exp.Schema or exp.Table
    table_name = table_node.name
    schema_name = None
    if hasattr(table_node, 'db') and table_node.db:
        schema_name = table_node.db

    columns = []
    for col_def in stmt.find_all(exp.ColumnDef):
        col_info = {
            "name": col_def.name,
            "type": col_def.kind.sql(dialect="tsql") if col_def.kind else None,
            "constraints": [],
        }
        for constraint in col_def.args.get("constraints", []):
            if isinstance(constraint.kind, exp.PrimaryKeyColumnConstraint):
                col_info["constraints"].append("PRIMARY KEY")
            elif isinstance(constraint.kind, exp.NotNullColumnConstraint):
                col_info["constraints"].append("NOT NULL")
            elif isinstance(constraint.kind, exp.UniqueColumnConstraint):
                col_info["constraints"].append("UNIQUE")
            elif isinstance(constraint.kind, exp.DefaultColumnConstraint):
                col_info["constraints"].append(
                    f"DEFAULT {constraint.kind.this.sql()}"
                )
        columns.append(col_info)

    # Table-level constraints (PK, FK defined separately)
    table_constraints = []
    for tc in stmt.find_all(exp.PrimaryKey):
        cols = [c.name for c in tc.find_all(exp.Column)]
        table_constraints.append({"type": "PRIMARY KEY", "columns": cols})
    for fk in stmt.find_all(exp.ForeignKey):
        table_constraints.append({
            "type": "FOREIGN KEY",
            "columns": [c.name for c in fk.expressions],
            "ref_table": fk.args.get("reference", {}).get("this", {}).name
            if fk.args.get("reference") else None,
        })

    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "columns": columns,
        "constraints": table_constraints,
    }
```

### Pattern 3: FastMCP Server with Lifespan (store access)

**What:** FastMCP server with typed lifespan context giving tools access to the knowledge store.

**When to use:** MCP-01, MCP-02 — server skeleton with store dependency injection

```python
# Source: https://github.com/modelcontextprotocol/python-sdk README
from contextlib import asynccontextmanager
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP, Context

@dataclass
class AppContext:
    store_path: str  # path to knowledge.db

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    # Load config, open store connection
    config = load_config()
    ctx = AppContext(store_path=config.store_path)
    yield ctx
    # Cleanup on shutdown

mcp = FastMCP("db-wiki", lifespan=app_lifespan)

@mcp.tool()
async def ingest(file_path: str, ctx: Context) -> str:
    """Ingest a DDL file into the knowledge store."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    # ... implementation
    return f"Ingested {file_path}"

def main():
    mcp.run()  # stdio transport by default
```

### Pattern 4: Typer CLI with Sub-Commands

**What:** Typer app with `init` and `connect` as top-level commands, matching D-06 structure.

**When to use:** CLI-01, CLI-02

```python
# Source: https://typer.tiangolo.com/
import typer
from pathlib import Path

app = typer.Typer(help="DB Wiki — turn undocumented databases into queryable knowledge.")

@app.command()
def init(
    store_path: Path = typer.Option(
        Path(".db-wiki"), "--store-path", help="Directory for knowledge store"
    )
):
    """Initialize a new db-wiki knowledge store in the current directory."""
    store_path.mkdir(parents=True, exist_ok=True)
    # write config.yaml, create knowledge.db
    typer.echo(f"Initialized knowledge store at {store_path}")

@app.command()
def connect(
    connection_string: str = typer.Argument(..., help="SQL Server connection string")
):
    """Register a live database connection in the knowledge store config."""
    # update config.yaml with db_connection section
    typer.echo("Connection registered.")

@app.command()
def ingest(
    file: Path = typer.Argument(..., help="DDL file or directory to ingest"),
):
    """Parse and ingest DDL files into the knowledge store."""
    pass

def main():
    app()
```

### Pattern 5: Pydantic v2 YAML Config

**What:** Type-safe YAML config loading using pydantic-settings with YamlConfigSettingsSource.

**When to use:** CONFIG-02, CONFIG-03

```python
# Source: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings, YamlConfigSettingsSource, SettingsConfigDict

class StorageConfig(BaseModel):
    path: str = ".db-wiki"

class DatabaseConfig(BaseModel):
    connection_string: str | None = None
    timeout_seconds: int = 30

class DBWikiConfig(BaseSettings):
    storage: StorageConfig = StorageConfig()
    database: DatabaseConfig = DatabaseConfig()

    model_config = SettingsConfigDict(yaml_file=".db-wiki/config.yaml")

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):
        return (YamlConfigSettingsSource(settings_cls),)

def load_config(store_path: str = ".db-wiki") -> DBWikiConfig:
    """Load config from YAML, falling back to defaults if file doesn't exist."""
    try:
        return DBWikiConfig(_yaml_file=f"{store_path}/config.yaml")
    except Exception:
        return DBWikiConfig()
```

### Pattern 6: Bi-temporal SQLite Schema

**What:** Entity table layout with all 8 temporal columns (4 concepts x 2 formats per D-01/D-02) plus current-state view.

**When to use:** STORE-01, STORE-02, STORE-03

```sql
-- Source: D-01 and D-02 decisions from CONTEXT.md
CREATE TABLE IF NOT EXISTS db_tables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    -- entity data
    table_name  TEXT NOT NULL,
    schema_name TEXT,
    description TEXT,
    -- valid time (when fact was true in the real world)
    valid_from      TEXT NOT NULL,   -- ISO: "2026-04-10T13:00:00Z"
    valid_from_ts   INTEGER NOT NULL, -- Unix epoch
    valid_until     TEXT,            -- NULL = currently valid
    valid_until_ts  INTEGER,
    -- transaction time (when we learned about it)
    recorded_at     TEXT NOT NULL,
    recorded_at_ts  INTEGER NOT NULL,
    invalidated_at  TEXT,
    invalidated_at_ts INTEGER
);

-- Mandatory access layer view (STORE-02)
CREATE VIEW IF NOT EXISTS current_db_tables AS
SELECT * FROM db_tables
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;
```

### Anti-Patterns to Avoid

- **Querying raw temporal tables directly:** Any `SELECT * FROM db_tables` in application code violates STORE-02. All queries must go through `current_db_tables` (and equivalent views for other entities).
- **Using parse_one() on multi-statement files:** Raises an error on the second statement. Always use `sqlglot.parse()` which returns a list.
- **Mixing async and sync in FastMCP tools:** FastMCP handles both transparently, but mixing within the same call chain (e.g., calling async from sync without await) causes subtle bugs. Keep all tools async.
- **Storing ISO timestamps as naive (no timezone):** All timestamps must be UTC with Z suffix to avoid comparison bugs when the host timezone changes.
- **Hard-coding .db-wiki/ paths:** Config must respect the `--store-path` override from D-07. Use `Path` objects throughout, derive from config.
- **Creating pydantic-settings model with yaml_file pointing to non-existent file:** On first `db-wiki init` the file doesn't exist yet. Handle FileNotFoundError gracefully or create a minimal default first.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL parsing and AST extraction | Custom regex/string parser | sqlglot | Bracket identifiers, NVARCHAR/NCHAR types, schema qualifiers ([dbo].[table]), and inline constraints are all edge cases that regex fails on. sqlglot handles them. |
| CLI argument parsing and help | argparse boilerplate | typer | Type hint-driven schema generation, auto-help text, subcommands with zero boilerplate. |
| MCP protocol wire format | Custom JSON-RPC | mcp (FastMCP) | Protocol versioning, transport negotiation, schema generation. Hand-rolling this breaks on spec updates. |
| Config validation and coercion | Custom dict parsing | pydantic-settings | Type coercion, nested models, environment variable override, missing key defaults. |
| YAML reading for config | Custom file read + json.loads | pyyaml (via pydantic-settings) | YAML anchors, multi-document, type edge cases. |

**Key insight:** Phase 1 has no "hard problems" that require custom solutions. All five components (parser, store, MCP, CLI, config) have well-established library solutions. The risk is in integration discipline (bi-temporal view enforcement, tolerant parsing) not in implementing new algorithms.

---

## Common Pitfalls

### Pitfall 1: sqlglot constraint node type confusion

**What goes wrong:** Inline column constraints in sqlglot are wrapped in `exp.ColumnConstraint` nodes, where the actual constraint type is in `constraint.kind` (e.g., `exp.PrimaryKeyColumnConstraint`), not directly `exp.PrimaryKey`. Using `isinstance(constraint, exp.PrimaryKey)` on a column-level constraint finds nothing.

**Why it happens:** sqlglot distinguishes between table-level constraints (`exp.PrimaryKey`, `exp.ForeignKey`) and column-level constraints (`exp.PrimaryKeyColumnConstraint`, `exp.NotNullColumnConstraint`, etc.).

**How to avoid:** When iterating `col_def.args.get("constraints", [])`, check `constraint.kind` type, not `constraint` itself.

**Warning signs:** Parser returns no constraints even for a DDL with obvious `NOT NULL PRIMARY KEY` columns.

### Pitfall 2: Bi-temporal view missing from schema migration

**What goes wrong:** Entity table is created correctly with all 8 temporal columns, but the `current_*` view is not created in the same migration. Application code written before the view exists quietly queries raw tables, establishing the bad pattern.

**Why it happens:** Schema init is split across multiple tasks or the view creation step is deferred.

**How to avoid:** Create the view in the same function/migration as the entity table. Never return from `schema.py` functions without the matching view existing.

**Warning signs:** Any `SELECT` in application code references a table name without the `current_` prefix.

### Pitfall 3: pydantic-settings YAML file path resolution

**What goes wrong:** `YamlConfigSettingsSource` resolves the YAML path relative to the current working directory, not relative to the store path. If `db-wiki` is run from a different directory than `.db-wiki/config.yaml`, config loads fail silently (falls back to defaults).

**Why it happens:** pydantic-settings uses a fixed path string, not a dynamic resolver.

**How to avoid:** Resolve the config path to absolute before passing it to BaseSettings. Accept `--store-path` as a CLI option, resolve to absolute, then pass to config loader.

**Warning signs:** `db-wiki ingest` from a parent directory of the store silently uses defaults instead of stored config.

### Pitfall 4: FastMCP lifespan context type safety

**What goes wrong:** `ctx.request_context.lifespan_context` is typed as `Any` unless you explicitly parameterize the `Context` type. Accessing wrong attributes at runtime causes `AttributeError` that only appear when a tool is actually called.

**Why it happens:** FastMCP's generic typing requires explicit type parameters to enable type-checked context access.

**How to avoid:** Define `AppContext` as a dataclass and use `Context[ServerSession, AppContext]` in tool signatures.

**Warning signs:** pyright reports `Any` type on lifespan_context access.

### Pitfall 5: sqlglot version mismatch between CLAUDE.md and registry

**What goes wrong:** CLAUDE.md documents sqlglot 25.x but the current version is 30.4.2. If tests or imports rely on 25.x-specific API behavior, they will pass with pinned 25.x but fail when uv resolves to latest.

**Why it happens:** Training data lag + documentation not updated with each release.

**How to avoid:** Pin to `sqlglot>=30.0,<31` in pyproject.toml. The core DDL parsing API (`parse()`, `exp.ColumnDef`, `find_all()`) is stable across these versions.

**Warning signs:** CI passes locally with an old pinned version but fails in a clean install.

---

## Code Examples

### Full pyproject.toml skeleton

```toml
# Source: https://docs.astral.sh/uv/concepts/projects/config/ [CITED]
[project]
name = "db-wiki"
version = "0.1.0"
description = "Self-learning database knowledge engine"
requires-python = ">=3.11"
dependencies = [
    "sqlglot>=30.0,<31",
    "mcp>=1.27,<2",
    "typer>=0.24,<1",
    "pydantic>=2.12,<3",
    "pydantic-settings>=2.0,<3",
    "pyyaml>=6.0",
]

[project.scripts]
db-wiki = "db_wiki.cli.app:main"
db-wiki-mcp = "db_wiki.server.app:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
```

### SQLite WAL mode + schema init

```python
# [ASSUMED] Pattern — standard sqlite3 WAL setup
import sqlite3
from pathlib import Path

def open_store(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sqlglot 25.x (CLAUDE.md) | sqlglot 30.4.2 | Ongoing rapid releases | Core DDL API unchanged; pin to `>=30.0,<31` |
| mcp 1.x generic (CLAUDE.md) | mcp 1.27.0 | 2025 | FastMCP API stable; `lifespan` typing improved |
| click (CLAUDE.md suggestion) | typer (CONTEXT.md choice) | N/A | Typer wraps click; same underlying behavior |
| pytest-asyncio strict mode (old default) | asyncio_mode = "auto" (1.3.0) | pytest-asyncio 1.0 | Must set in pyproject.toml or all async tests need explicit `@pytest.mark.asyncio` |

**Deprecated/outdated:**
- sqlglot 25.x pin in CLAUDE.md: Current version is 30.4.2 with the same core API. Update the pin.
- `mcp.server.fastmcp.Context` import path: Verify current import path in mcp 1.27.x — may have moved to `mcp.server.fastmcp` or a sub-module. The lifespan API was updated in 1.x releases.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | pyyaml is the correct PyPI package name for YAML parsing | Standard Stack | Low — easily verified; pyyaml is the de-facto standard |
| A2 | pydantic-settings version is 2.x and supports YamlConfigSettingsSource | Standard Stack | Medium — if the YAML source API changed, config loading pattern needs update |
| A3 | `ctx.request_context.lifespan_context` is the correct attribute path in mcp 1.27.0 | Code Examples | Medium — FastMCP API evolves; verify against mcp 1.27 source before implementing |
| A4 | `exp.PrimaryKeyColumnConstraint`, `exp.NotNullColumnConstraint` are the correct node type names in sqlglot 30.x | Code Examples | Medium — node type names may have changed; run a quick test against a sample DDL to verify before building the full extractor |
| A5 | SQLite WAL mode is safe for concurrent access from MCP server + CLI on same database | Architecture | Low — WAL is well-documented SQLite behavior; multiple readers + single writer is the standard use case |

---

## Open Questions

1. **sqlglot constraint node names in 30.x**
   - What we know: sqlglot distinguishes column-level vs table-level constraints with different node type names
   - What's unclear: Whether `exp.PrimaryKeyColumnConstraint` is the exact class name in 30.4.2, or if it was renamed
   - Recommendation: Wave 0 task — write a 5-line test that parses `CREATE TABLE t (id INT PRIMARY KEY NOT NULL)` and prints all constraint node types to verify names before writing the extractor

2. **FastMCP lifespan context access in mcp 1.27**
   - What we know: The lifespan pattern is documented and stable; the exact attribute path on the Context object may vary
   - What's unclear: Whether it's `ctx.request_context.lifespan_context` or a different path in 1.27
   - Recommendation: Wave 0 task — create a minimal FastMCP server, add a tool that prints `dir(ctx)`, run it to inspect the actual API

3. **pydantic-settings YAML source import path**
   - What we know: pydantic-settings 2.x has YAML support; `YamlConfigSettingsSource` requires pyyaml
   - What's unclear: Whether `from pydantic_settings import YamlConfigSettingsSource` works in 2.x or needs a different import
   - Recommendation: Verify with `python -c "from pydantic_settings import YamlConfigSettingsSource"` after install

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12.4 | — |
| uv | Package manager | Yes | 0.8.4 | pip + venv |
| pip | Package install | Yes | 24.0 | — |
| sqlglot | INGEST-01 | Not installed (dev machine) | install 30.4.2 | — |
| mcp | MCP-01 | Not installed | install 1.27.0 | — |
| typer | CLI-01 | Not installed | install 0.24.1 | — |
| pydantic | CONFIG-03 | Not installed | install 2.12.5 | — |
| pytest | Testing | Not installed | install 9.0.3 | — |
| pytest-asyncio | Async tests | Not installed | install 1.3.0 | — |

**Missing dependencies with no fallback:** None — all installable via `uv add`.

**Missing dependencies with fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-01 | Parse CREATE TABLE DDL into tables/columns/constraints | unit | `pytest tests/test_ddl_parser.py -x` | Wave 0 |
| INGEST-01 | Tolerant parsing — bad statement skipped, rest parsed | unit | `pytest tests/test_ddl_parser.py::test_tolerant_parse -x` | Wave 0 |
| INGEST-01 | CREATE INDEX parsed into index records | unit | `pytest tests/test_ddl_parser.py::test_create_index -x` | Wave 0 |
| INGEST-01 | ALTER TABLE ADD CONSTRAINT parsed | unit | `pytest tests/test_ddl_parser.py::test_alter_table -x` | Wave 0 |
| STORE-01 | SQLite DB created with all 8 temporal columns per entity table | unit | `pytest tests/test_store.py::test_schema_created -x` | Wave 0 |
| STORE-02 | current_* views exist and filter correctly | unit | `pytest tests/test_store.py::test_views -x` | Wave 0 |
| STORE-03 | db_tables, db_columns, db_relationships tables exist | unit | `pytest tests/test_store.py::test_entity_tables -x` | Wave 0 |
| MCP-01 | FastMCP server starts on stdio without error | smoke | `pytest tests/test_server.py::test_server_starts -x` | Wave 0 |
| MCP-02 | Async tool returns job_id for long-running ops | unit | `pytest tests/test_server.py::test_async_tool -x` | Wave 0 |
| CLI-01 | `db-wiki --help` shows commands | smoke | `pytest tests/test_cli.py::test_help -x` | Wave 0 |
| CLI-02 | `db-wiki init` creates `.db-wiki/config.yaml` and `knowledge.db` | integration | `pytest tests/test_cli.py::test_init -x` | Wave 0 |
| CONFIG-03 | YAML config loads with defaults when file absent | unit | `pytest tests/test_config.py::test_defaults -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/conftest.py` — shared fixtures (temp dir, in-memory SQLite)
- [ ] `tests/test_ddl_parser.py` — covers INGEST-01
- [ ] `tests/test_store.py` — covers STORE-01, STORE-02, STORE-03
- [ ] `tests/test_server.py` — covers MCP-01, MCP-02
- [ ] `tests/test_cli.py` — covers CLI-01, CLI-02
- [ ] `tests/test_config.py` — covers CONFIG-03
- [ ] Framework install: `uv add --dev pytest pytest-asyncio ruff`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Local-only tool; no authentication in Phase 1 |
| V3 Session Management | No | No sessions; stateless CLI/MCP tools |
| V4 Access Control | No | Single-user local tool |
| V5 Input Validation | Yes | pydantic for config; sqlglot for SQL input (parse, don't exec) |
| V6 Cryptography | No | No secrets stored in Phase 1 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal in `--store-path` argument | Tampering | Resolve to absolute path with `Path.resolve()` before use; restrict to user-controlled directories |
| SQL injection via DDL file content | Tampering | Not applicable — DDL is parsed structurally by sqlglot, never executed against any database |
| Config file injection (YAML) | Tampering | pydantic-settings validates types; do NOT use `yaml.load()` (use `yaml.safe_load()` directly or pydantic-settings) |
| Unbounded file read | Denial of Service | Add max file size limit (configurable, default 50MB) in ingest command before passing to sqlglot |

---

## Sources

### Primary (HIGH confidence)
- `pip index versions sqlglot` — version 30.4.2 confirmed current [VERIFIED: registry]
- `pip index versions mcp` — version 1.27.0 confirmed current [VERIFIED: registry]
- `pip index versions typer` — version 0.24.1 confirmed current [VERIFIED: registry]
- `pip index versions pydantic` — version 2.12.5 confirmed current [VERIFIED: registry]
- `pip index versions pytest-asyncio` — version 1.3.0 confirmed current [VERIFIED: registry]
- https://github.com/tobymao/sqlglot/blob/main/posts/onboarding.md — DDL parsing patterns, `exp.Command` fallback behavior [CITED]
- https://github.com/modelcontextprotocol/python-sdk README — FastMCP setup, lifespan, tool registration, stdio transport [CITED]
- https://typer.tiangolo.com/ — Typer command group and entry point patterns [CITED]
- `.planning/phases/01-foundation/01-CONTEXT.md` — locked design decisions D-01 through D-08 [VERIFIED: file read]
- `CLAUDE.md` §Technology Stack — project constraints and library selection rationale [VERIFIED: file read]

### Secondary (MEDIUM confidence)
- https://docs.pydantic.dev/latest/concepts/pydantic_settings/ — pydantic-settings YAML source pattern [CITED via WebSearch]
- https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html — asyncio_mode configuration [CITED via WebSearch]

### Tertiary (LOW confidence)
- General bi-temporal schema design principles — applied to SQLite; no single authoritative SQLite-specific source [ASSUMED pattern]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI registry
- Architecture: HIGH — locked decisions from CONTEXT.md, stable library APIs
- Pitfalls: MEDIUM — sqlglot constraint node names need runtime verification (A4)
- Test map: HIGH — requirements are concrete and map cleanly to unit tests

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable libraries; sqlglot releases frequently but API is backwards-compatible within major version)
