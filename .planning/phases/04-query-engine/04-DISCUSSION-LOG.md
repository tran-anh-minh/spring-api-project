# Phase 4: Query Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 04-query-engine
**Areas discussed:** NL-to-SQL Strategy, Context Assembly, Self-correcting Loop, MCP/CLI Tool Surface

---

## NL-to-SQL Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| LLM generates SQL directly | Feed schema context + NL question to LLM, get T-SQL back. Hybrid search resolves concepts, BFS finds JOIN paths. | ✓ |
| Template + LLM hybrid | Pre-built templates for common patterns, LLM fallback for complex queries. | |
| Template-only, no LLM | Pure template-based, deterministic, limited to anticipated patterns. | |

**User's choice:** LLM generates SQL directly
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Classify tier first | Classify question tier, use tier-specific context assembly and SQL generation. | ✓ |
| Unified pipeline | Same pipeline for all queries. | |

**User's choice:** Classify tier first
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Store as SQL fragments | dbwiki:define_metric stores SQL expression + source tables. Substitute into queries. | ✓ |
| Store as semantic definitions | Store NL definition + example SQL. LLM re-derives each time. | |

**User's choice:** Store as SQL fragments
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| LLM required for ask/explain | Query generation needs LLM. Search/lineage work offline. | |
| Full offline fallback | Template-based fallback when no LLM. Every tool works without API keys. | ✓ |

**User's choice:** Full offline fallback
**Notes:** Diverged from recommended — user wants every tool to work without API keys.

---

## Context Assembly (L0/L1/L2)

| Option | Description | Selected |
|--------|-------------|----------|
| Relevance-scored tiers | L0 for all, L1 for search/BFS-related, L2 for core referenced. Score-based cutoffs. | ✓ |
| Fixed-depth tiers | L2 for mentioned, L1 for 1-hop, L0 for 2-hop. | |
| LLM-selected tiers | Two-pass: LLM picks which tables need detail. | |

**User's choice:** Relevance-scored tiers
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| On-demand at query time | Generate/cache wiki content when queried. Invalidate on fact changes. | ✓ |
| Batch after learning loop | Generate all wiki pages after each loop run. | |
| Background lazy generation | Generate in background on ingest, update incrementally. | |

**User's choice:** On-demand at query time
**Notes:** None

---

## Self-correcting Loop

| Option | Description | Selected |
|--------|-------------|----------|
| Parse-validate-retry | Parse with sqlglot, verify in knowledge store, retry on failure. Max 3 attempts. | ✓ |
| Execute-and-retry | Execute against live DB, catch errors, retry with real error messages. | |
| Both: validate first, then execute | Parse-validate as gate, then optionally execute. | |

**User's choice:** Parse-validate-retry
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Query decomposition | Analyst Agent breaks tier 3+ queries into sub-queries, resolves each, composes final SQL. | ✓ |
| Always single-pass | No decomposition, single LLM call for all queries. | |

**User's choice:** Query decomposition
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Cache generated SQL | Cache question hash to generated SQL. Invalidate on schema/knowledge changes. | ✓ |
| No caching | Every question goes through full pipeline. | |

**User's choice:** Cache generated SQL
**Notes:** None

---

## MCP/CLI Tool Surface

| Option | Description | Selected |
|--------|-------------|----------|
| Core query tools first | ask, explain, define_metric, execute. Analysis tools deferred to Phase 5. | |
| All MCP-04/MCP-05 tools | Full 15+ tool surface in Phase 4. | |
| Query tools + analysis tools | All query + analysis tools. Only manage tools deferred to Phase 5. | ✓ |

**User's choice:** Query tools + analysis tools
**Notes:** Broader scope than recommended — user wants analysis tools in Phase 4.

| Option | Description | Selected |
|--------|-------------|----------|
| SQL + optional execution | Always return SQL. Execute only with --execute flag. | ✓ |
| Always execute if connected | Auto-execute when live DB available. | |
| Separate execute tool | dbwiki:ask returns SQL only, separate dbwiki:execute tool. | |

**User's choice:** SQL + optional execution
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Wiki page + relationships | Full L1/L2 wiki page with columns, constraints, relationships, enum labels. | ✓ |
| Minimal summary only | Short description + key relationships. | |

**User's choice:** Wiki page + relationships
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Visual output (Mermaid) | state_machine returns Mermaid diagram + text. branch_analysis returns structured report. | ✓ |
| Text-only output | Plain text descriptions only. | |
| Both formats | Mermaid + text, client picks. | |

**User's choice:** Visual output (Mermaid)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Knowledge store analysis | Analysis tools operate on knowledge store only. No live DB required. | ✓ |
| Live DB + knowledge store | Combine knowledge store with live DB queries for richer analysis. | |

**User's choice:** Knowledge store analysis
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Table + JSON flag | Rich table default, --json for structured, --sql-only for raw SQL. | ✓ |
| JSON-first | Default JSON, --pretty for table. | |

**User's choice:** Table + JSON flag
**Notes:** Consistent with Phase 2 CLI patterns.

---

## Claude's Discretion

- LLM prompt templates for SQL generation and query decomposition
- Relevance scoring algorithm for L0/L1/L2 tier assignment
- Token counting strategy for 8K budget
- Query tier classification heuristics
- SQL template library for offline mode
- Cache implementation details
- Mermaid diagram formatting
- Pydantic models for input/output schemas

## Deferred Ideas

- Manage tools (status, lint, history, export, loop) — Phase 5
- Live DB queries for analysis tools — future enhancement
- Two-pass LLM context selection — optimization if needed
