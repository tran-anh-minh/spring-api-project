# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 01-foundation
**Areas discussed:** Schema Design, DDL Parser Scope, Project Structure, Configuration & Initialization

---

## Schema Design

### Bi-temporal table structure

| Option | Description | Selected |
|--------|-------------|----------|
| Single table with temporal columns | Each entity table has valid_from/valid_until/recorded_at/invalidated_at directly. Views filter to current rows. Graphiti pattern. | ✓ |
| Separate history tables | Main tables hold current state, _history tables hold past versions. Cleaner current queries, more complex temporal. | |
| You decide | Claude picks based on Graphiti pattern and SQLite constraints. | |

**User's choice:** Single table with temporal columns
**Notes:** Direct match to the Graphiti bi-temporal pattern already decided in project research.

### Temporal column format

| Option | Description | Selected |
|--------|-------------|----------|
| ISO timestamps (TEXT) | Human-readable, standard SQLite datetime functions work | |
| Unix epochs (INTEGER) | Faster comparisons, smaller storage, need conversion | |
| Both | Dual columns per temporal field — ISO for readability, epoch for indexing | ✓ |

**User's choice:** Both — store ISO timestamps and Unix epochs for each temporal column
**Notes:** User wants the benefits of both formats. Each temporal field gets a pair (e.g., valid_from TEXT + valid_from_ts INTEGER).

---

## DDL Parser Scope

### DDL constructs to handle

| Option | Description | Selected |
|--------|-------------|----------|
| CREATE TABLE only | Tables, columns, inline constraints. Minimal viable. | |
| CREATE TABLE + CREATE INDEX + ALTER TABLE ADD CONSTRAINT | Full schema coverage including out-of-line constraints and indexes. | ✓ |
| Full DDL | Everything plus CREATE VIEW, CREATE SCHEMA, permissions. | |

**User's choice:** CREATE TABLE + CREATE INDEX + ALTER TABLE ADD CONSTRAINT
**Notes:** Full schema graph from day one without over-scoping into views/permissions.

### Error handling

| Option | Description | Selected |
|--------|-------------|----------|
| Parse what you can, skip what you can't | Log warnings, continue. Never fail entire file. | ✓ |
| Strict mode | Fail file on parse errors. User must fix DDL. | |
| You decide | | |

**User's choice:** Tolerant parsing with warnings
**Notes:** Real-world SQL files often have issues; tolerant approach prevents blocking on edge cases.

---

## Project Structure

### Package organization

| Option | Description | Selected |
|--------|-------------|----------|
| Single package, flat modules | db_wiki/ with parser.py, store.py, etc. Simple. | |
| Single package, layered sub-packages | db_wiki/core/, db_wiki/ingest/, db_wiki/server/, db_wiki/cli/. Mirrors 5-layer architecture. | ✓ |
| You decide | | |

**User's choice:** Layered sub-packages
**Notes:** Mirrors the 5-layer architecture defined in project research.

### Entry points

| Option | Description | Selected |
|--------|-------------|----------|
| Two entry points | db-wiki (CLI/Typer) and db-wiki-mcp (MCP/FastMCP). Separate commands. | ✓ |
| Single entry point with subcommand | db-wiki for everything, db-wiki serve for MCP. | |
| You decide | | |

**User's choice:** Two separate entry points
**Notes:** Clean separation between CLI and MCP server concerns.

---

## Configuration & Initialization

### Store location

| Option | Description | Selected |
|--------|-------------|----------|
| Project-local (.db-wiki/) | Default in current directory, git-ignorable. | |
| User-global (~/.db-wiki/) | Default in home directory, cross-project. | |
| Configurable | User chooses, with a default | ✓ |

**User's choice:** Configurable with project-local default
**Notes:** Default to .db-wiki/ in current directory, overridable via --store-path or config.

### Default location

| Option | Description | Selected |
|--------|-------------|----------|
| Project-local (.db-wiki/) | Current directory, each project isolated | ✓ |
| User-global (~/.db-wiki/) | Home directory, cross-project by default | |

**User's choice:** Project-local (.db-wiki/) as default
**Notes:** Isolated per project by default, overridable for shared scenarios.

---

## Claude's Discretion

- Exact SQLite table schemas and column names
- View definitions for bi-temporal filtering
- Specific sqlglot API usage for DDL parsing
- Typer command group structure
- FastMCP skill registration patterns
- Pydantic model definitions for config validation

## Deferred Ideas

None — discussion stayed within phase scope.
