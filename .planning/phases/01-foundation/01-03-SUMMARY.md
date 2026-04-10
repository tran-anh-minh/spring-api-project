---
phase: 01-foundation
plan: "03"
subsystem: api
tags: [mcp, fastmcp, typer, cli, sqlite, lifespan, stdio]

requires:
  - phase: 01-01
    provides: open_store, init_schema, load_config, write_default_config, DBWikiConfig

provides:
  - FastMCP server (db-wiki-mcp entry point) with stdio transport and lifespan context
  - ingest MCP tool with file validation and size limit enforcement
  - status MCP tool querying current_* views
  - Typer CLI (db-wiki entry point) with init, connect, ingest commands
  - AppContext dataclass for typed store access in MCP tools

affects: [02-ingest, 03-search, 04-learning, 05-query]

tech-stack:
  added: []
  patterns:
    - "FastMCP lifespan pattern: @asynccontextmanager yields AppContext dataclass, accessed via ctx.request_context.lifespan_context"
    - "CLI idempotency: check both config.yaml and knowledge.db exist before init; skip with message if both present"
    - "ImportError guard for optional ddl_parser: catch ImportError and return user-friendly error"
    - "Path.resolve() on all user-supplied paths before file operations (T-03-01 pattern)"

key-files:
  created:
    - db_wiki/server/app.py
    - db_wiki/cli/app.py
    - tests/test_server.py
    - tests/test_cli.py
  modified: []

key-decisions:
  - "ctx.request_context.lifespan_context confirmed as correct access path for AppContext in mcp 1.27; verified against RequestContext dataclass source"
  - "mcp.settings.lifespan used for test verification of lifespan registration (not a private attribute)"
  - "_tool_manager.list_tools() is synchronous in mcp 1.27 (not a coroutine); tests use it directly"
  - "ingest tool uses Path.resolve() for T-03-02 mitigation even though lifespan_context.store_path is already resolved"

patterns-established:
  - "FastMCP pattern: AppContext dataclass with typed fields, opened in app_lifespan, yielded to tools via ctx.request_context.lifespan_context"
  - "CLI pattern: all store_path options default to Path('.db-wiki') and are resolved to absolute in each command"
  - "TDD RED-GREEN: write structural tests first (all fail), then implement, confirm all green"

requirements-completed: [MCP-01, MCP-02, CLI-01, CLI-02]

duration: 35min
completed: "2026-04-10"
---

# Phase 1 Plan 3: FastMCP Server and Typer CLI Summary

**FastMCP server with typed lifespan context and ingest/status tools, plus Typer CLI with init/connect/ingest commands — both entry points wired to the SQLite knowledge store**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-04-10T08:02:00Z
- **Completed:** 2026-04-10T08:37:51Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- FastMCP server with `app_lifespan` that opens/closes the SQLite store, typed `AppContext` dataclass for tools to access the store without globals
- `ingest` MCP tool with file existence/type/size validation (T-03-02, T-03-03 mitigations); graceful ImportError fallback until Plan 02 ships ddl_parser
- `status` MCP tool querying `current_db_tables`, `current_db_columns`, `current_db_relationships` views
- Typer CLI `init` creates `.db-wiki/config.yaml` + `knowledge.db` idempotently; `connect` persists connection string; `ingest` validates input and delegates to ddl_parser
- 15 tests (7 server structural + 8 CLI behavioral) all passing via TDD

## Task Commits

Each task was committed atomically:

1. **Task 1: FastMCP server with lifespan and ingest tool** - `ade9b56` (feat)
2. **Task 2: Typer CLI with init, connect, and ingest commands** - `e0960e2` (feat)

_Note: Both tasks used TDD — failing tests committed alongside implementation in same atomic commit_

## Files Created/Modified

- `db_wiki/server/app.py` - FastMCP server with AppContext, app_lifespan, ingest tool, status tool, main()
- `db_wiki/cli/app.py` - Typer CLI with init, connect, ingest commands and main()
- `tests/test_server.py` - 7 structural tests for FastMCP registration and AppContext shape
- `tests/test_cli.py` - 8 behavioral tests using CliRunner for all CLI commands

## Decisions Made

- `ctx.request_context.lifespan_context` verified as correct access path (confirmed from `RequestContext` dataclass source in mcp 1.27 — it has a `lifespan_context: LifespanContextT` field directly)
- `mcp.settings.lifespan` used in test to verify lifespan was passed to FastMCP constructor — cleaner than private attribute introspection
- `_tool_manager.list_tools()` confirmed synchronous (returns a list directly, not a coroutine) — tests use it directly without asyncio
- AppContext field type annotations use concrete types (`Path`, `sqlite3.Connection`) for pyright compatibility (Pitfall 4 from RESEARCH.md)

## Deviations from Plan

None — plan executed exactly as written. The one open question from RESEARCH.md (lifespan context access path) was resolved by reading the mcp source directly before implementation.

## Issues Encountered

None. The lifespan context path `ctx.request_context.lifespan_context` was confirmed correct by inspecting the `RequestContext` dataclass source. No API surprises.

## Known Stubs

- `ingest` MCP tool and CLI `ingest` command both contain `ImportError` guards for `db_wiki.ingest.ddl_parser`. These are intentional — Plan 01-02 delivers that module. When ddl_parser is available, the guards pass through to real parsing. No functionality is blocked for plans that don't call ingest.

## Threat Flags

No new threat surface beyond the plan's threat model. T-03-01 through T-03-04 mitigations applied as specified.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Both entry points (`db-wiki` CLI, `db-wiki-mcp` MCP server) are fully functional for init/connect
- `ingest` in both is wired and validated; will activate when Plan 01-02 ddl_parser is available
- Ready for Plan 01-02 (DDL parser) to complete the ingest pipeline

---
*Phase: 01-foundation*
*Completed: 2026-04-10*
