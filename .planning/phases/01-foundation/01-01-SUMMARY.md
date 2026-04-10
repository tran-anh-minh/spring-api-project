---
phase: 01-foundation
plan: "01"
subsystem: core
tags: [scaffold, schema, config, sqlite, bi-temporal, pydantic]
dependency_graph:
  requires: []
  provides:
    - db_wiki Python package installable via uv
    - SQLite bi-temporal schema (5 entity tables + 5 current_* views)
    - open_store() and init_schema() for DB connection management
    - DBWikiConfig YAML config loader with defaults fallback
  affects:
    - 01-02: DDL parser depends on db_wiki package, store, and config
    - 01-03: MCP + CLI skeletons depend on store and config
tech_stack:
  added:
    - sqlglot 30.4.2
    - mcp 1.27.0
    - typer 0.24.1
    - pydantic 2.12.5
    - pydantic-settings 2.13.1
    - pyyaml 6.0.3
    - pytest 9.0.3
    - pytest-asyncio 1.3.0
    - ruff 0.15.10
    - hatchling (build backend)
  patterns:
    - TDD (RED -> GREEN) for Task 2 and Task 3
    - Bi-temporal schema: valid_from/until + recorded_at/invalidated_at per row
    - Mandatory current_* view access layer (never query raw tables)
    - Path.resolve() before sqlite3.connect() for path traversal prevention
    - yaml.safe_load() exclusively (never yaml.load())
key_files:
  created:
    - pyproject.toml
    - db_wiki/__init__.py
    - db_wiki/core/__init__.py
    - db_wiki/core/schema.py
    - db_wiki/core/store.py
    - db_wiki/core/config.py
    - db_wiki/ingest/__init__.py
    - db_wiki/server/__init__.py
    - db_wiki/server/app.py
    - db_wiki/cli/__init__.py
    - db_wiki/cli/app.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_store.py
    - tests/test_config.py
  modified: []
decisions:
  - "Used plain pydantic BaseModel + yaml.safe_load instead of pydantic-settings YamlConfigSettingsSource — simpler, avoids path resolution pitfall (Pitfall 3), resolves Open Question 3"
  - "Entry point stubs created in db_wiki/cli/app.py and db_wiki/server/app.py so pyproject.toml entry points work immediately after uv sync"
  - "IngestConfig added with max_file_size_mb=50 per threat model (unbounded file read DoS mitigation, even though ingest is a later plan)"
metrics:
  duration_minutes: 15
  tasks_completed: 3
  tests_written: 43
  tests_passing: 43
  completed_date: "2026-04-10"
requirements_fulfilled:
  - STORE-01
  - STORE-02
  - STORE-03
  - STORE-04
  - CONFIG-02
  - CONFIG-03
---

# Phase 01 Plan 01: Project Scaffold, Bi-temporal Schema, and Config — Summary

**One-liner:** Python package scaffold with SQLite bi-temporal schema (5 entity tables + 5 current_* views, 8 temporal columns each) and Pydantic YAML config loader.

## What Was Built

### Task 1 — Project scaffold and pyproject.toml (commit 4fcc126)

Created the complete Python package structure per D-05:

- `pyproject.toml` with all required dependencies, entry points (`db-wiki` + `db-wiki-mcp`), pytest asyncio_mode=auto, ruff config
- `db_wiki/__init__.py` with `__version__ = "0.1.0"`
- Package stubs: `db_wiki/core/`, `db_wiki/ingest/`, `db_wiki/server/`, `db_wiki/cli/`
- Minimal entry point implementations: `db_wiki/cli/app.py` (Typer) and `db_wiki/server/app.py` (FastMCP)
- `tests/conftest.py` with `tmp_store_path`, `in_memory_db`, and `initialized_db` fixtures
- `uv sync` succeeded, installing 49 packages including all core dependencies

### Task 2 — SQLite bi-temporal schema and store module (commits 0d6b445, aeb3119)

TDD approach (RED then GREEN):

**Schema** (`db_wiki/core/schema.py`): `SCHEMA_SQL` constant containing DDL for all 5 entity tables — `db_tables`, `db_columns`, `db_procedures`, `db_relationships`, `db_indexes`. Each table has 8 temporal columns per D-01/D-02. Each table has a matching `current_*` view filtering `WHERE valid_until IS NULL AND invalidated_at IS NULL`. Performance indexes on `valid_from_ts` and `recorded_at_ts` for each table.

**Store** (`db_wiki/core/store.py`):
- `open_store(db_path: Path)` — resolves to absolute path (T-01-01), sets WAL mode + foreign_keys, row_factory=sqlite3.Row
- `init_schema(conn)` — executes `conn.executescript(get_schema_sql())`

25 tests, all passing.

### Task 3 — YAML configuration system (commits c2647d2, c079512)

TDD approach (RED then GREEN):

**Config** (`db_wiki/core/config.py`): Three nested Pydantic models (`StorageConfig`, `DatabaseConfig`, `IngestConfig`) composed into `DBWikiConfig`. `load_config(store_path)` reads `store_path/config.yaml` using `yaml.safe_load()` and falls back to defaults on missing/empty file. `write_default_config(store_path)` dumps defaults to YAML, creating parent dirs as needed.

18 tests, all passing.

## Deviations from Plan

### Auto-added (Rule 2 — missing critical functionality)

**1. Entry point stubs for cli/app.py and server/app.py**
- **Found during:** Task 1 — pyproject.toml references `db_wiki.cli.app:main` and `db_wiki.server.app:main`; these modules did not exist, so `uv sync` would succeed but the package would fail to install correctly if entry points were tested
- **Fix:** Created minimal `db_wiki/cli/app.py` with Typer app stub and `db_wiki/server/app.py` with FastMCP stub
- **Files modified:** `db_wiki/cli/app.py`, `db_wiki/server/app.py`
- **Commit:** 4fcc126

**2. `IngestConfig` class added to config.py**
- **Found during:** Task 3 — the plan's acceptance criteria listed `class IngestConfig` and the test file imports it; also the threat model notes unbounded file read as a DoS risk
- **Fix:** Added `IngestConfig(max_file_size_mb: int = 50)` to `DBWikiConfig`
- **Files modified:** `db_wiki/core/config.py`
- **Commit:** c079512 (included in the plan's own action spec — not truly a deviation, but documenting for clarity)

## Threat Surface Scan

No new threat surface beyond what was planned in the threat model. All T-01-01 and T-01-02 mitigations are implemented:

| Mitigation | Location | Implementation |
|------------|----------|----------------|
| T-01-01: Path traversal via --store-path | `open_store()` | `Path(db_path).resolve()` before `sqlite3.connect()` |
| T-01-02: YAML injection | `load_config()` | `yaml.safe_load()` exclusively; pydantic validates types after loading |

## Commits

| Task | Type | Hash | Message |
|------|------|------|---------|
| 1 | feat | 4fcc126 | feat(01-01): create project scaffold and pyproject.toml |
| 2 RED | test | 0d6b445 | test(01-01): add failing tests for bi-temporal schema and store |
| 2 GREEN | feat | aeb3119 | feat(01-01): implement bi-temporal SQLite schema and store module |
| 3 RED | test | c2647d2 | test(01-01): add failing tests for YAML config system |
| 3 GREEN | feat | c079512 | feat(01-01): implement YAML configuration system with Pydantic |

## Test Results

```
43 passed in 0.31s
```

- `tests/test_store.py` — 25 tests (schema creation, temporal columns, views, open_store)
- `tests/test_config.py` — 18 tests (defaults, YAML loading, write/load round-trip, sections)

## Self-Check: PASSED

- All 9 required files exist in worktree
- All 5 commits verified in git log
- 43/43 tests pass in final run
