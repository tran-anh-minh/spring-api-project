---
phase: 04-query-engine
fixed_at: 2026-04-11T12:30:00Z
review_path: .planning/phases/04-query-engine/04-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-04-11T12:30:00Z
**Source review:** .planning/phases/04-query-engine/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: SQL Injection Bypass via CTE/Subquery in Executor SELECT Check

**Files modified:** `db_wiki/query/executor.py`
**Commit:** d862ade
**Applied fix:** Replaced naive `sql.strip().upper().startswith("SELECT")` check with AST-based validation using `sqlglot.parse()`. New `_is_safe_select()` function parses SQL with T-SQL dialect, rejects multi-statement queries (e.g. `SELECT 1; DROP TABLE x`), rejects non-SELECT statements, and handles CTEs/comments correctly.

### WR-01: TOCTOU Race in Cache -- Two datetime.now() Calls

**Files modified:** `db_wiki/query/cache.py`
**Commit:** e4b1f7f
**Applied fix:** Captured `datetime.now(timezone.utc)` once into a local variable, then derived both `now_iso` and `now_ts` from that single timestamp, eliminating the tick-boundary inconsistency.

### WR-02: Dead Code in Pipeline -- find_join_paths Results Ignored

**Files modified:** `db_wiki/query/pipeline.py`
**Commit:** 6acdb33
**Applied fix:** Removed the dead nested loop that called `find_join_paths()` but discarded results (loop body was `pass`). Also removed the now-unused `find_join_paths` import.

### WR-03: Server state_machine Tool Queries Wrong Column Names

**Files modified:** `db_wiki/server/app.py`
**Commit:** 82e8834
**Applied fix:** Changed query column names from `from_state, to_state, via_procedure` to `from_value, to_value, source_procedure_id` to match the actual `current_state_transitions` view schema defined in `db_wiki/core/schema.py`.

### WR-04: L2 Core Tables Always Added Without Budget Check

**Files modified:** `db_wiki/query/context.py`
**Commit:** 1cc2bb7
**Applied fix:** Added budget check (`if used_tokens + block_tokens > schema_budget: break`) before appending L2 blocks, preventing core table context from exceeding the token budget and starving L1/L0 context.

### WR-05: connect Command Writes LLM API Key to Config File

**Files modified:** `db_wiki/cli/app.py`
**Commit:** 3c1bda8
**Applied fix:** Changed `config.model_dump()` to `config.model_dump(exclude={"learning": {"llm_api_key"}})` in the connect command's config write path, preventing accidental persistence of the LLM API key to the YAML config file.

---

_Fixed: 2026-04-11T12:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
