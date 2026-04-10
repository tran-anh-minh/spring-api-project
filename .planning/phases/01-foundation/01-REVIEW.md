---
phase: 01-foundation
reviewed: 2026-04-10T12:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - db_wiki/__init__.py
  - db_wiki/cli/__init__.py
  - db_wiki/cli/app.py
  - db_wiki/core/__init__.py
  - db_wiki/core/config.py
  - db_wiki/core/models.py
  - db_wiki/core/schema.py
  - db_wiki/core/store.py
  - db_wiki/ingest/__init__.py
  - db_wiki/ingest/ddl_parser.py
  - db_wiki/server/__init__.py
  - db_wiki/server/app.py
  - tests/conftest.py
  - tests/test_cli.py
  - tests/test_config.py
  - tests/test_ddl_parser.py
  - tests/test_server.py
  - tests/test_store.py
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-04-10T12:00:00Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 01 delivers a solid foundation: bi-temporal SQLite schema, YAML config with Pydantic validation, DDL parser using sqlglot, FastMCP server skeleton, and Typer CLI. Security posture is good -- `yaml.safe_load` is used consistently, all SQL INSERTs use parameterized queries, and paths are resolved before file operations.

Key concerns are: a timestamp drift bug in `ingest_ddl` where `now_iso` and `now_ts` can diverge, an invalid foreign key reference (table_id=0) for orphan indexes, a resource leak if `ingest_ddl` raises between commits, and unquoted table names in PRAGMA calls in test helpers. No critical/security issues were found.

## Warnings

### WR-01: Timestamp drift between now_iso and now_ts in ingest_ddl

**File:** `db_wiki/ingest/ddl_parser.py:383-384`
**Issue:** Two separate `datetime.now(timezone.utc)` calls produce `now_iso` and `now_ts`. If the calls straddle a second boundary, the ISO string and Unix timestamp will refer to different seconds. This creates inconsistent bi-temporal records where `valid_from` and `valid_from_ts` do not agree.
**Fix:**
```python
now = datetime.now(timezone.utc)
now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
now_ts = int(now.timestamp())
```

### WR-02: Index ingested with table_id=0 when parent table not in batch

**File:** `db_wiki/ingest/ddl_parser.py:484`
**Issue:** When an index references a table not in the current parse batch, `table_id_map.get(idx.table_name, 0)` defaults to `0`. This inserts a row with `table_id=0` which does not reference any valid `db_tables` row, violating referential integrity (the FK constraint `db_indexes.table_id REFERENCES db_tables(id)` is declared in schema). With `PRAGMA foreign_keys=ON`, this will cause a runtime error. Without it, it creates an orphan record.
**Fix:**
```python
parent_table_id = table_id_map.get(idx.table_name)
if parent_table_id is None:
    logger.warning(
        "Skipping index %s: table %s not found in current batch",
        idx.index_name,
        idx.table_name,
    )
    continue
```

### WR-03: Connection leak if ingest_ddl raises between first and second commit

**File:** `db_wiki/ingest/ddl_parser.py:444-506`
**Issue:** `ingest_ddl` calls `conn.commit()` at line 444 (after tables/columns) and again at line 506 (after relationships/indexes). If an exception occurs between the two commits, the first batch is committed but the caller in `cli/app.py` (line 163-168) closes the connection in a `finally` block without rolling back. This leaves the store in a partial state with tables/columns inserted but no relationships/indexes -- a consistency gap.
**Fix:** Wrap the entire function body in a single transaction so it either fully commits or fully rolls back:
```python
try:
    # ... all inserts ...
    conn.commit()
except Exception:
    conn.rollback()
    raise
```
Or remove the intermediate commit at line 444 and keep only the final one at line 506.

### WR-04: MCP server ingest tool returns error strings instead of raising exceptions

**File:** `db_wiki/server/app.py:72-74`
**Issue:** The `ingest` MCP tool returns error messages as plain strings (e.g., `"Error: File not found: {file_path}"`) rather than raising exceptions or returning structured error responses. MCP clients (Claude Code) may not distinguish these from successful results, potentially treating error messages as valid ingest summaries. The `status` tool (line 128-129) has the same pattern.
**Fix:** Consider raising an `McpError` or returning a structured response that MCP clients can programmatically detect as an error. At minimum, log the errors so they appear in server diagnostics:
```python
if not path.exists():
    logger.error("File not found: %s", file_path)
    raise ValueError(f"File not found: {file_path}")
```

### WR-05: Missing WAL journal_mode pragma in test fixture

**File:** `tests/conftest.py:16-20`
**Issue:** The `in_memory_db` fixture enables `foreign_keys` but does not set `journal_mode=WAL`, diverging from production behavior in `open_store`. While WAL is not meaningful for `:memory:` databases, the `in_memory_db` fixture is also missing `PRAGMA` consistency with production. More importantly, this fixture does not close the connection -- it relies on garbage collection. For test reliability across platforms, consider yielding and closing.
**Fix:**
```python
@pytest.fixture
def in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
```

## Info

### IN-01: Unquoted table name in PRAGMA table_info call

**File:** `tests/test_store.py:29`
**Issue:** `f"PRAGMA table_info({table})"` uses f-string interpolation for the table name. While this is a test helper and `table` values come from a hardcoded constant (`ENTITY_TABLES`), the pattern is worth noting as it would be injection-vulnerable if the source of `table` changed.
**Fix:** No change needed for current usage since input is hardcoded. If the helper is reused with dynamic input in the future, use parameterized quoting.

### IN-02: Connection string stored in plaintext YAML

**File:** `db_wiki/cli/app.py:97-98`
**Issue:** The `connect` command writes the database connection string directly to `config.yaml` via `yaml.dump`. If the connection string contains credentials (e.g., `UID=sa;PWD=secret`), they will be stored in plaintext on disk. This is acceptable for local-first tooling but worth documenting as a known limitation.
**Fix:** Document in user-facing help text that connection strings with credentials are stored in plaintext. Consider a future enhancement for credential store integration.

### IN-03: Unused import pytest in test_server.py

**File:** `tests/test_server.py:8`
**Issue:** `pytest` is imported but not used directly in any test function (no `pytest.raises`, `pytest.mark`, etc.).
**Fix:** Remove the unused import:
```python
# Remove: import pytest
```

---

_Reviewed: 2026-04-10T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
