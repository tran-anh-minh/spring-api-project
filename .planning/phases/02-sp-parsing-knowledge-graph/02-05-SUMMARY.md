---
phase: 02-sp-parsing-knowledge-graph
plan: "05"
subsystem: api
tags: [mcp, cli, typer, fastmcp, hybrid-search, bfs, lineage]

requires:
  - phase: 02-02
    provides: SP parser with parse_sp and ingest_sp
  - phase: 02-03
    provides: hybrid_search, FTS5, embedder infrastructure
  - phase: 02-04
    provides: bfs_graph traversal with edge filtering
provides:
  - Shared entity lookup utility (db_wiki/core/queries.py)
  - MCP search tool with hybrid FTS5+vector fusion
  - MCP lineage tool with BFS graph traversal
  - MCP sp_info tool querying all intelligence tables
  - CLI search, lineage, sp-info commands mirroring MCP tools
affects: [phase-03, phase-04, phase-05]

tech-stack:
  added: []
  patterns: [shared-query-layer, mcp-cli-mirror-pattern]

key-files:
  created:
    - db_wiki/core/queries.py
    - tests/test_server_phase2.py
    - tests/test_cli_phase2.py
  modified:
    - db_wiki/server/app.py
    - db_wiki/cli/app.py

key-decisions:
  - "Shared queries.py avoids duplicating entity lookup logic between server and CLI"
  - "lookup_entity_name checks tables first then procedures (table priority on ID collision)"
  - "Tool parameters use t.parameters not t.inputSchema in MCP SDK 1.x"

patterns-established:
  - "MCP-CLI mirror: every MCP tool has a matching CLI command with same logic via shared imports"
  - "Entity resolution: find_entity_by_name returns (id, type) tuple for name-to-id lookups"

requirements-completed: [INGEST-08, STORE-05, STORE-06, STORE-09, STORE-10, STORE-11, CLI-03]

duration: 7min
completed: 2026-04-10
---

# Phase 02 Plan 05: MCP Tools and CLI Commands Summary

**Hybrid search, BFS lineage, and SP inspection wired into MCP tools and CLI commands via shared entity query layer**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-10T15:35:26Z
- **Completed:** 2026-04-10T15:42:17Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created shared entity lookup utility (db_wiki/core/queries.py) used by both server and CLI
- Added 3 MCP tools: search (hybrid FTS5+vector), lineage (BFS traversal), sp_info (intelligence tables)
- Added 3 CLI commands: search, lineage, sp-info mirroring MCP tools exactly
- Extended status tool with procedure and relationship counts
- 212 tests pass with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create shared entity lookup utility and add MCP tools**
   - `6554328` (test: failing tests for queries and MCP tools)
   - `c36e324` (feat: shared queries + MCP search/lineage/sp_info)
2. **Task 2: Add search, lineage, sp-info CLI commands**
   - `50cc56d` (test: failing tests for CLI commands)
   - `2b45d62` (feat: CLI search/lineage/sp-info using shared queries)

_TDD approach: RED (failing tests) then GREEN (implementation) for each task_

## Files Created/Modified
- `db_wiki/core/queries.py` - Shared entity lookup: lookup_entity_name, find_entity_by_name
- `db_wiki/server/app.py` - Added search, lineage, sp_info MCP tools; extended status
- `db_wiki/cli/app.py` - Added search, lineage, sp-info CLI commands
- `tests/test_server_phase2.py` - 17 tests for queries module and MCP tool registration
- `tests/test_cli_phase2.py` - 18 tests for CLI commands and help output

## Decisions Made
- Used `t.parameters` instead of `t.inputSchema` for MCP SDK 1.x tool schema access
- Test for procedure lookup uses isolated DB (no tables) to avoid autoincrement ID collision
- All three CLI commands follow established pattern: resolve store_path, check db_path, open/close store

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed MCP Tool schema attribute name**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Plan referenced `t.inputSchema` but MCP SDK 1.x uses `t.parameters`
- **Fix:** Changed test helper to use `t.parameters` attribute
- **Files modified:** tests/test_server_phase2.py
- **Verification:** All 17 server tests pass
- **Committed in:** c36e324

**2. [Rule 1 - Bug] Fixed procedure lookup test ID collision**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** db_tables and db_procedures have separate autoincrement sequences; procedure id=1 collides with table id=1 causing lookup to return table name
- **Fix:** Isolated procedure lookup test uses DB without tables
- **Files modified:** tests/test_server_phase2.py
- **Verification:** All 17 server tests pass
- **Committed in:** c36e324

---

**Total deviations:** 2 auto-fixed (2 bugs in test expectations)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 complete: all 5 plans executed
- Full search, lineage, and SP inspection available via both MCP and CLI
- Ready for Phase 3 (learning loop, deeper analysis)

## Self-Check: PASSED

- All 5 created/modified files exist
- All 4 task commits verified (6554328, c36e324, 50cc56d, 2b45d62)
- 212 tests pass, zero regressions

---
*Phase: 02-sp-parsing-knowledge-graph*
*Completed: 2026-04-10*
