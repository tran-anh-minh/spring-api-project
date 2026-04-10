---
phase: 03-learning-loop
verified: 2026-04-11T03:00:00Z
status: human_needed
score: 5/5
overrides_applied: 0
deferred:
  - truth: "LEARN-13 background loop scheduling (fast/medium/deep/human)"
    addressed_in: "Phase 5"
    evidence: "Phase 5 goal: 'schedule background learning'. Plan 03-05 explicitly states 'LEARN-13 scheduling is manual-trigger only (deferred to Phase 5 per D-06)'"
human_verification:
  - test: "Trigger learning loop on a real knowledge store with seeded Phase 2 data and observe gap detection output"
    expected: "run_learning_loop returns summary showing gaps detected, processed, and approved/rejected counts"
    why_human: "Integration test with real data flow through all 5 phases requires seeded store with realistic schema data"
  - test: "Use MCP discover tool from Claude Code and verify it returns meaningful results"
    expected: "Tool triggers learning loop, returns summary string, does not hang or timeout"
    why_human: "MCP tool invocation via Claude Code requires running MCP server with stdio transport"
  - test: "Use CLI 'db-wiki confirm' and 'db-wiki teach' commands against a store with existing facts"
    expected: "confirm sets confidence to 1.0, teach adds new fact with human_confirmed=True"
    why_human: "End-to-end CLI test with real file system store requires manual setup"
---

# Phase 3: Learning Loop Verification Report

**Phase Goal:** The system autonomously identifies knowledge gaps and deepens its understanding through iterative investigation
**Verified:** 2026-04-11T03:00:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can trigger a learning loop run and observe gap detection finding unlabeled enums, orphan tables, and missing joins | VERIFIED | `run_learning_loop()` in orchestrator.py calls `detect_all_gaps()` which aggregates 12 rules including `detect_unlabeled_enums`, `detect_orphan_tables`, `detect_missing_joins`. MCP `discover` tool and CLI `discover` command both wire to `run_learning_loop`. 7 orchestrator tests pass. |
| 2 | Human can confirm a fact via `dbwiki:confirm` and its confidence is set to 1.0, never silently overridden | VERIFIED | `confirm_fact()` in confirm.py sets `confidence=1.0` and `human_confirmed=1`. MCP `confirm` tool in server/app.py calls `confirm_fact` via `anyio.to_thread.run_sync`. CLI `confirm` command mirrors the same. `decay_confidence()` uses `decay_confirmed_monthly=0.005` (0.5%/month) for human-confirmed facts. 6 confirm tests pass. |
| 3 | Conflict between two sources produces SUPERSEDE/KEEP/SPLIT/ESCALATE resolution with logged rationale | VERIFIED | `resolve_conflict()` in confidence.py returns tuple of (resolution, rationale_string). Implements KEEP (different conditions), SPLIT (sub-contexts), ESCALATE (score diff < threshold), SUPERSEDE_A/SUPERSEDE_B (clear winner). `apply_findings()` in pipeline.py calls `resolve_conflict` on CONFLICT classification. 6 conflict resolution tests pass. |
| 4 | Confidence decays over time for stale facts and is reinforced when new evidence supports existing knowledge | VERIFIED | `decay_confidence()` computes `current * ((1.0 - rate_per_day) ** days_since_update)` with 1%/week normal, 0.5%/month confirmed. `reinforce_confidence()` adds `evidence_weight` capped at 1.0. Pipeline REINFORCE path calls `reinforce_confidence`. 7 decay/reinforce tests pass. |
| 5 | Gap cooldown prevents the same gap from being re-created infinitely across loop iterations | VERIFIED | `upsert_gaps()` in gap_detector.py checks for existing (gap_type, entity_name): skips open/investigating, skips permanent, skips resolved with active cooldown. `bump_attempt_count()` in pipeline.py applies escalating cooldown from `cooldown_hours=[1,4,24,72,168]`. After `max_attempts_before_permanent=5`, marks gap permanent. Tests verify dedup and cooldown. |

**Score:** 5/5 truths verified

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | LEARN-13: Background loop scheduling (fast/medium/deep/human) | Phase 5 | Phase 5 goal: "schedule background learning". Plan 03-05 must_haves explicitly states deferral per D-06. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db_wiki/learning/schema_ext.py` | 3 tables, 3 views, indexes | VERIFIED | 151 lines, LEARNING_SCHEMA_SQL with knowledge_gaps, agent_tasks, agent_results + views + indexes |
| `db_wiki/learning/models.py` | Pydantic models | VERIFIED | 111 lines, GapInfo, GapRecord, UpdateOp, FindingItem, AgentFindings |
| `db_wiki/learning/gap_detector.py` | 12 detection rules + aggregator + upsert | VERIFIED | 536 lines, 12 detect_* functions + detect_all_gaps + upsert_gaps |
| `db_wiki/learning/gap_scorer.py` | Priority scoring formula | VERIFIED | 203 lines, score_gap + score_and_prioritize + get_eligible_gaps |
| `db_wiki/learning/confidence.py` | Decay, reinforce, conflict, SP reliability | VERIFIED | 272 lines, all 5 exported functions present |
| `db_wiki/learning/pipeline.py` | 4-op update pipeline | VERIFIED | 393 lines, classify_update + apply_findings + mark_gap_resolved + bump_attempt_count |
| `db_wiki/learning/orchestrator.py` | Learning loop coordinator | VERIFIED | 131 lines, run_learning_loop with all 5 phases |
| `db_wiki/learning/confirm.py` | Confirm/teach logic | VERIFIED | 128 lines, confirm_fact + teach_fact |
| `db_wiki/learning/agents/base.py` | LLM client + task lifecycle | VERIFIED | 142 lines, call_llm + create_task_record + save_result_record + complete_task |
| `db_wiki/learning/agents/collector.py` | Collector Agent | VERIFIED | 155 lines, collect_evidence + _execute_sample + _build_sampling_query |
| `db_wiki/learning/agents/research.py` | Research Agent | VERIFIED | 199 lines, research_gap with LLM + heuristic fallback |
| `db_wiki/learning/agents/review.py` | Review Agent | VERIFIED | 154 lines, review_findings with quality gate |
| `db_wiki/server/app.py` | MCP tools: discover, confirm, teach | VERIFIED | @mcp.tool() decorators for all three, wired to orchestrator/confirm |
| `db_wiki/cli/app.py` | CLI commands: discover, confirm, teach | VERIFIED | @app.command() decorators for all three, wired to orchestrator/confirm |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| orchestrator.py | gap_detector.py | detect_all_gaps, upsert_gaps | WIRED | Lines 30, 55-56 |
| orchestrator.py | agents/collector.py | collect_evidence | WIRED | Lines 27, 81 |
| orchestrator.py | agents/research.py | research_gap | WIRED | Lines 28, 87 |
| orchestrator.py | agents/review.py | review_findings | WIRED | Lines 29, 93 |
| orchestrator.py | pipeline.py | apply_findings, mark_gap_resolved, bump_attempt_count | WIRED | Lines 32, 100-101, 105, 119 |
| server/app.py | orchestrator.py | run_learning_loop | WIRED | Lines 346, 349 |
| server/app.py | confirm.py | confirm_fact, teach_fact | WIRED | Lines 374, 404 |
| cli/app.py | orchestrator.py | run_learning_loop | WIRED | Lines 490, 492 |
| cli/app.py | confirm.py | confirm_fact, teach_fact | WIRED | Lines 518, 546 |
| core/store.py | schema_ext.py | init_learning_schema | WIRED | Verified by test: init_schema creates knowledge_gaps table |
| pipeline.py | confidence.py | resolve_conflict, reinforce_confidence | WIRED | Pattern found in pipeline.py |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| orchestrator.py | new_gaps | detect_all_gaps(conn) | SQL queries against Phase 2 current_* views | FLOWING |
| orchestrator.py | evidence | collect_evidence(conn, gap, config) | pyodbc queries (or no-op fallback) | FLOWING |
| orchestrator.py | findings | research_gap(conn, gap, evidence, config) | LLM or heuristic analysis | FLOWING |
| orchestrator.py | reviewed | review_findings(conn, gap, findings, config) | Quality-gated filtering | FLOWING |
| confirm.py | fact write | classify_update + SQL INSERT | Direct SQL INSERT with confidence=1.0 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 3 tests pass | `uv run pytest tests/test_gap_detector.py tests/test_gap_scorer.py tests/test_confidence.py tests/test_pipeline.py tests/test_orchestrator.py tests/test_confirm.py tests/test_agents.py -v` | 97 passed, 2 xpassed in 0.32s | PASS |
| Wave 0 stubs now pass (implementation complete) | `uv run pytest tests/test_gap_detection.py tests/test_learning_loop.py tests/test_conflict_resolution.py -v` | 17 xpassed in 0.11s | PASS |
| All key imports work | `python -c "from db_wiki.learning.orchestrator import run_learning_loop; ..."` | "All imports OK" | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LEARN-01 | 03-05 | Five-phase learning loop | SATISFIED | orchestrator.py implements Discover->Investigate->Reason->Validate->Consolidate |
| LEARN-02 | 03-02 | 12 gap detection rules | SATISFIED | 12 detect_* functions in gap_detector.py |
| LEARN-03 | 03-02 | Gap priority scoring formula | SATISFIED | score_gap in gap_scorer.py with D-12 weights |
| LEARN-04 | 03-04 | Data sampling via live DB | SATISFIED | collector.py with pyodbc, timeout, max_rows, query_budget |
| LEARN-05 | 03-02, 03-04 | Enum/bitmask auto-detection | SATISFIED | detect_unlabeled_enums rule + research heuristic for unlabeled_enum |
| LEARN-06 | 03-03 | 4-operation update pipeline | SATISFIED | classify_update returns ADD/REINFORCE/CONFLICT/NOOP |
| LEARN-07 | 03-03 | Conflict resolution strategies | SATISFIED | resolve_conflict returns SUPERSEDE/KEEP/SPLIT/ESCALATE |
| LEARN-08 | 03-03 | SP reliability scoring | SATISFIED | compute_sp_reliability with D-17 formula |
| LEARN-09 | 03-03 | Confidence decay with reinforcement | SATISFIED | decay_confidence + reinforce_confidence |
| LEARN-10 | 03-06 | Human confirmation skill | SATISFIED | confirm_fact/teach_fact + MCP confirm/teach tools |
| LEARN-11 | 03-01, 03-02, 03-03 | Gap cooldown history | SATISFIED | upsert_gaps dedup + bump_attempt_count with cooldown_hours |
| LEARN-12 | 03-03 | Source independence weighting | SATISFIED | count_independent_sources in confidence.py |
| LEARN-13 | NONE (deferred) | Background loop scheduling | DEFERRED | Explicitly deferred to Phase 5 per D-06; Phase 5 goal covers scheduling |
| STORE-08 | 03-01 | Knowledge gaps table | SATISFIED | knowledge_gaps table with severity, attempt_count, cooldown, bi-temporal |
| MCP-03 | 03-06 | Learn skills (discover, confirm, teach) | SATISFIED | Three @mcp.tool() decorators in server/app.py |
| AGENT-01 | 03-04 | Research Agent | SATISFIED | research_gap with LLM + heuristic fallback |
| AGENT-02 | 03-04 | Review Agent | SATISFIED | review_findings with quality gate |
| AGENT-04 | 03-04 | Collector Agent | SATISFIED | collect_evidence with safety limits |
| AGENT-05 | 03-05 | Orchestrator | SATISFIED | run_learning_loop coordinates all agents |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| agents/research.py | 162 | "Heuristic: placeholder description generated" | INFO | Intentional: low-confidence (0.2) auto-generated description for coverage_gap type, goes through review pipeline. Not a code stub. |
| tests/test_agents.py | - | 2 xpassed tests (Wave 0 stubs now passing) | INFO | Wave 0 xfail markers should be removed now that implementation is complete. Non-blocking. |

### Human Verification Required

### 1. End-to-End Learning Loop with Real Data

**Test:** Trigger `db-wiki discover` on a store with ingested Phase 2 data (tables, SPs, enum_values with missing labels)
**Expected:** Summary shows gaps detected, processed, and approved/rejected counts. Knowledge store has new/updated facts.
**Why human:** Requires seeded store with realistic schema data and end-to-end pipeline execution beyond unit test scope.

### 2. MCP Tool Integration

**Test:** Use `dbwiki:discover`, `dbwiki:confirm`, `dbwiki:teach` tools from Claude Code via MCP
**Expected:** Tools respond without hanging, return meaningful results, confirm/teach modify facts correctly
**Why human:** MCP tool invocation requires running MCP server with stdio transport in Claude Code environment.

### 3. CLI Confirm/Teach with Real Store

**Test:** Run `db-wiki teach column Orders.Status enum_label Active` then `db-wiki confirm column Orders.Status enum_label Active` against a real store
**Expected:** teach adds fact with confidence=1.0 and human_confirmed=True; confirm verifies it
**Why human:** End-to-end CLI test with real file system store and actual fact persistence.

### Gaps Summary

No blocking gaps found. All 5 roadmap success criteria verified with code evidence and 114 passing tests (97 implementation + 17 Wave 0). LEARN-13 (background scheduling) is explicitly deferred to Phase 5 with clear evidence. Three human verification items remain for end-to-end integration testing.

---

_Verified: 2026-04-11T03:00:00Z_
_Verifier: Claude (gsd-verifier)_
