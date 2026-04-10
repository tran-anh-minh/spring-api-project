---
plan: 03-04
status: complete
started: 2026-04-11T01:05:00+07:00
completed: 2026-04-11T01:25:00+07:00
---

## Result

Implemented three learning loop agent types and shared infrastructure per D-01 hybrid agent architecture.

**Task 1: Base Infrastructure + Collector Agent** — Shared LLM client (Claude/OpenAI) with offline fallback. Task lifecycle management (create, save result, complete) with bi-temporal versioning. Collector Agent samples live DB via pyodbc with safety limits (timeout, max_rows, query_budget). No-op fallback when no connection.

**Task 2: Research + Review Agents** — Research Agent investigates gaps using LLM or deterministic heuristics for unlabeled_enum, orphan_table, missing_fk, coverage_gap types. LLM confidence capped at 0.7 per T-03-08. Review Agent quality-gates findings: rejects all when evidence_quality < 0.2, filters items with confidence < 0.1, discards empty values.

## Key Files

### key-files.created
- `db_wiki/learning/agents/__init__.py` — Package init
- `db_wiki/learning/agents/base.py` — call_llm, create_task_record, save_result_record, complete_task
- `db_wiki/learning/agents/collector.py` — collect_evidence, _execute_sample, _build_sampling_query
- `db_wiki/learning/agents/research.py` — research_gap with LLM + heuristic fallback
- `db_wiki/learning/agents/review.py` — review_findings with quality gate
- `tests/test_agents.py` — 11 tests passing, 2 xfail for orchestrator stubs

## Test Results

11 passed, 2 xfailed in 0.19s.

## Self-Check: PASSED

- [x] Collector falls back to no-op when no DB connection (AGENT-04)
- [x] Research works without LLM in heuristic mode (AGENT-01)
- [x] Review rejects low-quality findings (AGENT-02)
- [x] All agents return AgentFindings (D-02)
- [x] LLM calls are optional and config-gated (D-03)
- [x] Collector has safety limits (D-04)
- [x] pyodbc, anthropic, openai imported inside function bodies (soft deps)

## Deviations

None.
