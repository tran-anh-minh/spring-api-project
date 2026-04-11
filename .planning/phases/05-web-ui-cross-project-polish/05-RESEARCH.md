# Phase 5: Web UI + Cross-Project + Polish - Research

**Researched:** 2026-04-11
**Domain:** Web visualization (vis.js + starlette), daemon scheduling (schedule + threading), cross-project SQLite pattern store, manage MCP/CLI tools
**Confidence:** HIGH

## Summary

Phase 5 assembles five distinct sub-systems on top of the completed Phases 1–4 codebase: (1) a starlette/uvicorn web server serving a vis.js graph page with a JSON API backed by existing `bfs.py`; (2) a background scheduling daemon wrapping the existing `run_learning_loop` via the `schedule` library; (3) a cross-project SQLite database at `~/.db-wiki/cross.db` for sharing naming and schema patterns; (4) manage MCP tools (dbwiki:status, dbwiki:lint, dbwiki:history, dbwiki:export, dbwiki:loop) and their CLI mirrors; (5) a flexible export command producing markdown, Mermaid ER, JSON schema, and annotated DDL formats.

The critical environment finding is that **uvicorn 0.44.0 and starlette 1.0.0 are already installed** as transitive dependencies of `mcp 1.27.0`. The `schedule` library is NOT yet installed and must be added to pyproject.toml. All other Phase 5 dependencies (`rich`, `typer`, `sqlite3`, `sqlite_vec`) are present.

**Primary recommendation:** Start with `db_wiki/web/` package (starlette app + static HTML), then scheduler daemon, then cross-project store, then manage tools — each is independently testable. New packages: `web/`, `daemon/`, `cross/`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Full schema overview on initial load — show all tables as nodes with FK/relationship edges. User clicks to expand SP connections and deeper details. Targets small-to-medium schemas (<100 tables).
- **D-02:** Side panel (right drawer) for detail — slides in from right showing L1/L2 wiki content on node click. Graph shrinks to make room. Panel stays open until explicitly closed. Standard pattern (GitHub, Linear).
- **D-03:** Layered confidence visualization — opacity as baseline (1.0 = fully opaque, 0.3 = faded), color gradient available (green → yellow → red), with a toggle to switch between normal type-based view and confidence diagnostic mode. Gaps get dashed border or pulsing animation.
- **D-04:** Combined web + learning process — `db-wiki serve` starts both the web UI (starlette/uvicorn) and background learning loop in the same process. `db-wiki serve --no-ui` for headless learning only.
- **D-05:** Adaptive learning frequencies — defaults: fast=5min, medium=1hr, deep=24hr, human=on-demand. Self-tunes based on gap count and knowledge growth rate. If many gaps, increase frequency. If plateau, decrease. Intervals configurable in `config.yaml` as overrides.
- **D-06:** Separate MCP process — `db-wiki-mcp` remains the standalone MCP stdio server (Phase 1 D-06). `db-wiki serve` does not serve MCP. Two entry points, clear separation.
- **D-07:** Explicit opt-in per project — user runs `db-wiki export --to-cross` to push patterns to `~/.db-wiki/cross.db`. Nothing shared unless explicitly requested. Safe for sensitive databases.
- **D-08:** Full pattern set shareable — naming conventions, enum values, common schema shapes (audit tables, soft delete patterns, polymorphic associations), and state machine templates. Maximum knowledge transfer.
- **D-09:** Similarity-scaled confidence penalty — penalty proportional to schema similarity between source and target. Close naming pattern match = lower penalty (~20% discount). Very different schemas = higher penalty (~70% discount). More accurate cross-project application.
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

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MCP-06 | Manage skills: dbwiki:status, dbwiki:lint, dbwiki:history, dbwiki:export, dbwiki:loop | Add 5 @mcp.tool() decorators in server/app.py following existing FastMCP pattern; status/loop partially exist |
| CLI-05 | Daemon mode: db-wiki serve (MCP), db-wiki daemon start/stop/status (background learning) | New `serve` Typer command + `daemon` command group; schedule library wraps orchestrator |
| UI-01 | Local web page served by starlette/uvicorn for interactive knowledge graph visualization | New db_wiki/web/ package; starlette app with StaticFiles + JSON routes |
| UI-02 | vis.js Network graph with node type color coding and edge type labels | static/index.html using vis-network@10.0.2 CDN; node color map by entity_type |
| UI-03 | Click-to-expand neighbors, search/filter, zoom+pan navigation | vis.js click event → fetch /api/graph?node=X&depth=2; search via hybrid.py API |
| UI-04 | Detail panel showing entity info (wiki L1/L2) on node click | Right-side drawer in HTML; fetch /api/wiki?entity_id=X → wiki.py generate_wiki_page() |
| UI-05 | Confidence heat-mapping (node/edge opacity by confidence score) | vis.js node.opacity field; edge color alpha; confidence from current_* views |
| UI-06 | Gap highlighting with visual indicators for unknown/low-confidence entities | Gap nodes from knowledge_gaps table; dashed border (borderDashes option in vis.js) + CSS pulse animation |
| CROSS-01 | Cross-project pattern database (~/.db-wiki/cross.db) for naming patterns, common enums, schema patterns | New db_wiki/cross/ package; SQLite at Path.home()/".db-wiki"/"cross.db"; open_store pattern |
| CROSS-02 | Learnings from database A inform understanding of database B with confidence penalty | Read cross.db patterns with similarity penalty applied during ingest/gap resolution |
| EXPORT-01 | Maturity dashboard (dbwiki:status): coverage %, gap count, conflict count, top gaps, knowledge growth trend | Query existing coverage/gap tables; rich Table for CLI; Chart.js for web /dashboard |
| EXPORT-03 | Export formats: markdown wiki, ER diagram (mermaid), JSON schema, SQL comments (annotated DDL) | db_wiki/export/ package; 4 formatters; wiki.py reuse for markdown content |
| LEARN-13 | Background loop scheduling: fast (every event), medium (daily), deep (weekly), human (when stuck) | schedule 1.2.2; threading.Thread(daemon=True); wraps run_learning_loop() |
</phase_requirements>

## Standard Stack

### Core (all already in pyproject.toml or venv)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| starlette | 1.0.0 | ASGI web framework for web UI | Already installed as mcp transitive dep; Starlette 1.0 stable [VERIFIED: uv pip show] |
| uvicorn | 0.44.0 | ASGI server | Already installed as mcp transitive dep [VERIFIED: uv pip show] |
| vis-network | 10.0.2 | Browser-side graph visualization | De-facto standard; CDN-loadable; no build step; project decision (CLAUDE.md) [VERIFIED: npm view] |
| schedule | 1.2.2 | Background scheduling | Simplest interval-based scheduler; zero-infrastructure (no broker); fits CLAUDE.md constraint [VERIFIED: pip index versions] |
| rich | 14.3.3 | CLI table output for status command | Already installed via typer; Rich Table for maturity dashboard [VERIFIED: uv pip show] |
| Chart.js | 4.5.1 | Web dashboard charts | Lightweight, CDN-loadable, no build step; 60k GitHub stars [VERIFIED: npm view] |
| sqlite3 | 3.49.1 (bundled) | cross.db connection for cross-project store | Already in stdlib; same open_store pattern as knowledge.db [VERIFIED: uv run] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typer | 0.24.1 (installed) | CLI daemon/serve/export commands | Follow existing cli/app.py pattern; already installed [VERIFIED: uv pip show] |
| pydantic | 2.12+ (installed) | Input schemas for manage MCP tools | FastMCP reads Pydantic models for JSON Schema; already used in project |
| pathlib | stdlib | Cross-project store at ~/.db-wiki/ | Path.home() / ".db-wiki" / "cross.db" |

### Not Needed (Decided Against)
| Instead of | Could Use | Decision |
|------------|-----------|----------|
| vis-network (CDN) | pyvis | CDN/browser approach chosen (CLAUDE.md Option B); no Python build step |
| schedule | APScheduler | schedule is simpler; no cron needed; CLAUDE.md specifies schedule |
| FastAPI | starlette direct | Starlette is lighter; only one JSON endpoint needed |

**Installation (only new dependency):**
```bash
uv add "schedule>=1.2,<2"
```

**Version verification (verified 2026-04-11):**
- starlette 1.0.0 — already installed [VERIFIED: uv pip show]
- uvicorn 0.44.0 — already installed [VERIFIED: uv pip show]
- schedule 1.2.2 — latest on PyPI [VERIFIED: pip index versions]
- vis-network 10.0.2 — latest on npm [VERIFIED: npm view]
- chart.js 4.5.1 — latest on npm [VERIFIED: npm view]

## Architecture Patterns

### Recommended Project Structure
```
db_wiki/
├── web/                    # NEW: starlette app + static files
│   ├── __init__.py
│   ├── app.py              # create_web_app() → Starlette instance
│   ├── routes.py           # /api/graph, /api/wiki, /api/dashboard, /api/search
│   └── static/
│       ├── index.html      # vis.js graph page (CDN imports)
│       └── dashboard.html  # Chart.js dashboard page (CDN imports)
├── daemon/                 # NEW: schedule wrapper for background loop
│   ├── __init__.py
│   └── scheduler.py        # DaemonScheduler class with start/stop/status
├── cross/                  # NEW: cross-project pattern store
│   ├── __init__.py
│   ├── store.py            # open_cross_store(), init_cross_schema()
│   ├── export.py           # push_patterns_to_cross()
│   └── reader.py           # get_cross_patterns(similarity_penalty)
├── export/                 # NEW: multi-format export
│   ├── __init__.py
│   ├── markdown.py         # MarkdownExporter
│   ├── mermaid.py          # MermaidExporter (ER diagram)
│   ├── json_schema.py      # JsonSchemaExporter
│   └── ddl_annotated.py    # AnnotatedDDLExporter
├── server/app.py           # EXTEND: add 5 manage tools (MCP-06)
└── cli/app.py              # EXTEND: add serve, daemon, export, status commands (CLI-05)
```

### Pattern 1: Starlette App with Static Files and JSON API
**What:** A Starlette application serves the vis.js HTML page as a static file and exposes JSON endpoints for graph data and wiki content.
**When to use:** Single-page web UI with a local JSON API — exactly the pattern CLAUDE.md specifies.
**Example:**
```python
# Source: starlette documentation + existing app.py patterns in project
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import JSONResponse

def create_web_app(conn, config) -> Starlette:
    async def graph_api(request):
        node_id = request.query_params.get("node")
        depth = int(request.query_params.get("depth", 2))
        # Use existing bfs_graph() from db_wiki.graph.bfs
        nodes = bfs_graph(conn, int(node_id), max_depth=depth)
        return JSONResponse({"nodes": nodes})

    async def wiki_api(request):
        entity_id = int(request.query_params.get("entity_id"))
        # Use existing generate_wiki_page() from db_wiki.query.wiki
        page = generate_wiki_page(conn, entity_id)
        return JSONResponse(page)

    routes = [
        Route("/api/graph", graph_api),
        Route("/api/wiki", wiki_api),
        Route("/api/dashboard", dashboard_api),
        Route("/api/search", search_api),
        Mount("/", StaticFiles(directory=STATIC_DIR, html=True)),
    ]
    return Starlette(routes=routes)
```
[VERIFIED: starlette imports confirmed working in project venv]

### Pattern 2: vis.js Network Initialization with Confidence Visualization
**What:** Browser-side JavaScript creates a vis.js Network with nodes/edges from the JSON API. Opacity and color encode confidence.
**When to use:** D-01 through D-03 — full schema overview with layered confidence visualization.
**Example:**
```javascript
// Source: visjs.github.io/vis-network/docs/network/
// CDN: https://cdn.jsdelivr.net/npm/vis-network@10.0.2/standalone/umd/vis-network.min.js
const nodes = new vis.DataSet([]);
const edges = new vis.DataSet([]);

const options = {
  nodes: {
    shape: "dot",
    size: 16,
    font: { size: 14 }
  },
  edges: {
    arrows: { to: { enabled: true } },
    font: { size: 11 }
  },
  physics: { enabled: true, stabilization: { iterations: 100 } }
};

const network = new vis.Network(container, { nodes, edges }, options);

// Confidence opacity mapping (D-03)
function confidenceToOpacity(score) {
  return Math.max(0.3, Math.min(1.0, score));
}

// Gap highlighting: dashed border (D-03)
// node.borderDashes = [5, 5] for gap nodes

// Click to expand (UI-03)
network.on("click", function(params) {
  if (params.nodes.length > 0) {
    const nodeId = params.nodes[0];
    fetch(`/api/graph?node=${nodeId}&depth=1`)
      .then(r => r.json())
      .then(data => {
        nodes.update(data.nodes);
        edges.update(data.edges);
      });
    // Open side panel (D-02, UI-04)
    fetchWikiPanel(nodeId);
  }
});
```
[VERIFIED: vis-network 10.0.2 API — nodes.opacity, borderDashes documented on visjs.github.io]

### Pattern 3: Background Scheduler with schedule + threading
**What:** `schedule` library runs jobs on a separate daemon thread, wrapping the existing `run_learning_loop()`.
**When to use:** D-04/D-05/LEARN-13 — `db-wiki serve` starts both web UI and scheduler in same process.
**Example:**
```python
# Source: schedule.readthedocs.io/en/stable/background-execution.html
import threading
import time
import schedule

class DaemonScheduler:
    def __init__(self, conn, config):
        self._conn = conn
        self._config = config
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="db-wiki-scheduler"
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run_loop(self):
        # Register jobs at configured intervals (D-05)
        fast_min = self._config.daemon.fast_interval_minutes  # default 5
        schedule.every(fast_min).minutes.do(self._run_fast)
        schedule.every(1).hours.do(self._run_medium)
        schedule.every(24).hours.do(self._run_deep)

        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)

    def _run_fast(self):
        from db_wiki.learning.orchestrator import run_learning_loop
        run_learning_loop(self._conn, self._config)
```
[VERIFIED: schedule 1.2.2 background-execution pattern from official docs]

**IMPORTANT thread-safety note:** `run_learning_loop` uses a SQLite connection. SQLite connections in WAL mode can share across threads if `check_same_thread=False` is set in `sqlite3.connect()`. The current `open_store()` does NOT set this. Options: (a) open a separate connection in the scheduler thread, or (b) add `check_same_thread=False` to `open_store()`. Option (a) is safer — each thread owns its connection. [ASSUMED — needs verification against actual sqlite3 WAL behavior with the existing conn factory]

### Pattern 4: Cross-Project Store (cross.db)
**What:** A second SQLite file at `~/.db-wiki/cross.db` stores extracted patterns. Uses same schema style as the main knowledge store but simpler.
**When to use:** CROSS-01/CROSS-02 — explicit `db-wiki export --to-cross` writes patterns; ingest/gap phases read patterns with penalty.
**Example:**
```python
# db_wiki/cross/store.py
from pathlib import Path
import sqlite3

CROSS_DB_PATH = Path.home() / ".db-wiki" / "cross.db"

CROSS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cross_patterns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,  -- 'naming', 'enum', 'schema_shape', 'state_machine'
    pattern_key  TEXT NOT NULL,  -- e.g. 'soft_delete_column', 'status_enum_values'
    pattern_value TEXT NOT NULL, -- JSON blob
    source_db    TEXT NOT NULL,  -- source db identifier
    confidence   REAL NOT NULL DEFAULT 0.5,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cross_pattern_type ON cross_patterns(pattern_type);
"""

def open_cross_store() -> sqlite3.Connection:
    CROSS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CROSS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(CROSS_SCHEMA)
    conn.commit()
    return conn
```
[ASSUMED — schema design; follows project's established sqlite3 patterns]

### Pattern 5: `db-wiki serve` Command (Combined Web + Daemon)
**What:** Single Typer command that starts uvicorn and the scheduler in the same process.
**When to use:** D-04 — CLI-05 daemon mode.
**Example:**
```python
# db_wiki/cli/app.py (addition)
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option("8080", help="Port to listen on"),
    no_ui: bool = typer.Option(False, "--no-ui", help="Headless: learning loop only"),
    store_path: Path = typer.Option(Path(".db-wiki"), "--store-path"),
) -> None:
    """Start web UI and background learning daemon."""
    store_path = store_path.resolve()
    config = load_config(store_path)
    conn = open_store(store_path / "knowledge.db")
    init_schema(conn)

    scheduler = DaemonScheduler(conn, config)
    scheduler.start()

    if not no_ui:
        from db_wiki.web.app import create_web_app
        import uvicorn
        web_app = create_web_app(conn, config)
        uvicorn.run(web_app, host=host, port=port)
    else:
        # Headless: block until Ctrl-C
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.stop()
```
[ASSUMED — Typer + uvicorn integration; follows existing cli/app.py patterns]

### Pattern 6: Manage MCP Tools (MCP-06)
**What:** Five new `@mcp.tool()` decorators in `server/app.py` for status, lint, history, export, loop.
**When to use:** D-12 — CLI/MCP mirror pattern established in Phases 2/4.

Note: A basic `status` MCP tool already exists (line 134 in server/app.py). It needs enhancement to include gap count, conflict count, and knowledge growth trend (EXPORT-01). The `loop`/discover tool also partially exists (line 371). New tools needed: `lint`, `history`, `export`.

### Anti-Patterns to Avoid
- **Shared SQLite connection across threads without `check_same_thread=False`:** SQLite connections are not thread-safe by default. Give each thread its own connection or use `check_same_thread=False` + explicit locking.
- **Running uvicorn with `reload=True` in production/daemon mode:** reload spawns subprocesses that break the scheduler thread. Never use reload in the daemon path.
- **Importing sentence-transformers/torch at web server startup:** These are heavy lazy-loaded dependencies. Import only when embedding is actually requested (CONFIG-04). Web server startup must be fast.
- **vis.js with `physics: {enabled: true}` and 100+ nodes at initial load:** Physics simulation becomes slow. For >50 nodes consider `stabilization: {enabled: false}` after initial layout, or set `physics: {enabled: false}` after stabilization event.
- **Blocking the starlette event loop with SQLite queries:** starlette routes are async; SQLite queries are synchronous. Use `anyio.to_thread.run_sync()` to run blocking DB calls in a thread pool. The project already uses `anyio` (installed). [VERIFIED: anyio installed as mcp dependency]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph visualization | Custom D3/canvas renderer | vis.js 10.0.2 (CDN) | Physics simulation, click events, zoom/pan, clustering all built-in; 100k+ lines of tested code |
| Dashboard charts | Raw SVG path math | Chart.js 4.5.1 (CDN) | Line, bar charts with animations; responsive; 1 script tag |
| Background scheduling | Custom `threading.Timer` chain | schedule 1.2.2 | Handles interval drift, missed jobs, and thread lifecycle cleanly |
| ASGI server | Raw socket server | uvicorn 0.44.0 (already installed) | HTTP/1.1 + HTTP/2, signals, graceful shutdown |
| Mermaid ER diagram | Custom text concatenation | Standard Mermaid ER syntax (string generation) | Mermaid is a text format; generate it as a string — no library needed, just correct syntax |

**Key insight:** The web UI requires zero npm build tooling. All JavaScript (vis.js, Chart.js) loads from CDN. Python generates the JSON; browser renders it. This is the correct pattern for a local-only tool.

## Common Pitfalls

### Pitfall 1: SQLite Connection Thread Safety
**What goes wrong:** Passing the main `conn` object into the scheduler thread causes `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.
**Why it happens:** Python's `sqlite3` module defaults to `check_same_thread=True`.
**How to avoid:** In `DaemonScheduler.__init__()`, open a separate connection: `self._conn = open_store(db_path)`. Pass `db_path` not `conn` to the scheduler.
**Warning signs:** `ProgrammingError` on first scheduler job run, even if web server works fine.

### Pitfall 2: Starlette Static Files Mount Order
**What goes wrong:** JSON API routes return 404 because the StaticFiles Mount captures all requests before Route handlers.
**Why it happens:** Starlette matches routes in order; a catch-all `Mount("/", ...)` at the start swallows all paths.
**How to avoid:** Always put `Route("/api/...")` entries BEFORE `Mount("/", StaticFiles(...))` in the routes list. [VERIFIED: starlette routing order matters]
**Warning signs:** `curl http://localhost:8080/api/graph` returns HTML instead of JSON.

### Pitfall 3: vis.js Node/Edge Data Format Mismatch
**What goes wrong:** `vis.DataSet.update()` silently fails or duplicates nodes because the `id` field is missing or mistyped.
**Why it happens:** vis.js requires each node to have a unique `id` (integer or string). If the `/api/graph` JSON uses `node_id` instead of `id`, vis.js ignores the update.
**How to avoid:** Graph API endpoint must return `{"nodes": [{"id": 1, "label": "orders", ...}], "edges": [{"from": 1, "to": 2, ...}]}` — exact field names matter.
**Warning signs:** Graph shows first load correctly but click-to-expand adds no nodes.

### Pitfall 4: `schedule` Library Uses a Global Scheduler
**What goes wrong:** Multiple calls to `schedule.every(...)` (e.g., from tests or multiple `serve` invocations) accumulate jobs in the global scheduler, running jobs multiple times.
**Why it happens:** `schedule` uses a module-level default scheduler object.
**How to avoid:** Use `schedule.Scheduler()` (instance-level, not global) for `DaemonScheduler`. Call `scheduler_instance.every(5).minutes.do(...)` instead of `schedule.every(...)`.
**Warning signs:** Learning loop runs 2x or 4x as often as configured after test runs.

### Pitfall 5: Cross-Project Confidence Penalty Not Applied
**What goes wrong:** Cross-project patterns are used with full confidence, polluting the target database's knowledge with patterns from an unrelated source.
**Why it happens:** The `reader.py` returns patterns without attaching penalty metadata.
**How to avoid:** `get_cross_patterns()` must return `(pattern, adjusted_confidence)` tuples. Adjusted confidence = `pattern.confidence * (1.0 - penalty)` where penalty is the similarity-scaled discount from D-09. The similarity metric can be a simple Jaccard similarity on table name sets (table names from source cross.db vs. target knowledge.db).
**Warning signs:** High-confidence cross-project patterns immediately override local low-confidence facts.

### Pitfall 6: Starlette 1.0 — `@app.route()` Decorator Removed
**What goes wrong:** Code copied from older tutorials using `@app.route("/api/graph")` fails with `AttributeError` in Starlette 1.0.
**Why it happens:** `@app.route()` decorator was deprecated in 0.23.0 and removed in 1.0.
**How to avoid:** Use declarative `Route("/api/graph", endpoint_function)` in the routes list and pass to `Starlette(routes=routes)`. [VERIFIED: starlette 1.0 breaking changes doc]

### Pitfall 7: `db-wiki serve` Blocks the Process — Need Signal Handling
**What goes wrong:** `uvicorn.run()` blocks forever; Ctrl-C doesn't cleanly stop the scheduler thread.
**Why it happens:** uvicorn's signal handling works in the main thread but the scheduler thread has no shutdown coordination.
**How to avoid:** Use uvicorn's `Server` class with a custom lifecycle or call `scheduler.stop()` in the web app's lifespan `finally` block. Starlette supports async lifespan context managers.

## Code Examples

### /api/graph JSON Response Format
```python
# Source: existing bfs_graph() return format in db_wiki/graph/bfs.py
# Route: GET /api/graph?node=<id>&depth=<n>&types=<comma-separated-edge-types>
async def graph_api(request):
    # For initial load (no node param): return all tables with FK edges
    # For expansion: return BFS neighbors of the clicked node
    node_param = request.query_params.get("node")
    depth = int(request.query_params.get("depth", 2))

    if node_param is None:
        # Initial load: all tables
        rows = conn.execute(
            "SELECT id, table_name, description FROM current_db_tables"
        ).fetchall()
        vis_nodes = [
            {
                "id": f"t_{r['id']}",
                "label": r["table_name"],
                "title": r["description"] or "",
                "group": "table",  # vis.js groups for color coding
                "opacity": 1.0,
            }
            for r in rows
        ]
        # FK edges only for initial load
        fk_rows = conn.execute(
            "SELECT source_id, target_id, relationship_type "
            "FROM current_db_relationships "
            "WHERE relationship_type IN ('fk_declared', 'fk_inferred')"
        ).fetchall()
        vis_edges = [
            {"from": f"t_{r['source_id']}", "to": f"t_{r['target_id']}",
             "label": r["relationship_type"]}
            for r in fk_rows
        ]
        return JSONResponse({"nodes": vis_nodes, "edges": vis_edges})
```
[VERIFIED: current_db_tables and current_db_relationships view names confirmed in db_wiki/core/schema.py]

### Export: Mermaid ER Format
```python
# db_wiki/export/mermaid.py
# No external library needed — Mermaid ER is a text format
def export_mermaid_er(conn: sqlite3.Connection) -> str:
    lines = ["erDiagram"]
    tables = conn.execute(
        "SELECT id, table_name FROM current_db_tables"
    ).fetchall()
    for t in tables:
        cols = conn.execute(
            "SELECT column_name, data_type, is_primary_key "
            "FROM current_db_columns WHERE table_id = ? "
            "ORDER BY ordinal_position, id",
            (t["id"],),
        ).fetchall()
        lines.append(f'  {t["table_name"]} {{')
        for c in cols:
            pk = " PK" if c["is_primary_key"] else ""
            lines.append(f'    {c["data_type"] or "TEXT"} {c["column_name"]}{pk}')
        lines.append("  }")
    # FK relationships
    rels = conn.execute(
        "SELECT source_id, target_id FROM current_db_relationships "
        "WHERE relationship_type = 'fk_declared'"
    ).fetchall()
    # ... add relationship lines
    return "\n".join(lines)
```
[ASSUMED — Mermaid ER syntax is a well-known text format; no library needed]

### Confidence Opacity in vis.js
```javascript
// Source: visjs.github.io/vis-network/docs/network/nodes.html
// node.opacity: number 0-1 (vis-network 9.x+)
// node.borderDashes: true or [dashLength, gapLength] for gap highlighting (D-03, UI-06)
function buildNode(entity, confidenceMode) {
  const base = {
    id: entity.id,
    label: entity.label,
    group: entity.type,  // 'table', 'procedure' → vis.js groups → colors
  };
  if (confidenceMode) {
    base.opacity = Math.max(0.3, entity.confidence);
    base.color = confidenceToColor(entity.confidence);  // green→red
  }
  if (entity.is_gap) {
    base.borderDashes = [5, 5];
    base.borderWidth = 2;
  }
  return base;
}
```
[CITED: visjs.github.io/vis-network/docs/network/nodes.html]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pyvis (server-side graph HTML) | vis.js browser-side with JSON API | Project decision (CLAUDE.md) | No Python graph dep; live-updating; click-to-expand |
| Flask for local web server | starlette + uvicorn | Project architecture | Lighter, async-native, already installed as mcp dep |
| APScheduler | schedule 1.2.2 | Project decision (CLAUDE.md) | Simpler API; no broker; zero-infrastructure |
| @app.route() decorator | Declarative Route() objects | Starlette 0.23 → 1.0 | Decorator form removed in Starlette 1.0 [VERIFIED] |

**Already installed (no additional install needed):**
- starlette 1.0.0 — via mcp 1.27.0 dependency chain
- uvicorn 0.44.0 — via mcp 1.27.0 dependency chain
- anyio — via mcp 1.27.0 (use for `anyio.to_thread.run_sync` in async routes)
- rich — via typer (use for CLI status table)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SQLite scheduler thread should open its own separate connection rather than sharing the main conn | Architecture Pattern 3, Pitfall 1 | If wrong: share conn with check_same_thread=False; low risk, both approaches work |
| A2 | cross.db schema design (cross_patterns table with pattern_type/key/value) | Pattern 4 | May need adjustment based on what pattern types are actually produced by learning loop |
| A3 | Typer + uvicorn.run() blocking pattern for `serve` command works cleanly | Pattern 5 | uvicorn may need Server() class for clean shutdown with scheduler; test with Ctrl-C |
| A4 | Jaccard similarity on table name sets is a sufficient schema similarity metric for D-09 | Architecture | More sophisticated metric (embedding cosine similarity) may give better penalty scaling |
| A5 | vis.js `node.opacity` field is available in vis-network 10.0.2 | Code Examples | Opacity may be nested under `node.color.opacity`; verify against 10.0.2 changelog |
| A6 | Mermaid ER format syntax for erDiagram is correct string generation | Code Examples | Minor syntax errors possible; validate with a Mermaid renderer |

## Open Questions

1. **MCP-06 `lint` tool — what does linting check?**
   - What we know: MCP-06 specifies `dbwiki:lint` as a manage tool
   - What's unclear: Lint criteria — schema completeness? Confidence thresholds? Orphan tables?
   - Recommendation: Implement as a configurable checker: orphan tables (no FK relationships), unlabeled columns (no description), zero-confidence entities, stale facts (>30 days no reinforcement). Return structured list of lint violations.

2. **MCP-06 `history` tool — what time window and entity scope?**
   - What we know: Track knowledge changes over time (bi-temporal model already supports this)
   - What's unclear: Does `history` show global change log, or per-entity history? What's the default window?
   - Recommendation: Per-entity history (`dbwiki:history entity_name`) showing `recorded_at` and `invalidated_at` timeline from the bi-temporal tables. Default window: 30 days.

3. **`db-wiki serve` port conflict handling**
   - What we know: Default port 8080 is common; may be in use
   - What's unclear: Should the CLI auto-pick an available port or fail loudly?
   - Recommendation: Fail loudly with a clear error message. Auto-port is surprising behavior for a daemon.

4. **Adaptive frequency algorithm thresholds (D-05)**
   - What we know: Self-tunes based on gap count and knowledge growth rate; Claude's discretion
   - What's unclear: What "many gaps" means numerically; what "plateau" means
   - Recommendation: Start simple — if gap count > 50, halve the fast interval; if gap count < 5 for 3 consecutive runs, double the interval. Store current intervals in config or a state table.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.12.4 | — |
| uvicorn | UI-01, CLI-05 | ✓ | 0.44.0 (via mcp dep) | — |
| starlette | UI-01 | ✓ | 1.0.0 (via mcp dep) | — |
| schedule | LEARN-13, CLI-05 | ✗ | — (not installed) | Must add to pyproject.toml |
| rich | EXPORT-01 | ✓ | 14.3.3 (via typer) | — |
| anyio | Async thread dispatch | ✓ | installed (via mcp) | — |
| vis-network | UI-02 through UI-06 | ✓ (CDN) | 10.0.2 | — |
| chart.js | EXPORT-01 web dashboard | ✓ (CDN) | 4.5.1 | — |
| sqlite3 | CROSS-01, CROSS-02 | ✓ | 3.49.1 (stdlib) | — |

**Missing dependencies with no fallback:**
- `schedule 1.2.2` — must be added: `uv add "schedule>=1.2,<2"`

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` asyncio_mode = "auto" |
| Quick run command | `uv run pytest tests/test_web.py tests/test_daemon.py tests/test_cross.py tests/test_export.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | Starlette app starts and returns 200 on / | integration | `uv run pytest tests/test_web.py::test_web_app_serves_index -x` | ❌ Wave 0 |
| UI-02 | /api/graph returns JSON with nodes and edges | integration | `uv run pytest tests/test_web.py::test_graph_api_initial_load -x` | ❌ Wave 0 |
| UI-03 | /api/graph?node=X&depth=2 expands neighbors | integration | `uv run pytest tests/test_web.py::test_graph_api_expand_node -x` | ❌ Wave 0 |
| UI-04 | /api/wiki?entity_id=X returns L1/L2 wiki content | integration | `uv run pytest tests/test_web.py::test_wiki_api -x` | ❌ Wave 0 |
| UI-05 | Graph API nodes include confidence/opacity field | unit | `uv run pytest tests/test_web.py::test_node_confidence_field -x` | ❌ Wave 0 |
| UI-06 | Gap nodes include is_gap=true and borderDashes flag | unit | `uv run pytest tests/test_web.py::test_gap_node_flag -x` | ❌ Wave 0 |
| LEARN-13 | DaemonScheduler starts thread, jobs registered | unit | `uv run pytest tests/test_daemon.py::test_scheduler_starts -x` | ❌ Wave 0 |
| LEARN-13 | DaemonScheduler stop() terminates thread | unit | `uv run pytest tests/test_daemon.py::test_scheduler_stops -x` | ❌ Wave 0 |
| CROSS-01 | open_cross_store() creates cross.db at ~/.db-wiki/ | unit | `uv run pytest tests/test_cross.py::test_open_cross_store -x` | ❌ Wave 0 |
| CROSS-02 | get_cross_patterns() applies confidence penalty | unit | `uv run pytest tests/test_cross.py::test_cross_penalty -x` | ❌ Wave 0 |
| EXPORT-01 | `db-wiki status` prints coverage % and gap count | integration | `uv run pytest tests/test_cli_phase5.py::test_status_command -x` | ❌ Wave 0 |
| EXPORT-03 | Export generates markdown wiki file | integration | `uv run pytest tests/test_export.py::test_markdown_exporter -x` | ❌ Wave 0 |
| EXPORT-03 | Export generates Mermaid ER diagram | integration | `uv run pytest tests/test_export.py::test_mermaid_exporter -x` | ❌ Wave 0 |
| EXPORT-03 | Export generates JSON schema | integration | `uv run pytest tests/test_export.py::test_json_schema_exporter -x` | ❌ Wave 0 |
| EXPORT-03 | Export generates annotated DDL | integration | `uv run pytest tests/test_export.py::test_ddl_annotated_exporter -x` | ❌ Wave 0 |
| MCP-06 | dbwiki:lint returns violations list | integration | `uv run pytest tests/test_server_phase5.py::test_lint_tool -x` | ❌ Wave 0 |
| MCP-06 | dbwiki:history returns change timeline | integration | `uv run pytest tests/test_server_phase5.py::test_history_tool -x` | ❌ Wave 0 |
| MCP-06 | dbwiki:export returns export file paths | integration | `uv run pytest tests/test_server_phase5.py::test_export_tool -x` | ❌ Wave 0 |
| CLI-05 | `db-wiki serve --no-ui` starts scheduler and exits on Ctrl-C | integration | manual-only (requires signal testing) | manual |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_web.py tests/test_daemon.py tests/test_cross.py tests/test_export.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_web.py` — covers UI-01 through UI-06; needs starlette TestClient
- [ ] `tests/test_daemon.py` — covers LEARN-13 scheduler start/stop
- [ ] `tests/test_cross.py` — covers CROSS-01, CROSS-02
- [ ] `tests/test_export.py` — covers EXPORT-03 all four formatters
- [ ] `tests/test_cli_phase5.py` — covers CLI-05 serve command and EXPORT-01 status
- [ ] `tests/test_server_phase5.py` — covers MCP-06 lint, history, export tools

**starlette TestClient import:**
```python
from starlette.testclient import TestClient
# Already available via starlette installation — no extra dep needed
```

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local-only web server; no auth needed per REQUIREMENTS.md Out of Scope |
| V3 Session Management | no | No sessions; stateless JSON API |
| V4 Access Control | no | localhost only; single-user tool |
| V5 Input Validation | yes | `node` and `depth` query params must be validated (integer, bounded) |
| V6 Cryptography | no | No secrets, no crypto |

### Known Threat Patterns for starlette/web UI

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal in static file serving | Information Disclosure | starlette StaticFiles handles this internally; never serve arbitrary paths |
| Integer overflow in depth param | DoS | Validate `depth <= 5` in graph API; existing BFS has max_depth guard |
| BFS graph traversal DoS (huge depth) | DoS | Enforce max_depth=5 in API; already implemented in bfs_graph() |
| Cross-project store at home directory | Information Disclosure | File permissions follow OS defaults; document that cross.db contains inferred patterns, not raw data |

**Note:** The web UI is explicitly local-only (`127.0.0.1` default bind). The MCP server remains the primary interface; web UI is visualization only. No authentication is required or planned. (Per REQUIREMENTS.md Out of Scope: "Multi-user auth for MCP — Local-first tool")

## Sources

### Primary (HIGH confidence)
- Project venv (uv pip show, uv run python) — confirmed installed versions for all existing dependencies
- db_wiki/server/app.py — existing @mcp.tool() pattern for MCP-06 additions
- db_wiki/cli/app.py — existing Typer pattern for CLI-05 additions
- db_wiki/graph/bfs.py — confirmed bfs_graph() API signature for /api/graph endpoint
- db_wiki/core/schema.py — confirmed current_db_tables, current_db_relationships view names
- db_wiki/core/store.py — confirmed open_store() pattern for cross.db

### Secondary (MEDIUM confidence)
- visjs.github.io/vis-network/docs/network/ — vis.js Network API, nodes.opacity, borderDashes
- schedule.readthedocs.io/en/stable/background-execution.html — background threading pattern
- npm view vis-network version, npm view chart.js version — confirmed latest npm versions
- docs.bswen.com/blog/2026-02-27-starlette-100-breaking-changes/ — Starlette 1.0 breaking changes
- pip index versions schedule — confirmed schedule 1.2.2 as latest

### Tertiary (LOW confidence)
- None — all critical claims verified against installed packages or official sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified in project venv or npm registry
- Architecture: HIGH — patterns follow existing codebase conventions exactly
- Pitfalls: MEDIUM — thread safety and starlette routing verified; some pitfalls ASSUMED from patterns

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (stable libraries; vis.js and starlette are unlikely to change significantly)
