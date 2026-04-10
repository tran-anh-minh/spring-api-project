# Phase 3: Learning Loop - Research

**Researched:** 2026-04-10
**Domain:** Autonomous knowledge gap detection, confidence management, agent orchestration, SQLite-backed update pipeline
**Confidence:** HIGH (codebase fully verified; all patterns from existing Phases 1-2 code confirmed)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Hybrid agents — gap detection and data collection are pure Python code (SQL queries, heuristics). Reasoning and validation use LLM when available, fall back to heuristics when not. System works fully offline, enhanced with LLM.
- **D-02:** Agents communicate via shared SQLite tables — knowledge_gaps, agent_tasks, and agent_results tables. Orchestrator queries these to coordinate. Persistent, auditable, no in-memory coupling.
- **D-03:** LLM provider is configurable — support both Claude (Anthropic) and OpenAI via config setting (`learning.llm_provider`). User sets API key. No default provider assumption — LLM features are opt-in.
- **D-04:** Collector Agent data sampling — direct pyodbc queries against connected live DB with safety limits (read-only, timeout, max_rows, query_budget from config). Falls back to no-op when no live DB connection is configured.
- **D-05:** Single-pass sequential execution — one complete cycle: Discover finds all gaps, Investigate processes top-N by priority, Reason analyzes findings, Validate checks conclusions, Consolidate writes approved changes. Each run processes a configurable batch.
- **D-06:** Scheduling deferred to Phase 5.
- **D-07:** Manual trigger only — user runs `db-wiki discover` (CLI) or calls `dbwiki:discover` (MCP) to start a loop run.
- **D-08:** Configurable gap batch size — `learning.max_gaps_per_run` config setting with default 10.
- **D-09:** All 12 gap rules implemented together.
- **D-10:** Conservative gap detection — only create gaps when concrete evidence exists.
- **D-11:** Exponential backoff cooldown — 1h → 4h → 24h → 72h → 168h. After 5 failed attempts, mark 'permanent'.
- **D-12:** Gap priority scoring: severity_weight×0.3 + connectivity×0.25 + query_frequency×0.20 + staleness×0.15 + solvability×0.10. Weights configurable.
- **D-13:** Combined confidence decay — 1%/week light time-based + event-driven decay on SP body changes/contradictions. Reinforcement on confirming evidence.
- **D-14:** Automatic conflict resolution with logging — SUPERSEDE/KEEP/SPLIT/ESCALATE based on confidence + recency + source count. ESCALATE only when score diff < 0.1.
- **D-15:** Human confirmation sets confidence 1.0 with very slow decay (0.5%/month). Flag for re-confirmation on schema change rather than auto-invalidate.
- **D-16:** Simple source counting — each SP = one independent source.
- **D-17:** SP reliability formula: baseline 0.5 + adjustments for recency/callers/dynamic SQL/contradictions/partial AST. Stored in sp_reliability table.
- **D-18:** 4-operation update pipeline: ADD, REINFORCE, CONFLICT, NOOP. Classification by matching entity + attribute.

### Claude's Discretion

- Exact SQLite DDL for knowledge_gaps, agent_tasks, agent_results tables
- Specific gap detection SQL queries for each of the 12 rules
- LLM prompt templates for Research and Review agents
- Collector Agent query generation strategy
- MCP tool input/output schemas for dbwiki:discover, dbwiki:confirm, dbwiki:teach
- CLI command structure for learning loop commands
- Internal data structures for loop state management

### Deferred Ideas (OUT OF SCOPE)

- Background scheduling (LEARN-13) — deferred to Phase 5
- Body similarity checking for source independence
- Variable tracking through SP execution paths
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LEARN-01 | Five-phase learning loop: Discover → Investigate → Reason → Validate → Consolidate | Loop orchestration patterns section |
| LEARN-02 | Gap detection with 12 rules | Gap detection SQL patterns section |
| LEARN-03 | Gap priority scoring formula | Priority scoring section |
| LEARN-04 | Data sampling engine via live DB (pyodbc) | Collector Agent section |
| LEARN-05 | Enum and bitmask auto-detection from CASE/SP names/sampling | Enum detection section; Phase 2 EnumDetection model reusable |
| LEARN-06 | 4-operation update pipeline: ADD, REINFORCE, CONFLICT, NOOP | Update pipeline section |
| LEARN-07 | Conflict resolution: SUPERSEDE, KEEP, SPLIT, ESCALATE | Conflict resolution section |
| LEARN-08 | SP reliability scoring | SP reliability section; existing sp_reliability table reusable |
| LEARN-09 | Confidence decay over time with reinforcement | Confidence management section |
| LEARN-10 | Human confirmation (dbwiki:confirm) setting confidence=1.0 | MCP/CLI section |
| LEARN-11 | Gap cooldown history to prevent infinite cycling | knowledge_gaps DDL + cooldown section |
| LEARN-12 | Source independence weighting | Simple source counting (D-16) |
| LEARN-13 | Background loop scheduling | DEFERRED to Phase 5 |
| STORE-08 | Knowledge gaps table with severity, attempt count, cooldown history | Schema DDL section |
| MCP-03 | Learn skills: dbwiki:discover, dbwiki:confirm, dbwiki:teach | MCP tool section |
| AGENT-01 | Research Agent: deep investigation before knowledge updates | Agent architecture section |
| AGENT-02 | Review Agent: quality gate before mutations | Agent architecture section |
| AGENT-04 | Collector Agent: systematic data gathering with safety limits | Collector Agent section |
| AGENT-05 | Orchestrator: coordinates loop, spawns agents, applies approved changes | Loop orchestration section |
</phase_requirements>

---

## Summary

Phase 3 builds the learning engine on top of Phases 1-2 foundations. The codebase already has the bi-temporal store, SP parsing, FTS5 + vector search, and BFS graph traversal — all reusable from Phase 3. The primary new work is: three new SQLite tables (knowledge_gaps, agent_tasks, agent_results), a 12-rule gap detector, a gap priority scorer, a 4-operation update pipeline with conflict resolution, confidence decay mechanics, SP reliability scoring, a Collector Agent for live-DB sampling, and MCP/CLI exposure of the learning loop.

The architecture is firmly locked (D-01 through D-18). The key insight is that agents are **pure Python functions**, not threads or processes — they run synchronously within a single loop invocation. The Orchestrator is the function that calls them in sequence, reading/writing shared SQLite tables at each step. LLM calls are optional and gated by config; every step has a pure-Python fallback.

The most complex single piece is the gap detection module: 12 rules each expressed as SQL queries against the existing Phase 2 tables. The second most complex is conflict resolution, which requires a scoring function that compares two existing facts and decides SUPERSEDE/KEEP/SPLIT/ESCALATE.

**Primary recommendation:** Build Phase 3 as a new `db_wiki/learning/` package. Each agent is a module. The loop orchestrator is `db_wiki/learning/orchestrator.py`. Gap rules are individual functions in `db_wiki/learning/gap_detector.py`. Confidence management lives in `db_wiki/learning/confidence.py`. The update pipeline lives in `db_wiki/learning/pipeline.py`.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python sqlite3 | stdlib | knowledge_gaps / agent_tasks / agent_results tables | Same pattern as all Phase 1-2 tables |
| pydantic | 2.12+ | GapInfo, AgentTask, AgentResult models | Established pattern in models.py |
| pyodbc | 4.x | Collector Agent live DB queries | Config-driven, falls back to no-op (D-04) |
| anthropic SDK | 0.x | Research/Review Agent LLM calls | Optional — only when `learning.llm_provider=claude` |
| openai SDK | 1.x | Research/Review Agent LLM calls | Optional — only when `learning.llm_provider=openai` |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| db_wiki.graph.bfs | (local) | Gap connectivity score (hops from entity to other entities) | Priority scoring: connectivity component |
| db_wiki.search.hybrid | (local) | Concept resolution during gap investigation | Research Agent: find related entities |
| db_wiki.search.fts | (local) | FTS sync before gap investigation queries | Ensure FTS index fresh |
| db_wiki.core.schema | (local) | Extend SCHEMA_SQL with Phase 3 tables | Append to existing SCHEMA_SQL constant |

### New Optional Dependencies

```toml
# pyproject.toml additions
[project.optional-dependencies]
llm = ["anthropic>=0.30,<1", "openai>=1.0,<2"]
live-db = ["pyodbc>=4.0,<5"]
```

**Version verification:** [VERIFIED: pyproject.toml] — anthropic and openai are NOT currently installed. They must be added as optional deps. pyodbc is also absent.

**Installation:**
```bash
# For LLM-enhanced learning (optional)
uv add --optional llm anthropic openai
# For live DB sampling (optional)
uv add --optional live-db pyodbc
```

---

## Architecture Patterns

### Recommended Project Structure

```
db_wiki/
├── learning/
│   ├── __init__.py
│   ├── orchestrator.py     # Discover→Investigate→Reason→Validate→Consolidate loop
│   ├── gap_detector.py     # 12 gap detection rules as SQL-based functions
│   ├── gap_scorer.py       # Priority scoring formula (D-12)
│   ├── pipeline.py         # 4-op update pipeline: ADD/REINFORCE/CONFLICT/NOOP (D-18)
│   ├── confidence.py       # Decay, reinforcement, conflict resolution (D-13/D-14/D-15)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── research.py     # Research Agent (AGENT-01): LLM-powered deep investigation
│   │   ├── review.py       # Review Agent (AGENT-02): quality gate
│   │   ├── collector.py    # Collector Agent (AGENT-04): live DB sampling via pyodbc
│   │   └── base.py         # Shared AgentResult type, LLM client helpers
│   └── schema_ext.py       # New DDL: knowledge_gaps, agent_tasks, agent_results
```

### Pattern 1: New Table DDL — Follow Bi-Temporal Template

Every new table follows the exact pattern in `db_wiki/core/schema.py`. [VERIFIED: schema.py lines 13-38]

```python
# Source: db_wiki/core/schema.py pattern
LEARNING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_type            TEXT NOT NULL,   -- 'unlabeled_enum'|'orphan_table'|'missing_join'|...
    entity_type         TEXT NOT NULL,   -- 'table'|'column'|'procedure'|'relationship'
    entity_id           INTEGER,         -- references the affected entity (nullable)
    entity_name         TEXT NOT NULL,   -- human-readable name for display
    description         TEXT,
    severity            REAL NOT NULL DEFAULT 0.5,   -- 0.0-1.0
    priority_score      REAL NOT NULL DEFAULT 0.0,   -- computed by gap_scorer
    status              TEXT NOT NULL DEFAULT 'open', -- 'open'|'investigating'|'resolved'|'permanent'
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    cooldown_until      TEXT,            -- ISO datetime after which gap may be re-processed
    cooldown_until_ts   INTEGER,         -- epoch seconds
    last_attempt_at     TEXT,
    last_attempt_at_ts  INTEGER,
    resolution_notes    TEXT,
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_status
    ON knowledge_gaps(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_priority
    ON knowledge_gaps(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_valid_from_ts
    ON knowledge_gaps(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_recorded_at_ts
    ON knowledge_gaps(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_knowledge_gaps AS
SELECT * FROM knowledge_gaps
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_tasks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id              INTEGER NOT NULL REFERENCES knowledge_gaps(id),
    agent_type          TEXT NOT NULL,   -- 'research'|'review'|'collector'
    status              TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'running'|'done'|'failed'
    input_json          TEXT,            -- JSON blob: task parameters
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_gap_id
    ON agent_tasks(gap_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_status
    ON agent_tasks(status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_valid_from_ts
    ON agent_tasks(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_recorded_at_ts
    ON agent_tasks(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_agent_tasks AS
SELECT * FROM agent_tasks
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;

-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id             INTEGER NOT NULL REFERENCES agent_tasks(id),
    agent_type          TEXT NOT NULL,
    success             INTEGER NOT NULL DEFAULT 0,   -- 0 or 1
    findings_json       TEXT,            -- structured JSON: facts found, confidence, sources
    rationale           TEXT,            -- human-readable explanation
    approved            INTEGER,         -- NULL=pending, 1=approved, 0=rejected (Review Agent sets this)
    -- bi-temporal columns
    valid_from          TEXT NOT NULL,
    valid_from_ts       INTEGER NOT NULL,
    valid_until         TEXT,
    valid_until_ts      INTEGER,
    recorded_at         TEXT NOT NULL,
    recorded_at_ts      INTEGER NOT NULL,
    invalidated_at      TEXT,
    invalidated_at_ts   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_agent_results_task_id
    ON agent_results(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_results_valid_from_ts
    ON agent_results(valid_from_ts);
CREATE INDEX IF NOT EXISTS idx_agent_results_recorded_at_ts
    ON agent_results(recorded_at_ts);

CREATE VIEW IF NOT EXISTS current_agent_results AS
SELECT * FROM agent_results
WHERE valid_until IS NULL
  AND invalidated_at IS NULL;
"""
```

**Integration point:** Append LEARNING_SCHEMA_SQL to SCHEMA_SQL in `db_wiki/core/schema.py`, OR import and concatenate in `db_wiki/learning/schema_ext.py` and call from `init_schema()`. The latter keeps Phase 3 additions isolated. [ASSUMED] — either approach works; recommend separate file for cleaner phase boundaries.

### Pattern 2: Config Extension — Pydantic Nested Model

[VERIFIED: db_wiki/core/config.py] — existing pattern uses Pydantic nested BaseModel sections.

```python
# Source: db_wiki/core/config.py extension pattern
class LearningGapWeightsConfig(BaseModel):
    severity: float = 0.30
    connectivity: float = 0.25
    query_frequency: float = 0.20
    staleness: float = 0.15
    solvability: float = 0.10

class LearningConfig(BaseModel):
    max_gaps_per_run: int = 10
    llm_provider: str | None = None   # None = offline mode; "claude" or "openai"
    llm_api_key: str | None = None
    llm_model: str | None = None      # e.g. "claude-opus-4-5", "gpt-4o"
    decay_rate_weekly: float = 0.01   # 1% per week (D-13)
    decay_rate_confirmed_monthly: float = 0.005  # 0.5%/month for human-confirmed (D-15)
    conflict_escalate_threshold: float = 0.1  # ESCALATE when score diff < 0.1 (D-14)
    cooldown_hours: list[int] = [1, 4, 24, 72, 168]  # D-11
    max_attempts_before_permanent: int = 5   # D-11
    collector_timeout_seconds: int = 10
    collector_max_rows: int = 100
    collector_query_budget: int = 20
    gap_weights: LearningGapWeightsConfig = LearningGapWeightsConfig()

# Add to DBWikiConfig:
# learning: LearningConfig = LearningConfig()
```

### Pattern 3: MCP Tool — @mcp.tool() Decorator

[VERIFIED: db_wiki/server/app.py] — existing tools use `@mcp.tool()` + `ctx: Context` + `app_ctx: AppContext = ctx.request_context.lifespan_context`.

```python
# Source: db_wiki/server/app.py pattern
@mcp.tool()
async def discover(ctx: Context, max_gaps: int = 10) -> str:
    """Run a learning loop: detect knowledge gaps and investigate top N.

    Args:
        max_gaps: Maximum gaps to investigate in this run (default 10).

    Returns:
        Summary of gaps found, investigated, and facts updated.
    """
    app_ctx: AppContext = ctx.request_context.lifespan_context
    config = load_config(app_ctx.store_path)
    from db_wiki.learning.orchestrator import run_learning_loop
    summary = run_learning_loop(app_ctx.conn, config)
    return summary

@mcp.tool()
async def confirm(
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
    ctx: Context,
) -> str:
    """Confirm a fact as human-verified (sets confidence to 1.0, LEARN-10).

    Args:
        entity_type: "table", "column", "procedure", "enum", etc.
        entity_name: Name of the entity.
        attribute: Which attribute is confirmed (e.g., "description", "enum_label").
        value: The confirmed value.
    """
    ...

@mcp.tool()
async def teach(
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
    ctx: Context,
) -> str:
    """Teach the system a new fact directly (human-injected knowledge).

    Adds the fact with confidence=1.0 and human_confirmed=True.
    """
    ...
```

### Pattern 4: Orchestrator — Sequential Phase Execution

```python
# Source: Architecture decision D-05
def run_learning_loop(conn: sqlite3.Connection, config: DBWikiConfig) -> str:
    """Single-pass: Discover → Investigate → Reason → Validate → Consolidate."""
    from db_wiki.learning.gap_detector import detect_all_gaps
    from db_wiki.learning.gap_scorer import score_and_prioritize
    from db_wiki.learning.agents.collector import collect_evidence
    from db_wiki.learning.agents.research import research_gap
    from db_wiki.learning.agents.review import review_findings
    from db_wiki.learning.pipeline import apply_findings

    now_ts = int(time.time())
    now_iso = datetime.utcnow().isoformat()

    # Phase 1: Discover
    new_gaps = detect_all_gaps(conn, now_ts, now_iso)
    upsert_gaps(conn, new_gaps)  # dedup by (gap_type, entity_id, entity_name)

    # Phase 2: Select top-N eligible gaps
    batch = get_eligible_gaps(conn, config.learning.max_gaps_per_run, now_ts)

    approved_count = 0
    for gap in batch:
        # Phase 3: Investigate — Collector gathers evidence
        task_id = create_task(conn, gap.id, "collector")
        evidence = collect_evidence(conn, gap, config)
        save_result(conn, task_id, evidence)

        # Phase 4: Reason — Research Agent analyzes
        task_id = create_task(conn, gap.id, "research")
        findings = research_gap(conn, gap, evidence, config)
        save_result(conn, task_id, findings)

        # Phase 5: Validate — Review Agent approves/rejects
        task_id = create_task(conn, gap.id, "review")
        review = review_findings(conn, gap, findings, config)
        save_result(conn, task_id, review)

        if review.approved:
            # Consolidate — apply to knowledge store
            apply_findings(conn, gap, findings, now_ts, now_iso)
            mark_gap_resolved(conn, gap.id, now_ts, now_iso)
            approved_count += 1
        else:
            bump_attempt_count(conn, gap.id, config.learning)

    return f"Discovered {len(new_gaps)} gaps, processed {len(batch)}, approved {approved_count}"
```

### Pattern 5: Gap Detection — SQL Query per Rule

Each of the 12 rules queries existing Phase 2 tables. All use parameterized SQL via `?` placeholders.

```python
# Source: Phase 2 tables: enum_values, db_tables, db_relationships, db_columns
# Verified column names from db_wiki/core/schema.py

def detect_unlabeled_enums(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 1: Columns with CASE-detected values but no enum_label."""
    rows = conn.execute("""
        SELECT DISTINCT ev.table_name, ev.column_name, COUNT(*) as cnt
        FROM current_enum_values ev
        WHERE ev.enum_label IS NULL OR ev.enum_label = ''
        GROUP BY ev.table_name, ev.column_name
        HAVING cnt > 0
    """).fetchall()
    return [GapInfo(gap_type="unlabeled_enum", entity_type="column",
                    entity_name=f"{r['table_name']}.{r['column_name']}",
                    severity=0.7) for r in rows]

def detect_orphan_tables(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 2: Tables with zero relationships in either direction."""
    rows = conn.execute("""
        SELECT t.id, t.table_name
        FROM current_db_tables t
        WHERE NOT EXISTS (
            SELECT 1 FROM current_db_relationships r
            WHERE r.source_id = t.id OR r.target_id = t.id
        )
    """).fetchall()
    return [GapInfo(gap_type="orphan_table", entity_type="table",
                    entity_id=r["id"], entity_name=r["table_name"],
                    severity=0.5) for r in rows]

def detect_missing_joins(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 3: Column pairs that appear in JOINs but have no FK relationship."""
    # SP branches contain tables_touched_json; relationships exist for declared FKs.
    # Find table pairs co-appearing in JOIN branches without a declared fk_ relationship.
    rows = conn.execute("""
        SELECT r.source_id, r.target_id, r.relationship_type
        FROM current_db_relationships r
        WHERE r.relationship_type = 'joins_with'
          AND NOT EXISTS (
            SELECT 1 FROM current_db_relationships r2
            WHERE r2.source_id = r.source_id AND r2.target_id = r.target_id
              AND r2.relationship_type IN ('fk_declared', 'fk_inferred')
          )
    """).fetchall()
    return [GapInfo(gap_type="missing_join", entity_type="relationship",
                    entity_id=r["source_id"],
                    entity_name=f"rel_{r['source_id']}_to_{r['target_id']}",
                    severity=0.6) for r in rows]

def detect_stale_facts(conn: sqlite3.Connection, staleness_days: int = 90) -> list[GapInfo]:
    """Rule 4: Facts not reinforced for > staleness_days and confidence < 0.7."""
    threshold_ts = int(time.time()) - staleness_days * 86400
    rows = conn.execute("""
        SELECT ev.table_name, ev.column_name, ev.confidence, ev.recorded_at_ts
        FROM current_enum_values ev
        WHERE ev.confidence < 0.7 AND ev.recorded_at_ts < ?
    """, (threshold_ts,)).fetchall()
    return [GapInfo(gap_type="stale_fact", entity_type="column",
                    entity_name=f"{r['table_name']}.{r['column_name']}",
                    severity=0.4) for r in rows]

def detect_alias_clusters(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 5: Columns with aliases but no canonical name confirmed."""
    rows = conn.execute("""
        SELECT ca.table_name, ca.column_name, COUNT(*) as alias_count
        FROM current_column_aliases ca
        GROUP BY ca.table_name, ca.column_name
        HAVING alias_count > 1
    """).fetchall()
    return [GapInfo(gap_type="alias_cluster", entity_type="column",
                    entity_name=f"{r['table_name']}.{r['column_name']}",
                    severity=0.3) for r in rows]

def detect_incomplete_state_machines(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 6: State transitions where terminal states have outgoing transitions
    (likely missing transitions) or no transitions defined at all for columns
    that appear in UPDATE SET patterns."""
    # Detect columns that appear in state_transitions but have isolated states
    # (states that only appear as from_value OR only as to_value, but not both,
    # suggesting the graph is incomplete).
    rows = conn.execute("""
        SELECT table_name, column_name, from_value as state
        FROM current_state_transitions
        UNION
        SELECT table_name, column_name, to_value
        FROM current_state_transitions
    """).fetchall()
    # Group by table+column; flag if < 2 transitions exist (incomplete)
    from collections import defaultdict
    counts: dict = defaultdict(int)
    for r in rows:
        key = (r["table_name"], r["column_name"])
        counts[key] += 1
    gaps = []
    for (tbl, col), cnt in counts.items():
        if cnt < 2:
            gaps.append(GapInfo(gap_type="incomplete_state_machine",
                                entity_type="column",
                                entity_name=f"{tbl}.{col}", severity=0.6))
    return gaps

def detect_unresolved_calls(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 7: SP call chains where callee_id IS NULL (unresolved)."""
    rows = conn.execute("""
        SELECT cc.caller_id, cc.callee_name_raw, p.procedure_name
        FROM current_sp_call_chains cc
        JOIN current_db_procedures p ON cc.caller_id = p.id
        WHERE cc.is_resolved = 0
    """).fetchall()
    return [GapInfo(gap_type="unresolved_call", entity_type="procedure",
                    entity_id=r["caller_id"],
                    entity_name=r["procedure_name"],
                    description=f"Calls unresolved: {r['callee_name_raw']}",
                    severity=0.5) for r in rows]

def detect_low_confidence_facts(conn: sqlite3.Connection,
                                 threshold: float = 0.4) -> list[GapInfo]:
    """Rule 8: Any fact with confidence below threshold."""
    rows = conn.execute("""
        SELECT 'enum' as fact_type, table_name, column_name, confidence
        FROM current_enum_values WHERE confidence < ?
        UNION ALL
        SELECT 'bitmask', table_name, column_name, confidence
        FROM current_bitmask_definitions WHERE confidence < ?
        UNION ALL
        SELECT 'alias', table_name, column_name, confidence
        FROM current_column_aliases WHERE confidence < ?
    """, (threshold, threshold, threshold)).fetchall()
    return [GapInfo(gap_type="low_confidence_fact", entity_type="column",
                    entity_name=f"{r['table_name']}.{r['column_name']}",
                    severity=0.4) for r in rows]

def detect_cross_sp_contradictions(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 9: Same column has multiple enum_values with different labels for same value."""
    rows = conn.execute("""
        SELECT e1.table_name, e1.column_name, e1.enum_value,
               e1.enum_label as label1, e2.enum_label as label2
        FROM current_enum_values e1
        JOIN current_enum_values e2
          ON e1.table_name = e2.table_name
         AND e1.column_name = e2.column_name
         AND e1.enum_value = e2.enum_value
         AND e1.id < e2.id
        WHERE e1.enum_label != e2.enum_label
          AND e1.enum_label IS NOT NULL
          AND e2.enum_label IS NOT NULL
    """).fetchall()
    return [GapInfo(gap_type="cross_sp_contradiction", entity_type="column",
                    entity_name=f"{r['table_name']}.{r['column_name']}",
                    description=f"Value {r['enum_value']!r}: '{r['label1']}' vs '{r['label2']}'",
                    severity=0.8) for r in rows]

def detect_missing_fks(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 10: Column named *_id or *_code with no FK relationship declared."""
    rows = conn.execute("""
        SELECT c.id, c.table_id, c.column_name, t.table_name
        FROM current_db_columns c
        JOIN current_db_tables t ON c.table_id = t.id
        WHERE (c.column_name LIKE '%_id' OR c.column_name LIKE '%_code')
          AND c.is_primary_key = 0
          AND NOT EXISTS (
            SELECT 1 FROM current_db_relationships r
            WHERE r.source_id = t.id
              AND (r.source_column = c.column_name OR r.relationship_type = 'fk_declared')
          )
    """).fetchall()
    return [GapInfo(gap_type="missing_fk", entity_type="column",
                    entity_id=r["id"],
                    entity_name=f"{r['table_name']}.{r['column_name']}",
                    severity=0.6) for r in rows]

def detect_coverage_gaps(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 11: Tables or procedures with NULL description."""
    rows = conn.execute("""
        SELECT 'table' as etype, id, table_name as name
        FROM current_db_tables WHERE description IS NULL
        UNION ALL
        SELECT 'procedure', id, procedure_name
        FROM current_db_procedures WHERE description IS NULL
    """).fetchall()
    return [GapInfo(gap_type="coverage_gap", entity_type=r["etype"],
                    entity_id=r["id"], entity_name=r["name"],
                    severity=0.3) for r in rows]

def detect_pattern_anomalies(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 12: Procedures with parse_quality below 0.8 (degraded parsing)."""
    rows = conn.execute("""
        SELECT sr.procedure_id, p.procedure_name, sr.parse_quality
        FROM current_sp_reliability sr
        JOIN current_db_procedures p ON sr.procedure_id = p.id
        WHERE sr.parse_quality < 0.8 OR sr.is_degraded = 1
    """).fetchall()
    return [GapInfo(gap_type="pattern_anomaly", entity_type="procedure",
                    entity_id=r["procedure_id"],
                    entity_name=r["procedure_name"],
                    description=f"Parse quality: {r['parse_quality']:.0%}",
                    severity=0.4) for r in rows]
```

### Pattern 6: Gap Deduplication — Upsert Logic

Before inserting new gaps, check if a gap with same (gap_type, entity_name) already exists and is open/investigating. If it does and cooldown has not expired, skip it.

```python
def upsert_gap(conn: sqlite3.Connection, gap: GapInfo,
               now_ts: int, now_iso: str) -> int | None:
    """Insert gap if not already open; return gap_id or None if skipped."""
    existing = conn.execute("""
        SELECT id, status, cooldown_until_ts, attempt_count
        FROM current_knowledge_gaps
        WHERE gap_type = ? AND entity_name = ?
    """, (gap.gap_type, gap.entity_name)).fetchone()

    if existing:
        status = existing["status"]
        cooldown_ts = existing["cooldown_until_ts"] or 0
        if status in ("open", "investigating"):
            return existing["id"]   # already tracked
        if status == "permanent":
            return None             # do not recreate permanent gaps
        if status == "resolved" and now_ts < cooldown_ts:
            return None             # cooldown not expired
        if status == "resolved" and now_ts >= cooldown_ts:
            # Re-open gap with new bi-temporal row
            ...
    # Insert new gap
    ...
```

### Pattern 7: Priority Scoring Formula (D-12)

```python
def score_gap(conn: sqlite3.Connection, gap: GapInfo,
              weights: LearningGapWeightsConfig) -> float:
    """Compute priority score from D-12 formula."""
    severity = gap.severity  # pre-set by detector (0.0-1.0)

    # Connectivity: how many relationships does affected entity have?
    if gap.entity_id:
        hop_count = len(bfs_graph(conn, gap.entity_id, max_depth=2))
        connectivity = min(1.0, hop_count / 20.0)  # normalize: 20+ hops = 1.0
    else:
        connectivity = 0.0

    # Query frequency: not tracked in Phase 3 — default 0.5 [ASSUMED]
    # (Phase 4 will add query logs; for now use neutral value)
    query_frequency = 0.5

    # Staleness: time since gap was first recorded
    age_days = (int(time.time()) - gap.recorded_at_ts) / 86400
    staleness = min(1.0, age_days / 30.0)   # 30 days = max staleness

    # Solvability: gaps with live DB connection are more solvable
    solvability = 0.7 if gap.gap_type in SOLVABLE_WITH_SAMPLING else 0.3

    return (
        weights.severity * severity +
        weights.connectivity * connectivity +
        weights.query_frequency * query_frequency +
        weights.staleness * staleness +
        weights.solvability * solvability
    )
```

### Pattern 8: Confidence Management (D-13/D-14/D-15)

```python
# Source: Decision D-13, D-14, D-15

def decay_confidence(current: float, days_since_update: float,
                     is_human_confirmed: bool,
                     decay_weekly: float, decay_confirmed_monthly: float) -> float:
    """Apply time-based confidence decay."""
    if is_human_confirmed:
        # 0.5%/month = ~0.0167%/day (D-15)
        rate_per_day = decay_confirmed_monthly / 30.0
    else:
        # 1%/week = ~0.143%/day (D-13)
        rate_per_day = decay_weekly / 7.0
    decayed = current * ((1.0 - rate_per_day) ** days_since_update)
    return max(0.0, decayed)

def reinforce_confidence(current: float, evidence_weight: float = 0.1) -> float:
    """Reinforce confidence when new evidence confirms existing fact."""
    # Boost by evidence_weight, capped at 1.0 (unless human-confirmed)
    return min(1.0, current + evidence_weight)

def resolve_conflict(fact_a_conf: float, fact_a_sources: int, fact_a_ts: int,
                     fact_b_conf: float, fact_b_sources: int, fact_b_ts: int,
                     escalate_threshold: float = 0.1
                     ) -> tuple[str, str]:
    """Determine conflict resolution strategy and rationale.

    Returns: (strategy, rationale)
    strategy is one of: "SUPERSEDE_A" | "SUPERSEDE_B" | "KEEP_BOTH" | "SPLIT" | "ESCALATE"
    """
    # Score each fact: confidence * 0.6 + source_count_normalized * 0.3 + recency * 0.1
    score_a = fact_a_conf * 0.6 + min(1.0, fact_a_sources / 5.0) * 0.3 + (1.0 if fact_a_ts > fact_b_ts else 0.0) * 0.1
    score_b = fact_b_conf * 0.6 + min(1.0, fact_b_sources / 5.0) * 0.3 + (1.0 if fact_b_ts > fact_a_ts else 0.0) * 0.1

    diff = abs(score_a - score_b)
    if diff < escalate_threshold:
        return "ESCALATE", f"Score difference {diff:.3f} < threshold {escalate_threshold}"
    elif score_a > score_b:
        return "SUPERSEDE_B", f"Fact A score {score_a:.3f} > Fact B {score_b:.3f}"
    else:
        return "SUPERSEDE_A", f"Fact B score {score_b:.3f} > Fact A {score_a:.3f}"
```

### Pattern 9: 4-Operation Update Pipeline (D-18, LEARN-06)

```python
# Source: Mem0 pattern, decision D-18

class UpdateOp(str, Enum):
    ADD = "ADD"
    REINFORCE = "REINFORCE"
    CONFLICT = "CONFLICT"
    NOOP = "NOOP"

def classify_update(conn: sqlite3.Connection,
                    entity_type: str, entity_name: str,
                    attribute: str, new_value: str,
                    new_confidence: float) -> tuple[UpdateOp, int | None]:
    """Classify a proposed fact update as ADD/REINFORCE/CONFLICT/NOOP.

    Returns: (operation, existing_fact_id or None)
    """
    # Look for existing fact by entity + attribute key
    existing = find_existing_fact(conn, entity_type, entity_name, attribute)
    if not existing:
        return UpdateOp.ADD, None
    if existing["value"] == new_value:
        if abs(existing["confidence"] - new_confidence) < 0.05:
            return UpdateOp.NOOP, existing["id"]
        return UpdateOp.REINFORCE, existing["id"]
    return UpdateOp.CONFLICT, existing["id"]
```

### Pattern 10: SP Reliability Scoring (D-17, LEARN-08)

The `sp_reliability` table already exists from Phase 2 [VERIFIED: schema.py lines 199-227]. Phase 3 extends the scoring formula:

```python
def compute_sp_reliability(conn: sqlite3.Connection, proc_id: int,
                            now_ts: int) -> float:
    """Compute reliability score for a stored procedure (D-17)."""
    score = 0.5  # baseline

    rel = conn.execute(
        "SELECT has_dynamic_sql, partial_ast, parse_quality "
        "FROM current_sp_reliability WHERE procedure_id = ?", (proc_id,)
    ).fetchone()
    if not rel:
        return score

    if rel["has_dynamic_sql"]:
        score -= 0.2
    if rel["partial_ast"]:
        score -= 0.05

    # +0.1 for recent activity (modified in last 30 days)
    proc = conn.execute(
        "SELECT valid_from_ts FROM current_db_procedures WHERE id=?", (proc_id,)
    ).fetchone()
    if proc and (now_ts - proc["valid_from_ts"]) < 30 * 86400:
        score += 0.1

    # +0.05 per unique caller (up to 5)
    caller_count = conn.execute(
        "SELECT COUNT(DISTINCT caller_id) FROM current_sp_call_chains WHERE callee_id=?",
        (proc_id,)
    ).fetchone()[0]
    score += min(0.25, caller_count * 0.05)

    # -0.1 per contradiction (from agent_results)
    contradictions = conn.execute(
        "SELECT COUNT(*) FROM agent_results ar "
        "JOIN agent_tasks at ON ar.task_id = at.id "
        "WHERE at.gap_id IN (SELECT id FROM current_knowledge_gaps WHERE entity_id=?) "
        "AND ar.approved = 0", (proc_id,)
    ).fetchone()[0]
    score -= min(0.5, contradictions * 0.1)

    return max(0.0, min(1.0, score))
```

### Pattern 11: Collector Agent — pyodbc Safety Wrapper

```python
# Source: Decision D-04 + CLAUDE.md pyodbc section

def collect_sample(connection_string: str, query: str,
                   timeout: int, max_rows: int) -> list[dict] | None:
    """Execute a read-only sampling query against live DB.

    Returns None if connection fails — Collector falls back to no-op.
    """
    try:
        import pyodbc
    except ImportError:
        return None   # pyodbc not installed → no-op

    if not connection_string:
        return None   # not configured → no-op

    try:
        conn = pyodbc.connect(connection_string, timeout=timeout)
        conn.timeout = timeout
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchmany(max_rows)
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
    except Exception:
        logger.warning("Collector sampling failed", exc_info=True)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

### Pattern 12: LLM Agent — Optional, Config-Gated

```python
# Source: Decision D-03

def call_llm(prompt: str, config: LearningConfig) -> str | None:
    """Call LLM if configured; return None if offline or unavailable."""
    if not config.llm_provider or not config.llm_api_key:
        return None

    try:
        if config.llm_provider == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=config.llm_api_key)
            msg = client.messages.create(
                model=config.llm_model or "claude-opus-4-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return msg.content[0].text
        elif config.llm_provider == "openai":
            import openai
            client = openai.OpenAI(api_key=config.llm_api_key)
            resp = client.chat.completions.create(
                model=config.llm_model or "gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content
    except Exception:
        logger.warning("LLM call failed, falling back to heuristics", exc_info=True)
        return None
```

### Pattern 13: Cooldown / Backoff Logic (D-11, LEARN-11)

```python
COOLDOWN_HOURS = [1, 4, 24, 72, 168]  # configurable via LearningConfig

def compute_next_cooldown(attempt_count: int,
                          cooldown_hours: list[int]) -> int:
    """Return cooldown duration in seconds for attempt N.

    attempt_count=0 → cooldown_hours[0], etc.
    Beyond the list → last value (168h = 1 week).
    """
    idx = min(attempt_count, len(cooldown_hours) - 1)
    return cooldown_hours[idx] * 3600

def should_mark_permanent(attempt_count: int, max_attempts: int = 5) -> bool:
    return attempt_count >= max_attempts
```

### Anti-Patterns to Avoid

- **Storing loop state in memory only:** All agent results must go to agent_results table before being used by the next agent. Crash-safety and auditability require this (D-02).
- **Blocking async event loop with pyodbc:** pyodbc is synchronous. Since orchestrator is called from an async MCP tool, wrap the entire `run_learning_loop` call in `asyncio.get_event_loop().run_in_executor(None, ...)` or use `anyio.to_thread.run_sync()`. [ASSUMED] — standard pattern for sync-in-async Python.
- **Auto-invalidating human-confirmed facts on schema change:** D-15 says flag for re-confirmation, not auto-invalidate. Add a `needs_reconfirmation` flag or a gap of type `reconfirm_human_fact`.
- **Creating gaps speculatively:** D-10 requires concrete evidence. Do not create "missing FK" gaps from naming heuristics alone without at least one corroborating data signal.
- **Inserting duplicate gaps:** The upsert logic must check (gap_type, entity_name) before inserting. Failing this creates infinite gap cycling even with cooldowns.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL parameterization | String f-string SQL | sqlite3 `?` placeholders | SQL injection — all Phase 2 code already uses `?` |
| BFS for gap connectivity | Custom graph traversal | `db_wiki.graph.bfs.bfs_graph()` | Already implemented with cycle detection and edge filtering |
| Hybrid search in Research Agent | New search logic | `db_wiki.search.hybrid.hybrid_search()` | Already implemented with FTS5+vec |
| LLM SDK client construction | Raw HTTP calls | `anthropic.Anthropic()` / `openai.OpenAI()` | SDKs handle auth, retries, rate limits |
| Pydantic model JSON serialization | Custom JSON encode | `.model_dump_json()` / `.model_dump()` | Already in pydantic 2.x |
| Datetime formatting | Custom strftime | `datetime.utcnow().isoformat()` | Consistent with existing store pattern |
| Epoch timestamp | Custom | `int(time.time())` | Same as all Phase 2 bi-temporal columns |

**Key insight:** Phase 3 adds NO new infrastructure — it's pure orchestration logic calling existing sub-systems. The risk of hand-rolling anything is creating subtle inconsistencies with the bi-temporal model.

---

## Common Pitfalls

### Pitfall 1: Gap Cycling Without Proper Dedup Key

**What goes wrong:** detect_missing_join creates a gap. The gap is investigated, no FK found (correct — it may be intentional). Gap is resolved. Next loop run detects the same missing join again. Infinite gap creation.

**Why it happens:** Gap dedup key (gap_type, entity_name) must be stable and match across loop runs. If entity_name is constructed differently (e.g., `"rel_3_to_5"` vs `"Orders_to_Customers"`), dedup fails.

**How to avoid:** Use stable, normalized entity names as dedup keys. For relationships, use `f"{source_table_name}_to_{target_table_name}"` not ID-based names (IDs can change across re-ingests). For column gaps, use `f"{table_name}.{column_name}"`.

**Warning signs:** `attempt_count` on a gap that should be resolved keeps incrementing.

### Pitfall 2: Bi-Temporal Pattern Not Applied to New Tables

**What goes wrong:** knowledge_gaps table uses plain `created_at` instead of the bi-temporal 4-column pattern. This breaks the `current_*` view contract and makes Phase 4 temporal queries impossible.

**Why it happens:** It's tempting to simplify new tables. All existing tables in schema.py follow the bi-temporal pattern.

**How to avoid:** Every new table MUST have `valid_from / valid_from_ts / valid_until / valid_until_ts / recorded_at / recorded_at_ts / invalidated_at / invalidated_at_ts`. Use the code example from Pattern 1 verbatim.

### Pitfall 3: LLM Import at Module Level

**What goes wrong:** `import anthropic` at the top of `agents/research.py` causes ImportError on startup when anthropic is not installed.

**Why it happens:** LLM is optional (D-03). Users without API keys should not need the package.

**How to avoid:** All LLM imports inside the function body, wrapped in try/except ImportError. Follow the pyodbc pattern from Pattern 11.

### Pitfall 4: Confidence Decay Applied at Loop Time vs. Read Time

**What goes wrong:** If decay is applied by a background job that updates rows, it conflicts with the bi-temporal model (every update needs a new temporal row, not an UPDATE). If decay is applied at read time, it's not persisted.

**How to avoid:** Apply decay lazily at read time for display purposes. Persist decay only when a gap investigation explicitly re-evaluates the fact and writes a new bi-temporal row via the REINFORCE operation. This keeps the store append-only and preserves history. [ASSUMED] — consistent with Graphiti/bi-temporal design philosophy.

### Pitfall 5: pyodbc Blocking the Async MCP Handler

**What goes wrong:** `run_learning_loop()` calls `collect_sample()` which blocks with a synchronous pyodbc connection. Called from an async FastMCP tool, this blocks the event loop.

**How to avoid:** The async MCP tool wraps the synchronous orchestrator call:
```python
import anyio
result = await anyio.to_thread.run_sync(
    lambda: run_learning_loop(app_ctx.conn, config)
)
```

### Pitfall 6: SQLite Connection Shared Across Threads

**What goes wrong:** SQLite connections are not thread-safe by default. If `run_in_executor` is used, passing the existing `conn` from the MCP context into a thread causes "SQLite objects created in a thread can only be used in that same thread" errors.

**How to avoid:** Open a NEW connection inside the thread/executor with the same db_path. The orchestrator should open its own connection using `open_store(db_path)`.

```python
@mcp.tool()
async def discover(ctx: Context, max_gaps: int = 10) -> str:
    app_ctx: AppContext = ctx.request_context.lifespan_context
    db_path = app_ctx.store_path / "knowledge.db"
    config = load_config(app_ctx.store_path)

    import anyio
    from db_wiki.learning.orchestrator import run_learning_loop
    result = await anyio.to_thread.run_sync(
        lambda: run_learning_loop(db_path, config, max_gaps)
    )
    return result
```

---

## Code Examples

Verified patterns from codebase:

### Bi-temporal INSERT (write a new fact)
```python
# Source: db_wiki/ingest/ddl_parser.py pattern (consistent across Phase 1-2)
now_iso = datetime.utcnow().isoformat()
now_ts = int(time.time())
conn.execute("""
    INSERT INTO knowledge_gaps (
        gap_type, entity_type, entity_id, entity_name, description,
        severity, priority_score, status, attempt_count,
        valid_from, valid_from_ts, recorded_at, recorded_at_ts
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', 0, ?, ?, ?, ?)
""", (gap_type, entity_type, entity_id, entity_name, description,
      severity, priority_score, now_iso, now_ts, now_iso, now_ts))
```

### Bi-temporal UPDATE (invalidate old row, insert new)
```python
# Source: Phase 2 update patterns (store writes always invalidate + re-insert)
conn.execute("""
    UPDATE knowledge_gaps
    SET invalidated_at = ?, invalidated_at_ts = ?,
        valid_until = ?, valid_until_ts = ?
    WHERE id = ?
""", (now_iso, now_ts, now_iso, now_ts, gap_id))
# Then INSERT new row with updated fields
```

### Eligible gaps query (cooldown-aware)
```python
# Source: Decision D-11 cooldown logic
rows = conn.execute("""
    SELECT * FROM current_knowledge_gaps
    WHERE status IN ('open', 'resolved')
      AND (cooldown_until_ts IS NULL OR cooldown_until_ts <= ?)
    ORDER BY priority_score DESC
    LIMIT ?
""", (now_ts, max_gaps)).fetchall()
```

### Row factory access
```python
# Source: db_wiki/core/store.py — conn.row_factory = sqlite3.Row
# Rows can be accessed by column name
gap_type = row["gap_type"]      # correct
entity_id = row["entity_id"]    # correct
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling/cron gap detection | Event-driven + manual trigger | Phase 3 design | Manual-only in Phase 3; daemon in Phase 5 |
| Synchronous LLM in hot path | Optional LLM, always offline fallback | D-01/D-03 | System works without API key |
| Single confidence number | Bi-temporal confidence + decay + source count | D-13/D-16 | Full audit trail of confidence evolution |
| Store mutations as UPDATE | Bi-temporal append-only rows | D-18 + Phase 1 | Complete history, no data loss |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Decay applied at read time (lazy), persisted only on explicit re-evaluation | Pitfall 4 | If wrong: could create many bi-temporal rows on every loop run; performance impact at scale |
| A2 | `anyio.to_thread.run_sync` is the right async bridge for MCP FastMCP context | Pitfall 5 | If wrong: use `asyncio.get_event_loop().run_in_executor()` instead; functionally equivalent |
| A3 | query_frequency defaults to 0.5 in Phase 3 (Phase 4 adds actual query logs) | Pattern 7 | If wrong: all gaps have same query_frequency component; priority ordering less accurate |
| A4 | Schema extension via separate `LEARNING_SCHEMA_SQL` imported in `schema_ext.py` | Pattern 1 | If wrong: could append to SCHEMA_SQL in schema.py; minor style difference, no functional impact |
| A5 | `anyio` is transitively available via `mcp` SDK dependency | Pitfall 5 | If wrong: add `anyio` explicitly to pyproject.toml |

---

## Open Questions

1. **anyio availability via mcp SDK**
   - What we know: mcp SDK 1.x uses anyio internally for async transport
   - What's unclear: whether anyio is re-exported or needs explicit dep
   - Recommendation: Add `anyio>=4.0` to pyproject.toml explicitly to be safe

2. **agent_results `findings_json` schema**
   - What we know: Must be parseable by Consolidate phase to apply changes
   - What's unclear: Exact JSON structure (list of proposed fact updates?)
   - Recommendation: Define a `FindingsList` Pydantic model; serialize with `.model_dump_json()`; deserialize with `model_validate_json()` in Consolidate

3. **confirm / teach MCP tool — which tables to write to**
   - What we know: Human-confirmed facts should be stored at confidence=1.0
   - What's unclear: Should they write to `enum_values` directly (existing table), or a separate `human_facts` table?
   - Recommendation: Write to the relevant domain table (enum_values, column_aliases, etc.) with `detection_method='human_confirmed'` and confidence=1.0. No separate table needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12.4 | — |
| uv | Package mgr | ✓ | 0.8.4 | pip + venv |
| sqlite3 | Store | ✓ | bundled | — |
| sqlite-vec | Vector search | ✓ | 0.1.9 (pyproject) | — |
| mcp SDK | MCP server | ✓ | 1.27+ (pyproject) | — |
| pydantic 2.x | Models | ✓ | 2.12+ (pyproject) | — |
| typer | CLI | ✓ | 0.24+ (pyproject) | — |
| anthropic SDK | LLM (Claude) | ✗ | — | Offline heuristics (D-01) |
| openai SDK | LLM (OpenAI) | ✗ | — | Offline heuristics (D-01) |
| pyodbc | Collector Agent | ✗ | — | No-op collector (D-04) |
| anyio | Async bridge | ✗ (likely transitive) | — | asyncio.run_in_executor |

**Missing dependencies with no fallback:**
- None — all missing deps have explicit fallbacks defined in decisions D-01 and D-04.

**Missing dependencies with fallback:**
- anthropic/openai: LLM agents fall back to heuristic-only analysis. System remains fully functional offline.
- pyodbc: Collector Agent returns empty evidence. Gap investigation proceeds with schema-only analysis.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] asyncio_mode="auto" |
| Quick run command | `uv run pytest tests/test_learning_*.py -x -q` |
| Full suite command | `uv run pytest -x -q` (212 existing + new) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LEARN-01 | Loop runs 5 phases in sequence | integration | `pytest tests/test_learning_orchestrator.py -x` | ❌ Wave 0 |
| LEARN-02 | All 12 gap rules detect concrete cases | unit | `pytest tests/test_gap_detector.py -x` | ❌ Wave 0 |
| LEARN-03 | Priority score formula produces correct weights | unit | `pytest tests/test_gap_scorer.py -x` | ❌ Wave 0 |
| LEARN-04 | Collector returns None when no connection | unit | `pytest tests/test_collector.py -x` | ❌ Wave 0 |
| LEARN-05 | Enum detection from CASE + sampling | unit | `pytest tests/test_gap_detector.py::test_unlabeled_enum -x` | ❌ Wave 0 |
| LEARN-06 | ADD/REINFORCE/CONFLICT/NOOP classify correctly | unit | `pytest tests/test_pipeline.py -x` | ❌ Wave 0 |
| LEARN-07 | Conflict resolution returns correct strategy + rationale | unit | `pytest tests/test_confidence.py::test_conflict_resolution -x` | ❌ Wave 0 |
| LEARN-08 | SP reliability formula produces [0.0, 1.0] score | unit | `pytest tests/test_confidence.py::test_sp_reliability -x` | ❌ Wave 0 |
| LEARN-09 | Confidence decays correctly over days | unit | `pytest tests/test_confidence.py::test_decay -x` | ❌ Wave 0 |
| LEARN-10 | confirm tool sets confidence=1.0 in store | integration | `pytest tests/test_learning_mcp.py::test_confirm -x` | ❌ Wave 0 |
| LEARN-11 | Gap cooldown prevents re-creation within interval | unit | `pytest tests/test_gap_detector.py::test_cooldown -x` | ❌ Wave 0 |
| LEARN-12 | Source count increments per SP, not per evidence instance | unit | `pytest tests/test_pipeline.py::test_source_count -x` | ❌ Wave 0 |
| STORE-08 | knowledge_gaps table has all required columns | unit | `pytest tests/test_learning_schema.py -x` | ❌ Wave 0 |
| MCP-03 | discover/confirm/teach tools registered and callable | integration | `pytest tests/test_learning_mcp.py -x` | ❌ Wave 0 |
| AGENT-01 | Research Agent returns structured findings | unit | `pytest tests/test_agents.py::test_research_agent -x` | ❌ Wave 0 |
| AGENT-02 | Review Agent approves/rejects with rationale | unit | `pytest tests/test_agents.py::test_review_agent -x` | ❌ Wave 0 |
| AGENT-04 | Collector no-ops without connection string | unit | `pytest tests/test_agents.py::test_collector_noop -x` | ❌ Wave 0 |
| AGENT-05 | Orchestrator calls agents in correct order | integration | `pytest tests/test_learning_orchestrator.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_learning_*.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green (212 existing + new tests) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_learning_schema.py` — covers STORE-08: knowledge_gaps/agent_tasks/agent_results DDL
- [ ] `tests/test_gap_detector.py` — covers LEARN-02, LEARN-05, LEARN-11
- [ ] `tests/test_gap_scorer.py` — covers LEARN-03
- [ ] `tests/test_confidence.py` — covers LEARN-07, LEARN-08, LEARN-09
- [ ] `tests/test_pipeline.py` — covers LEARN-06, LEARN-12
- [ ] `tests/test_collector.py` — covers LEARN-04, AGENT-04
- [ ] `tests/test_agents.py` — covers AGENT-01, AGENT-02, AGENT-04
- [ ] `tests/test_learning_orchestrator.py` — covers LEARN-01, AGENT-05
- [ ] `tests/test_learning_mcp.py` — covers MCP-03, LEARN-10
- [ ] `tests/conftest.py` — extend with `learning_db` fixture (initialized_db + learning schema)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | LLM API keys in config.yaml, not hardcoded |
| V3 Session Management | no | Stateless MCP tools |
| V4 Access Control | no | Single-user local tool |
| V5 Input Validation | yes | Pydantic models for all MCP tool inputs; pyodbc parameterized queries |
| V6 Cryptography | no | No crypto in learning loop |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via gap entity_name | Tampering | `?` placeholders for all entity_name in SQL; validated from existing DB rows, not user input |
| LLM prompt injection via SP content | Tampering | SP body content treated as data, not instructions; LLM prompt wraps content in clear delimiters |
| pyodbc connection string leakage | Information Disclosure | connection_string stored in config.yaml (local file); never logged or returned in MCP responses |
| Runaway collector queries | Denial of Service | `collector_max_rows`, `collector_timeout_seconds`, `collector_query_budget` limits enforced (D-04) |
| Infinite loop in orchestrator | DoS | `max_gaps_per_run` hard limit; cooldown prevents re-processing; `max_attempts_before_permanent` stops stuck gaps |
| Path traversal via store_path | Tampering | `Path.resolve()` applied at CLI boundary — existing T-03-01 control already in place |

---

## Sources

### Primary (HIGH confidence)

- [VERIFIED: db_wiki/core/schema.py] — bi-temporal table DDL pattern, all Phase 2 tables confirmed
- [VERIFIED: db_wiki/core/config.py] — Pydantic config extension pattern
- [VERIFIED: db_wiki/server/app.py] — @mcp.tool() decorator, AppContext, lifespan pattern
- [VERIFIED: db_wiki/cli/app.py] — Typer command registration pattern
- [VERIFIED: db_wiki/graph/bfs.py] — bfs_graph() signature and return type
- [VERIFIED: db_wiki/core/store.py] — open_store(), init_schema(), sqlite-vec loading
- [VERIFIED: db_wiki/core/models.py] — Pydantic BaseModel patterns, existing SP models
- [VERIFIED: pyproject.toml] — current dependencies, optional dep pattern, pytest config
- [VERIFIED: tests/conftest.py] — fixture patterns for initialized_db

### Secondary (MEDIUM confidence)

- [CITED: .planning/phases/03-learning-loop/03-CONTEXT.md] — all locked decisions D-01 through D-18
- [CITED: .planning/REQUIREMENTS.md] — LEARN-01 through LEARN-13, STORE-08, MCP-03, AGENT-01-05

### Tertiary (LOW confidence / ASSUMED)

- anyio availability via mcp SDK transitive deps (A5)
- Lazy decay at read time approach (A1) — consistent with bi-temporal philosophy but not explicitly stated in decisions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all existing deps verified from pyproject.toml
- Architecture: HIGH — all patterns directly from existing Phase 1-2 codebase
- Pitfalls: HIGH — SQLite threading and bi-temporal pitfalls confirmed from codebase patterns
- Gap detection SQL: HIGH — all queries reference verified column names from schema.py
- LLM integration: MEDIUM — anthropic/openai SDK APIs cited from CLAUDE.md + general knowledge; not installed locally

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable deps; MCP SDK evolves but slowly)
