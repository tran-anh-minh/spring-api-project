# Phase 2: SP Parsing + Knowledge Graph - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can ingest stored procedures and explore the full relationship graph between tables and SPs. Includes SP parsing (table references, JOINs, mutations, control flow, call chains), parse quality tracking, enum/bitmask/state transition detection, hybrid search (vector + FTS5), and graph traversal via BFS. Exposes new capabilities through MCP tools and CLI commands.

</domain>

<decisions>
## Implementation Decisions

### SP Parsing Depth
- **D-01:** Flatten and extract approach for procedural blocks — walk the raw token/node tree even when sqlglot's AST is incomplete for IF/ELSE/WHILE/TRY bodies. Extract table refs and mutations best-effort. Flag the SP as `partial_ast` but still capture what's there.
- **D-02:** Dynamic SQL (EXEC(@sql), sp_executesql) is flagged and skipped — mark the SP as containing dynamic SQL, log the EXEC location, but don't attempt to parse the string content. Clean boundary per INGEST-06.
- **D-03:** Parse quality stored as silent metadata — parse_quality score and degraded flag stored in db_procedures. Surface only when queried (CLI status --quality or MCP tool). Don't interrupt normal ingest flow.
- **D-04:** Enum detection via CASE + naming heuristics — detect enums from CASE WHEN col = 'value' patterns AND from SP/column names matching patterns like *Status, *Type, *Flag. Confidence varies by evidence strength.

### Graph Traversal
- **D-05:** Python BFS only — implement BFS in Python with collections.deque over SQLite adjacency queries. No bfsvtab dependency. Performance is acceptable for <100k nodes. bfsvtab can be added as optional optimization later.
- **D-06:** Configurable edge type filtering per query — BFS accepts an optional edge_types filter. Default: traverse all 6 types (fk_declared, fk_inferred, joins_with, reads_from, writes_to, feeds_into). Users can narrow for specific traversal needs (e.g., data lineage = reads_from + writes_to + feeds_into).

### Embedding + Search
- **D-07:** Separate sqlite-vec tables per embedding provider — create vec_embeddings_384 or vec_embeddings_1536 based on configured provider. Only create the table matching the active provider. On provider switch, rebuild embeddings.
- **D-08:** Hybrid search via score fusion — run vector search and FTS5 independently, normalize scores to 0-1, combine with configurable weight (default 0.5/0.5). Return merged ranked list.
- **D-09:** On-demand embedding at first search — don't embed during ingest. Batch-embed all unembedded entities when the first search query triggers it. Keeps ingest fast, defers torch download until actually needed (CONFIG-04).

### Ingest Workflow
- **D-10:** One SP per file convention — expect each .sql file to contain one CREATE PROCEDURE. Directory = collection of SPs. Simple file-to-SP mapping for incremental re-parse.
- **D-11:** Invalidate old, insert new for re-parse — on body_hash change, set invalidated_at on old db_procedures row, insert new row. Cascade invalidation to derived rows (branches, call chains, relationships). Preserves bi-temporal history.
- **D-12:** --watch mode deferred to Phase 5 — Phase 5 has CLI-05 (daemon mode) where --watch naturally fits. Phase 2 implements directory ingest + glob support only.
- **D-13:** Auto-detect content type — parse files and auto-detect: CREATE PROCEDURE = SP, CREATE TABLE/INDEX/ALTER = DDL. --type flag overrides auto-detection. Least friction for users.

### State Transitions
- **D-14:** UPDATE WHERE literal match for state detection — detect UPDATE SET col = 'literal' WHERE col = 'literal' patterns where both sides are string/int literals on the same column. High confidence, low false positives.
- **D-15:** Evidence-based confidence scoring — literal-to-literal transitions = 0.9 confidence. Naming heuristic only = 0.3. Multiple SPs confirming same transition reinforces confidence.

### SP Call Chain Resolution
- **D-16:** Name-based matching for EXEC references — extract SP names from EXEC/EXECUTE statements, match against ingested db_procedures by name. Unresolved references stored as 'unresolved' with the raw name. Re-resolved on next ingest run.
- **D-17:** Detect and flag circular call chains — allow circular edges to exist but detect cycles during graph traversal. Flag circular SPs in sp_reliability with a 'has_cycle' marker. BFS visited-set prevents infinite loops.

### Schema Extensions
- **D-18:** All intelligence tables are bi-temporal — sp_branches, sp_reliability, sp_call_chains, enum_values, bitmask_definitions, state_transitions, column_aliases all follow the same valid_from/valid_until/recorded_at/invalidated_at pattern from Phase 1 (D-01/D-02). No exceptions.
- **D-19:** Unified embeddings table — single vec_embeddings table with entity_type + entity_id columns. Stores embeddings for tables, columns, SPs, and any future entity type. One sqlite-vec virtual table to manage.

### MCP/CLI Tools
- **D-20:** Core query MCP tools — add 'search' (hybrid vector+FTS5), 'lineage' (BFS from entity with edge type filter), 'sp_info' (SP details + branches + quality). Minimal surface, Phase 4 adds the full query engine.
- **D-21:** CLI mirrors MCP tools — 'db-wiki search', 'db-wiki lineage', 'db-wiki sp-info' with same capabilities as MCP tools, table/JSON output. Consistent mental model across interfaces.

### Claude's Discretion
- Exact SQLite DDL for new intelligence tables (column names, types, indexes)
- SP parser implementation details (sqlglot AST traversal patterns for procedural blocks)
- FTS5 index column selection and tokenizer configuration
- BFS implementation details (max depth defaults, result format)
- Score normalization algorithm for hybrid search
- Pydantic model definitions for SP-related entities

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs — requirements fully captured in decisions above and in project-level documents:

### Project-level
- `.planning/REQUIREMENTS.md` — Phase 2 requirements: INGEST-02 through INGEST-08, STORE-05, STORE-06, STORE-09, STORE-10, STORE-11, CLI-03, CONFIG-01, CONFIG-04
- `.planning/PROJECT.md` — Core constraints (SQLite only, Python, sqlglot, read-only safety, local-first privacy)
- `CLAUDE.md` §Technology Stack — sqlite-vec, FTS5, sentence-transformers, bfsvtab notes, sqlglot T-SQL capabilities and limitations

### Phase 1 foundation
- `.planning/phases/01-foundation/01-CONTEXT.md` — Bi-temporal model decisions (D-01/D-02), tolerant parsing (D-04), project structure (D-05/D-06)
- `db_wiki/core/schema.py` — Existing schema DDL with db_procedures table (has body_hash column)
- `db_wiki/core/models.py` — Pydantic model patterns for parsed entities
- `db_wiki/ingest/ddl_parser.py` — DDL parser patterns to extend for SP parsing
- `db_wiki/core/store.py` — Store connection management pattern
- `db_wiki/server/app.py` — MCP tool registration pattern via FastMCP

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db_wiki/ingest/ddl_parser.py` — parse_ddl_file() pattern for tolerant parsing with sqlglot. SP parser follows the same approach: parse with error_level=WARN, skip unparseable, collect warnings.
- `db_wiki/core/models.py` — Pydantic BaseModel pattern for intermediate parse results. SP models (SPInfo, BranchInfo, CallChainInfo, etc.) follow the same pattern.
- `db_wiki/core/store.py` — open_store() + init_schema() pattern. Phase 2 extends SCHEMA_SQL with new tables.
- `db_wiki/core/schema.py` — SCHEMA_SQL string with bi-temporal table + view pattern. New tables follow the same template.
- `db_wiki/server/app.py` — @mcp.tool() decorator pattern with AppContext for store access. New MCP tools follow the same pattern.

### Established Patterns
- Bi-temporal: every entity table has valid_from/valid_until/recorded_at/invalidated_at with dual format (TEXT + INTEGER)
- Current views: current_* views filter to active rows (valid_until IS NULL AND invalidated_at IS NULL)
- Tolerant parsing: ErrorLevel.WARN + skip-and-log for unparseable statements
- Parameterized SQL: all INSERTs use ? placeholders (security pattern T-02-02)
- Transaction wrapping: ingest_ddl() uses try/commit/except/rollback pattern

### Integration Points
- `db_wiki/core/schema.py` SCHEMA_SQL — new tables appended here
- `db_wiki/ingest/__init__.py` — new sp_parser module registered here
- `db_wiki/server/app.py` — new MCP tools (search, lineage, sp_info) added here
- `db_wiki/cli/app.py` — new CLI commands (search, lineage, sp-info, ingest --type) added here
- `pyproject.toml` — new dependencies: sqlite-vec, sentence-transformers (optional)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- **--watch mode** for file monitoring — deferred to Phase 5 (CLI-05 daemon mode) where it naturally fits
- **bfsvtab integration** — deferred as optional optimization. Python BFS is the primary implementation.
- **Variable tracking through SP execution paths** — sqlglot doesn't track variable values natively. Could enable richer state transition detection but high complexity. Candidate for Phase 3 learning loop.

</deferred>

---

*Phase: 02-sp-parsing-knowledge-graph*
*Context gathered: 2026-04-10*
