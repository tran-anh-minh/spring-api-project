# Roadmap: DB Wiki

## Overview

DB Wiki transforms undocumented legacy SQL Server databases into a queryable, self-improving knowledge engine. The build follows a hard dependency chain: store schema and DDL ingest must exist before SP parsing can reference entities, the relationship graph must exist before learning loop gap detection can operate, and concept resolution and BFS traversal must exist before query generation can produce accurate SQL. The five phases reflect this chain — each phase delivers a complete, independently verifiable capability that unlocks the next.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - SQLite bi-temporal schema, DDL ingest, async MCP/CLI skeleton
- [ ] **Phase 2: SP Parsing + Knowledge Graph** - sqlglot SP AST, full relationship graph, vector/FTS search
- [ ] **Phase 3: Learning Loop** - 5-phase orchestrator, gap queue, agents, confidence management
- [ ] **Phase 4: Query Engine** - Concept resolution, SQL generation, self-correcting loop, wiki export
- [ ] **Phase 5: Web UI + Cross-Project + Polish** - Graph visualization, cross-project DB, background scheduling, full export

## Phase Details

### Phase 1: Foundation
**Goal**: Users can ingest DDL files and query the resulting schema knowledge via MCP or CLI
**Depends on**: Nothing (first phase)
**Requirements**: INGEST-01, STORE-01, STORE-02, STORE-03, STORE-04, MCP-01, MCP-02, CLI-01, CLI-02, CONFIG-02, CONFIG-03
**Success Criteria** (what must be TRUE):
  1. User can run `db-wiki ingest schema.sql` and have tables, columns, constraints, and indexes stored in SQLite
  2. User can start the MCP server and register it with Claude Code without errors
  3. User can run `db-wiki init` and `db-wiki connect` to create a configured knowledge store
  4. All data access goes through bi-temporal views — no raw table queries in application code
  5. The system works offline from SQL files with no live database required
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold, SQLite bi-temporal schema, YAML config system
- [x] 01-02-PLAN.md — DDL parser and ingest pipeline (sqlglot)
- [x] 01-03-PLAN.md — FastMCP server skeleton and Typer CLI

### Phase 2: SP Parsing + Knowledge Graph
**Goal**: Users can ingest stored procedures and explore the full relationship graph between tables and SPs
**Depends on**: Phase 1
**Requirements**: INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, INGEST-07, INGEST-08, STORE-05, STORE-06, STORE-09, STORE-10, STORE-11, CLI-03, CONFIG-01, CONFIG-04
**Success Criteria** (what must be TRUE):
  1. User can ingest a directory of SP files and see table references, JOINs, mutations, and call chains stored per SP
  2. SP parse quality is tracked — SPs with >5% Anonymous nodes are flagged as degraded
  3. Relationship graph (fk_declared, fk_inferred, joins_with, reads_from, writes_to, feeds_into) is queryable via BFS
  4. Enum and bitmask values are detected and labeled from CASE statements and SP names
  5. Hybrid search (vector + FTS5) returns relevant entities when searching by partial name or description
**Plans:** 5 plans
**UI hint**: no

Plans:
- [x] 02-01-PLAN.md — Phase 2 schema tables, SP Pydantic models, sqlite-vec store integration, embedding config
- [x] 02-02-PLAN.md — SP parser module with three-pass extraction, batch ingest, CLI ingest extension
- [x] 02-03-PLAN.md — Search infrastructure: lazy-loaded embedder, FTS5 index, hybrid score fusion
- [x] 02-04-PLAN.md — Python BFS graph traversal with edge type filtering and cycle detection
- [x] 02-05-PLAN.md — MCP tools (search, lineage, sp_info) and CLI commands

### Phase 3: Learning Loop
**Goal**: The system autonomously identifies knowledge gaps and deepens its understanding through iterative investigation
**Depends on**: Phase 2
**Requirements**: LEARN-01, LEARN-02, LEARN-03, LEARN-04, LEARN-05, LEARN-06, LEARN-07, LEARN-08, LEARN-09, LEARN-10, LEARN-11, LEARN-12, LEARN-13, STORE-08, MCP-03, AGENT-01, AGENT-02, AGENT-04, AGENT-05
**Success Criteria** (what must be TRUE):
  1. User can trigger a learning loop run and observe gap detection finding unlabeled enums, orphan tables, and missing joins
  2. Human can confirm a fact via `dbwiki:confirm` and its confidence is set to 1.0, never silently overridden
  3. Conflict between two sources produces SUPERSEDE/KEEP/SPLIT/ESCALATE resolution with logged rationale
  4. Confidence decays over time for stale facts and is reinforced when new evidence supports existing knowledge
  5. Gap cooldown prevents the same gap from being re-created infinitely across loop iterations
**Plans**: TBD

### Phase 4: Query Engine
**Goal**: Users can ask natural language questions and receive accurate, validated SQL with full schema context
**Depends on**: Phase 3
**Requirements**: QUERY-01, QUERY-02, QUERY-03, QUERY-04, QUERY-05, QUERY-06, QUERY-07, QUERY-08, QUERY-09, STORE-07, MCP-04, MCP-05, CLI-04, AGENT-03, EXPORT-02
**Success Criteria** (what must be TRUE):
  1. User can ask "show me all orders for a customer" and receive valid T-SQL with correct table joins and alias mappings
  2. User can define a business metric (e.g., "revenue") and subsequent queries resolve it to the correct SQL expression
  3. Generated SQL is validated against the knowledge store — references to non-existent tables/columns are caught and rewritten
  4. Context assembly stays under 8K tokens for schemas with 100+ tables using L0/L1/L2 tiered loading
  5. User can execute the generated SQL against a live database and receive results inline
**Plans**: TBD
**UI hint**: no

### Phase 5: Web UI + Cross-Project + Polish
**Goal**: Users can visually explore the knowledge graph, share patterns across databases, and schedule background learning
**Depends on**: Phase 4
**Requirements**: MCP-06, CLI-05, UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, CROSS-01, CROSS-02, EXPORT-01, EXPORT-03
**Success Criteria** (what must be TRUE):
  1. User can open a local web page and see the knowledge graph rendered with node color coding, edge labels, confidence heat-mapping, and gap highlighting
  2. User can click a node to expand its neighbors and view the L1/L2 wiki detail in a side panel
  3. User can run `db-wiki daemon start` to enable background learning at fast/medium/deep/human frequencies
  4. User can view a maturity dashboard showing coverage %, gap count, conflict count, and knowledge growth trend
  5. Learnings from database A (naming patterns, common enums) are available with a confidence penalty when ingesting database B
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/3 | Planning complete | - |
| 2. SP Parsing + Knowledge Graph | 0/5 | Planning complete | - |
| 3. Learning Loop | 0/TBD | Not started | - |
| 4. Query Engine | 0/TBD | Not started | - |
| 5. Web UI + Cross-Project + Polish | 0/TBD | Not started | - |
