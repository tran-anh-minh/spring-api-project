# Requirements: DB Wiki

**Defined:** 2026-04-10
**Core Value:** Turn undocumented legacy databases into queryable, self-improving knowledge — natural language questions to accurate SQL without understanding thousands of stored procedures.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Ingest

- [ ] **INGEST-01**: Parse DDL files into tables, columns, constraints, and indexes
- [ ] **INGEST-02**: Parse stored procedures via sqlglot AST into table references, JOINs, and mutations
- [ ] **INGEST-03**: Extract SP control flow: IF/ELSE branches, CASE statements, variable tracking, nesting depth
- [ ] **INGEST-04**: Extract state transitions from UPDATE SET col=X WHERE col=Y patterns across SPs
- [ ] **INGEST-05**: Resolve SP call chains (SP-A calls SP-B calls SP-C)
- [ ] **INGEST-06**: Detect and flag dynamic SQL (EXEC(@sql)) as opaque with parse quality tracking
- [ ] **INGEST-07**: Track parse quality per SP (detect sqlglot exp.Anonymous nodes, set degraded status above 5%)
- [ ] **INGEST-08**: Support batch ingest of directories and incremental re-parse on file changes via body_hash

### Knowledge Store

- [ ] **STORE-01**: SQLite database with bi-temporal model (valid_from/until + recorded_at/invalidated_at) for all facts
- [ ] **STORE-02**: Bi-temporal views as mandatory access layer — no application code queries raw temporal tables
- [ ] **STORE-03**: Core entity tables: db_tables, db_columns, db_procedures with descriptions and metadata
- [ ] **STORE-04**: Relationship graph: db_relationships with types (fk_declared, fk_inferred, joins_with, reads_from, writes_to, feeds_into)
- [ ] **STORE-05**: SP intelligence: sp_branches (conditions, tables touched), sp_reliability (score, execution count, contradictions), sp_call_chains
- [ ] **STORE-06**: Value intelligence: enum_values, bitmask_definitions, state_transitions, column_aliases with confidence scores
- [ ] **STORE-07**: Wiki pages with L0/L1/L2 tiers (one-line / structured / full detail) following OpenViking pattern
- [ ] **STORE-08**: Knowledge gaps table with severity, attempt count, cooldown history, and auto-resolution tracking
- [ ] **STORE-09**: sqlite-vec for vector search (configurable: 384-dim local or 1536-dim OpenAI)
- [ ] **STORE-10**: FTS5 full-text search index on wiki pages and entity descriptions
- [ ] **STORE-11**: Graph traversal via bfsvtab with Python BFS fallback (collections.deque over adjacency queries)

### Learning Loop

- [ ] **LEARN-01**: Five-phase learning loop: Discover → Investigate → Reason → Validate → Consolidate
- [ ] **LEARN-02**: Gap detection with 12 rules (unlabeled enums, orphan tables, missing joins, stale facts, alias clusters, incomplete state machines, etc.)
- [ ] **LEARN-03**: Gap priority scoring: severity_weight x 0.3 + connectivity x 0.25 + query_frequency x 0.20 + staleness x 0.15 + solvability x 0.10
- [ ] **LEARN-04**: Data sampling engine via live DB connection (SELECT DISTINCT, value ranges, row counts, correlation checks)
- [ ] **LEARN-05**: Enum and bitmask auto-detection from CASE statements, SP names, data sampling, cross-project patterns
- [ ] **LEARN-06**: 4-operation update pipeline: ADD, REINFORCE, CONFLICT, NOOP (Mem0 pattern)
- [ ] **LEARN-07**: Conflict resolution strategies: SUPERSEDE, KEEP, SPLIT, ESCALATE with scoring formula
- [ ] **LEARN-08**: SP reliability scoring: baseline 0.5 with adjustments for recency, usage, callers, dynamic SQL, contradictions
- [ ] **LEARN-09**: Confidence decay over time (configurable rate, min threshold) with reinforcement on new evidence
- [ ] **LEARN-10**: Human confirmation skill (dbwiki:confirm) setting confidence=1.0, never overridden without asking
- [ ] **LEARN-11**: Gap cooldown history to prevent infinite gap cycling (gap A → investigate → re-creates gap A)
- [ ] **LEARN-12**: Source independence weighting (copy-paste SPs don't inflate confidence as independent sources)
- [ ] **LEARN-13**: Background loop scheduling: fast (every event), medium (daily), deep (weekly), human (when stuck)

### Query Engine

- [ ] **QUERY-01**: Concept resolution via hybrid search (sqlite-vec + FTS5 + wiki lookup) mapping NL terms to schema entities
- [ ] **QUERY-02**: Derived metric resolution: teachable business concept → SQL mappings (dbwiki:define_metric)
- [ ] **QUERY-03**: JOIN path finding via BFS graph traversal (shortest + highest confidence paths)
- [ ] **QUERY-04**: 6-tier query generation: lookup, aggregation, temporal, statistical, forensic, data quality
- [ ] **QUERY-05**: L0/L1/L2 context assembly: L0 for all related tables, L1 for relevant, L2 for core — under 8K tokens
- [ ] **QUERY-06**: SQL generation with full schema context including enum labels, alias mappings, value patterns
- [ ] **QUERY-07**: SQL validation: parse generated SQL with sqlglot, verify tables/columns exist in knowledge store
- [ ] **QUERY-08**: Self-correcting query loop: error → rewrite → retry with max attempts
- [ ] **QUERY-09**: Optional query execution against live DB with results returned

### MCP Server

- [ ] **MCP-01**: MCP server via Anthropic Python SDK (FastMCP) with stdio transport for Claude Code integration
- [ ] **MCP-02**: Async-first skill design: long operations return job ID, execute in background, expose status/poll
- [ ] **MCP-03**: Learn skills: dbwiki:ingest, dbwiki:connect, dbwiki:discover, dbwiki:confirm, dbwiki:define_metric, dbwiki:teach
- [ ] **MCP-04**: Ask skills: dbwiki:ask, dbwiki:explain, dbwiki:search, dbwiki:lineage, dbwiki:state_machine, dbwiki:branch_analysis
- [ ] **MCP-05**: Analyze skills: dbwiki:forensics, dbwiki:impact, dbwiki:coverage, dbwiki:data_quality, dbwiki:compare
- [ ] **MCP-06**: Manage skills: dbwiki:status, dbwiki:lint, dbwiki:history, dbwiki:export, dbwiki:loop

### CLI

- [ ] **CLI-01**: CLI interface (Typer) mirroring all MCP skills for standalone use
- [ ] **CLI-02**: Setup commands: db-wiki init, db-wiki connect
- [ ] **CLI-03**: Ingest commands with directory/glob support, --type flag, --from-db, --watch mode
- [ ] **CLI-04**: Query/discover/analyze commands matching all MCP skills
- [ ] **CLI-05**: Daemon mode: db-wiki serve (MCP), db-wiki daemon start/stop/status (background learning)

### Web UI

- [ ] **UI-01**: Local web page served by starlette/uvicorn for interactive knowledge graph visualization
- [ ] **UI-02**: vis.js Network graph with node type color coding and edge type labels
- [ ] **UI-03**: Click-to-expand neighbors, search/filter, zoom+pan navigation
- [ ] **UI-04**: Detail panel showing entity info (wiki L1/L2) on node click
- [ ] **UI-05**: Confidence heat-mapping (node/edge opacity by confidence score)
- [ ] **UI-06**: Gap highlighting with visual indicators for unknown/low-confidence entities

### Agents

- [ ] **AGENT-01**: Research Agent: deep investigation before knowledge updates, produces structured reports
- [ ] **AGENT-02**: Review Agent: quality gate before knowledge mutations, validates evidence supports conclusions
- [ ] **AGENT-03**: Analyst Agent: complex query decomposition for Tier 3+ queries
- [ ] **AGENT-04**: Collector Agent: systematic data gathering from live DB with safety limits (read-only, timeout, max rows, budget)
- [ ] **AGENT-05**: Orchestrator: coordinates learning loop, spawns agents, applies approved changes only

### Cross-Project

- [ ] **CROSS-01**: Cross-project pattern database (~/.db-wiki/cross.db) for naming patterns, common enums, schema patterns
- [ ] **CROSS-02**: Learnings from database A inform understanding of database B with confidence penalty

### Export & Dashboard

- [ ] **EXPORT-01**: Maturity dashboard (dbwiki:status): coverage %, gap count, conflict count, top gaps, knowledge growth trend
- [ ] **EXPORT-02**: Wiki generation: L0/L1/L2 tiered markdown pages compiled from knowledge store
- [ ] **EXPORT-03**: Export formats: markdown wiki, ER diagram (mermaid), JSON schema, SQL comments (annotated DDL)

### Configuration

- [ ] **CONFIG-01**: Configurable embedding provider: local sentence-transformers (all-MiniLM-L6-v2) or OpenAI (text-embedding-3-small)
- [ ] **CONFIG-02**: Configurable DB connection: works offline from SQL files, enhanced with live DB connection
- [ ] **CONFIG-03**: YAML configuration file (.db-wiki/config.yaml) for storage, database, ingest, learning, confidence, agents, context, server, and embedding settings
- [ ] **CONFIG-04**: Lazy-load torch/sentence-transformers only when embedding is first requested (avoid 1-2GB download on install)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Extended Ingest

- **INGEST-V2-01**: Parse triggers and SQL Agent jobs with same analysis as SPs
- **INGEST-V2-02**: Extract metadata from sys.columns, sys.dm_exec_procedure_stats, sys.triggers, msdb.dbo.sysjobs
- **INGEST-V2-03**: Pull DDL/SP definitions directly from connected DB (--from-db)
- **INGEST-V2-04**: File watcher for auto-ingest on .sql file changes

### Multi-Dialect

- **DIALECT-V2-01**: Support MySQL dialect via sqlglot
- **DIALECT-V2-02**: Support PostgreSQL dialect via sqlglot
- **DIALECT-V2-03**: Dialect-aware parsing pipeline with configurable sql_dialect setting

### Advanced Web UI

- **UI-V2-01**: SP overlay mode toggle showing stored procedure data flow paths
- **UI-V2-02**: State machine view (dedicated visualization for transition graphs)
- **UI-V2-03**: Lineage flow view (Dagre layout for data flow through SPs)
- **UI-V2-04**: Depth slider for controlling graph traversal depth

### Integrations

- **INT-V2-01**: CI/CD pipeline integration (lint with GitHub annotations, impact reports in PR comments)
- **INT-V2-02**: IDE extension (VS Code hover for table summaries, right-click for lineage/impact)
- **INT-V2-03**: Multi-user shared knowledge store via HTTP transport with authentication

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time CDC/streaming | Batch ingest sufficient for v1; CDC adds massive complexity |
| Write operations to target DB | Safety: strictly read-only access to prevent accidental mutations |
| Electron desktop app | Web UI + CLI sufficient; Electron adds 100MB+ overhead |
| Multi-dialect in v1 | Focus on T-SQL/SQL Server deeply; sqlglot supports others but each needs testing |
| Multi-user auth for MCP | Local-first tool; auth not needed for single-user MCP server |
| Chatbot UI in web page | MCP IS the chat interface; web UI is for graph visualization only |
| LLM-dependent structural parsing | Structural extraction must be deterministic (sqlglot), not LLM-based |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 1 | Pending |
| INGEST-02 | Phase 2 | Pending |
| INGEST-03 | Phase 2 | Pending |
| INGEST-04 | Phase 2 | Pending |
| INGEST-05 | Phase 2 | Pending |
| INGEST-06 | Phase 2 | Pending |
| INGEST-07 | Phase 2 | Pending |
| INGEST-08 | Phase 2 | Pending |
| STORE-01 | Phase 1 | Pending |
| STORE-02 | Phase 1 | Pending |
| STORE-03 | Phase 1 | Pending |
| STORE-04 | Phase 1 | Pending |
| STORE-05 | Phase 2 | Pending |
| STORE-06 | Phase 2 | Pending |
| STORE-07 | Phase 4 | Pending |
| STORE-08 | Phase 3 | Pending |
| STORE-09 | Phase 2 | Pending |
| STORE-10 | Phase 2 | Pending |
| STORE-11 | Phase 2 | Pending |
| LEARN-01 | Phase 3 | Pending |
| LEARN-02 | Phase 3 | Pending |
| LEARN-03 | Phase 3 | Pending |
| LEARN-04 | Phase 3 | Pending |
| LEARN-05 | Phase 3 | Pending |
| LEARN-06 | Phase 3 | Pending |
| LEARN-07 | Phase 3 | Pending |
| LEARN-08 | Phase 3 | Pending |
| LEARN-09 | Phase 3 | Pending |
| LEARN-10 | Phase 3 | Pending |
| LEARN-11 | Phase 3 | Pending |
| LEARN-12 | Phase 3 | Pending |
| LEARN-13 | Phase 3 | Pending |
| QUERY-01 | Phase 4 | Pending |
| QUERY-02 | Phase 4 | Pending |
| QUERY-03 | Phase 4 | Pending |
| QUERY-04 | Phase 4 | Pending |
| QUERY-05 | Phase 4 | Pending |
| QUERY-06 | Phase 4 | Pending |
| QUERY-07 | Phase 4 | Pending |
| QUERY-08 | Phase 4 | Pending |
| QUERY-09 | Phase 4 | Pending |
| MCP-01 | Phase 1 | Pending |
| MCP-02 | Phase 1 | Pending |
| MCP-03 | Phase 3 | Pending |
| MCP-04 | Phase 4 | Pending |
| MCP-05 | Phase 4 | Pending |
| MCP-06 | Phase 5 | Pending |
| CLI-01 | Phase 1 | Pending |
| CLI-02 | Phase 1 | Pending |
| CLI-03 | Phase 2 | Pending |
| CLI-04 | Phase 4 | Pending |
| CLI-05 | Phase 5 | Pending |
| UI-01 | Phase 5 | Pending |
| UI-02 | Phase 5 | Pending |
| UI-03 | Phase 5 | Pending |
| UI-04 | Phase 5 | Pending |
| UI-05 | Phase 5 | Pending |
| UI-06 | Phase 5 | Pending |
| AGENT-01 | Phase 3 | Pending |
| AGENT-02 | Phase 3 | Pending |
| AGENT-03 | Phase 4 | Pending |
| AGENT-04 | Phase 3 | Pending |
| AGENT-05 | Phase 3 | Pending |
| CROSS-01 | Phase 5 | Pending |
| CROSS-02 | Phase 5 | Pending |
| EXPORT-01 | Phase 5 | Pending |
| EXPORT-02 | Phase 4 | Pending |
| EXPORT-03 | Phase 5 | Pending |
| CONFIG-01 | Phase 2 | Pending |
| CONFIG-02 | Phase 1 | Pending |
| CONFIG-03 | Phase 1 | Pending |
| CONFIG-04 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 68 total
- Mapped to phases: 68
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-10 after initial definition*
