---
phase: 4
slug: query-engine
status: draft
nyquist_compliant: true
wave_0_complete: true
wave_0_strategy: tdd
created: 2026-04-11
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Wave 0 Strategy

Plans 01, 02, and 03 use `tdd="true"` on all tasks, which means test files are created as part of each task's RED-GREEN-REFACTOR cycle. This satisfies the Nyquist requirement without a separate Wave 0 plan -- every code-producing task creates its own test file before the implementation. The stub files listed in the original Wave 0 section are superseded by the actual TDD test files below.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Test File | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-----------|--------|
| 01-T1 | 01 | 1 | QUERY-01, QUERY-02, QUERY-03, STORE-07 | T-04-01 | SQL fragment validation via sqlglot | unit+TDD | `uv run pytest tests/test_query_resolver.py -x --tb=short` | tests/test_query_resolver.py | ⬜ pending |
| 01-T2 | 01 | 1 | STORE-07, EXPORT-02 | T-04-02 | Cache invalidation on schema change | unit+TDD | `uv run pytest tests/test_query_wiki.py -x --tb=short` | tests/test_query_wiki.py | ⬜ pending |
| 02-T1 | 02 | 1 | QUERY-04, QUERY-05 | T-04-05 | Context assembly reads local store only | unit+TDD | `uv run pytest tests/test_query_classifier.py tests/test_query_context.py -x --tb=short` | tests/test_query_classifier.py, tests/test_query_context.py | ⬜ pending |
| 02-T2 | 02 | 1 | QUERY-06, QUERY-07, QUERY-08 | T-04-03, T-04-04 | SQL validated via sqlglot qualify before use | unit+TDD | `uv run pytest tests/test_query_generator.py tests/test_query_validator.py -x --tb=short` | tests/test_query_generator.py, tests/test_query_validator.py | ⬜ pending |
| 03-T1 | 03 | 2 | QUERY-08, QUERY-09 | T-04-06, T-04-08 | SELECT-only execution, cache invalidation | unit+TDD | `uv run pytest tests/test_query_cache.py tests/test_query_executor.py -x --tb=short` | tests/test_query_cache.py, tests/test_query_executor.py | ⬜ pending |
| 03-T2 | 03 | 2 | AGENT-03 | T-04-07, T-04-09 | Pipeline requires explicit execute=True, analyst fallback | unit+TDD | `uv run pytest tests/test_analyst_agent.py tests/test_query_pipeline.py -x --tb=short` | tests/test_analyst_agent.py, tests/test_query_pipeline.py | ⬜ pending |
| 04-T1 | 04 | 3 | MCP-04 (partial), D-10 | T-04-10 | Pipeline validates SQL before execution | unit | `uv run pytest tests/test_server_phase4.py -x --tb=short -k "ask or explain or search or lineage"` | tests/test_server_phase4.py | ⬜ pending |
| 04-T2 | 04 | 3 | MCP-04 (partial) | T-04-11 | define_metric validates SQL fragments | unit | `uv run pytest tests/test_server_phase4.py -x --tb=short -k "define_metric or state_machine or branch_analysis"` | tests/test_server_phase4.py | ⬜ pending |
| 04-T3 | 04 | 3 | MCP-05 | T-04-12, T-04-13 | max_depth limits BFS, no PII exposure | unit | `uv run pytest tests/test_server_phase4.py -x --tb=short` | tests/test_server_phase4.py | ⬜ pending |
| 05-T1 | 05 | 3 | CLI-04 (partial) | T-04-14, T-04-15 | CLI ask validates SQL, define-metric validates fragments | unit | `uv run pytest tests/test_cli_phase4.py -x --tb=short -k "ask or explain or define_metric or state_machine or branch_analysis"` | tests/test_cli_phase4.py | ⬜ pending |
| 05-T2 | 05 | 3 | CLI-04 (partial) | T-04-16 | No PII exposure in coverage/quality reports | unit | `uv run pytest tests/test_cli_phase4.py -x --tb=short` | tests/test_cli_phase4.py | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live DB execution returns results | QUERY-09 | Requires SQL Server connection | Connect to test DB, run `dbwiki ask "show orders" --execute`, verify results |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covered by TDD approach (test files created per-task in Plans 01-03)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
