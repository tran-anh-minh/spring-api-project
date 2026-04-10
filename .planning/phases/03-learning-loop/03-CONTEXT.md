# Phase 3: Learning Loop - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

The system autonomously identifies knowledge gaps and deepens its understanding through iterative investigation. Implements the 5-phase learning loop (Discover → Investigate → Reason → Validate → Consolidate), gap detection with 12 rules, gap priority scoring, confidence management (decay + reinforcement + conflict resolution), human confirmation, data sampling engine, and the agent framework (Research, Review, Collector, Orchestrator). Exposes learning capabilities via MCP tools (dbwiki:discover, dbwiki:confirm, dbwiki:teach) and CLI commands. Background scheduling deferred to Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Agent Architecture
- **D-01:** Hybrid agents — gap detection and data collection are pure Python code (SQL queries, heuristics). Reasoning and validation use LLM when available, fall back to heuristics when not. System works fully offline, enhanced with LLM.
- **D-02:** Agents communicate via shared SQLite tables — knowledge_gaps, agent_tasks, and agent_results tables. Orchestrator queries these to coordinate. Persistent, auditable, no in-memory coupling.
- **D-03:** LLM provider is configurable — support both Claude (Anthropic) and OpenAI via config setting (e.g., `learning.llm_provider`). User sets API key. No default provider assumption — LLM features are opt-in.
- **D-04:** Collector Agent data sampling — direct pyodbc queries against connected live DB with safety limits (read-only, timeout, max_rows, query_budget from config). Falls back to no-op when no live DB connection is configured.

### Loop Orchestration
- **D-05:** Single-pass sequential execution — one complete cycle: Discover finds all gaps, Investigate processes top-N by priority, Reason analyzes findings, Validate checks conclusions, Consolidate writes approved changes. Each run processes a configurable batch.
- **D-06:** Scheduling deferred to Phase 5 — Phase 3 implements loop logic only. Phase 5 (CLI-05 daemon mode) adds fast/medium/deep/human scheduling frequencies.
- **D-07:** Manual trigger only — user runs `db-wiki discover` (CLI) or calls `dbwiki:discover` (MCP) to start a loop run. No automatic triggers in Phase 3.
- **D-08:** Configurable gap batch size — `learning.max_gaps_per_run` config setting with sensible default (10). User can tune based on patience and LLM budget.

### Gap Detection Rules
- **D-09:** All 12 gap rules implemented together — each rule is a Python function running SQL queries against the knowledge store. Rules: unlabeled enums, orphan tables, missing joins, stale facts, alias clusters, incomplete state machines, unresolved calls, low-confidence facts, cross-SP contradictions, missing FKs, coverage gaps, pattern anomalies.
- **D-10:** Conservative gap detection — only create gaps when concrete evidence exists (e.g., column used in CASE statement but no enum labels, table with zero FK relationships). No speculative gaps from naming heuristics alone.
- **D-11:** Exponential backoff cooldown — gap retry intervals: 1h → 4h → 24h → 72h → 168h. After 5 failed attempts, mark gap as 'permanent' requiring human review. Prevents infinite gap cycling (LEARN-11).
- **D-12:** Gap priority scoring with configurable weights — default formula: severity_weight×0.3 + connectivity×0.25 + query_frequency×0.20 + staleness×0.15 + solvability×0.10. Weights configurable in config.yaml under `learning.gap_weights`.

### Confidence & Conflicts
- **D-13:** Combined confidence decay — light time-based decay (configurable, default 1%/week) as background + stronger event-driven decay when SP body changes, schema changes, or contradicting evidence appears. Reinforcement when new evidence confirms existing fact.
- **D-14:** Automatic conflict resolution with detailed logging — system decides SUPERSEDE/KEEP/SPLIT/ESCALATE based on confidence + recency + independent source count. Full rationale logged. Only ESCALATE to human when score difference < 0.1 (too close to call).
- **D-15:** Human confirmation sets confidence 1.0 with slow decay — `dbwiki:confirm` sets confidence to 1.0 but still allows very slow time decay (0.5%/month). If schema changes make the confirmed fact questionable, flag for re-confirmation rather than auto-invalidate. Respects LEARN-10 spirit while acknowledging schema evolution.
- **D-16:** Simple source counting — each SP is counted as one independent source. No body similarity checking for source deduplication. Multiple SPs confirming same fact increases confidence. Simpler implementation, accepts minor inflation risk.

### SP Reliability Scoring
- **D-17:** SP reliability formula per LEARN-08 — baseline 0.5 with adjustments: +0.1 recent activity, +0.05 per unique caller, -0.2 has dynamic SQL, -0.1 per contradiction, -0.05 partial AST. Capped at [0.0, 1.0]. Stored in sp_reliability table.

### Update Pipeline
- **D-18:** 4-operation update pipeline (LEARN-06, Mem0 pattern) — every fact update classified as ADD (new knowledge), REINFORCE (same fact from new source → confidence boost), CONFLICT (contradicts existing → resolution), or NOOP (already known, no change). Classification based on matching existing facts by entity + attribute.

### Claude's Discretion
- Exact SQLite DDL for knowledge_gaps, agent_tasks, agent_results tables
- Specific gap detection SQL queries for each of the 12 rules
- LLM prompt templates for Research and Review agents
- Collector Agent query generation strategy (which SELECTs to run for each gap type)
- MCP tool input/output schemas for dbwiki:discover, dbwiki:confirm, dbwiki:teach
- CLI command structure for learning loop commands
- Internal data structures for loop state management

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/REQUIREMENTS.md` — Phase 3 requirements: LEARN-01 through LEARN-13, STORE-08, MCP-03, AGENT-01, AGENT-02, AGENT-04, AGENT-05
- `.planning/PROJECT.md` — Core constraints (SQLite only, Python, read-only safety, local-first privacy, configurable embedding)
- `CLAUDE.md` §Technology Stack — pyodbc for live DB, schedule library for background loop (Phase 5), Pydantic for models

### Phase 1 foundation
- `.planning/phases/01-foundation/01-CONTEXT.md` — Bi-temporal model (D-01/D-02), project structure (D-05/D-06), config system (D-07/D-08)

### Phase 2 knowledge graph
- `.planning/phases/02-sp-parsing-knowledge-graph/02-CONTEXT.md` — SP parsing depth (D-01 through D-04), graph traversal (D-05/D-06), confidence scoring patterns (D-14/D-15), schema extensions (D-18/D-19)

### Existing code
- `db_wiki/core/schema.py` — Current schema DDL with all bi-temporal tables, views, and Phase 2 intelligence tables
- `db_wiki/core/store.py` — Store connection management, sqlite-vec loading pattern
- `db_wiki/core/models.py` — Pydantic model patterns for SP entities (SPInfo, BranchInfo, EnumDetection, etc.)
- `db_wiki/graph/bfs.py` — BFS graph traversal implementation (reusable for gap connectivity scoring)
- `db_wiki/search/hybrid.py` — Hybrid search (usable for concept resolution in gap investigation)
- `db_wiki/server/app.py` — MCP tool registration pattern via FastMCP @mcp.tool() decorator
- `db_wiki/cli/app.py` — CLI command registration pattern via Typer
- `db_wiki/core/config.py` — YAML config loading pattern (extend for learning section)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db_wiki/core/schema.py` — Bi-temporal table + view template pattern. New tables (knowledge_gaps, agent_tasks, agent_results) follow the same CREATE TABLE IF NOT EXISTS + current_* view pattern.
- `db_wiki/core/models.py` — Pydantic BaseModel pattern. Agent models (GapInfo, AgentTask, AgentResult) follow the same pattern.
- `db_wiki/core/store.py` — open_store() + init_schema() pattern. Phase 3 extends SCHEMA_SQL with new tables.
- `db_wiki/graph/bfs.py` — BFS with edge type filtering and cycle detection. Reusable for computing gap connectivity scores.
- `db_wiki/search/hybrid.py` — Hybrid vector+FTS5 search. Reusable for concept resolution during gap investigation.
- `db_wiki/server/app.py` — @mcp.tool() decorator + AppContext pattern. New MCP tools (discover, confirm, teach) follow same pattern.
- `db_wiki/core/config.py` — Pydantic config model with nested sections. Extend with `learning` section for gap weights, batch size, decay rates, LLM provider settings.

### Established Patterns
- Bi-temporal: every entity table has valid_from/valid_until/recorded_at/invalidated_at with dual format (TEXT + INTEGER)
- Current views: current_* views filter to active rows (valid_until IS NULL AND invalidated_at IS NULL)
- Parameterized SQL: all queries use ? placeholders (security)
- Transaction wrapping: try/commit/except/rollback for multi-statement operations
- Tolerant processing: skip and log errors, don't fail entire operations

### Integration Points
- `db_wiki/core/schema.py` SCHEMA_SQL — new tables appended here
- `db_wiki/server/app.py` — new MCP tools (discover, confirm, teach) added here
- `db_wiki/cli/app.py` — new CLI commands (discover, confirm, teach) added here
- `db_wiki/core/config.py` — new `learning` config section added here
- `pyproject.toml` — potential new dependency: anthropic SDK and/or openai SDK (optional, for LLM-powered agents)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- **Background scheduling** (LEARN-13) — deferred to Phase 5 (CLI-05 daemon mode). Phase 3 implements manual-trigger-only loop logic.
- **Body similarity checking for source independence** — decided to use simple source counting (D-16). Could revisit if confidence inflation becomes a real problem.
- **Variable tracking through SP execution paths** — carried forward from Phase 2 deferred. Could enable richer gap detection but high complexity.

</deferred>

---

*Phase: 03-learning-loop*
*Context gathered: 2026-04-10*
