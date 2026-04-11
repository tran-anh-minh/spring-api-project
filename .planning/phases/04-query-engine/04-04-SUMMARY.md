---
plan: 04-04
phase: 04-query-engine
status: complete
started: 2026-04-11T12:20:00Z
completed: 2026-04-11T12:35:00Z
---

# Plan 04-04 Summary: MCP Tool Registration

## What was built

All Phase 4 MCP tools registered in `db_wiki/server/app.py`:

**MCP-04 (Core Query Tools):**
- `ask` — NL question → T-SQL with optional live execution
- `explain` — Wiki markdown for any table or procedure
- `define_metric` — Store reusable business metric SQL expressions
- `state_machine` — Mermaid state diagrams from state transitions
- `branch_analysis` — IF/ELSE branch reports for stored procedures

**MCP-05 (Analysis Tools):**
- `impact` — BFS impact analysis showing affected entities
- `coverage` — Knowledge store coverage percentages
- `data_quality` — Open gaps, low-confidence facts report
- `forensics` — Data flow tracing (upstream/downstream)
- `compare` — Side-by-side entity comparison

**D-10 Enhancements:**
- `search` tool enriched with "Related queries" suggestions via resolve_concepts
- `lineage` tool enriched with L0 wiki summaries per node

**AppContext extended** with `pipeline` field, initialized in lifespan with QueryPipeline.

## Key files

### Created
- `tests/test_server_phase4.py` — 41 tests covering all tools

### Modified
- `db_wiki/server/app.py` — Extended with 10 new MCP tools, AppContext.pipeline field, enhanced search/lineage

## Test results

41/41 tests passing. All existing tools remain registered.

## Deviations

All 3 plan tasks (Task 1: AppContext + ask/explain + D-10, Task 2: define_metric/state_machine/branch_analysis, Task 3: impact/coverage/data_quality/forensics/compare) were implemented in a single commit due to inline execution after subagent failure.

## Self-Check: PASSED

- [x] AppContext has pipeline field
- [x] All MCP-04 tools registered (ask, explain, define_metric, state_machine, branch_analysis)
- [x] All MCP-05 tools registered (impact, coverage, data_quality, forensics, compare)
- [x] search enhanced with resolve_concepts (D-10)
- [x] lineage enhanced with wiki L0 annotations (D-10)
- [x] All tools use anyio.to_thread.run_sync for async bridging
- [x] All tests pass
