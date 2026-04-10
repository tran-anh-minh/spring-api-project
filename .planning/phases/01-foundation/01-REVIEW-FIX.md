---
phase: 01-foundation
fixed_at: 2026-04-10T12:30:00Z
review_path: .planning/phases/01-foundation/01-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-10T12:30:00Z
**Source review:** .planning/phases/01-foundation/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

### WR-01: Timestamp drift between now_iso and now_ts in ingest_ddl

**Files modified:** `db_wiki/ingest/ddl_parser.py`
**Commit:** dce5c8b
**Applied fix:** Replaced two separate `datetime.now(timezone.utc)` calls with a single call stored in `now`, then derived both `now_iso` and `now_ts` from that single value. This ensures bi-temporal timestamps are always consistent.

### WR-02: Index ingested with table_id=0 when parent table not in batch

**Files modified:** `db_wiki/ingest/ddl_parser.py`
**Commit:** bed261d
**Applied fix:** Changed `table_id_map.get(idx.table_name, 0)` to `table_id_map.get(idx.table_name)` with an explicit `None` check. When parent table is not found, the index is skipped with a warning log instead of inserting an orphan record with `table_id=0`.

### WR-03: Connection leak if ingest_ddl raises between first and second commit

**Files modified:** `db_wiki/ingest/ddl_parser.py`
**Commit:** f48840c
**Applied fix:** Removed the intermediate `conn.commit()` after tables/columns insertion. Wrapped the entire insert block (tables, columns, relationships, indexes) in a single `try/except` with `conn.commit()` at the end and `conn.rollback()` on exception. This ensures atomic all-or-nothing ingestion.

### WR-04: MCP server ingest tool returns error strings instead of raising exceptions

**Files modified:** `db_wiki/server/app.py`
**Commit:** 9cba827
**Applied fix:** Replaced `return f"Error: ..."` patterns with `raise ValueError(...)` for validation errors (file not found, not a file, file too large) in the `ingest` tool. Changed the generic `except Exception` handlers in both `ingest` and `status` tools to log and re-raise instead of returning error strings. Added `logger.error()` calls before raises for server diagnostics.

### WR-05: Missing yield and connection close in test fixture

**Files modified:** `tests/conftest.py`
**Commit:** d39d00f
**Applied fix:** Changed `in_memory_db` fixture from `return conn` to `yield conn` followed by `conn.close()`. Removed the `-> sqlite3.Connection` return type annotation since generators have a different type. This ensures the connection is properly closed after each test.

---

_Fixed: 2026-04-10T12:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
