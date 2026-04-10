# Phase 3: Learning Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 03-learning-loop
**Areas discussed:** Agent architecture, Loop orchestration, Gap detection rules, Confidence & conflicts

---

## Agent Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Pure code heuristics | Agents are Python functions with rule-based logic. No LLM calls. | |
| LLM-powered reasoning | Agents call an LLM for investigation and reasoning steps. | |
| Hybrid: code detect, LLM reason | Gap detection and data collection are pure code. Reasoning uses LLM when available, falls back to heuristics. | ✓ |

**User's choice:** Hybrid: code detect, LLM reason
**Notes:** System works offline, enhanced with LLM when available.

| Option | Description | Selected |
|--------|-------------|----------|
| Shared SQLite tables | Agents read/write to coordination tables. Persistent, auditable. | ✓ |
| In-memory pipeline | Python objects passed between agents. Faster but no persistence. | |
| Message queue | Async queue for concurrent execution. | |

**User's choice:** Shared SQLite tables

| Option | Description | Selected |
|--------|-------------|----------|
| Anthropic Claude (via MCP) | LLM host as reasoning engine. Zero additional API keys. | |
| Configurable (Claude/OpenAI) | Multiple LLM providers via config. | ✓ |
| No default — optional addon | LLM reasoning is opt-in. Core works on heuristics. | |

**User's choice:** Configurable (Claude/OpenAI)

| Option | Description | Selected |
|--------|-------------|----------|
| Direct pyodbc queries | Collector connects via existing config. Respects safety limits. | |
| Delegated to user | Collector generates queries, user runs them. | |
| You decide | Claude picks best approach. | ✓ |

**User's choice:** Claude's discretion (direct pyodbc with safety limits selected)

---

## Loop Orchestration

| Option | Description | Selected |
|--------|-------------|----------|
| Single-pass sequential | One complete cycle per run. Simple, predictable. | ✓ |
| Iterative until convergence | Loop repeats until no new gaps. More thorough. | |
| Phase-at-a-time (resumable) | Each phase runs independently. Most flexible. | |

**User's choice:** Single-pass sequential

| Option | Description | Selected |
|--------|-------------|----------|
| Frequency controls batch size | Fast=1 gap, Medium=5, Deep=full scan. | |
| Frequency controls loop depth | Fast=discover only, Deep=full 5-phase. | |
| Defer scheduling to Phase 5 | Phase 3 = loop logic only. Phase 5 adds scheduling. | ✓ |

**User's choice:** Defer scheduling to Phase 5

| Option | Description | Selected |
|--------|-------------|----------|
| Manual only (CLI + MCP) | User triggers runs explicitly. | ✓ |
| Manual + post-ingest hook | Manual plus auto-discover after ingest. | |

**User's choice:** Manual only (CLI + MCP)

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable with sensible default | learning.max_gaps_per_run (default 10). | ✓ |
| Process all discovered gaps | Investigate every gap found. | |

**User's choice:** Configurable with sensible default

---

## Gap Detection Rules

| Option | Description | Selected |
|--------|-------------|----------|
| Core first, advanced later | 3 tiers of rules by complexity. | |
| All at once | All 12 rules in Phase 3. Each is a simple SQL query function. | ✓ |

**User's choice:** All 12 rules at once

| Option | Description | Selected |
|--------|-------------|----------|
| Exponential backoff | 1h → 4h → 24h → mark permanent after 5 attempts. | ✓ |
| Fixed cooldown + max attempts | Fixed 24h cooldown, 3 max attempts. | |

**User's choice:** Exponential backoff

| Option | Description | Selected |
|--------|-------------|----------|
| Conservative | Only gaps with concrete evidence. Few false positives. | ✓ |
| Balanced | Include reasonable guesses. Severity scoring. | |
| Aggressive | Gap for anything that could be enriched. | |

**User's choice:** Conservative (only gaps with concrete evidence)

| Option | Description | Selected |
|--------|-------------|----------|
| As defined in REQUIREMENTS | Fixed formula weights. | |
| Formula + configurable weights | Default formula, user can adjust weights in config. | ✓ |

**User's choice:** Formula + configurable weights

---

## Confidence & Conflicts

| Option | Description | Selected |
|--------|-------------|----------|
| Time-based linear decay | Fixed % per week with floor. | |
| Event-driven decay | Only decay on changes/contradictions. | |
| Combined | Light time decay + stronger event decay + reinforcement. | ✓ |

**User's choice:** Combined (time + event decay)

| Option | Description | Selected |
|--------|-------------|----------|
| Auto scoring formula | SUPERSEDE/KEEP/SPLIT/ESCALATE by score comparison. | |
| Always ESCALATE | All conflicts need human review. | |
| Auto + detailed logging | Auto-resolve, log rationale, ESCALATE only when too close (<0.1). | ✓ |

**User's choice:** Auto + detailed logging

| Option | Description | Selected |
|--------|-------------|----------|
| Confirm = 1.0, absolute protection | Never decayed or overridden. | |
| Confirm = 1.0 with slow decay | Very slow decay (0.5%/month), flag for re-confirmation on schema change. | ✓ |

**User's choice:** Confirm = 1.0 with slow decay

| Option | Description | Selected |
|--------|-------------|----------|
| Body similarity check | Compare SP bodies, >80% overlap = 1 source. | |
| Simple source counting | Each SP = 1 source. No deduplication. | ✓ |

**User's choice:** Simple source counting

---

## Claude's Discretion

- Exact SQLite DDL for new coordination tables
- Gap detection SQL queries for each rule
- LLM prompt templates for agents
- Collector Agent query strategy
- MCP tool schemas
- CLI command structure
- Internal loop state management
- SP reliability scoring formula details

## Deferred Ideas

- Background scheduling (LEARN-13) — deferred to Phase 5
- Body similarity for source independence — not needed now
- Variable tracking through SP execution paths — carried from Phase 2
