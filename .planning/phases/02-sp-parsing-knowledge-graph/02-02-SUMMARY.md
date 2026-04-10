---
plan: 02-02
phase: 02-sp-parsing-knowledge-graph
status: complete
started: "2026-04-10"
completed: "2026-04-10"
duration: ~14 min
commits: 5
tests_added: 23
tests_total: 144
regressions: 0
---

# Plan 02-02 Summary: SP Parser + Batch Ingest Pipeline

## What Was Built

Complete SP parser module using sqlglot AST analysis with regex fallback, plus batch ingest pipeline wired to the CLI. 15 functions in `sp_parser.py`:

1. **Parsing**: `parse_sp_file()` filters for CREATE PROCEDURE, `parse_sp()` orchestrates extraction, `detect_content_type()` auto-detects SP vs DDL.

2. **Three-pass extraction**: `extract_table_refs()` (AST + regex fallback), `extract_mutations()` (INSERT/UPDATE/DELETE/MERGE), `extract_branches()` (IF/IfBlock/CASE/WHILE + Command fallback), `extract_call_chains()` (EXEC classification + dynamic SQL regex), `extract_enum_detections()` (CASE WHEN patterns), `extract_state_transitions()` (UPDATE SET/WHERE literal matching).

3. **Ingest**: `ingest_sp()` writes to bi-temporal store with body_hash dedup (D-11), `invalidate_procedure()` cascades invalidation across 7 derived tables + relationships.

4. **CLI**: Extended `ingest` command with directory/glob support, `--type` flag, auto-detect, file size limit checking.

## Key Files

### Created
- `db_wiki/ingest/sp_parser.py` — 15 extraction/ingest functions (~920 lines)
- `tests/test_sp_parser.py` — 15 test cases covering all extraction + ingest paths
- `tests/test_cli_ingest.py` — 8 CLI ingest tests (directory, glob, type, size limit)

### Modified
- `db_wiki/ingest/__init__.py` — Module registration
- `db_wiki/cli/app.py` — Extended ingest command with directory/glob/--type

## Commits
1. `e09ea71` — test(02-02): add failing tests for SP parser module
2. `a97c5a5` — feat(02-02): implement SP parser with sqlglot AST analysis and regex fallback
3. `64f45ca` — test(02-02): add CLI ingest tests for SP directory/glob support
4. `8db1e48` — fix(02-02): fix sqlglot T-SQL parsing edge cases and add IfBlock/Command regex fallbacks

## Deviations

- **sqlglot T-SQL IF**: sqlglot uses `exp.IfBlock` (not `exp.If`) for procedural IF in T-SQL. Added support for both node types.
- **Multi-statement bodies**: sqlglot needs semicolons between statements in SP bodies (not BEGIN/END blocks) to parse correctly. Test SQL patterns adjusted accordingly. Regex fallback handles cases where sqlglot falls to Command nodes.
- **Dynamic SQL regex**: Added `DYNAMIC_SQL_RE` and `SP_EXECUTESQL_RE` patterns to detect dynamic SQL in Command fallback nodes where exp.Execute is not produced.

## Test Results

23 new tests, 144 total passing, 0 regressions.

## Self-Check: PASSED
- [x] All tasks executed (2/2)
- [x] Each task committed individually
- [x] SUMMARY.md created
- [x] All tests passing
- [x] No regressions
