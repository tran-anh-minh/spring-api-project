# DB Wiki

## What This Is

A self-learning database knowledge engine delivered as an MCP server and CLI tool. It parses SQL schemas, stored procedures, triggers, and jobs to build a knowledge graph in SQLite, then iteratively deepens understanding through a five-phase learning loop (Discover, Investigate, Reason, Validate, Consolidate). Users query the knowledge via natural language and get exact SQL, wiki pages, lineage graphs, state machines, and data quality reports. Designed for both personal use and open-source distribution.

## Core Value

Turn undocumented legacy databases into queryable, self-improving knowledge — so any team member (developer, tester, BA, support) can ask natural language questions and get accurate SQL without needing to understand thousands of stored procedures.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Parse DDL files into tables, columns, constraints, indexes
- [ ] Parse stored procedures via sqlglot AST into table refs, JOINs, mutations, control flow
- [ ] Parse triggers and SQL Agent jobs with same analysis as SPs
- [ ] Detect and flag dynamic SQL (EXEC(@sql)) as opaque
- [ ] Extract metadata from sys.columns, sys.dm_exec_procedure_stats, sys.triggers, msdb.dbo.sysjobs
- [ ] Store all entities in SQLite with bi-temporal model (valid_from/until + recorded_at/invalidated_at)
- [ ] Build relationship graph (fk_declared, fk_inferred, joins_with, reads_from, writes_to, feeds_into)
- [ ] SP control flow analysis: IF/ELSE branch extraction, variable tracking, nesting depth
- [ ] State machine extraction from UPDATE SET col=X WHERE col=Y patterns across SPs
- [ ] SP call chain resolution (SP-A calls SP-B calls SP-C)
- [ ] Gap priority queue with 12 detection rules (unlabeled enums, orphan tables, missing joins, stale facts, etc.)
- [ ] Data sampling engine via live DB connection (SELECT DISTINCT, value ranges, row counts)
- [ ] Enum and bitmask auto-detection and labeling from CASE statements, SP names, data sampling
- [ ] Human confirmation skill (dbwiki:confirm) setting confidence=1.0
- [ ] Audit infrastructure discovery (timestamp columns, history tables, system-versioned tables)
- [ ] 4-operation update pipeline (ADD, REINFORCE, CONFLICT, NOOP) adapted from Mem0 pattern
- [ ] SP reliability scoring (recency, execution count, caller count, dynamic SQL, contradictions)
- [ ] Contradiction detection and resolution (SUPERSEDE/KEEP/SPLIT/ESCALATE)
- [ ] Confidence decay and reinforcement across learning loop iterations
- [ ] Alias cluster detection and merging with validation
- [ ] Concept resolution via hybrid search (sqlite-vec embeddings + FTS5 keyword + wiki lookup)
- [ ] Derived metric resolution (teachable business concept to SQL mappings)
- [ ] JOIN path finding via BFS graph traversal (bfsvtab)
- [ ] 6-tier query generation (lookup, aggregation, temporal, statistical, forensic, data quality)
- [ ] SQL validation (parse generated SQL with sqlglot, verify against knowledge store)
- [ ] Self-correcting query loop (error → rewrite → retry)
- [ ] Wiki page generation with L0/L1/L2 tiered context loading (OpenViking pattern)
- [ ] Cross-project pattern database (~/.db-wiki/cross.db) for naming patterns, common enums, schema patterns
- [ ] Background learning loop scheduling (fast/medium/deep/human frequencies)
- [ ] Maturity dashboard (dbwiki:status) with coverage %, gap count, conflict count
- [ ] MCP server with all skills: ingest, ask, explain, search, discover, confirm, define_metric, teach, lineage, state_machine, branch_analysis, forensics, impact, coverage, data_quality, compare, status, lint, history, export, loop, connect
- [ ] CLI interface mirroring all MCP skills for standalone and CI/CD use
- [ ] Configurable embedding provider (local sentence-transformers or OpenAI)
- [ ] Configurable DB connection (works offline from files, enhanced with live DB; prefer live connection)
- [ ] Local web UI for knowledge graph visualization (inspired by codebase-memory-mcp)

### Out of Scope

- Real-time streaming/CDC from database — batch ingest only for v1
- Write operations to target database — strictly read-only
- GUI desktop application — web UI is for graph viewing only, not full app
- Non-SQL Server dialects — T-SQL/MSSQL only for v1, multi-dialect deferred
- OAuth/authentication for MCP server — local use, no auth needed for v1

## Context

- Primary target: Microsoft SQL Server databases with large stored procedure codebases
- User has experience with codebase-memory-mcp (DeusData) and wants similar graph visualization
- Architecture synthesizes patterns from 9 existing tools: codebase-memory-mcp (SQLite graph + BFS), claude-mem (progressive disclosure), Mem0 (4-op pipeline), Graphiti/Zep (bi-temporal model), OpenViking (L0/L1/L2 tiering), LangGraph (self-correcting loops), Cognee (auto-correction), Karpathy LLM Wiki (wiki compilation), LLM Wiki v2 (confidence decay)
- Novel additions: sqlglot AST parsing, domain entity types, data sampling engine, gap priority queue, SP reliability scoring, state machine extraction, query tier system, derived metrics, domain templates, audit discovery, data quality engine
- 5-layer architecture: Ingest → Knowledge Store → Learning Loop → Query Engine → MCP Server + Skills
- 4 agent types: Research Agent, Review Agent, Analyst Agent, Collector Agent
- Hook-driven automation: on_file_change, on_ingest_complete, on_query_success/failure, on_conflict_detected, on_human_confirmation, on_session_start, on_idle, on_schedule

## Constraints

- **Storage**: SQLite only — zero infrastructure, no Neo4j/Docker. Single file knowledge store
- **SQL Parsing**: sqlglot for AST analysis — must handle T-SQL dialect including control flow
- **Language**: Python — for sqlglot, sentence-transformers, and Anthropic MCP SDK compatibility
- **MCP Protocol**: Must conform to Anthropic MCP server specification for Claude Code integration
- **Safety**: All database queries are read-only. Collector Agent has timeout + max rows + query budget limits
- **Privacy**: Local-first. Embedding provider configurable. No data sent externally unless user opts into OpenAI embeddings

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite over Neo4j for graph storage | Zero infrastructure requirement (C6), portable single-file DB, bfsvtab provides BFS traversal | — Pending |
| sqlglot for SQL parsing | Open source, multi-dialect capable, full AST access for both data flow and control flow extraction | — Pending |
| Bi-temporal model from Graphiti | Database knowledge changes over time — must track "when true" vs "when learned" for SP evolution | — Pending |
| L0/L1/L2 tiered context from OpenViking | Token efficiency critical when querying hundreds of tables — load detail progressively | — Pending |
| 4-op update pipeline from Mem0 | Proven framework for knowledge updates — ADD/REINFORCE/CONFLICT/NOOP covers all cases | — Pending |
| Python over TypeScript | sqlglot is Python-native, sentence-transformers ecosystem, MCP SDK available in Python | — Pending |
| SQL Server only for v1 | Focus on one dialect deeply rather than spreading thin across many | — Pending |
| Local web UI for graph visualization | User wants visual graph exploration similar to codebase-memory-mcp | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-10 after initialization*
