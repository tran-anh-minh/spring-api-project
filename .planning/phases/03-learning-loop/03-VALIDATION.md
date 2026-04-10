---
phase: 3
slug: learning-loop
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `uv run pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `uv run pytest tests/ -v --timeout=60`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| *Populated during planning* | | | | | | | | | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

Wave 0 is addressed by **03-00-PLAN.md** which creates the following test stubs before any implementation begins:

- [ ] `tests/test_gap_detection.py` — stubs for LEARN-01, LEARN-02, LEARN-03, LEARN-11 (partial)
- [ ] `tests/test_learning_loop.py` — stubs for LEARN-06, LEARN-08, LEARN-09
- [ ] `tests/test_conflict_resolution.py` — stubs for LEARN-07, LEARN-11, LEARN-12
- [ ] `tests/test_agents.py` — stubs for AGENT-01, AGENT-02, AGENT-04, AGENT-05

All stubs use `pytest.mark.xfail` so the suite stays green until implementation lands.

*Existing test infrastructure (pytest, conftest.py) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM-enhanced reasoning produces useful output | AGENT-01 | Requires live LLM API key | Run `db-wiki discover` with `learning.llm_provider` configured, verify reasoning output is contextually relevant |
| Live DB data sampling returns meaningful results | AGENT-04 | Requires live SQL Server connection | Configure pyodbc connection, run discover on a table with known data patterns |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (03-00-PLAN.md)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (Wave 0 plan 03-00-PLAN.md creates stubs)
