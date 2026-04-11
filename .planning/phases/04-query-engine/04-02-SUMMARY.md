---
phase: 04-query-engine
plan: "02"
subsystem: query-engine
tags: [query-classification, context-assembly, sql-generation, sql-validation, tsql, offline-first]
dependency_graph:
  requires:
    - db_wiki/core/config.py (DBWikiConfig, LearningConfig)
    - db_wiki/learning/agents/base.py (call_llm)
    - db_wiki/core/schema.py (current_db_tables, current_db_columns, current_db_relationships, current_enum_values, current_state_transitions views)
    - db_wiki/core/store.py (init_schema for tests)
  provides:
    - db_wiki/query/classifier.py (classify_query, QueryTier)
    - db_wiki/query/context.py (assemble_context, estimate_tokens, ContextResult)
    - db_wiki/query/generator.py (generate_sql, generate_sql_template, build_generation_prompt, GenerationResult)
    - db_wiki/query/validator.py (validate_sql, build_schema_map)
  affects:
    - Plan 03 (pipeline orchestrator uses all 4 modules as processing steps)
tech_stack:
  added: []
  patterns:
    - "6-tier keyword heuristic classification with more-specific tier tie-breaking"
    - "L0/L1/L2 tiered context assembly with token budget enforcement (8K default)"
    - "Dual-path SQL generation: LLM prompt (online) + template (offline)"
    - "sqlglot qualify() for schema-aware SQL validation before execution"
key_files:
  created:
    - db_wiki/query/__init__.py
    - db_wiki/query/classifier.py
    - db_wiki/query/context.py
    - db_wiki/query/generator.py
    - db_wiki/query/validator.py
    - tests/test_query_classifier.py
    - tests/test_query_context.py
    - tests/test_query_generator.py
    - tests/test_query_validator.py
  modified: []
decisions:
  - "Tie-breaking in keyword classifier: more-specific tiers (DATA_QUALITY) win over generic (LOOKUP) on equal score, using >= comparison with definition-order iteration"
  - "Aggregation template uses default column names (amount/value) since exact columns are unknown without LLM; template returns from_template=True so callers know to treat SQL as approximate"
  - "validate_sql preserves original SQL string (not qualify() output) because qualify() lowercases identifiers, which would corrupt T-SQL bracket-quoted names"
metrics:
  duration_minutes: 20
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_created: 9
  files_modified: 0
  tests_added: 51
---

# Phase 04 Plan 02: Query Pipeline Modules Summary

**One-liner:** 6-tier keyword + LLM classifier, L0/L1/L2 token-budgeted context assembler, dual-path T-SQL generator with retry support, sqlglot qualify()-based SQL validator.

## What Was Built

Four core pipeline modules for the NL-to-SQL query engine:

### 1. Query Tier Classifier (`classifier.py`)

- `QueryTier` enum: LOOKUP, AGGREGATION, TEMPORAL, STATISTICAL, FORENSIC, DATA_QUALITY
- `classify_query(question, config)`: keyword heuristics offline + LLM enhancement when configured
- `TIER_KEYWORDS` dict: keyword lists per tier for fast offline matching
- Tie-breaking: more-specific tiers (defined later in enum) win ties — DATA_QUALITY beats LOOKUP on equal keyword score
- LLM path: calls `call_llm()` with classification prompt, parses tier name from response, falls back to keywords on failure

### 2. Context Assembler (`context.py`)

- `estimate_tokens(text)`: `max(1, int(len(text) / 3.5))` char-based approximation
- `CHARS_PER_TOKEN = 3.5`, `DEFAULT_TOKEN_BUDGET = 8000`
- `ContextResult` dataclass: text, token_count, l0_count, l1_count, l2_count
- `assemble_context(conn, core_ids, related_ids, budget)`:
  - L2 (core): full detail — columns with types/nullability/PK, relationships, enums, state transitions
  - L1 (related): medium — column names+types, FK relationships. Drops tables that exceed budget
  - L0 (all others): one-line summary `{name} ({col_count} cols)`. Truncates at budget
  - 3000 tokens reserved for question + instructions

### 3. SQL Generator (`generator.py`)

- `GenerationResult` dataclass: sql (str|None), prompt_used, from_template
- `SQL_SYSTEM_PROMPT`: T-SQL constraints (TOP N, GETDATE(), bracket quoting)
- `build_generation_prompt()`: assembles system + schema context + optional metrics + question + optional retry error
- `generate_sql()`: LLM path when configured, template fallback
- `generate_sql_template()`: offline templates for LOOKUP (SELECT TOP 100) and AGGREGATION (COUNT/SUM/AVG with GROUP BY). Returns sql=None for tiers 3-6

### 4. SQL Validator (`validator.py`)

- `build_schema_map(conn)`: queries current_db_columns + current_db_tables → `{table: {col: dtype}}`
- `validate_sql(sql, schema_map)`: parse_one() for syntax + qualify() for schema validation
- Returns list of error strings (empty = valid). Preserves original SQL for error messages

## Test Coverage

51 tests total, all passing:
- `test_query_classifier.py`: 13 tests — all 6 tier keywords, LLM path, fallback, enum values
- `test_query_context.py`: 11 tests — token estimation, budget enforcement, L0/L1/L2 content, empty inputs
- `test_query_generator.py`: 17 tests — prompt construction, LLM path, template fallback, retry/metrics
- `test_query_validator.py`: 10 tests — schema map build, valid SQL, unknown columns, syntax errors

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed keyword tie-breaking for DATA_QUALITY vs LOOKUP**
- **Found during:** Task 1 GREEN phase
- **Issue:** `classify_query("find columns with NULL values")` returned LOOKUP because "find" (LOOKUP) and "null" (DATA_QUALITY) both scored 1, and LOOKUP came first in enum definition order with `>` comparison
- **Fix:** Changed to `>=` comparison so later (more-specific) tiers win ties; only updates when score > 0 to preserve LOOKUP default for no-match case
- **Files modified:** db_wiki/query/classifier.py
- **Commit:** cf873f9

**2. [Rule 1 - Bug] Fixed CHARS_PER_TOKEN type annotation to match spec**
- **Found during:** Acceptance criteria verification
- **Issue:** Code had `CHARS_PER_TOKEN: float = 3.5` but spec/acceptance criteria required `CHARS_PER_TOKEN = 3.5`
- **Fix:** Removed type annotation
- **Files modified:** db_wiki/query/context.py
- **Commit:** 6bb380d

## Known Stubs

The `generate_sql_template()` for AGGREGATION uses default column names (`amount` for SUM, `value` for AVG) when the "by {column}" pattern in the question doesn't provide a specific column name. This is an acknowledged limitation of offline template generation — the returned SQL has `from_template=True` so callers know it may need LLM refinement. This is intentional per the plan spec ("these require LLM or Analyst Agent").

## Security Notes

T-04-03: User question in LLM prompt — mitigated by "Generate T-SQL only" instruction and validate_sql() always called before execution (enforced in Plan 03 orchestrator).

T-04-04: SQL validation does NOT check statement type (SELECT vs DML). The executor in Plan 03 must verify statement type is SELECT before executing.

T-04-05: Context assembly reads only from local SQLite knowledge store — no external exposure.

## Self-Check: PASSED

- db_wiki/query/classifier.py: FOUND
- db_wiki/query/context.py: FOUND
- db_wiki/query/generator.py: FOUND
- db_wiki/query/validator.py: FOUND
- tests/test_query_classifier.py: FOUND
- tests/test_query_context.py: FOUND
- tests/test_query_generator.py: FOUND
- tests/test_query_validator.py: FOUND
- 51/51 tests pass
- Commits: cf873f9 (task 1), 191da7f (task 2), 6bb380d (fix)
