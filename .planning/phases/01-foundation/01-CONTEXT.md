# Phase 1: Foundation - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

SQLite bi-temporal knowledge store schema, DDL file parser (CREATE TABLE + CREATE INDEX + ALTER TABLE ADD CONSTRAINT), async MCP server skeleton with FastMCP, CLI skeleton with Typer, and YAML configuration system. Users can ingest DDL files and query the resulting schema knowledge via MCP or CLI.

</domain>

<decisions>
## Implementation Decisions

### Schema Design
- **D-01:** Single table with temporal columns — each entity table (db_tables, db_columns, etc.) has valid_from/valid_until/recorded_at/invalidated_at directly on rows. Bi-temporal views filter to "current" rows as mandatory access layer.
- **D-02:** Dual time format — both ISO timestamps (TEXT, e.g., `2026-04-10T13:00:00Z`) and Unix epoch integers (INTEGER) for each temporal column. Epochs for indexing/comparisons, ISO for human readability. Example: `valid_from` (TEXT) + `valid_from_ts` (INTEGER).

### DDL Parser Scope
- **D-03:** Parser handles CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD CONSTRAINT. Extracts tables, columns with types, inline constraints (PK, FK, NOT NULL, DEFAULT, UNIQUE), and indexes.
- **D-04:** Tolerant parsing — log warnings for unparseable statements, skip them, continue with the rest. Never fail an entire file because of one bad statement.

### Project Structure
- **D-05:** Layered sub-packages mirroring the 5-layer architecture: `db_wiki/core/` (store, models), `db_wiki/ingest/` (parsers), `db_wiki/server/` (MCP), `db_wiki/cli/`.
- **D-06:** Two separate entry points: `db-wiki` for CLI (Typer) and `db-wiki-mcp` for MCP server (FastMCP stdio transport).

### Configuration & Initialization
- **D-07:** Configurable store location with project-local default. `db-wiki init` creates `.db-wiki/` in current directory with `config.yaml` and `knowledge.db`. Overridable via `--store-path` flag or config setting.
- **D-08:** YAML configuration file at `.db-wiki/config.yaml` for storage, database connection, and future settings.

### Claude's Discretion
- Exact SQLite table schemas and column names
- View definitions for bi-temporal filtering
- Specific sqlglot API usage for DDL parsing
- Typer command group structure
- FastMCP skill registration patterns
- Pydantic model definitions for config validation

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs — requirements fully captured in decisions above and in project-level documents:

- `.planning/REQUIREMENTS.md` — Phase 1 requirements: INGEST-01, STORE-01 through STORE-04, MCP-01, MCP-02, CLI-01, CLI-02, CONFIG-02, CONFIG-03
- `.planning/PROJECT.md` — Core constraints (SQLite only, Python, sqlglot, MCP protocol, read-only safety, local-first privacy)
- `CLAUDE.md` §Technology Stack — Recommended libraries with versions, alternatives considered, what NOT to use

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None yet — Phase 1 establishes the foundational patterns for all subsequent phases

### Integration Points
- `pyproject.toml` entry points for `db-wiki` (CLI) and `db-wiki-mcp` (MCP server)
- `.db-wiki/config.yaml` as the configuration interface
- `.db-wiki/knowledge.db` as the SQLite knowledge store

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-10*
