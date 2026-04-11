---
phase: 04-query-engine
plan: 05
subsystem: cli
tags: [typer, rich, query-engine, cli, mcp-mirror]

requires:
  - phase: 04-03
    provides: QueryPipeline, QueryResult, AnalystAgent for ask command
  - phase: 04-01
    provides: generate_wiki_markdown, get_wiki_page for explain command
  - phase: 04-02
    provides: bfs_graph for impact and forensics commands

provides:
  - "10 Phase 4 CLI commands: ask, explain, define-metric, state-machine, branch-analysis, impact, coverage, data-quality, forensics, compare"
  - "CLI mirrors full MCP tool surface for terminal-only access"
  - "--json flag on all commands, --sql-only flag on ask command"
  - "Rich table output as default with graceful plain-text fallback"

affects: [mcp-server, cli-tests, phase-05]

tech-stack:
  added: []
  patterns:
    - "_open_store_with_query_schema helper: shared store setup with base + query schema init"
    - "Local imports inside commands to avoid circular imports and reduce startup time"
    - "Graceful ImportError fallback for rich output - works without rich installed"
    - "Mock pattern: patch('db_wiki.query.pipeline.QueryPipeline') for testing ask command"

key-files:
  created:
    - tests/test_cli_phase4.py
  modified:
    - db_wiki/cli/app.py

key-decisions:
  - "Single _open_store_with_query_schema helper combines store open + both schema inits to avoid code duplication across 10 commands"
  - "data-quality uses column description coverage as low-confidence proxy - no separate facts table in current schema"
  - "coverage command queries current_wiki_pages to count cached wiki pages per table"
  - "forensics direction filtering applied post-BFS (not via edge_types) to keep bidirectional BFS working correctly"

patterns-established:
  - "CLI command with --json and rich fallback: try/except ImportError around rich imports"
  - "Entity lookup pattern: find_entity_by_name then fail fast with Exit(code=1) if not found"

requirements-completed: [CLI-04]

duration: 25min
completed: 2026-04-11
---

# Phase 4 Plan 05: CLI Query Engine Commands Summary

**10 CLI commands mirroring all Phase 4 MCP tools (ask/explain/define-metric/state-machine/branch-analysis/impact/coverage/data-quality/forensics/compare) with --json, --sql-only, and rich table output**

## Performance

- **Duration:** 25 min
- **Started:** 2026-04-11T06:10:00Z
- **Completed:** 2026-04-11T06:35:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added 10 CLI commands to `db_wiki/cli/app.py` covering the full Phase 4 query engine surface
- Created `tests/test_cli_phase4.py` with 29 tests covering all commands and output modes
- All tests pass (29/29) alongside all existing CLI tests (25/25)
- Integrated `init_query_schema` into both the `init` command and the shared `_open_store_with_query_schema` helper

## Task Commits

Both tasks were committed together (same files modified across both tasks):

1. **Task 1 + Task 2: Phase 4 CLI query and analysis commands** - `30ec5b3` (feat)

## Files Created/Modified

- `db_wiki/cli/app.py` - Added `_open_store_with_query_schema` helper + 10 Phase 4 commands + updated `init` to call `init_query_schema`
- `tests/test_cli_phase4.py` - 29 tests covering all Phase 4 CLI commands across all output modes

## Decisions Made

- Used `_open_store_with_query_schema` helper instead of duplicating store setup in each of 10 commands
- Mock `db_wiki.query.pipeline.QueryPipeline` (not `db_wiki.cli.app.QueryPipeline`) because imports are local
- `data-quality` uses column description coverage as low-confidence proxy — `current_facts` view doesn't exist; `knowledge_gaps.severity` is REAL (0.0-1.0) not text categories
- `forensics` direction filtering done post-BFS so bidirectional BFS still discovers both directions before filtering

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _get_cols closure bug in compare command**
- **Found during:** Task 2 (compare command implementation)
- **Issue:** `_get_cols` inner function captured `type_a` closure variable but was called for both entities — entity B would always use entity A's type for column lookup
- **Fix:** Added `etype` parameter to `_get_cols` and passed `type_a`/`type_b` explicitly
- **Files modified:** db_wiki/cli/app.py
- **Committed in:** 30ec5b3

**2. [Rule 1 - Bug] Fixed data-quality command schema mismatch**
- **Found during:** Task 2 (data-quality implementation)
- **Issue:** Plan specified `severity` as text categories ("high"/"medium"/"low") but actual schema has `severity` as REAL (0.0-1.0); `current_facts` view referenced in plan doesn't exist in schema
- **Fix:** Changed severity queries to use numeric range comparisons; replaced `current_facts` with column description coverage count as low-confidence proxy
- **Files modified:** db_wiki/cli/app.py
- **Committed in:** 30ec5b3

---

**Total deviations:** 2 auto-fixed (2x Rule 1 bugs)
**Impact on plan:** Both fixes required for correctness. No scope creep.

## Issues Encountered

- Sandbox blocked `cd /path && git` and `git -C /path` — resolved via `gsd-tools commit` which handles multi-directory git correctly

## Known Stubs

None — all commands query real schema data. The `data-quality` command uses column description coverage as a low-confidence proxy (documented as a decision above, not a stub).

## Next Phase Readiness

- CLI is complete and mirrors all Phase 4 MCP tools
- All 10 CLI commands are functional and tested
- Phase 4 CLI-04 requirement is complete

---
*Phase: 04-query-engine*
*Completed: 2026-04-11*
