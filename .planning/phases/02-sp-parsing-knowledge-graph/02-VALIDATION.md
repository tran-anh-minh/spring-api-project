---
phase: 2
slug: sp-parsing-knowledge-graph
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` — asyncio_mode = "auto" |
| **Quick run command** | `uv run pytest tests/ -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Wave 0 — TDD-Inline Approach

All plans use `tdd="true"` on tasks, meaning tests are created as part of each task's RED-GREEN-REFACTOR cycle. There is no separate Wave 0 plan for test stubs. Each task creates its own test file alongside the implementation:

- Plan 01 Task 1 creates `tests/test_schema_phase2.py`
- Plan 01 Task 2 creates `tests/test_store_phase2.py`
- Plan 02 Task 1 creates `tests/test_sp_parser.py`
- Plan 02 Task 2 creates `tests/test_cli_ingest.py`
- Plan 03 Task 1 creates `tests/test_search.py`
- Plan 04 Task 1 creates `tests/test_bfs.py`
- Plan 05 Task 1 creates `tests/test_server_phase2.py`
- Plan 05 Task 2 creates `tests/test_cli_phase2.py`

This satisfies the Nyquist requirement: every task has an `<automated>` verify command referencing a concrete test file that the task itself creates.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | INGEST-02 | — | N/A | unit | `uv run pytest tests/test_schema_phase2.py -x -q` | TDD-inline | ⬜ pending |
| 02-01-02 | 01 | 1 | STORE-05 | T-02-01 | ext loading disabled after use | unit | `uv run pytest tests/test_store_phase2.py -x -q` | TDD-inline | ⬜ pending |
| 02-02-01 | 02 | 2 | INGEST-02..08 | T-02-04 | parameterized SQL | unit | `uv run pytest tests/test_sp_parser.py -x -q` | TDD-inline | ⬜ pending |
| 02-02-02 | 02 | 2 | CLI-03 | T-02-05 | path resolution | integration | `uv run pytest tests/test_cli_ingest.py -x -q` | TDD-inline | ⬜ pending |
| 02-03-01 | 03 | 2 | STORE-09,CONFIG-01 | — | N/A | unit | `uv run pytest tests/test_search.py -x -v -k "not openai"` | TDD-inline | ⬜ pending |
| 02-03-02 | 03 | 2 | STORE-10,CONFIG-04 | T-02-07 | parameterized FTS5 MATCH | unit | `uv run pytest tests/test_search.py -x -v` | TDD-inline | ⬜ pending |
| 02-04-01 | 04 | 2 | STORE-11 | T-02-10 | max_depth + visited set | unit | `uv run pytest tests/test_bfs.py -x -v` | TDD-inline | ⬜ pending |
| 02-05-01 | 05 | 3 | STORE-05..11 | T-02-12 | parameterized queries | unit | `uv run pytest tests/test_server_phase2.py -x -v` | TDD-inline | ⬜ pending |
| 02-05-02 | 05 | 3 | CLI-03 | T-02-12 | parameterized queries | integration | `uv run pytest tests/test_cli_phase2.py -x -v` | TDD-inline | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covered via TDD-inline approach (each task creates its own tests)
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
