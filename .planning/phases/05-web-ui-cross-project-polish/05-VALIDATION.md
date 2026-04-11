---
phase: 5
slug: web-ui-cross-project-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` asyncio_mode = "auto" |
| **Quick run command** | `uv run pytest tests/test_web.py tests/test_daemon.py tests/test_cross.py tests/test_export.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_web.py tests/test_daemon.py tests/test_cross.py tests/test_export.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | UI-01 | — | N/A | integration | `uv run pytest tests/test_web.py::test_web_app_serves_index -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | UI-02 | — | N/A | integration | `uv run pytest tests/test_web.py::test_graph_api_initial_load -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | UI-03 | T-05-01 | Validate depth<=5 | integration | `uv run pytest tests/test_web.py::test_graph_api_expand_node -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | UI-04 | — | N/A | integration | `uv run pytest tests/test_web.py::test_wiki_api -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | UI-05 | — | N/A | unit | `uv run pytest tests/test_web.py::test_node_confidence_field -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | UI-06 | — | N/A | unit | `uv run pytest tests/test_web.py::test_gap_node_flag -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | LEARN-13 | — | N/A | unit | `uv run pytest tests/test_daemon.py::test_scheduler_starts -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | LEARN-13 | T-05-02 | Own SQLite conn per thread | unit | `uv run pytest tests/test_daemon.py::test_scheduler_stops -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | CROSS-01 | — | N/A | unit | `uv run pytest tests/test_cross.py::test_open_cross_store -x` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 2 | CROSS-02 | — | N/A | unit | `uv run pytest tests/test_cross.py::test_cross_penalty -x` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 3 | EXPORT-01 | — | N/A | integration | `uv run pytest tests/test_cli_phase5.py::test_status_command -x` | ❌ W0 | ⬜ pending |
| 05-04-02 | 04 | 3 | EXPORT-03 | — | N/A | integration | `uv run pytest tests/test_export.py::test_markdown_exporter -x` | ❌ W0 | ⬜ pending |
| 05-04-03 | 04 | 3 | EXPORT-03 | — | N/A | integration | `uv run pytest tests/test_export.py::test_mermaid_exporter -x` | ❌ W0 | ⬜ pending |
| 05-04-04 | 04 | 3 | EXPORT-03 | — | N/A | integration | `uv run pytest tests/test_export.py::test_json_schema_exporter -x` | ❌ W0 | ⬜ pending |
| 05-04-05 | 04 | 3 | EXPORT-03 | — | N/A | integration | `uv run pytest tests/test_export.py::test_ddl_annotated_exporter -x` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 3 | MCP-06 | — | N/A | integration | `uv run pytest tests/test_server_phase5.py::test_lint_tool -x` | ❌ W0 | ⬜ pending |
| 05-05-02 | 05 | 3 | MCP-06 | — | N/A | integration | `uv run pytest tests/test_server_phase5.py::test_history_tool -x` | ❌ W0 | ⬜ pending |
| 05-05-03 | 05 | 3 | MCP-06 | — | N/A | integration | `uv run pytest tests/test_server_phase5.py::test_export_tool -x` | ❌ W0 | ⬜ pending |
| 05-05-04 | 05 | 3 | CLI-05 | — | N/A | manual | manual (requires signal testing) | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_web.py` — stubs for UI-01 through UI-06; needs starlette TestClient
- [ ] `tests/test_daemon.py` — covers LEARN-13 scheduler start/stop
- [ ] `tests/test_cross.py` — covers CROSS-01, CROSS-02
- [ ] `tests/test_export.py` — covers EXPORT-03 all four formatters
- [ ] `tests/test_cli_phase5.py` — covers CLI-05 serve command and EXPORT-01 status
- [ ] `tests/test_server_phase5.py` — covers MCP-06 lint, history, export tools

*starlette TestClient import: `from starlette.testclient import TestClient` — already available via starlette installation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `db-wiki serve --no-ui` starts scheduler and exits on Ctrl-C | CLI-05 | Requires signal testing (SIGINT) | 1. Run `db-wiki serve --no-ui` 2. Verify scheduler logs 3. Press Ctrl-C 4. Verify clean shutdown |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
