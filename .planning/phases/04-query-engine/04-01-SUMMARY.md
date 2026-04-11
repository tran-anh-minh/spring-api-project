---
phase: 04-query-engine
plan: 01
subsystem: query-engine
tags: [query, schema, resolver, wiki, cache, bfs, hybrid-search, derived-metrics]
dependency_graph:
  requires:
    - db_wiki/search/hybrid.py (hybrid_search)
    - db_wiki/graph/bfs.py (bfs_graph)
    - db_wiki/core/schema.py (base schema)
    - db_wiki/core/store.py (open_store, init_schema)
  provides:
    - db_wiki/core/query_schema.py (wiki_pages, derived_metrics, query_cache DDL)
    - db_wiki/query/resolver.py (resolve_concepts, find_join_paths, define_metric, get_metric, get_schema_version)
    - db_wiki/query/wiki.py (get_wiki_page, generate_wiki_l0/l1/l2, generate_wiki_markdown, invalidate_wiki_cache)
  affects:
    - Phase 4 plans 02-05 (query pipeline, MCP/CLI tools depend on these modules)
tech_stack:
  added: []
  patterns:
    - Bi-temporal table pattern (valid_from/until + recorded_at/invalidated_at) for wiki_pages and derived_metrics
    - schema_version-based cache invalidation (MAX recorded_at_ts across key tables)
    - SQL fragment safety validation via sqlglot.parse_one + keyword blocklist (T-04-01)
    - TDD red-green cycle for both tasks
key_files:
  created:
    - db_wiki/core/query_schema.py
    - db_wiki/query/__init__.py
    - db_wiki/query/resolver.py
    - db_wiki/query/wiki.py
    - tests/test_query_resolver.py
    - tests/test_query_wiki.py
  modified: []
decisions:
  - "SQL fragment validation wraps fragment in SELECT before sqlglot.parse_one to handle expression-only inputs (not full statements)"
  - "get_schema_version uses MAX(recorded_at_ts) across 3 tables (db_tables, db_columns, db_relationships) to detect any schema change"
  - "wiki cache uses unique partial index on (entity_type, entity_id, tier) WHERE valid_until IS NULL AND invalidated_at IS NULL to enforce one active cache entry per entity+tier"
  - "find_join_paths reconstructs path from BFS result node path field (list of IDs) rather than re-querying edges"
metrics:
  duration: ~15 minutes
  completed: 2026-04-11
  tasks_completed: 2
  files_created: 6
  tests_added: 45
---

# Phase 04 Plan 01: Query Engine Foundation Summary

**One-liner:** Schema extension (3 tables + 2 views) + hybrid-search concept resolver + BFS JOIN path finder + derived metric CRUD with sqlglot safety validation + L0/L1/L2 wiki generator with schema_version cache invalidation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Schema extension + concept resolver module | b14c65b | db_wiki/core/query_schema.py, db_wiki/query/__init__.py, db_wiki/query/resolver.py, tests/test_query_resolver.py |
| 2 | On-demand wiki page generator with cache | 164af94 | db_wiki/query/wiki.py, tests/test_query_wiki.py |

## What Was Built

### Task 1: Schema Extension + Concept Resolver

**db_wiki/core/query_schema.py** — DDL for 3 new tables and 2 views:
- `wiki_pages`: bi-temporal cache of L0/L1/L2 wiki content per entity. Unique partial index on `(entity_type, entity_id, tier) WHERE valid_until IS NULL AND invalidated_at IS NULL`.
- `derived_metrics`: bi-temporal user-defined metric definitions (name → SQL expression). Same unique partial index on `metric_name`.
- `query_cache`: pure cache (not bi-temporal) for NL→SQL query results keyed by `question_hash`.
- `current_wiki_pages` and `current_derived_metrics` views: filter by `valid_until IS NULL AND invalidated_at IS NULL`.

**db_wiki/query/resolver.py** — Core resolution primitives:
- `ResolvedEntity`, `JoinStep`, `MetricDefinition` dataclasses.
- `resolve_concepts(conn, query, embedding_config)` — calls `hybrid_search()`, fetches entity names from `current_db_*` views, returns sorted list of `ResolvedEntity`.
- `find_join_paths(conn, start_id, end_id, max_depth=4)` — calls `bfs_graph()` with `edge_types=["fk_declared","fk_inferred","joins_with"]`, reconstructs path to target, looks up column names from `current_db_relationships`, returns `list[JoinStep]`.
- `define_metric(conn, name, sql_fragment, ...)` — validates sql_fragment (rejects `;`, `DROP`, `INSERT`, `DELETE`, `EXEC`, `UPDATE`, etc. via word-boundary regex + `sqlglot.parse_one()`), inserts into `derived_metrics` with bi-temporal timestamps.
- `get_metric()`, `get_all_metrics()` — SELECT from `current_derived_metrics`.
- `get_schema_version(conn)` — `MAX(recorded_at_ts)` across `db_tables`, `db_columns`, `db_relationships`.

### Task 2: Wiki Page Generator

**db_wiki/query/wiki.py** — On-demand wiki generation with caching:
- `generate_wiki_l0(conn, entity_type, entity_id)` — one-line summary: `"{name} - {col_count} columns, {rel_count} relationships"` for tables; `"{name} - touches {n} tables"` for procedures.
- `generate_wiki_l1(conn, entity_type, entity_id)` — L0 + column list (name/type/nullable/PK) + relationship list for tables; L0 + table refs + branch count + reliability for procedures.
- `generate_wiki_l2(conn, entity_type, entity_id)` — L1 + enum values + state transitions for tables; L1 + branch details + call chain + description for procedures.
- `get_wiki_page(conn, entity_type, entity_id, tier)` — checks `current_wiki_pages` for cached entry matching `schema_version`; returns cached or generates fresh, invalidates stale, stores new.
- `invalidate_wiki_cache(conn, entity_type, entity_id)` — sets `invalidated_at` on all non-invalidated rows.
- `generate_wiki_markdown(conn, entity_type, entity_id)` — EXPORT-02 full markdown document with `#`, `## Summary`, `## Details` sections combining L0+L1+L2.

## Test Results

- `tests/test_query_resolver.py`: 25 tests, all pass
- `tests/test_query_wiki.py`: 20 tests, all pass
- **Total: 45 tests, 45 passed, 0 failed**

## Deviations from Plan

### Auto-fixed Issues

None significant.

**1. [Rule 1 - Bug] Test for schema_version cache invalidation used time.sleep(0.01)**
- **Found during:** Task 2 testing
- **Issue:** `time.sleep(0.01)` is not enough to increment `recorded_at_ts` (integer seconds), so schema_version appeared equal in both inserts, and the cache was never invalidated.
- **Fix:** Modified test to directly manipulate `recorded_at_ts` (insert Customers with `schema_v1 + 1`) to reliably force a schema_version change without sleep.
- **Files modified:** tests/test_query_wiki.py

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundaries introduced. The `define_metric` SQL fragment validation (T-04-01) was implemented as required by the threat register.

## Known Stubs

None — all functions produce real content from the knowledge store. The `generate_wiki_l0/l1/l2` functions gracefully handle missing data (e.g., `"not found"` for unknown entity IDs).

## Self-Check: PASSED

- FOUND: db_wiki/core/query_schema.py
- FOUND: db_wiki/query/__init__.py
- FOUND: db_wiki/query/resolver.py
- FOUND: db_wiki/query/wiki.py
- FOUND: tests/test_query_resolver.py
- FOUND: tests/test_query_wiki.py
- FOUND commit b14c65b: feat(04-01): schema extension + concept resolver module
- FOUND commit 164af94: feat(04-01): on-demand wiki page generator with cache
