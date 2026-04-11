---
phase: 04-query-engine
verified: 2026-04-11T13:00:00Z
status: human_needed
score: 5/5
overrides_applied: 0
human_verification:
  - test: "Ask 'show me all orders for a customer' via MCP or CLI against a real ingested schema"
    expected: "Returns valid T-SQL with correct table joins and alias mappings"
    why_human: "End-to-end NL-to-SQL quality requires real schema data and human judgment on SQL correctness"
  - test: "Define metric 'revenue' as SUM(order_total) then ask a question referencing revenue"
    expected: "Subsequent query resolves the metric and includes SUM(order_total) in generated SQL"
    why_human: "Metric resolution in query generation requires real pipeline execution with LLM or template"
  - test: "Run db-wiki ask 'show orders' --execute against a live SQL Server"
    expected: "SQL executes and returns result rows inline"
    why_human: "Live DB execution requires actual database connection"
---

# Phase 4: Query Engine Verification Report

**Phase Goal:** Users can ask natural language questions and receive accurate, validated SQL with full schema context
**Verified:** 2026-04-11T13:00:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can ask "show me all orders for a customer" and receive valid T-SQL with correct table joins and alias mappings | VERIFIED | QueryPipeline.run() chains classify->resolve->join_paths->context->generate->validate. pipeline.py:83 `def run()`, resolver.py:157 `find_join_paths()` with edge_types fk_declared/fk_inferred/joins_with. MCP `ask` tool at server/app.py:460, CLI `ask` at cli/app.py:592. 13 pipeline tests + 41 server tests + 29 CLI tests pass. |
| 2 | User can define a business metric (e.g., "revenue") and subsequent queries resolve it to the correct SQL expression | VERIFIED | resolver.py:276 `define_metric()` with sqlglot validation. generator.py:73 includes "Defined Metrics" section in LLM prompt. pipeline.py:287 passes metrics to generate_sql. MCP `define_metric` at server/app.py:555, CLI `define-metric` at cli/app.py:712. Tests verify metric CRUD and prompt inclusion. |
| 3 | Generated SQL is validated against the knowledge store -- references to non-existent tables/columns are caught and rewritten | VERIFIED | validator.py:55 `validate_sql()` uses sqlglot.parse_one() + optimizer.qualify.qualify() at line 95 with dialect="tsql". pipeline.py:284-306 retry loop feeds validation errors back into generate_sql via previous_error parameter. max_retries=3 from config. 10 validator tests + pipeline retry tests pass. |
| 4 | Context assembly stays under 8K tokens for schemas with 100+ tables using L0/L1/L2 tiered loading | VERIFIED | context.py:21 CHARS_PER_TOKEN=3.5, context.py:56 `assemble_context()` with L2 for core, L1 for related (drops lowest-scored when budget exceeded), L0 for all others. DEFAULT_TOKEN_BUDGET=8000. 11 context tests including budget enforcement pass. |
| 5 | User can execute the generated SQL against a live database and receive results inline | VERIFIED | executor.py:23 `execute_query()` with SELECT-only guard (line 38), lazy pyodbc import (line 58), fetchmany row limiting (line 77). pipeline.py:157 calls execute_query when execute=True. MCP ask tool accepts execute=True, CLI ask accepts --execute flag. 11 executor tests pass. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db_wiki/core/query_schema.py` | DDL for wiki_pages, derived_metrics, query_cache + views | VERIFIED | 110 lines. 3 CREATE TABLE + 2 CREATE VIEW statements confirmed. |
| `db_wiki/query/resolver.py` | Concept resolution, JOIN paths, metric CRUD | VERIFIED | 397 lines. 15 functions/classes. resolve_concepts, find_join_paths, define_metric, get_metric, get_schema_version all present. |
| `db_wiki/query/wiki.py` | Wiki page generation L0/L1/L2 | VERIFIED | 462 lines. 22 functions. generate_wiki_l0/l1/l2, get_wiki_page, invalidate_wiki_cache, generate_wiki_markdown all present. |
| `db_wiki/query/classifier.py` | 6-tier query classification | VERIFIED | 154 lines. QueryTier enum + classify_query with call_llm integration. |
| `db_wiki/query/context.py` | L0/L1/L2 context assembly | VERIFIED | 315 lines. assemble_context with token budgeting, queries current_db_* views. |
| `db_wiki/query/generator.py` | SQL generation LLM + template | VERIFIED | 240 lines. generate_sql, generate_sql_template, build_generation_prompt with retry support. |
| `db_wiki/query/validator.py` | SQL validation via sqlglot qualify | VERIFIED | 104 lines. build_schema_map + validate_sql with optimizer.qualify.qualify(). |
| `db_wiki/query/pipeline.py` | QueryPipeline orchestrator | VERIFIED | 325 lines. QueryPipeline.run() chains all steps. _single_pass with retry loop. |
| `db_wiki/query/cache.py` | NL-to-SQL cache | VERIFIED | 101 lines. SHA-256 hashing, schema version invalidation. |
| `db_wiki/query/executor.py` | Live DB executor | VERIFIED | 99 lines. SELECT-only guard, lazy pyodbc, fetchmany limiting. |
| `db_wiki/query/analyst.py` | Analyst Agent for tier 3+ | VERIFIED | 193 lines. AnalystAgent with decompose/compose, LLM fallback. |
| `db_wiki/server/app.py` | All MCP tools registered | VERIFIED | 990 lines. 10 async MCP tools confirmed: ask, explain, define_metric, state_machine, branch_analysis, impact, coverage, data_quality, forensics, compare. |
| `db_wiki/cli/app.py` | All CLI commands | VERIFIED | 1230 lines. 10 CLI commands with --json flags, --sql-only on ask. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| pipeline.py | resolver.py | resolve_concepts(), find_join_paths() | WIRED | Imported line 32, called at lines 230, 244 |
| pipeline.py | classifier.py | classify_query() | WIRED | Imported line 24, called at line 124 |
| pipeline.py | context.py | assemble_context() | WIRED | Imported line 25, called at line 260 |
| pipeline.py | generator.py | generate_sql() | WIRED | Imported line 27, called at line 287 |
| pipeline.py | validator.py | validate_sql() | WIRED | Imported line 34, called at line 306 |
| pipeline.py | cache.py | get_cached_query(), cache_query() | WIRED | Imported lines 20-22, called at lines 110, 144 |
| resolver.py | hybrid_search | hybrid_search() call | WIRED | Imports from db_wiki.search.hybrid |
| resolver.py | bfs_graph | bfs_graph() call | WIRED | Imports from db_wiki.graph.bfs |
| server/app.py | pipeline.py | QueryPipeline in lifespan | WIRED | Line 55-58: imports and creates QueryPipeline in lifespan |
| server/app.py | wiki.py | generate_wiki_markdown | WIRED | Line 531: imported, line 546: called |
| cli/app.py | pipeline.py | QueryPipeline for ask | WIRED | Line 612: local import, line 617: created |
| cli/app.py | wiki.py | generate_wiki_markdown | WIRED | Line 689: local import, line 700: called |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 4 tests pass | uv run pytest (12 test files) | 216 passed in 5.91s | PASS |
| No TODO/placeholder markers | grep TODO/FIXME/PLACEHOLDER | Zero matches | PASS |
| QueryPipeline module exports | python -c import check | All imports resolve | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| QUERY-01 | 04-01 | Concept resolution via hybrid search | SATISFIED | resolver.py resolve_concepts() calls hybrid_search |
| QUERY-02 | 04-01 | Derived metric resolution | SATISFIED | resolver.py define_metric/get_metric with sqlglot validation |
| QUERY-03 | 04-01 | JOIN path finding via BFS | SATISFIED | resolver.py find_join_paths() with edge_types filter |
| QUERY-04 | 04-02 | 6-tier query generation | SATISFIED | classifier.py QueryTier with 6 values |
| QUERY-05 | 04-02 | L0/L1/L2 context under 8K tokens | SATISFIED | context.py assemble_context with budget enforcement |
| QUERY-06 | 04-02 | SQL generation with schema context | SATISFIED | generator.py with enums/aliases in context |
| QUERY-07 | 04-02 | SQL validation via sqlglot | SATISFIED | validator.py validate_sql with qualify() |
| QUERY-08 | 04-02, 04-03 | Self-correcting query loop | SATISFIED | pipeline.py retry loop with error feedback |
| QUERY-09 | 04-03 | Optional query execution | SATISFIED | executor.py execute_query with SELECT guard |
| STORE-07 | 04-01 | Wiki pages L0/L1/L2 | SATISFIED | wiki.py generate_wiki_l0/l1/l2 + cache |
| MCP-04 | 04-04 | Ask skills: ask, explain, search, lineage, state_machine, branch_analysis | SATISFIED | server/app.py all tools registered + search/lineage enhanced |
| MCP-05 | 04-04 | Analyze skills: forensics, impact, coverage, data_quality, compare | SATISFIED | server/app.py 5 analysis tools registered |
| CLI-04 | 04-05 | Query/discover/analyze CLI commands | SATISFIED | cli/app.py 10 commands with --json |
| AGENT-03 | 04-03 | Analyst Agent for tier 3+ | SATISFIED | analyst.py AnalystAgent with decompose/compose + 16 tests |
| EXPORT-02 | 04-01 | Wiki generation L0/L1/L2 markdown | SATISFIED | wiki.py generate_wiki_markdown |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none found) | - | - | - | - |

No TODO, FIXME, placeholder, or stub patterns detected in any Phase 4 source files.

### Human Verification Required

### 1. End-to-End NL-to-SQL Quality

**Test:** Ingest a real schema (e.g., AdventureWorks), then ask "show me all orders for a customer" via `db-wiki ask` or MCP `ask` tool.
**Expected:** Returns valid T-SQL with correct JOIN between Orders and Customers tables, proper alias resolution.
**Why human:** Automated tests use mocks. Real NL-to-SQL quality requires actual schema data and human judgment on whether the generated SQL is semantically correct.

### 2. Metric Resolution in Queries

**Test:** Run `db-wiki define-metric revenue "SUM(order_total)" --tables Orders`, then ask "what is the revenue by customer?"
**Expected:** Generated SQL includes SUM(order_total) resolved from the defined metric.
**Why human:** Requires real pipeline execution with LLM or template to verify metric integration in generated SQL.

### 3. Live DB Execution

**Test:** With a connected SQL Server, run `db-wiki ask "show all orders" --execute`
**Expected:** SQL executes successfully and returns result rows displayed in rich table format.
**Why human:** Requires actual database connection and pyodbc driver installation.

### Gaps Summary

No automated verification gaps found. All 5 roadmap success criteria are verified at the code level: artifacts exist, are substantive (4720 lines across 13 files), are fully wired (all key links confirmed), and tests pass (216/216). Three items require human testing to confirm end-to-end behavior with real data.

---

_Verified: 2026-04-11T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
