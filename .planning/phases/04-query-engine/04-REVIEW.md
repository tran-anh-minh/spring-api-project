---
phase: 04-query-engine
reviewed: 2026-04-11T12:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - db_wiki/server/app.py
  - db_wiki/cli/app.py
  - db_wiki/core/config.py
  - db_wiki/core/query_schema.py
  - db_wiki/query/__init__.py
  - db_wiki/query/analyst.py
  - db_wiki/query/cache.py
  - db_wiki/query/executor.py
  - db_wiki/query/pipeline.py
  - db_wiki/query/resolver.py
  - db_wiki/query/wiki.py
  - db_wiki/query/classifier.py
  - db_wiki/query/context.py
  - db_wiki/query/generator.py
  - db_wiki/query/validator.py
  - tests/test_server_phase4.py
  - tests/test_cli_phase4.py
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-04-11T12:00:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 4 introduces the NL-to-SQL query engine pipeline with classifier, resolver, context assembler, generator, validator, executor, cache, wiki page generator, and analyst agent. The MCP server and CLI app are extended with 10 new tools/commands. Overall code quality is solid with good security discipline (SELECT-only enforcement, SQL fragment validation, BFS depth caps). Key concerns: a SQL injection bypass in the executor's SELECT-only check, a TOCTOU race in the cache module, and several dead code paths in the pipeline.

## Critical Issues

### CR-01: SQL Injection Bypass via CTE/Subquery in Executor SELECT Check

**File:** `db_wiki/query/executor.py:38`
**Issue:** The SELECT-only safety check uses `sql.strip().upper().startswith("SELECT")` which can be bypassed by valid T-SQL that starts with `WITH` (CTE), or by prepending a comment like `/* */ DELETE ...` after a SELECT. More critically, a query like `SELECT 1; DROP TABLE Orders` would pass the check since it starts with SELECT but contains a destructive second statement after the semicolon.
**Fix:** Parse the SQL with sqlglot and verify the AST node type is a Select, and that only one statement is present:
```python
import sqlglot
from sqlglot.errors import ParseError

def _is_safe_select(sql: str) -> bool:
    try:
        statements = sqlglot.parse(sql, dialect="tsql")
    except ParseError:
        return False
    if len(statements) != 1:
        return False  # reject multi-statement
    return statements[0] is not None and isinstance(
        statements[0], sqlglot.exp.Select
    )
```

## Warnings

### WR-01: TOCTOU Race in Cache — Two datetime.now() Calls

**File:** `db_wiki/query/cache.py:79-80`
**Issue:** `cache_query()` calls `datetime.now(timezone.utc)` twice on consecutive lines to get ISO and timestamp values. These could differ by up to a second across a tick boundary, causing `created_at` and `created_at_ts` to be inconsistent.
**Fix:** Capture once and derive both:
```python
now = datetime.now(timezone.utc)
now_iso = now.isoformat()
now_ts = int(now.timestamp())
```

### WR-02: Dead Code in Pipeline — find_join_paths Results Ignored

**File:** `db_wiki/query/pipeline.py:244-252`
**Issue:** The `_single_pass` method calls `find_join_paths()` in a nested loop but the returned `steps` are never used. The inner loop body is just `pass`. This means JOIN path discovery is executed (potentially expensive BFS queries) but contributes nothing to context assembly. The `related_ids` list is populated from non-table entities instead.
**Fix:** Either remove the dead join-path loop entirely, or extract intermediate table IDs from the steps and add them to `related_ids`:
```python
for step in steps:
    # Look up intermediate table IDs and add to related_ids
    mid_id = _lookup_table_id(conn, step.to_table)
    if mid_id and mid_id not in core_ids:
        related_ids.append(mid_id)
```

### WR-03: Server state_machine Tool Queries Wrong Column Names

**File:** `db_wiki/server/app.py:598-599`
**Issue:** The `state_machine` MCP tool queries `from_state, to_state, via_procedure` columns from `current_state_transitions`, but the schema (as used in CLI and wiki.py) uses `from_value, to_value` column names. The `state_transitions` table was created with `from_value`/`to_value` columns (see `cli/app.py:761` and `wiki.py:104-108`). This will cause an `OperationalError` at runtime if the actual schema uses `from_value`/`to_value`.
**Fix:** Update the query to use consistent column names:
```python
transitions = app.conn.execute(
    "SELECT from_value, to_value, source_procedure_id "
    "FROM current_state_transitions "
    "WHERE table_name = ? AND column_name = ?",
    (table_name, column_name),
).fetchall()
```

### WR-04: L2 Core Tables Always Added Without Budget Check

**File:** `db_wiki/query/context.py:89-96`
**Issue:** In `assemble_context()`, L2 blocks for core tables are always added without checking against `schema_budget`. If core tables are large (many columns, enums, transitions), L2 alone could exceed the budget, leaving no room for L1/L0 context. Only L1 blocks are budget-checked.
**Fix:** Add budget checking for L2 blocks, or at minimum cap the number of core tables and track against `schema_budget`:
```python
for table_id in core_entity_ids:
    block = _build_l2_block(conn, table_id)
    if not block:
        continue
    block_tokens = estimate_tokens(block)
    if used_tokens + block_tokens > schema_budget:
        break  # stop adding L2 blocks when budget exhausted
    l2_blocks.append(block)
    used_tokens += block_tokens
```

### WR-05: connect Command Writes LLM API Key to Config File

**File:** `db_wiki/cli/app.py:109-112`
**Issue:** The `connect` command does `config.model_dump()` which includes all fields, and then writes via `yaml.dump`. Unlike `write_default_config()` (which excludes `llm_api_key` at line 130 of config.py), this path writes the full config including `learning.llm_api_key` if it was loaded from the existing config. This could persist a secret in plaintext that was only meant to be in memory.
**Fix:** Exclude the API key when writing:
```python
yaml.dump(
    config.model_dump(exclude={"learning": {"llm_api_key"}}),
    f, default_flow_style=False
)
```

## Info

### IN-01: Duplicate json Import in CLI explain Command

**File:** `db_wiki/cli/app.py:686,705`
**Issue:** `import json as json_mod` appears at line 686 (top of function) and again at line 705 (inside the `if json_output:` block). The second import is redundant.
**Fix:** Remove the duplicate import at line 705.

### IN-02: Broad Exception Catch in define_metric MCP Tool

**File:** `db_wiki/server/app.py:582`
**Issue:** The except clause `except (ValueError, Exception) as e` is redundant since `Exception` is a superclass of `ValueError`. This catches all exceptions and returns them as user-facing error messages, which could leak internal details (stack traces, file paths).
**Fix:** Catch `ValueError` specifically for user-facing errors, and let other exceptions propagate:
```python
try:
    metric_id = await anyio.to_thread.run_sync(_do)
    return f"Metric '{name}' defined successfully (id={metric_id})."
except ValueError as e:
    return f"Error defining metric: {e}"
```

### IN-03: Unused Import in Executor

**File:** `db_wiki/query/executor.py:58`
**Issue:** The `noqa: F401` comment on the first `import pyodbc` indicates it is only imported for existence checking. The module is then re-imported at line 71 as `_pyodbc`. The first import is solely a probe, which is fine but could be simplified.
**Fix:** Combine into a single import block:
```python
try:
    import pyodbc
except ImportError:
    return {...}
# Use pyodbc directly below
conn = pyodbc.connect(connection_string, timeout=timeout_seconds)
```

---

_Reviewed: 2026-04-11T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
