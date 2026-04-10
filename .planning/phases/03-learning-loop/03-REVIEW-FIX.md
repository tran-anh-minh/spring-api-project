---
phase: 03-learning-loop
fixed_at: 2026-04-11T12:15:00Z
review_path: .planning/phases/03-learning-loop/03-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 5
skipped: 1
status: partial
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-04-11T12:15:00Z
**Source review:** .planning/phases/03-learning-loop/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6
- Fixed: 5
- Skipped: 1

## Fixed Issues

### CR-01: SQL Injection via f-string Table Name in _invalidate_row

**Files modified:** `db_wiki/learning/pipeline.py`
**Commit:** 59126ef
**Applied fix:** Added defense-in-depth assertion validating the table name is from the known whitelist (`enum_values`, `bitmask_definitions`, `column_aliases`) before interpolating into the SQL string.

### WR-01: SUPERSEDE Logic Applies Wrong Fact When Existing Wins

**Files modified:** `db_wiki/learning/pipeline.py`
**Commit:** 59126ef (combined with CR-01 -- same file)
**Applied fix:** Replaced `strategy.startswith("SUPERSEDE")` with explicit `SUPERSEDE_A` and `SUPERSEDE_B` branches. `SUPERSEDE_A` (new finding wins) invalidates existing and writes new. `SUPERSEDE_B` (existing wins) is a no-op pass. This is a logic bug fix -- requires human verification.

### WR-03: confirm_fact Calls Undefined Column for human_confirmed

**Files modified:** `db_wiki/learning/confirm.py`
**Commit:** ddc589f
**Applied fix:** Updated the misleading docstrings in both the module header and `confirm_fact` function to accurately state that human confirmation is tracked via `detection_method='human_confirmed'` convention rather than a separate `human_confirmed` column on fact tables.

### WR-04: Missing Input Validation on config.learning.llm_api_key Exposure

**Files modified:** `db_wiki/core/config.py`
**Commit:** c015018
**Applied fix:** Added `exclude={"learning": {"llm_api_key"}}` to `model_dump()` call in `write_default_config` to prevent API keys from being serialized to plaintext config files.

### WR-05: Bare except in orchestrator Error Handler Swallows All Errors

**Files modified:** `db_wiki/learning/orchestrator.py`
**Commit:** 454832f
**Applied fix:** Replaced bare `pass` in the inner `except Exception` block with `logger.warning()` call including `exc_info=True` to log failures during `bump_attempt_count` error recovery, preventing silent failure and potential infinite retry loops.

## Skipped Issues

### WR-02: Recency Score is Binary, Not Gradual

**File:** `db_wiki/learning/confidence.py:103-111`
**Reason:** The review itself states "This is a design choice documented in D-14". The binary recency scoring (0.1 if newer, 0.0 otherwise) is intentional per the design document. No code change needed -- this is advisory feedback, not a defect.
**Original issue:** The recency component in resolve_conflict is binary (0.1 if newer, 0.0 otherwise) rather than gradual.

---

_Fixed: 2026-04-11T12:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
