---
phase: 02-sp-parsing-knowledge-graph
verified: 2026-04-10T16:00:00Z
status: passed
score: 5/5
overrides_applied: 0
---

# Phase 2: SP Parsing + Knowledge Graph Verification Report

**Phase Goal:** Users can ingest stored procedures and explore the full relationship graph between tables and SPs
**Verified:** 2026-04-10T16:00:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can ingest a directory of SP files and see table references, JOINs, mutations, and call chains stored per SP | VERIFIED | `sp_parser.py` (958 lines) has `parse_sp`, `extract_table_refs`, `extract_mutations`, `extract_call_chains`, `ingest_sp`. CLI `ingest` command accepts directories with `**/*.sql` glob and `--type` flag. Spot-check: `parse_sp("CREATE PROCEDURE dbo.GetOrders AS SELECT o.*, c.Name FROM Orders o JOIN Customers c ON o.CustomerId = c.Id")` returns 1 procedure with `table_refs=['Customers', 'Orders']` and 2 relationships. INSERTs to sp_branches, sp_reliability, sp_call_chains, enum_values, state_transitions confirmed in code. |
| 2 | SP parse quality is tracked -- SPs with >5% Anonymous nodes are flagged as degraded | VERIFIED | `compute_parse_quality()` at line 515 counts `exp.Anonymous` nodes, returns `(quality, is_degraded)` where degraded = quality < 0.95. `ingest_sp` writes to `sp_reliability` table with `parse_quality`, `is_degraded` columns. Spot-check: simple SP returns quality=1.0, degraded=False. |
| 3 | Relationship graph (fk_declared, fk_inferred, joins_with, reads_from, writes_to, feeds_into) is queryable via BFS | VERIFIED | `bfs_graph()` in `graph/bfs.py` (116 lines) uses `collections.deque` with visited set, queries `current_db_relationships` view. Supports edge_types filtering, bidirectional traversal, max_depth, cycle detection. Spot-check: BFS from Orders (id=1) with reads_from edge to Customers (id=2) returns 2 nodes at depths 0 and 1. MCP `lineage` tool and CLI `lineage` command both wire to `bfs_graph`. |
| 4 | Enum and bitmask values are detected and labeled from CASE statements and SP names | VERIFIED | `extract_enum_detections()` at line 399 finds `exp.Case` nodes and extracts value/label pairs with detection_method="case_when". Schema has `enum_values` and `bitmask_definitions` tables. Spot-check: SP with `CASE WHEN Status = 1 THEN 'Active' WHEN Status = 2 THEN 'Inactive'` returns 1 enum detection with values `[{'value': '1', 'label': 'Active'}, {'value': '2', 'label': 'Inactive'}]`. |
| 5 | Hybrid search (vector + FTS5) returns relevant entities when searching by partial name or description | VERIFIED | `hybrid_search()` in `search/hybrid.py` (116 lines) calls `search_fts()` and `Embedder.search_similar()`, fuses scores via `fuse_scores()`. FTS5 virtual table `fts_entities` created in schema. `populate_fts_from_store()` reads from `current_db_tables` and `current_db_procedures`. Spot-check: FTS populated with 2 entities, search for "Order" returns 1 match (Orders table). Embedder lazy-loads sentence-transformers inside `ensure_ready()`, not at module level. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db_wiki/ingest/sp_parser.py` | SP parsing pipeline | VERIFIED | 958 lines, 15 functions, AST + regex fallback, wired to models and schema |
| `db_wiki/search/embedder.py` | Lazy-loaded embedding generation | VERIFIED | 113 lines, Embedder class, lazy import of sentence_transformers |
| `db_wiki/search/fts.py` | FTS5 index management | VERIFIED | 79 lines, populate_fts, search_fts, sync_fts |
| `db_wiki/search/hybrid.py` | Score fusion search | VERIFIED | 116 lines, fuse_scores, hybrid_search |
| `db_wiki/graph/bfs.py` | Python BFS over SQLite adjacency | VERIFIED | 116 lines, bfs_graph with deque, visited set, edge filtering |
| `db_wiki/core/queries.py` | Shared entity lookup utility | VERIFIED | 56 lines, lookup_entity_name, find_entity_by_name |
| `db_wiki/server/app.py` | search, lineage, sp_info MCP tools | VERIFIED | 331 lines, 3 new @mcp.tool() decorated functions |
| `db_wiki/cli/app.py` | search, lineage, sp-info CLI commands | VERIFIED | 470 lines, 3 new commands with full implementations |
| `db_wiki/core/schema.py` | Phase 2 table DDL | VERIFIED | 7 intelligence tables + FTS5 + current_* views |
| `db_wiki/core/models.py` | SP Pydantic models | VERIFIED | 7 model classes (SPInfo, MutationInfo, BranchInfo, CallChainInfo, EnumDetection, StateTransitionInfo, SPParseResult) |
| `db_wiki/core/store.py` | sqlite-vec extension loading | VERIFIED | enable_load_extension + sqlite_vec.load + disable after |
| `db_wiki/core/config.py` | EmbeddingConfig | VERIFIED | EmbeddingConfig class with provider="local" default |
| `tests/test_sp_parser.py` | SP parser test suite | VERIFIED | 328 lines, 15+ test cases |
| `tests/test_bfs.py` | BFS test suite | VERIFIED | 179 lines, 10 test cases |
| `tests/test_search.py` | Search test suite | VERIFIED | 457 lines, 24 test cases |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `sp_parser.py` | `models.py` | `from db_wiki.core.models import.*SPInfo` | WIRED | Line 16: imports SPInfo, SPParseResult, MutationInfo, etc. |
| `sp_parser.py` | `schema.py` | INSERT INTO sp_branches, sp_reliability, etc. | WIRED | Lines 772-866: parameterized INSERTs to all intelligence tables |
| `server/app.py` | `queries.py` | `from db_wiki.core.queries import` | WIRED | Lines 162, 213: lookup_entity_name, find_entity_by_name |
| `server/app.py` | `hybrid.py` | `hybrid_search` call | WIRED | Lines 164, 172: import and call hybrid_search |
| `server/app.py` | `bfs.py` | `bfs_graph` call | WIRED | Lines 214, 225: import and call bfs_graph |
| `cli/app.py` | `queries.py` | `from db_wiki.core.queries import` | WIRED | Lines 286, 346: shared imports |
| `cli/app.py` | `hybrid.py` | `hybrid_search` call | WIRED | Lines 288, 296: import and call hybrid_search |
| `cli/app.py` | `bfs.py` | `bfs_graph` call | WIRED | Lines 347, 360: import and call bfs_graph |
| `cli/app.py` | `sp_parser.py` | CLI ingest calls sp_parser | WIRED | Line 135: import detect_content_type, ingest_sp, parse_sp |
| `store.py` | `sqlite_vec` | enable_load_extension + sqlite_vec.load | WIRED | Lines 35-37: load and disable extension |
| `embedder.py` | `sentence-transformers` | lazy import inside ensure_ready | WIRED | Line 46: `from sentence_transformers import SentenceTransformer` inside method |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `server/app.py` search tool | results | hybrid_search() -> search_fts() + Embedder.search_similar() | FTS queries fts_entities MATCH; vec queries sqlite-vec | FLOWING |
| `server/app.py` lineage tool | results | bfs_graph() -> SELECT from current_db_relationships | Real SQLite queries on relationship graph | FLOWING |
| `server/app.py` sp_info tool | row, rel_row, branches, chains, rels | SELECT from current_db_procedures, current_sp_reliability, current_sp_branches, current_sp_call_chains, current_db_relationships | Real DB queries on intelligence tables | FLOWING |
| `cli/app.py` search command | results | hybrid_search() | Same path as MCP tool | FLOWING |
| `cli/app.py` lineage command | results | bfs_graph() | Same path as MCP tool | FLOWING |
| `cli/app.py` sp-info command | row, rel_row, etc. | Direct SQL queries | Same queries as MCP tool | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SP parsing extracts table refs | `parse_sp(CREATE PROCEDURE...)` | 1 procedure, table_refs=['Customers','Orders'], 2 relationships | PASS |
| Content type detection | `detect_content_type(sp_sql)` / `detect_content_type(ddl_sql)` | "sp" / "ddl" | PASS |
| Enum detection from CASE | `parse_sp(SP with CASE WHEN Status=1...)` | 1 enum detection with values [Active, Inactive] | PASS |
| Parse quality scoring | `parse_sp(simple SP)` | quality=1.0, degraded=False | PASS |
| Entity lookup | `lookup_entity_name(conn, 1)` | "Orders" | PASS |
| Entity name resolution | `find_entity_by_name(conn, "Orders")` | (1, "table") | PASS |
| BFS traversal | `bfs_graph(conn, 1, max_depth=2)` | 2 nodes at depths 0 and 1 | PASS |
| FTS5 search | `search_fts(conn, "Order")` | 1 result matching "Orders" | PASS |
| Pydantic models | SPInfo + SPParseResult construction | Models instantiate with correct field types | PASS |
| All tests | `uv run pytest tests/ -x` | 212 passed in 4.20s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INGEST-02 | 02-01, 02-02 | Parse SPs via sqlglot AST into table refs, JOINs, mutations | SATISFIED | `extract_table_refs`, `extract_mutations` in sp_parser.py |
| INGEST-03 | 02-01, 02-02 | Extract SP control flow: IF/ELSE, CASE, nesting depth | SATISFIED | `extract_branches` handles If, IfBlock, Case, While nodes |
| INGEST-04 | 02-01, 02-02 | Extract state transitions from UPDATE SET/WHERE patterns | SATISFIED | `extract_state_transitions` in sp_parser.py |
| INGEST-05 | 02-01, 02-02 | Resolve SP call chains | SATISFIED | `extract_call_chains` with classify_execute |
| INGEST-06 | 02-01, 02-02 | Detect and flag dynamic SQL | SATISFIED | has_dynamic_sql flag, dynamic_sql_locations in SPInfo |
| INGEST-07 | 02-01, 02-02 | Track parse quality per SP | SATISFIED | `compute_parse_quality` counts Anonymous nodes |
| INGEST-08 | 02-02, 02-05 | Batch ingest with incremental re-parse via body_hash | SATISFIED | CLI directory ingest + body_hash dedup in ingest_sp |
| STORE-05 | 02-01 | SP intelligence tables (sp_branches, sp_reliability, sp_call_chains) | SATISFIED | 3 tables in schema.py with bi-temporal columns |
| STORE-06 | 02-01 | Value intelligence (enum_values, bitmask_definitions, state_transitions, column_aliases) | SATISFIED | 4 tables in schema.py with bi-temporal columns |
| STORE-09 | 02-01, 02-03 | sqlite-vec for vector search | SATISFIED | sqlite_vec loaded in store, Embedder with init_vec_table |
| STORE-10 | 02-01, 02-03 | FTS5 full-text search index | SATISFIED | fts_entities virtual table, populate_fts, search_fts |
| STORE-11 | 02-04 | Graph traversal via Python BFS fallback | SATISFIED | bfs_graph with deque, visited set, edge filtering |
| CLI-03 | 02-02, 02-05 | Ingest with directory/glob, --type flag | SATISFIED | CLI ingest accepts Path with glob, --type option |
| CONFIG-01 | 02-01, 02-03 | Configurable embedding provider | SATISFIED | EmbeddingConfig with provider field, local/openai support |
| CONFIG-04 | 02-03 | Lazy-load torch/sentence-transformers | SATISFIED | Module-level has no torch/sentence_transformers imports |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | No anti-patterns found in Phase 2 files |

### Human Verification Required

No human verification items identified. All phase deliverables are programmatically verifiable through code inspection, grep patterns, and behavioral spot-checks.

### Gaps Summary

No gaps found. All 5 roadmap success criteria verified with code evidence and behavioral spot-checks. All 15 requirement IDs satisfied. 212 tests passing with zero regressions.

---

_Verified: 2026-04-10T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
