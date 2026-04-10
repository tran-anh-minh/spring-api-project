---
phase: 02-sp-parsing-knowledge-graph
fixed_at: 2026-04-10T00:00:00Z
review_path: .planning/phases/02-sp-parsing-knowledge-graph/02-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-10T00:00:00Z
**Source review:** .planning/phases/02-sp-parsing-knowledge-graph/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: SQL Injection via Column Name Interpolation in BFS Module

**Files modified:** `db_wiki/graph/bfs.py`
**Commit:** b94d8c8
**Applied fix:** Added `_VALID_COLUMNS` allowlist and validation check at the top of `_get_neighbors()` that raises `ValueError` if `match_col` or `return_col` are not in `{"source_id", "target_id"}`. Prevents any future caller from passing arbitrary column names into f-string SQL.

### WR-01: Dangling Foreign Key (target_id=0) for Unresolved Relationship Targets

**Files modified:** `db_wiki/ingest/sp_parser.py`
**Commit:** 6f9d4b9
**Applied fix:** Changed `target_id or 0` to `target_id` in the INSERT statement for `db_relationships`. Since `target_id` is already set to `None` when `target_row` is not found, this now correctly inserts `NULL` instead of `0` for unresolved targets.

### WR-02: FTS5 Query Not Sanitized Against Special Syntax

**Files modified:** `db_wiki/search/fts.py`
**Commit:** f585248
**Applied fix:** Added query sanitization in `search_fts()` that escapes internal double quotes and wraps the query as a FTS5 phrase literal. This prevents FTS5 syntax operators (`OR`, `AND`, `NOT`, `NEAR`, `*`, `:`) in user input from causing `sqlite3.OperationalError`.

### WR-03: Connection Resource Leak in CLI Commands

**Files modified:** `db_wiki/cli/app.py`
**Commit:** 6651ea0
**Applied fix:** Wrapped the `search` and `lineage` CLI command bodies in `try/finally` blocks to ensure `conn.close()` is called even when exceptions occur. Removed redundant `conn.close()` calls from early-return branches (now handled by `finally`).

### WR-04: FTS Normalization Inverted (Higher abs(rank) Scored Higher)

**Files modified:** `db_wiki/search/hybrid.py`
**Commit:** c7f8ae6
**Status:** fixed: requires human verification
**Applied fix:** Changed FTS score normalization from `abs(r[3]) / max_abs` to `1.0 - (abs(r[3]) / max_abs)`. This inverts the scale so that less negative FTS5 rank values (better matches) receive higher normalized scores in the fused result. This is a logic fix that should be verified with actual search results.

### WR-05: f-string SQL Table Name Construction in Embedder

**Files modified:** `db_wiki/search/embedder.py`
**Commit:** 21e6314
**Applied fix:** Added validation in the `vec_table_name` property that checks the generated name is a valid Python identifier (via `str.isidentifier()`). Raises `ValueError` if the name contains invalid characters, preventing potential SQL injection if `dimensions` is ever sourced from untrusted input.

## Skipped Issues

None -- all in-scope findings were fixed.

---

_Fixed: 2026-04-10T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
