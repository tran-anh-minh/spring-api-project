---
phase: 04-query-engine
plan: "03"
subsystem: query
tags: [pipeline, cache, executor, analyst-agent, nl-to-sql, orchestration]
dependency_graph:
  requires: ["04-01", "04-02"]
  provides: ["query/pipeline.py", "query/cache.py", "query/executor.py", "query/analyst.py"]
  affects: ["MCP server tools", "CLI ask command"]
tech_stack:
  added: []
  patterns:
    - "QueryPipeline chaining classify→resolve→context→generate→validate→retry with cache"
    - "Self-correcting SQL loop feeding validation errors back into generation prompt"
    - "AnalystAgent decompose/compose pattern for tier 3+ complex queries"
    - "Soft dependency pattern for pyodbc (lazy import with clear error message)"
    - "SELECT-only executor guard with fetchmany row limiting"
key_files:
  created:
    - db_wiki/query/cache.py
    - db_wiki/query/executor.py
    - db_wiki/query/analyst.py
    - db_wiki/query/pipeline.py
    - tests/test_query_cache.py
    - tests/test_query_executor.py
    - tests/test_analyst_agent.py
    - tests/test_query_pipeline.py
  modified:
    - db_wiki/core/config.py
decisions:
  - "AnalystAgent does not extend BaseAgent — it is a query-time agent, not a learning agent; keeping it separate avoids coupling to agent_tasks/agent_results tables"
  - "Pipeline _analyst_pass returns None when decompose returns [original_question] so single-pass falls through cleanly without double-execution"
  - "Cache write only occurs on successful generation (sql is not None and no validation errors)"
  - "executor.py uses lazy pyodbc import inside execute_query to keep pyodbc as optional soft dependency"
metrics:
  duration: "~30 minutes"
  completed: "2026-04-11"
  tasks_completed: 2
  files_created: 8
  files_modified: 1
  tests_added: 50
---

# Phase 4 Plan 03: Query Pipeline Orchestrator + Cache + Executor + Analyst Agent Summary

**One-liner:** QueryPipeline orchestrating full NL-to-SQL flow with SHA-256 schema-versioned cache, SELECT-only live executor via pyodbc soft dependency, and AnalystAgent decompose/compose for tier 3+ queries with verified offline fallback.

## What Was Built

### db_wiki/core/config.py (modified)
Added `QueryConfig` Pydantic model with `token_budget=8000`, `max_retries=3`, `cache_enabled=True`, `max_execution_rows=100`. Added `query: QueryConfig = QueryConfig()` field to `DBWikiConfig`. No existing fields modified.

### db_wiki/query/cache.py (new)
NL-to-SQL cache with SHA-256 question hashing and schema version invalidation:
- `compute_question_hash()` — SHA-256 of normalized (stripped, lowercased) question
- `get_cached_query()` — returns SQL only when question_hash AND schema_version match
- `cache_query()` — INSERT OR REPLACE with ISO timestamp and unix epoch
- `clear_cache()` — deletes all rows, returns rowcount

### db_wiki/query/executor.py (new)
Optional live DB executor (T-04-06, T-04-07 mitigations):
- Rejects any non-SELECT statement before attempting connection
- Requires `config.database.connection_string` to be set
- Soft dependency: `import pyodbc` inside function body with clear install message
- `cursor.fetchmany(max_execution_rows)` enforces row limit
- Converts rows to `list[dict]` via `cursor.description`
- Returns structured `{"success", "rows", "error", "row_count"}` dict

### db_wiki/query/analyst.py (new)
Analyst Agent for Tier 3+ query decomposition (AGENT-03):
- `AnalystAgent.decompose()` — LLM prompt produces numbered sub-questions; parsed by `_parse_numbered_list()`; falls back to `[original_question]` when LLM unavailable/fails
- `AnalystAgent.compose()` — LLM prompt combines sub-query SQLs into single CTE-based T-SQL; falls back to first successful sub-result SQL when LLM unavailable
- Does not extend BaseAgent (query-time agent, not learning agent)

### db_wiki/query/pipeline.py (new)
QueryPipeline orchestrator — single entry point for MCP/CLI:
- `@dataclass QueryResult` — question, tier, sql, validation_errors, attempts, from_cache, context_tokens, execution_result
- `QueryPipeline.__init__()` — builds schema_map once at construction
- `QueryPipeline.run()` — full pipeline: cache check → classify → analyst (tier 3+ with LLM) → single-pass → cache write → execute
- `QueryPipeline._single_pass()` — resolve concepts → core/related IDs → assemble context → generate+validate loop with `max_retries` and error feedback → return QueryResult
- `QueryPipeline._analyst_pass()` — decomposes, runs sub-pass on each, composes, validates composed SQL, falls through to single-pass on failure

## Tests Added (50 total, all passing)

| File | Tests | Coverage |
|------|-------|----------|
| tests/test_query_cache.py | 10 | compute_question_hash, get_cached_query, cache_query, clear_cache |
| tests/test_query_executor.py | 11 | SELECT guard, missing connection, pyodbc not installed, successful rows, row limiting, error handling |
| tests/test_analyst_agent.py | 16 | decompose with/without LLM, compose with/without LLM, numbered list parser, fallback behaviors |
| tests/test_query_pipeline.py | 13 | cache hit/miss, single-pass success, retry loop, max_retries, tier 3+ analyst, offline fallback, execute path, cache write |

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

No new security surface introduced beyond what the threat model documented in the plan (T-04-06 through T-04-09). All mitigations implemented:
- T-04-06: SELECT-only guard in executor.py, fetchmany row limiting, timeout enforced
- T-04-07: execute=False default in pipeline.run(); read-only enforced at executor
- T-04-08: Cache is local SQLite, same trust boundary; no execution without explicit execute=True
- T-04-09: LLM decomposition outputs go through full validate_sql() pipeline

## Self-Check

- [x] db_wiki/query/cache.py — contains compute_question_hash, get_cached_query, cache_query, hashlib.sha256
- [x] db_wiki/query/executor.py — contains execute_query, SELECT check, import pyodbc, fetchmany
- [x] db_wiki/query/analyst.py — contains class AnalystAgent, def decompose, def compose, call_llm
- [x] db_wiki/query/pipeline.py — contains class QueryPipeline, @dataclass QueryResult, def run, def _single_pass, resolve_concepts, classify_query, assemble_context, generate_sql, validate_sql, execute_query, retry loop
- [x] db_wiki/core/config.py — contains class QueryConfig(BaseModel), token_budget: int = 8000, max_retries: int = 3, query: QueryConfig = QueryConfig()
- [x] 50 tests passing (pytest exit 0)
- [x] tests/test_analyst_agent.py contains test for no-LLM fallback returning [original_question]
- [x] tests/test_query_pipeline.py contains test for AnalystAgent offline fallback behavior
