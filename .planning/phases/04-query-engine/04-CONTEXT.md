# Phase 4: Query Engine - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can ask natural language questions and receive accurate, validated T-SQL with full schema context. Implements concept resolution, derived metrics, JOIN path finding, 6-tier query classification, L0/L1/L2 context assembly, SQL generation and validation, self-correcting query loop, optional live DB execution, wiki page generation, and the Analyst Agent. Exposes query and analysis tools via MCP (ask, explain, search, lineage, state_machine, branch_analysis, forensics, impact, coverage, data_quality, compare, define_metric) and CLI commands.

</domain>

<decisions>
## Implementation Decisions

### NL-to-SQL Strategy
- **D-01:** LLM generates SQL directly — hybrid search (Phase 2) resolves NL concepts to schema entities, BFS finds JOIN paths, LLM assembles the final T-SQL query with full schema context.
- **D-02:** Query tier classification first (QUERY-04) — classify incoming question as lookup/aggregation/temporal/statistical/forensic/data_quality before context assembly. Tier determines how much context to load and which generation strategy to use.
- **D-03:** Derived metrics stored as SQL fragments (QUERY-02) — `dbwiki:define_metric` stores the SQL expression + source tables. When a query references a defined metric, substitute the stored SQL fragment into the generated query.
- **D-04:** Full offline fallback — template-based SQL generation when no LLM is configured. Every tool works without API keys. LLM enhances quality but is not required. Matches Phase 3 pattern (D-01: hybrid agents, enhanced with LLM).

### Context Assembly (L0/L1/L2)
- **D-05:** Relevance-scored tiering (QUERY-05) — L0 (one-line summary) for all tables in schema. L1 (columns + types + key constraints) for tables related to query via hybrid search and BFS. L2 (full detail: constraints, relationships, enum labels, state machines, wiki) for core tables directly referenced. Score-based cutoffs to stay under 8K token budget.
- **D-06:** Wiki pages generated on-demand (STORE-07, EXPORT-02) — generate and cache wiki content when a table/SP is queried or explicitly requested via explain. Invalidate cache when underlying facts change (schema re-ingest, learning loop updates). No upfront batch generation.

### Self-correcting Loop
- **D-07:** Parse-validate-retry cycle (QUERY-07, QUERY-08) — after LLM generates SQL: (1) parse with sqlglot to verify syntax, (2) verify all table/column references exist in knowledge store, (3) on failure, feed error + original question back to LLM for rewrite. Maximum 3 attempts. Offline template mode: validate only, no retry.
- **D-08:** Analyst Agent decomposes complex queries (AGENT-03) — for tier 3+ queries (temporal, statistical, forensic, data quality), Analyst Agent breaks the question into sub-queries, resolves each through the pipeline, then composes the final SQL. Uses LLM for decomposition. Simpler tiers go through single-pass generation.
- **D-09:** Cache NL-to-SQL mappings — cache question hash to generated SQL. Invalidate when schema or knowledge store changes (re-ingest, learning loop updates). Avoids redundant LLM calls for repeated questions.

### MCP/CLI Tool Surface
- **D-10:** Full query + analysis tools in Phase 4 — implement all MCP-04 tools (ask, explain, search, lineage, state_machine, branch_analysis) and all MCP-05 tools (forensics, impact, coverage, data_quality, compare), plus define_metric. Manage tools (status, lint, history, export, loop) deferred to Phase 5. Existing search/lineage from Phase 2 get enhanced with query engine capabilities.
- **D-11:** ask returns SQL + optional execution (QUERY-09) — always return generated SQL. If live DB connected AND user passes `--execute` (CLI) or `execute=true` (MCP), also run the query and return results inline. Default: SQL only.
- **D-12:** explain returns wiki page + relationships — for tables: columns, constraints, relationships, enum labels, state machines, SPs that read/write. For SPs: description, tables touched, branches, reliability score. Uses on-demand cached wiki pages (D-06).
- **D-13:** state_machine returns Mermaid diagram + text description of transitions. branch_analysis returns structured report of IF/ELSE paths with tables touched per branch. Both leverage Phase 2 knowledge store data.
- **D-14:** Analysis tools operate on knowledge store only — impact uses BFS from entity showing affected SPs/tables, coverage reports % of tables with relationships/descriptions, data_quality reports low-confidence facts + gaps, forensics traces data flow, compare does cross-entity comparison. No live DB queries required for analysis.
- **D-15:** CLI output: rich table default, `--json` for structured JSON, `--sql-only` for raw SQL without explanation. Consistent with existing Phase 2 CLI patterns (CLI-04).

### Claude's Discretion
- LLM prompt templates for SQL generation and query decomposition
- Exact relevance scoring algorithm for L0/L1/L2 tier assignment
- Token counting strategy for 8K budget enforcement
- Query tier classification heuristics (NL patterns to tier mapping)
- SQL template library for offline mode (which patterns to support)
- Cache implementation details (storage, invalidation triggers)
- Mermaid diagram formatting for state machines
- Pydantic models for query engine input/output schemas
- Internal data structures for query pipeline state

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Query engine requirements
- `.planning/REQUIREMENTS.md` — QUERY-01 through QUERY-09, STORE-07, MCP-04, MCP-05, CLI-04, AGENT-03, EXPORT-02
- `.planning/PROJECT.md` — Core constraints (SQLite only, read-only safety, configurable LLM, local-first)

### Technology stack
- `CLAUDE.md` §Technology Stack — sqlglot for SQL validation, sqlite-vec for vector search, sentence-transformers for embeddings, MCP SDK for server tools

### Prior phase decisions
- `.planning/phases/01-foundation/01-CONTEXT.md` — Schema design (D-01/D-02 bi-temporal), project structure (D-05/D-06 layered packages, entry points), config system (D-07/D-08)
- `.planning/phases/02-sp-parsing-knowledge-graph/02-CONTEXT.md` — Hybrid search (D-08 score fusion), BFS traversal (D-05/D-06 Python BFS with edge type filtering), embedding tables (D-07/D-19), SP parsing patterns
- `.planning/phases/03-learning-loop/03-CONTEXT.md` — Agent architecture (D-01 hybrid agents, D-02 SQLite communication, D-03 configurable LLM), confidence model (D-13/D-14/D-15)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db_wiki/search/hybrid.py`: Hybrid search with score fusion — directly usable for concept resolution (QUERY-01)
- `db_wiki/search/embedder.py`: Embedding generation — reuse for query embedding
- `db_wiki/search/fts.py`: FTS5 search — part of hybrid search pipeline
- `db_wiki/graph/bfs.py`: BFS traversal with edge type filtering — reuse for JOIN path finding (QUERY-03) and impact analysis
- `db_wiki/learning/agents/base.py`: Agent base class — extend for Analyst Agent (AGENT-03)
- `db_wiki/learning/agents/research.py`: Research Agent pattern — reference for Analyst Agent design
- `db_wiki/server/app.py`: FastMCP server with lifespan context — add new tools here
- `db_wiki/cli/app.py`: Typer CLI — add new commands here
- `db_wiki/core/store.py`: Store management with sqlite-vec — query cache can use same store
- `db_wiki/core/config.py`: YAML config — extend for query engine settings

### Established Patterns
- Bi-temporal views as mandatory access layer (STORE-02) — all queries go through `current_*` views
- FastMCP tool registration with Pydantic input schemas
- Typer command mirroring MCP tools with table/JSON output
- Hybrid agents: pure Python code + optional LLM enhancement (Phase 3 D-01)
- Agent communication via shared SQLite tables (Phase 3 D-02)

### Integration Points
- Query engine sits between Knowledge Store (Layer 2) and MCP Server (Layer 5) in the 5-layer architecture
- Concept resolution connects to hybrid search (Layer 2)
- JOIN path finding connects to BFS graph traversal (Layer 2)
- SQL validation connects to sqlglot (used by ingest parsers)
- Live DB execution connects to pyodbc (used by Collector Agent in Phase 3)
- Wiki generation reads from all knowledge store tables

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- Manage tools (dbwiki:status, dbwiki:lint, dbwiki:history, dbwiki:export, dbwiki:loop) — Phase 5
- Background loop scheduling — Phase 5 (CLI-05 daemon mode)
- Live DB queries for analysis tools (actual NULL rates, schema drift) — future enhancement
- Two-pass LLM context selection (LLM picks which tables need detail) — optimization if single-pass proves insufficient

</deferred>

---

*Phase: 04-query-engine*
*Context gathered: 2026-04-11*
