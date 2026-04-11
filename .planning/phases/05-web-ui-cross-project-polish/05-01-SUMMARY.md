---
phase: 05-web-ui-cross-project-polish
plan: "01"
subsystem: web-ui
tags: [starlette, vis.js, chart.js, web-ui, api-routes, graph-visualization]
dependency_graph:
  requires:
    - db_wiki.graph.bfs.bfs_graph
    - db_wiki.query.wiki.get_wiki_page
    - db_wiki.search.hybrid.hybrid_search
    - db_wiki.core.store.open_store
    - db_wiki.core.config.DBWikiConfig
  provides:
    - db_wiki.web.app.create_web_app
    - db_wiki.web.routes.make_routes
    - db_wiki/web/static/index.html
    - db_wiki/web/static/dashboard.html
  affects:
    - db_wiki.core.config.DBWikiConfig (extended with WebConfig, DaemonConfig)
    - pyproject.toml (added starlette, uvicorn dependencies)
tech_stack:
  added:
    - starlette>=0.38 (ASGI web framework for API routes and static file serving)
    - uvicorn>=0.30 (ASGI server for running the starlette app)
    - anyio.to_thread.run_sync (non-blocking DB call pattern)
  patterns:
    - API routes declared before StaticFiles mount to avoid shadowing
    - Closure-based route handlers capture conn+config from create_web_app
    - All blocking SQLite calls wrapped in anyio.to_thread.run_sync
    - vis.js DataSet for client-side graph state management
    - Chart.js for dashboard metric visualization
key_files:
  created:
    - db_wiki/web/__init__.py
    - db_wiki/web/app.py
    - db_wiki/web/routes.py
    - db_wiki/web/static/index.html
    - db_wiki/web/static/dashboard.html
  modified:
    - db_wiki/core/config.py (added WebConfig, DaemonConfig to DBWikiConfig)
    - pyproject.toml (added starlette, uvicorn dependencies)
decisions:
  - "Route ordering: API routes declared before Mount StaticFiles to prevent shadowing (RESEARCH pitfall 2)"
  - "Closure pattern: make_routes() returns 5 async functions capturing conn+config via closure"
  - "BFS node ID format: 't_{id}' prefix for all table nodes to allow entity type disambiguation"
  - "Depth cap: min(int(depth_param), 5) enforces T-05-01 DoS prevention"
  - "Thread safety: one conn per create_web_app call; blocking calls run in anyio thread pool"
metrics:
  duration_minutes: 45
  completed_date: "2026-04-11"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 2
---

# Phase 5 Plan 01: Web App with vis.js Graph and Chart.js Dashboard Summary

Starlette web app with vis.js graph visualization page, Chart.js dashboard page, and 5 JSON API endpoints serving knowledge graph data from the existing SQLite store.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create starlette web app with JSON API routes | 551b3a9 | db_wiki/web/app.py, db_wiki/web/routes.py, db_wiki/core/config.py, pyproject.toml |
| 2 | Create static HTML pages (graph + dashboard) | 8b41f7e | db_wiki/web/static/index.html, db_wiki/web/static/dashboard.html |

## What Was Built

### Task 1: Starlette Web App + API Routes

`db_wiki/web/app.py` provides `create_web_app(db_path, config) -> Starlette` that:
- Opens its own SQLite connection via `open_store(db_path)` (thread-safe)
- Declares 5 API routes before the static file mount (prevents shadowing)
- Serves `db_wiki/web/static/` with `html=True` for SPA-style routing

`db_wiki/web/routes.py` provides `make_routes(conn, config)` returning 5 async handlers:
- `graph_api`: Full schema load or BFS expansion (`/api/graph`, `/api/graph?node=X&depth=N`)
- `wiki_api`: L1/L2 wiki content for an entity (`/api/wiki?entity_id=X`)
- `search_api`: Hybrid search results (`/api/search?q=...`)
- `dashboard_api`: Coverage metrics and gap summary (`/api/dashboard`)
- `export_api`: Stub returning 501 (`/api/export` POST, deferred to Plan 04)

`db_wiki/core/config.py` extended with:
- `WebConfig(host="127.0.0.1", port=8080)`
- `DaemonConfig(fast_interval_minutes=5, medium_interval_minutes=60, deep_interval_minutes=1440, adaptive=True)`

### Task 2: Static HTML Pages

`index.html` (vis.js graph page) implements:
- Toolbar: "DB Wiki" title, search input (debounced 300ms), Type/Confidence view toggle, Dashboard link, Export All button
- Graph canvas: vis.js Network with forceAtlas2Based physics (200 iterations, then physics disabled)
- Side panel (360px, slides in from right on node click): entity name, type badge, confidence, L1/L2 wiki content, gap badges
- Node type colors: table=#3b82f6, stored_procedure=#8b5cf6, column=#10b981, index=#f59e0b, constraint=#6b7280
- Confidence view: maps confidence score to color (#22c55e → #ef4444) with opacity 0.45–1.0
- Gap nodes: borderDashes=[6,3], border=#ef4444 with CSS pulse animation
- Empty state: "No schema ingested yet" with instructions
- Error state: "Could not load graph data" with troubleshooting tip

`dashboard.html` (Chart.js dashboard page) implements:
- Same toolbar (Graph link instead of Dashboard link)
- Stat row: Schema Coverage %, Open Gaps N, Conflicts N
- Charts row: Coverage Over Time (line), Gap Burndown (bar) using chart.js@4.5.1
- Top Gaps table: gap_type, description, severity, attempts, last_attempted

## Threat Mitigations Applied

| ID | Mitigation | Implementation |
|----|-----------|----------------|
| T-05-01 | BFS depth DoS cap | `depth = min(int(depth_param), 5)` in `graph_api` |
| T-05-03 | Generic error messages | All exceptions log full trace but return generic JSON error strings |
| T-05-04 | node param as int | `int(node_param)` with try/except returning 400 on ValueError |
| T-05-05 | Export POST stub | Returns 501 — no filesystem writes yet |

## Deviations from Plan

**1. [Rule 2 - Missing Dependency] Added starlette and uvicorn to pyproject.toml**
- Found during: Task 1 setup
- Issue: starlette and uvicorn were not in pyproject.toml dependencies
- Fix: Added `starlette>=0.38,<1` and `uvicorn>=0.30,<1`
- Files modified: pyproject.toml

**2. [Rule 3 - Worktree Branch Issue] Bad initial commit undone**
- Found during: Task 1 commit
- Issue: Worktree was created from wrong branch, causing `git reset --soft` to stage thousands of unrelated .claude/skills files. First commit attempt included 3401 extra files.
- Fix: Used `node -e "execSync('git reset ...')"` to undo the bad commit, then staged only the correct files.
- Impact: No code changes, just commit history cleanup. Task 1 commit (551b3a9) is clean.

**3. [Rule 3 - Context Shift] Orchestrator merged worktree mid-execution**
- Found during: Task 2
- Issue: The orchestrator merged the worktree branch during Task 1 execution. Bash cwd shifted to main repo.
- Fix: Task 2 HTML files were written to and committed in the main repo (D:/Working/Project/db-wiki) which is correct. Work continued without disruption.

## Known Stubs

- `/api/export` (POST) — returns `{"status": "not_implemented", "export_path": ""}` with 501. Per plan, actual implementation is deferred to Plan 04.

## Threat Flags

None — no new network endpoints beyond what's in the plan's threat model.

## Self-Check

### Files Created
- [x] db_wiki/web/__init__.py — exists
- [x] db_wiki/web/app.py — exists, contains `create_web_app`, `from starlette.applications import Starlette`, `StaticFiles`
- [x] db_wiki/web/routes.py — exists, contains all 4 async handlers, `anyio.to_thread.run_sync`, `min(int(depth_param), 5)`
- [x] db_wiki/web/static/index.html — exists, contains `vis-network@10.0.2`, `DB Wiki`, `#1a1a2e`, `#16213e`, `forceAtlas2Based`, `borderDashes`, `No schema ingested yet`, `/api/graph`, `/api/wiki`, `/api/search`
- [x] db_wiki/web/static/dashboard.html — exists, contains `chart.js@4.5.1`, `Schema Coverage`, `/api/dashboard`

### Modified Files
- [x] db_wiki/core/config.py — contains `class WebConfig` and `class DaemonConfig`
- [x] pyproject.toml — contains `starlette>=0.38` and `uvicorn>=0.30`

### Commits
- [x] 551b3a9 — feat(05-01): create starlette web app with JSON API routes
- [x] 8b41f7e — feat(05-01): create vis.js graph page and Chart.js dashboard page

## Self-Check: PASSED
