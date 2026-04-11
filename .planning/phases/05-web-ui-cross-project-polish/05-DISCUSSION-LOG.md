# Phase 5: Web UI + Cross-Project + Polish - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 05-web-ui-cross-project-polish
**Areas discussed:** Graph visualization UX, Daemon lifecycle, Cross-project pattern sharing, Export & dashboard format

---

## Graph Visualization UX

### Initial load behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Full schema overview | Show all tables as nodes with FK/relationship edges on load | ✓ |
| Search-first | Empty canvas with search bar, build outward from searched node | |
| Smart default | Top-20 most connected tables on load with search bar | |

**User's choice:** Full schema overview
**Notes:** Good for the target use case — legacy databases where you want to see the big picture.

### Detail panel interaction

| Option | Description | Selected |
|--------|-------------|----------|
| Side panel (right drawer) | Slides in from right, shows L1/L2 wiki content, graph shrinks | ✓ |
| Split pane (resizable) | Graph left, detail right with draggable divider | |
| Overlay tooltip | Floating card near clicked node, dismisses on click-away | |

**User's choice:** Side panel (right drawer)
**Notes:** Standard pattern, gives plenty of room for L2 detail content.

### Confidence & gap visualization

| Option | Description | Selected |
|--------|-------------|----------|
| Opacity-based | Node/edge opacity scales with confidence, gaps get dashed border | ✓ |
| Color gradient | Green → yellow → red scale, gaps with distinct color outline | ✓ |
| Toggle overlay | Default view is clean, toggle activates confidence diagnostic mode | ✓ |

**User's choice:** All three combined
**Notes:** Layered approach — opacity as baseline, color gradient available, toggle to switch modes.

---

## Daemon Lifecycle

### Process model

| Option | Description | Selected |
|--------|-------------|----------|
| In-process background thread | Foreground process, Ctrl+C stops, no PID file | |
| Forked background process | Fork to background, PID file, start/stop/status commands | |
| Combined with web server | `db-wiki serve` runs web UI + learning loop in same process | ✓ |

**User's choice:** Combined with web server
**Notes:** Single process to manage. `--no-ui` flag for headless learning only.

### Learning frequency mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed defaults | fast=5min, medium=1hr, deep=24hr, human=on-demand | |
| Adaptive | Start with defaults, adjust based on gap count and growth rate | ✓ |
| User-defined only | No presets, user sets all intervals in config | |

**User's choice:** Adaptive
**Notes:** Self-tunes based on gap count and knowledge growth rate.

### MCP server relationship

| Option | Description | Selected |
|--------|-------------|----------|
| Separate processes | `db-wiki serve` for web+learning, `db-wiki-mcp` for MCP stdio | ✓ |
| Unified with mode flag | Single `db-wiki serve` with `--mcp` flag for stdio transport | |

**User's choice:** Separate processes
**Notes:** Keeps existing two-entry-point pattern from Phase 1 D-06.

---

## Cross-Project Pattern Sharing

### Population model

| Option | Description | Selected |
|--------|-------------|----------|
| Automatic with opt-out | Every project contributes to `~/.db-wiki/cross.db` automatically | |
| Explicit opt-in per project | `db-wiki export --to-cross` to push patterns | ✓ |
| Export/import model | No global store, file-based portable exchange | |

**User's choice:** Explicit opt-in per project
**Notes:** Safe for sensitive databases — no surprises.

### Shareable pattern scope

| Option | Description | Selected |
|--------|-------------|----------|
| Naming conventions only | Column naming patterns only | |
| Naming + enum values | Add common enum labels | |
| Full pattern set | Naming, enums, schema shapes, state machine templates | ✓ |

**User's choice:** Full pattern set
**Notes:** Maximum knowledge transfer with confidence penalty as guard.

### Confidence penalty model

| Option | Description | Selected |
|--------|-------------|----------|
| Flat discount | All cross-project patterns at 50% of original confidence | |
| Similarity-scaled | Penalty proportional to schema similarity | ✓ |
| Fixed low ceiling | Always start at confidence 0.3 regardless of source | |

**User's choice:** Similarity-scaled
**Notes:** More useful when schemas actually resemble each other.

---

## Export & Dashboard Format

### Dashboard presentation

| Option | Description | Selected |
|--------|-------------|----------|
| CLI table only | Rich table output from `db-wiki status` | |
| CLI + web dashboard | CLI table + `/dashboard` route with charts | ✓ |
| Web only | Dashboard in web UI, CLI has basic stats only | |

**User's choice:** CLI + web dashboard
**Notes:** Best of both — quick CLI checks plus rich web charts.

### Export command interface

| Option | Description | Selected |
|--------|-------------|----------|
| Per-format flags | `--markdown`, `--mermaid`, etc. for specific formats | ✓ |
| Export-all bundle | `db-wiki export` generates all formats to output directory | ✓ |
| Per-entity export | `db-wiki export orders --format markdown` for granular control | ✓ |

**User's choice:** All three combined
**Notes:** Full flexibility — default exports everything, flags for format selection, positional arg for entity scoping.

### MCP manage tools scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full mirror | All manage commands as both CLI and MCP tools | ✓ |
| Selective | status/history/export as both, lint/loop CLI-only | |

**User's choice:** Full mirror
**Notes:** Consistent with Phase 2/4 pattern where CLI mirrors MCP.

---

## Claude's Discretion

- vis.js layout algorithm and clustering configuration
- Node color scheme for entity types
- Search/filter UI implementation details
- Adaptive frequency algorithm specifics
- Schema similarity metric for cross-project penalty
- Web dashboard chart library choice
- Export file/directory naming conventions
- Pydantic models for manage tool schemas

## Deferred Ideas

None — discussion stayed within phase scope
