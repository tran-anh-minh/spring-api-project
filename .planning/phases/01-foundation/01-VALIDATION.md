---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | INGEST-01 | — | N/A | unit | `uv run pytest tests/test_ddl_parser.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STORE-01 | — | N/A | unit | `uv run pytest tests/test_store.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STORE-02 | — | N/A | unit | `uv run pytest tests/test_store.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STORE-03 | — | N/A | unit | `uv run pytest tests/test_store.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STORE-04 | — | N/A | unit | `uv run pytest tests/test_store.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-01 | — | N/A | integration | `uv run pytest tests/test_server.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-02 | — | N/A | integration | `uv run pytest tests/test_server.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CLI-01 | — | N/A | integration | `uv run pytest tests/test_cli.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CLI-02 | — | N/A | integration | `uv run pytest tests/test_cli.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CONFIG-02 | — | N/A | unit | `uv run pytest tests/test_config.py -v` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CONFIG-03 | — | N/A | unit | `uv run pytest tests/test_config.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (temp SQLite DB, sample DDL files)
- [ ] `tests/test_ddl_parser.py` — stubs for INGEST-01
- [ ] `tests/test_store.py` — stubs for STORE-01 through STORE-04
- [ ] `tests/test_server.py` — stubs for MCP-01, MCP-02
- [ ] `tests/test_cli.py` — stubs for CLI-01, CLI-02
- [ ] `tests/test_config.py` — stubs for CONFIG-02, CONFIG-03
- [ ] pytest + pytest-asyncio dev dependency install

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MCP server registers in Claude Code | MCP-01 | Requires Claude Code IDE integration | 1. Run `db-wiki-mcp` 2. Register in Claude Code settings 3. Verify tool list appears |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
