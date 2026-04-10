---
phase: 2
slug: sp-parsing-knowledge-graph
status: draft
nyquist_compliant: false
wave_0_complete: false
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

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | INGEST-02 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py -x -q` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 0 | INGEST-03 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py::test_branch_extraction -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 0 | INGEST-04 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py::test_state_transitions -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 0 | INGEST-05 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py::test_call_chains -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 0 | INGEST-06 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py::test_dynamic_sql -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 0 | INGEST-07 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py::test_parse_quality -x` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 0 | INGEST-08 | — | N/A | unit | `uv run pytest tests/test_sp_parser.py::test_incremental_reparse -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | STORE-05 | — | N/A | unit | `uv run pytest tests/test_schema.py::test_sp_tables -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | STORE-06 | — | N/A | unit | `uv run pytest tests/test_schema.py::test_value_intelligence_tables -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | STORE-09 | — | N/A | unit | `uv run pytest tests/test_search.py::test_vector_search -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | STORE-10 | — | N/A | unit | `uv run pytest tests/test_search.py::test_fts_search -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | STORE-11 | — | N/A | unit | `uv run pytest tests/test_graph.py::test_bfs -x` | ❌ W0 | ⬜ pending |
| 02-03-04 | 03 | 2 | CONFIG-01 | — | N/A | unit | `uv run pytest tests/test_search.py::test_embedding_provider -x` | ❌ W0 | ⬜ pending |
| 02-03-05 | 03 | 2 | CONFIG-04 | — | N/A | unit | `uv run pytest tests/test_search.py::test_lazy_load -x` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 2 | CLI-03 | — | N/A | integration | `uv run pytest tests/test_cli.py::test_ingest_directory -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_sp_parser.py` — stubs for INGEST-02 through INGEST-08
- [ ] `tests/test_schema.py` — stubs for STORE-05, STORE-06 table creation
- [ ] `tests/test_search.py` — stubs for STORE-09, STORE-10, CONFIG-01, CONFIG-04
- [ ] `tests/test_graph.py` — stubs for STORE-11 BFS traversal
- [ ] Extend `tests/test_cli.py` — stubs for CLI-03 directory ingest

*Existing tests/conftest.py will be extended — not created from scratch*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
