---
phase: 03-learning-loop
reviewed: 2026-04-11T12:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - db_wiki/learning/__init__.py
  - db_wiki/learning/agents/__init__.py
  - db_wiki/learning/agents/base.py
  - db_wiki/learning/agents/collector.py
  - db_wiki/learning/agents/research.py
  - db_wiki/learning/agents/review.py
  - db_wiki/learning/confidence.py
  - db_wiki/learning/confirm.py
  - db_wiki/learning/gap_detector.py
  - db_wiki/learning/gap_scorer.py
  - db_wiki/learning/models.py
  - db_wiki/learning/orchestrator.py
  - db_wiki/learning/pipeline.py
  - db_wiki/learning/schema_ext.py
  - db_wiki/core/config.py
  - db_wiki/core/store.py
  - db_wiki/server/app.py
  - db_wiki/cli/app.py
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-04-11T12:00:00Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

The Phase 3 learning loop implementation is well-structured with clean separation between agents (collector, research, review), the pipeline (4-operation classify/apply), confidence management, gap detection (12 rules), and orchestration. Bi-temporal versioning is consistently applied. The code handles offline/no-LLM mode gracefully with heuristic fallbacks.

Key concerns: one SQL injection vector in `_invalidate_row` via f-string table name interpolation, a conflict resolution logic bug where SUPERSEDE applies the wrong fact in one branch, and several missing error handling paths in the orchestrator and confirm modules.

## Critical Issues

### CR-01: SQL Injection via f-string Table Name in _invalidate_row

**File:** `db_wiki/learning/pipeline.py:336-339`
**Issue:** `_invalidate_row` interpolates `table` (derived from `_table_for_attribute`) directly into an f-string SQL query. While `_table_for_attribute` currently returns only from a hardcoded whitelist of 3 values, this pattern is fragile. If a new attribute type is added with a table name derived from user input, or if `_table_for_attribute` is refactored to accept dynamic input, this becomes a SQL injection vector. The same pattern exists in the `confirm.py` module's `_write_confirmed_fact` which also uses attribute-based branching but constructs SQL safely with literal table names.
**Fix:** Add an assertion or explicit validation that the table name is from the known set, or use a dictionary dispatch to pre-built SQL statements:
```python
def _invalidate_row(
    conn: sqlite3.Connection,
    attribute: str,
    row_id: int,
    now_ts: int,
    now_iso: str,
) -> None:
    """Invalidate a bi-temporal row in the appropriate table."""
    table = _table_for_attribute(attribute)
    if table is None:
        return
    # Defense-in-depth: validate table is from known set
    assert table in ("enum_values", "bitmask_definitions", "column_aliases"), \
        f"Unexpected table name: {table}"
    conn.execute(
        f"UPDATE {table} SET invalidated_at = ?, invalidated_at_ts = ? "
        f"WHERE id = ? AND invalidated_at IS NULL",
        (now_iso, now_ts, row_id),
    )
```

## Warnings

### WR-01: SUPERSEDE Logic Applies Wrong Fact When Existing Wins

**File:** `db_wiki/learning/pipeline.py:162-165`
**Issue:** When `resolve_conflict` returns `SUPERSEDE_B`, the code invalidates the existing fact and writes the **new** finding. But `SUPERSEDE_B` means "Fact A supersedes Fact B" (i.e., Fact A wins). In this context, Fact A is the **existing** fact and Fact B is the **new** finding. So `SUPERSEDE_B` should mean the existing fact wins and the new finding should be discarded -- but the code does the opposite: it replaces the existing fact with the new finding. Similarly, `SUPERSEDE_A` (Fact B wins, meaning the new finding wins) would also trigger replacement since both `SUPERSEDE_B` and `SUPERSEDE_A` hit the same `strategy.startswith("SUPERSEDE")` branch.
**Fix:** Differentiate the two SUPERSEDE strategies:
```python
if strategy == "SUPERSEDE_A":
    # Fact B (new finding) wins over Fact A (existing)
    _invalidate_row(conn, item.attribute, existing["id"], now_ts, now_iso)
    _write_new_fact(conn, item.entity_type, item.entity_name,
                    item.attribute, item.value, item.confidence,
                    item.source, now_ts, now_iso)
elif strategy == "SUPERSEDE_B":
    # Fact A (existing) wins -- discard new finding, no changes needed
    pass
```

### WR-02: Recency Score is Binary, Not Gradual

**File:** `db_wiki/learning/confidence.py:103-111`
**Issue:** The recency component in `resolve_conflict` is binary: 0.1 if a fact is newer, 0.0 otherwise. When both facts have the same timestamp (`fact_a_ts == fact_b_ts`), both get recency = 0.0, which is correct. However, when timestamps differ by even 1 second, the full 0.1 weight is applied. Combined with the SUPERSEDE bug in WR-01, this binary scoring can produce unexpected outcomes.
**Fix:** This is a design choice documented in D-14, but consider adding a comment explaining the intentional binary nature, or use a gradual decay based on time difference.

### WR-03: confirm_fact Calls Undefined Column for human_confirmed

**File:** `db_wiki/learning/confirm.py:48`
**Issue:** `_write_confirmed_fact` writes to `enum_values`, `bitmask_definitions`, or `column_aliases`, but none of these tables have a `human_confirmed` column based on the schema shown in `schema_ext.py` and the test fixtures. The `detection_method` field is set to `'human_confirmed'` as a workaround, but the docstring says "Sets confidence to 1.0 and human_confirmed to True" -- there is no actual `human_confirmed` flag being persisted on the fact row itself. The `human_confirmed` flag only exists on `knowledge_gaps`.
**Fix:** Either add a `human_confirmed` column to the Phase 2 fact tables, or update the docstring to clarify that human confirmation is tracked via `detection_method='human_confirmed'` and `confidence=1.0` as a convention:
```python
def confirm_fact(...) -> str:
    """Confirm an existing fact as human-verified.

    Sets confidence to 1.0 and detection_method to 'human_confirmed'.
    Human-confirmed facts get slower decay rate (0.5%/month) -- the decay
    function checks detection_method, not a separate flag.
    """
```

### WR-04: Missing Input Validation on config.learning.llm_api_key Exposure

**File:** `db_wiki/core/config.py:59`
**Issue:** `LearningConfig.llm_api_key` is stored as a plain string in the Pydantic model. When `write_default_config` serializes the config to YAML via `config.model_dump()`, if a user has set an API key, it will be written in plaintext to `config.yaml`. While this is a config file, the `model_dump()` call does not redact sensitive fields.
**Fix:** Mark `llm_api_key` as a secret field or exclude it from serialization:
```python
from pydantic import SecretStr

class LearningConfig(BaseModel):
    llm_api_key: str | None = None  # Consider using environment variable instead

# In write_default_config, exclude secrets:
config_file.write_text(
    yaml.dump(config.model_dump(exclude={"learning": {"llm_api_key"}}), ...),
)
```

### WR-05: Bare except in orchestrator Error Handler Swallows All Errors

**File:** `db_wiki/learning/orchestrator.py:126-127`
**Issue:** The inner `except Exception: pass` block at line 126-127 silently swallows failures in `bump_attempt_count` during error recovery. If the bump fails (e.g., database corruption), there is no logging and no indication that the gap's attempt count was not incremented, which could cause infinite retry loops.
**Fix:** Add logging to the fallback error handler:
```python
except Exception:
    logger.warning(
        "Failed to bump attempt count for gap %d during error recovery",
        gap.id, exc_info=True,
    )
```

## Info

### IN-01: Unused Parameter entity_type in confirm_fact and teach_fact

**File:** `db_wiki/learning/confirm.py:22,55`
**Issue:** Both `confirm_fact` and `teach_fact` accept an `entity_type` parameter but never use it. The parameter is passed from both CLI and MCP tool handlers.
**Fix:** Either use `entity_type` for validation (e.g., verify it matches the attribute type) or remove it from the function signatures and callers.

### IN-02: Hardcoded bit_position=0 for Bitmask Writes

**File:** `db_wiki/learning/pipeline.py:377` and `db_wiki/learning/confirm.py:113`
**Issue:** Both `_write_new_fact` and `_write_confirmed_fact` hardcode `bit_position=0` when writing bitmask definitions. This means all bitmask labels are written to position 0, making it impossible to distinguish between different bit positions through the learning loop or teach commands.
**Fix:** Consider extracting bit_position from the value string or adding it as an attribute parameter:
```python
# e.g., value format "3:IsAdmin" where 3 is bit_position
```

### IN-03: Wave 0 Test Stubs Still Marked xfail

**File:** `tests/test_conflict_resolution.py`, `tests/test_gap_detection.py`, `tests/test_learning_loop.py`
**Issue:** These Wave 0 test stub files are still marked with `@pytest.mark.xfail` and contain empty test methods that only import modules. The actual implementations now exist and are tested in newer test files (`test_confidence.py`, `test_gap_detector.py`, `test_pipeline.py`, `test_orchestrator.py`). These stubs are dead test code.
**Fix:** Remove the Wave 0 stub files since they are superseded by comprehensive tests:
```
tests/test_conflict_resolution.py  -> superseded by tests/test_confidence.py
tests/test_gap_detection.py        -> superseded by tests/test_gap_detector.py
tests/test_learning_loop.py        -> superseded by tests/test_pipeline.py + test_orchestrator.py
```

---

_Reviewed: 2026-04-11T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
