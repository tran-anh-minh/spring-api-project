---
phase: 05-web-ui-cross-project-polish
plan: "00"
subsystem: testing
tags: [pytest, xfail, tdd, wave-0, nyquist]

requires: []
provides:
  - "27 xfail test stubs covering all Phase 5 requirements (UI-01..UI-06, LEARN-13, CROSS-01, CROSS-02, EXPORT-01, EXPORT-03, CLI-05, MCP-06)"
  - "6 test files: test_web.py, test_daemon.py, test_cross.py, test_export.py, test_cli_phase5.py, test_server_phase5.py"
affects:
  - "05-01 (web UI): must flip test_web.py stubs green"
  - "05-02 (daemon): must flip test_daemon.py stubs green"
  - "05-03 (cross-project): must flip test_cross.py stubs green"
  - "05-04 (export): must flip test_export.py and test_cli_phase5.py stubs green"
  - "05-05 (MCP tools): must flip test_server_phase5.py stubs green"

tech-stack:
  added: []
  patterns:
    - "xfail stubs with strict=True: all Phase 5 tests start as xfail before implementation"
    - "Import-at-test-time: module imports inside test bodies to avoid collection errors on missing modules"

key-files:
  created:
    - tests/test_web.py
    - tests/test_daemon.py
    - tests/test_cross.py
    - tests/test_export.py
    - tests/test_cli_phase5.py
    - tests/test_server_phase5.py
  modified: []

key-decisions:
  - "strict=True on all xfail markers: unexpected passes will surface immediately as errors"
  - "Imports inside test bodies: prevents collection-time ImportError on missing Phase 5 modules"
  - "27 stubs across 6 files: one stub per validation map entry in 05-VALIDATION.md"

patterns-established:
  - "Wave 0 test file naming: test_{subsystem}.py for each Phase 5 plan"
  - "Stub pattern: @pytest.mark.xfail(reason=XFAIL_REASON, strict=True) + import inside body"

requirements-completed:
  - UI-01
  - UI-02
  - UI-03
  - UI-04
  - UI-05
  - UI-06
  - LEARN-13
  - CROSS-01
  - CROSS-02
  - EXPORT-01
  - EXPORT-03
  - MCP-06
  - CLI-05

duration: 10min
completed: 2026-04-11
---

# Phase 05 Plan 00: Wave 0 Test Stubs Summary

**27 xfail test stubs covering all Phase 5 requirements across 6 test files, enabling TDD-first execution for every subsequent wave**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-11T00:00:00Z
- **Completed:** 2026-04-11
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Created 6 test files with 27 xfail stubs covering all 05-VALIDATION.md verification map entries
- All 27 stubs collected by pytest without import errors (imports deferred inside test bodies)
- Strict xfail markers ensure unexpected passes surface immediately as errors

## Task Commits

1. **Task 1: Create test stubs for web UI and daemon** - `3c71bf6` (test)
2. **Task 2: Create test stubs for cross-project, export, CLI, and MCP** - `8d7d1df` (test)

## Files Created/Modified

- `tests/test_web.py` - 8 stubs: UI-01..UI-06 (web app, graph API, search, wiki, dashboard)
- `tests/test_daemon.py` - 4 stubs: LEARN-13 (scheduler start/stop, instance isolation, adaptive frequency)
- `tests/test_cross.py` - 4 stubs: CROSS-01, CROSS-02 (open store, schema, penalty, push patterns)
- `tests/test_export.py` - 4 stubs: EXPORT-03 (markdown, mermaid, json_schema, ddl_annotated exporters)
- `tests/test_cli_phase5.py` - 3 stubs: CLI-05, EXPORT-01 (status, serve, export commands)
- `tests/test_server_phase5.py` - 4 stubs: MCP-06 (lint, history, export, loop tools)

## Decisions Made

- Used `strict=True` on all xfail markers so unexpected passes fail loudly rather than being silently ignored
- Deferred all module imports to inside test bodies so pytest can collect stubs even before implementation modules exist

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 27 stubs are in place; subsequent plans (05-01 through 05-05) can flip stubs green one-by-one
- Wave 0 Nyquist compliance satisfied: every Phase 5 requirement has a failing test before implementation begins

---
*Phase: 05-web-ui-cross-project-polish*
*Completed: 2026-04-11*
