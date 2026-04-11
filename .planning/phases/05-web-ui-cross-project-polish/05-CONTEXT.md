# Phase 5: Web UI + Cross-Project + Polish - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can visually explore the knowledge graph via a local web page, share patterns across databases, schedule background learning, view a maturity dashboard, and export knowledge in multiple formats. Implements graph visualization (vis.js), daemon mode (web UI + learning loop), cross-project pattern database, manage/export MCP tools and CLI commands.

</domain>

<decisions>
## Implementation Decisions

### Graph Visualization UX
- **D-01:** Full schema overview on initial load — show all tables as nodes with FK/relationship edges. User clicks to expand SP connections and deeper details. Targets small-to-medium schemas (<100 tables).
- **D-02:** Side panel (right drawer) for detail — slides in from right showing L1/L2 wiki content on node click. Graph shrinks to make room. Panel stays open until explicitly closed. Standard pattern (GitHub, Linear).
- **D-03:** Layered confidence visualization — opacity as baseline (1.0 = fully opaque, 0.3 = faded), color gradient available (green → yellow → red), with a toggle to switch between normal type-based view and confidence diagnostic mode. Gaps get dashed border or pulsing animation.

### Daemon Lifecycle
- **D-04:** Combined web + learning process — `db-wiki serve` starts both the web UI (starlette/uvicorn) and background learning loop in the same process. `db-wiki serve --no-ui` for headless learning only.
- **D-05:** Adaptive learning frequencies — defaults: fast=5min, medium=1hr, deep=24hr, human=on-demand. Self-tunes based on gap count and knowledge growth rate. If many gaps, increase frequency. If plateau, decrease. Intervals configurable in `config.yaml` as overrides.
- **D-06:** Separate MCP process — `db-wiki-mcp` remains the standalone MCP stdio server (Phase 1 D-06). `db-wiki serve` does not serve MCP. Two entry points, clear separation.

### Cross-Project Pattern Sharing
- **D-07:** Explicit opt-in per project — user runs `db-wiki export --to-cross` to push patterns to `~/.db-wiki/cross.db`. Nothing shared unless explicitly requested. Safe for sensitive databases.
- **D-08:** Full pattern set shareable — naming conventions, enum values, common schema shapes (audit tables, soft delete patterns, polymorphic associations), and state machine templates. Maximum knowledge transfer.
- **D-09:** Similarity-scaled confidence penalty — penalty proportional to schema similarity between source and target. Close naming pattern match = lower penalty (~20% discount). Very different schemas = higher penalty (~70% discount). More accurate cross-project application.

### Export & Dashboard
- **D-10:** CLI + web dashboard — `db-wiki status` prints coverage %, gap count, conflict count, top gaps, and knowledge growth trend as a rich table. Web UI has a `/dashboard` route with charts (coverage over time, gap burndown).
- **D-11:** Flexible export command — `db-wiki export` generates all formats (markdown wiki, Mermaid ER, JSON schema, annotated DDL) for all entities to `.db-wiki/export/`. Per-format flags (`--markdown`, `--mermaid`, etc.) to select specific formats. Per-entity scoping (`db-wiki export orders --format markdown`) for granular control.
- **D-12:** Full CLI/MCP mirror for manage tools — all MCP-06 tools (dbwiki:status, dbwiki:lint, dbwiki:history, dbwiki:export, dbwiki:loop) available as both CLI commands and MCP tools. Consistent with Phase 2/4 pattern.

### Claude's Discretion
- vis.js layout algorithm and clustering configuration
- Node color scheme for entity types (tables, SPs, columns)
- Search/filter UI implementation in graph page
- Adaptive frequency algorithm specifics (thresholds, adjustment rates)
- Schema similarity metric for cross-project confidence penalty
- Web dashboard chart library choice (Chart.js, lightweight option)
- Export file/directory naming conventions
- Pydantic models for manage tool input/output schemas

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 5 requirements
- `.planning/REQUIREMENTS.md` — UI-01 through UI-06, CLI-05, MCP-06, CROSS-01, CROSS-02, EXPORT-01, EXPORT-03, LEARN-13

### Technology stack
- `CLAUDE.md` §Technology Stack — uvicorn + starlette for web server, vis.js for graph visualization (Option B: browser-side with JSON API), schedule library for background loop, pyvis notes
- `CLAUDE.md` §Web UI Graph Visualization — vis.js as de-facto standard, CDN loadable, starlette serves static HTML + `/api/graph` JSON endpoint

### Prior phase decisions
- `.planning/phases/01-foundation/01-CONTEXT.md` — Two entry points D-06 (db-wiki CLI, db-wiki-mcp MCP server), config system D-07/D-08, project structure D-05
- `.planning/phases/02-sp-parsing-knowledge-graph/02-CONTEXT.md` — --watch mode deferred to Phase 5 (D-12), BFS traversal D-05/D-06, hybrid search D-08
- `.planning/phases/03-learning-loop/03-CONTEXT.md` — Scheduling deferred to Phase 5 (D-06), agent architecture D-01 through D-04, orchestrator for single-pass loop execution
- `.planning/phases/04-query-engine/04-CONTEXT.md` — Manage tools deferred to Phase 5 (D-10), wiki page generation D-06

### Existing code
- `db_wiki/server/app.py` — FastMCP server pattern, extend with manage tools
- `db_wiki/cli/app.py` — Typer CLI, extend with serve/export/status commands
- `db_wiki/core/config.py` — YAML config, extend with web UI and daemon settings
- `db_wiki/learning/orchestrator.py` — Learning loop single-pass execution, wrap with scheduler
- `db_wiki/graph/bfs.py` — BFS traversal, reuse for graph API endpoint
- `db_wiki/query/wiki.py` — Wiki page generation, reuse for detail panel content
- `db_wiki/search/hybrid.py` — Hybrid search, reuse for graph search/filter

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db_wiki/graph/bfs.py` — BFS traversal with edge type filtering. Directly usable for `/api/graph` endpoint to return node neighbors at specified depth.
- `db_wiki/query/wiki.py` — Wiki page generation (L1/L2 content). Provides the detail panel content when user clicks a node.
- `db_wiki/search/hybrid.py` — Hybrid vector + FTS5 search. Powers the graph search/filter functionality.
- `db_wiki/learning/orchestrator.py` — Single-pass learning loop. Wrap with `schedule` library for background execution.
- `db_wiki/core/config.py` — Pydantic config model with nested sections. Extend with `web`, `daemon`, and `cross_project` sections.
- `db_wiki/server/app.py` — FastMCP tool registration. Add manage tools (status, lint, history, export, loop) following same pattern.
- `db_wiki/cli/app.py` — Typer commands. Add serve, export, status commands following same pattern.

### Established Patterns
- FastMCP @mcp.tool() decorator with Pydantic input schemas for MCP tools
- Typer command groups mirroring MCP tool surface
- Bi-temporal views as mandatory access layer for all queries
- YAML config with Pydantic validation
- Hybrid agents: pure Python + optional LLM enhancement

### Integration Points
- New `db_wiki/web/` package for starlette app, static files, and API routes
- `db_wiki/daemon/` package for scheduler wrapping orchestrator
- `db_wiki/cross/` package for cross-project store management
- `pyproject.toml` — new dependencies: uvicorn, starlette, schedule
- `db-wiki serve` entry point in pyproject.toml

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-web-ui-cross-project-polish*
*Context gathered: 2026-04-11*
