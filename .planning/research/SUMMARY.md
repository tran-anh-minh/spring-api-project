# Research Summary: DB Wiki

**Synthesized:** 2026-04-10
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

## Executive Summary

db-wiki is a local-first, zero-infrastructure knowledge engine for legacy SQL Server databases. It ingests DDL and stored procedure bodies via sqlglot AST parsing, builds a bi-temporal knowledge graph in a single SQLite file, and exposes the result as an MCP tool for Claude Code. The correct architecture mirrors codebase-memory-mcp: a shared skill layer called by both MCP server and CLI, read-only agent workers, and all knowledge mutations gated through a Review Agent before application. The query path follows the OpenViking L0/L1/L2 tiered context pattern to keep LLM prompts under 8K tokens regardless of schema size.

## Recommended Stack

| Component | Choice | Confidence |
|-----------|--------|------------|
| Language | Python 3.11+ | HIGH |
| SQL Parsing | sqlglot 25.x (T-SQL dialect) | MEDIUM |
| Storage | SQLite + bi-temporal schema | HIGH |
| Vector Search | sqlite-vec (384-dim for local, 1536 for OpenAI) | MEDIUM |
| Full-Text Search | SQLite FTS5 | HIGH |
| Graph Traversal | bfsvtab (with Python BFS fallback) | LOW |
| MCP Server | Anthropic MCP Python SDK (FastMCP) | HIGH |
| CLI | Typer | HIGH |
| Local Embeddings | sentence-transformers all-MiniLM-L6-v2 (22MB) | HIGH |
| OpenAI Embeddings | text-embedding-3-small (configurable) | HIGH |
| Web UI Graph | vis.js Network | HIGH |
| Web Server | starlette/uvicorn (embedded in Python package) | HIGH |
| DB Connection | pyodbc (SQL Server) | HIGH |

## Table Stakes Features

- DDL parsing into tables, columns, constraints, indexes
- FK relationship detection (declared + inferred)
- Natural language to SQL query generation (Core Value)
- MCP protocol compliance for Claude Code integration
- CLI interface mirroring all MCP skills
- Zero-infrastructure setup (single SQLite file)
- Offline-capable operation (files only, enhanced with live DB)
- Entity search (hybrid: vector + FTS5 + wiki)
- Status/coverage dashboard
- Ingest progress feedback

## Key Differentiators

- SP AST parsing for documentation (nobody does this)
- Self-learning loop with gap detection (5-phase: Discover/Investigate/Reason/Validate/Consolidate)
- Enum and bitmask auto-labeling from CASE statements + SP names + data sampling
- State machine extraction from UPDATE patterns
- SP reliability scoring
- Confidence decay + bi-temporal knowledge tracking
- Derived metric mapping (teachable business concepts)
- L0/L1/L2 tiered context loading for token efficiency
- Local web UI for knowledge graph visualization

## Anti-Features (Do NOT Build)

- Real-time CDC/streaming
- Write operations to target DB
- Multi-dialect support in v1
- Electron desktop app
- Multi-user authentication
- LLM-dependent extraction for structural parsing
- Chatbot UI in web page (MCP IS the chat interface)

## Critical Risks

### 1. sqlglot T-SQL Silent Failures (HIGH)
sqlglot returns partial ASTs for procedural T-SQL (cursors, MERGE, TRY...CATCH, INSERT...EXEC) without errors. **Prevention:** Check for `exp.Anonymous` nodes after every parse, track `parse_quality` per SP, set threshold at 5%.

### 2. MCP stdio Blocking (HIGH)
Long-running skills block Claude Code's stdio channel, causing timeout/disconnect. **Prevention:** Async-first skill design from day 1 — return job ID immediately, execute in background, expose status/poll.

### 3. Learning Loop Pathologies (MEDIUM)
Three failure modes: confidence drift (REINFORCE without decay), infinite gap cycling, hallucinated agreement (copy-paste SPs inflating confidence). **Prevention:** Design confidence decay formula, gap cooldown history, and source independence weighting before first loop iteration.

### 4. sqlite-vec Performance (MEDIUM)
Without HNSW indexing, vector search degrades non-linearly at 50k+ entities. **Prevention:** Hybrid FTS5-first + vector-on-filtered-set architecture. Benchmark during Phase 2, not Phase 4.

### 5. Bi-temporal Query Leaks (MEDIUM)
Raw table queries bypass temporal views, surfacing invalidated facts. **Prevention:** Create views immediately after schema, enforce all app code goes through views.

## Architecture Summary

- **5 layers:** Ingest → Knowledge Store → Learning Loop → Query Engine → MCP Server + Skills
- **Shared skill layer:** `core/skills/` called identically by MCP, CLI, and Web UI
- **Agent isolation:** Read-only workers return reports; only Orchestrator mutates knowledge store
- **4 agents:** Research, Review, Analyst, Collector — all produce structured reports, never direct mutations
- **Transport:** MCP (stdio JSON-RPC) + CLI (Typer) + Web (starlette) — all calling same skill functions

## Suggested Phase Structure

| Phase | Focus | Key Deliverables |
|-------|-------|-----------------|
| 1 | Foundation | SQLite bi-temporal schema + views, DDL parser, async MCP/CLI skeleton |
| 2 | SP Parsing + Knowledge Graph | sqlglot SP AST with parse quality gate, relationship graph, BFS, sqlite-vec benchmark |
| 3 | Learning Loop | 5-phase orchestrator, gap queue, agents, confidence decay, enum labeling, human confirmation |
| 4 | Query Engine | Concept resolver, BFS path finder, L0/L1/L2 context, SQL generation, self-correcting retry |
| 5 | Web UI + Cross-Project + Polish | vis.js graph visualization, cross-project DB, background scheduler, export |

## Open Questions

1. sqlite-vec HNSW index availability in current release — verify at Phase 2 start
2. bfsvtab PyPI package name — may need compile from source; Python BFS fallback ready
3. sqlglot T-SQL procedural AST completeness — build 20-SP test corpus before Phase 2
4. Dynamic SQL percentage in target codebase — if >40%, coverage ceiling may be too low
5. MCP SDK FastMCP API stability — verify current 1.x docs before pinning

---
*Synthesized: 2026-04-10*
