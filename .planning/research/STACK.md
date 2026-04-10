# Stack Research

**Domain:** Python database knowledge engine — SQL parsing, SQLite graph/vector storage, MCP server, local web UI
**Researched:** 2026-04-10
**Confidence:** MEDIUM (Context7/WebSearch/WebFetch unavailable in this session; based on training data through August 2025 with explicit confidence flags per component)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | sqlglot, sentence-transformers, and MCP SDK are all Python-native. 3.11+ for `tomllib` stdlib, better perf. 3.12 is fine but 3.11 is the safer compatibility baseline given sentence-transformers wheel availability. |
| sqlglot | 25.x (latest) | T-SQL AST parsing | Only mature open-source SQL parser that handles T-SQL dialect with full AST — extracts table refs, JOIN types, WHERE predicates, INSERT…SELECT, CTE chains. Pure Python, no native deps. |
| SQLite (via `sqlite3`) | 3.45+ (bundled) | Graph + relational store | Zero infrastructure. Single file. The `sqlite3` stdlib module is sufficient for graph storage; WAL mode for concurrent reads. |
| sqlite-vec | 0.1.x | Vector similarity search | Alex Garcia's SQLite extension for ANN search directly in SQLite. Replaces Chroma/pgvector. Avoids separate vector DB infrastructure. Python package `sqlite-vec` loads the extension automatically. |
| mcp (Python SDK) | 1.x | MCP server protocol | Anthropic's official Python MCP SDK. `FastMCP` decorator API makes skill registration ~5 lines per tool. The only SDK that is guaranteed to match the MCP spec that Claude Code consumes. |
| sentence-transformers | 3.x | Local embeddings | HuggingFace library for running embedding models locally. `all-MiniLM-L6-v2` (384-dim, 22MB) is the right default for this use case — fast CPU inference, good semantic quality for SQL/schema text. |
| pyodbc | 4.x | Live SQL Server connection | De-facto standard Python → SQL Server via ODBC. Works with Microsoft ODBC Driver 17/18. Needed for Collector Agent data sampling. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| bfsvtab | 0.x (Alex Garcia) | BFS graph traversal as SQLite virtual table | Required for JOIN path finding (hop 1–5 traversal). Lets you write `SELECT * FROM bfs(graph, start_node, max_depth)` in SQL. Use when implementing `lineage` and `path_find` skills. |
| FTS5 | Built into SQLite 3.20+ | Full-text keyword search | Keyword fallback in hybrid search. Already in SQLite stdlib — no install needed. Use `CREATE VIRTUAL TABLE ... USING fts5(...)` for SP names, column descriptions, wiki content. |
| openai | 1.x | OpenAI embeddings (optional) | Only loaded when user sets `embedding_provider=openai`. `text-embedding-3-small` (1536-dim) gives higher quality at cost of API calls and privacy. Make this a soft dependency. |
| uvicorn + starlette | 0.30.x / 0.38.x | Web server for local UI | Lightweight ASGI server for serving the graph visualization web page. Starlette for routing static files + a `/api/graph` JSON endpoint. Avoids Flask weight for this use case. |
| pyvis OR vis.js (client-side) | pyvis 0.3.x | Graph visualization | Two options below — see Stack Patterns section. pyvis generates self-contained HTML from Python; vis.js runs in browser with the JSON API. |
| pydantic | 2.x | Config + data validation | MCP tool input schemas use Pydantic models. FastMCP auto-generates JSON Schema from Pydantic. Also use for config file parsing. |
| click | 8.x | CLI interface | Standard Python CLI library. `click` groups mirror MCP skills cleanly. Used in codebase-memory-mcp and other reference tools. |
| schedule OR APScheduler | schedule 1.x | Background learning loop | `schedule` is simpler for fixed-interval loops (fast/medium/deep frequencies). APScheduler if cron-style scheduling needed. Default: `schedule`. |
| pyproject.toml / uv | uv 0.4+ | Package management | `uv` for fast installs. `pyproject.toml` as the single source of truth for deps. Required for clean MCP install experience (`uvx db-wiki` workflow). |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package manager + virtual env | Faster than pip, better lockfile story than poetry for OSS distribution. `uv run` avoids explicit venv activation for CLI use. |
| pytest | Unit + integration testing | Standard. Use `pytest-asyncio` for async MCP handler tests. |
| ruff | Linting + formatting | Replaces flake8 + black + isort in one tool. Extremely fast. |
| pyright | Type checking | Better than mypy for Pydantic v2 + modern Python type hints. |

---

## Installation

```bash
# Core dependencies (pyproject.toml)
uv add sqlglot mcp sqlite-vec sentence-transformers pyodbc pydantic click

# Web UI
uv add uvicorn starlette

# Optional (OpenAI embeddings)
uv add openai

# Dev
uv add --dev pytest pytest-asyncio ruff pyright

# Background scheduling
uv add schedule
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| sqlglot | antlr4-python3-runtime + T-SQL grammar | If you need 100% T-SQL spec compliance for edge cases (PIVOT, OPENJSON, FOR XML). sqlglot is ~95% complete on T-SQL. ANTLR is more complete but requires maintaining a grammar file and is significantly heavier. |
| sqlglot | python-sqlparse | Never for this project. sqlparse is a tokenizer, not a parser — it produces no AST and cannot extract relationships or analyze control flow. |
| sqlite-vec | chromadb | If you want a richer vector DB API. But Chroma requires a separate process or heavy deps. sqlite-vec keeps everything in one `.db` file, which is required by the zero-infrastructure constraint. |
| sqlite-vec | faiss | faiss is faster at large scale but is a C++ lib with complex install. sqlite-vec is pure SQL API, simpler, and at <1M embeddings the performance difference is irrelevant. |
| sentence-transformers | OpenAI `text-embedding-3-small` | If the user opts in to cloud embeddings. Better quality (especially for business/financial language). Required config toggle, not the default (privacy constraint). |
| mcp (official SDK) | Building raw JSON-RPC server | Never. The official SDK handles transport negotiation, protocol versioning, and tool schema generation. Hand-rolling the protocol is fragile and breaks on spec updates. |
| uvicorn + starlette | Flask | Flask works but adds more deps. Starlette is lighter and async-native, which matters when the web UI is served alongside an async MCP server loop. |
| uvicorn + starlette | FastAPI | FastAPI is overkill — we only need a static file server + one JSON endpoint. FastAPI adds pydantic-dependent OpenAPI generation that's wasted here. |
| uv | pip + venv | uv is strictly better for new projects. Faster, better lockfile, supports `uvx` for zero-install CLI. |
| click | argparse | click is cleaner for nested command groups (e.g., `db-wiki ingest`, `db-wiki ask`). argparse works but is more verbose. |
| schedule | celery | celery requires a message broker (Redis/RabbitMQ). Zero-infrastructure constraint makes celery a non-starter. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| python-sqlparse | Tokenizer only, no AST. Cannot extract table references, JOIN conditions, or control flow from stored procedures. Commonly confused with a parser but produces no usable tree. | sqlglot |
| Neo4j | Requires a running Docker container or server process. Violates the zero-infrastructure constraint. overkill for a single-project knowledge store. | SQLite + bfsvtab for graph traversal |
| chromadb (as primary store) | Separate process/file system. Heavy C++ deps. Unnecessary when sqlite-vec provides ANN search inside the same SQLite file. | sqlite-vec inside the project's SQLite DB |
| langchain | Enormous dependency tree, frequent breaking changes, abstracts away control that this project needs explicit. The architecture is custom (5-layer, 4-op pipeline) — langchain abstractions fight you more than help. | Direct library calls (sqlglot, mcp, sentence-transformers) |
| pgvector / postgres | Requires a running Postgres server. Violates zero-infrastructure. | sqlite-vec |
| networkx | Python-only in-memory graph. Can't persist or query at scale. Good for prototyping but breaks at 100k+ nodes. | SQLite adjacency table + bfsvtab |
| Flask | More deps than needed for a single static-file server + one API route. Sync-only adds complexity with an async MCP server. | uvicorn + starlette |
| spaCy for NLP/entity extraction | spaCy's NER is trained for natural language prose, not SQL code. Would misidentify SQL keywords as entities. This project extracts entities from DDL/AST, not from text. | sqlglot AST traversal + custom domain extractors |
| PyMSSQL | Deprecated. Last meaningful update 2021. ODBC-based pyodbc is the current standard for SQL Server from Python. | pyodbc |

---

## Stack Patterns by Variant

**If user has no live DB connection (file-only mode):**
- Skip pyodbc entirely
- Parse DDL + SP files from disk only
- Use sentence-transformers local embeddings (no API key needed)
- All features work except data sampling and sys.* metadata

**If user opts into OpenAI embeddings:**
- Add `openai` as soft dependency (only imported when `embedding_provider=openai`)
- Use `text-embedding-3-small` — 1536 dimensions, good cost/quality tradeoff
- Store dimension count in config — sqlite-vec tables must match embedding size at creation time

**If graph visualization is needed (web UI):**

Option A — pyvis (simpler, fully Python-side):
- `uv add pyvis`
- Generate a self-contained `graph.html` file from Python NetworkX-style API
- Serve it as a static file from starlette
- No JavaScript build step required
- Limitation: pyvis generates static snapshots, not live-updating graphs

Option B — vis.js in browser + JSON API (more interactive):
- Starlette serves `static/index.html` with vis.js loaded from CDN
- `/api/graph?node=X&depth=2` returns JSON adjacency data
- Browser renders live, with click-to-expand navigation
- This is closer to what codebase-memory-mcp does
- Recommendation: Option B — it matches the codebase-memory-mcp interaction model the user wants

**For the learning loop scheduling:**
- Use `schedule` library for simple interval-based triggers (every 5 min / 1 hr / 24 hr)
- Run in a background thread via `threading.Thread(daemon=True)`
- Do NOT use async for the scheduler — it runs blocking IO (DB queries, SP parsing) that should be in threads

---

## sqlglot T-SQL Capabilities and Limitations

**What sqlglot handles well in T-SQL:**
- `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE` statements — full AST
- `FROM`/`JOIN` clauses — table references, aliases, join types
- `WHERE`, `HAVING`, `GROUP BY`, `ORDER BY` — predicate extraction
- CTEs (`WITH ... AS`)
- Subqueries and derived tables
- `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX` — DDL
- `CREATE PROCEDURE` — parses the body as a statement list
- `EXEC`/`EXECUTE` — recognizes the node but body is opaque (dynamic SQL)
- Arithmetic and comparison expressions in predicates
- `CASE` expressions — branch extraction for enum detection

**What sqlglot does NOT handle well in T-SQL (confirmed gaps):**
- `IF`/`ELSE` control flow — parsed as nodes but the AST structure for IF blocks is not a dedicated `If` node in all versions; requires manual traversal of the token tree. Confidence: MEDIUM (this is an active development area in sqlglot)
- `WHILE` loops — similar to IF; present as parse nodes but may not be fully structured
- `DECLARE @var` + variable assignment tracking — sqlglot parses the syntax but does NOT track variable values through execution paths. You must build a custom variable-tracking visitor on top of the AST.
- `EXEC (@sql)` dynamic SQL — correctly identified as EXEC but the string content is opaque. Flag and skip.
- `GOTO` / labels — rarely used in modern SPs, but if present, control flow analysis breaks
- `TRY`/`CATCH` blocks — parsed but not structurally represented as exception flow
- Table-valued parameters (`@tvp`) — basic support; complex TVP usage may parse incorrectly
- `FOR XML` / `FOR JSON` — syntax recognized but semantic extraction is limited
- `OPENQUERY`, `OPENROWSET` — linked server queries parsed as function calls; table references inside are opaque

**Recommendation for M9 (SP control flow analysis):**
Use sqlglot for data flow (table refs, JOINs, mutations) and write a custom AST visitor for control flow. The visitor pattern sqlglot provides is solid — `node.walk()` or subclassing `sqlglot.expressions.Expression`. The control flow graph must be built manually on top of the raw AST nodes.

---

## sqlite-vec Notes

- **Python package:** `pip install sqlite-vec` — loads the compiled extension automatically via `sqlite_vec.load(conn)`
- **API:** Create a virtual table `CREATE VIRTUAL TABLE embeddings USING vec0(embedding FLOAT[384])` then `INSERT`, `SELECT ... ORDER BY vec_distance_L2(embedding, ?)` 
- **Dimension must be fixed at table creation** — if you switch from `all-MiniLM-L6-v2` (384-dim) to OpenAI (1536-dim), you need a separate table or migration
- **Approximate search:** Uses flat index by default (exact search). For >100k vectors, performance stays acceptable; at >1M vectors consider IVF index (if supported in the installed version)
- **Confidence:** MEDIUM — sqlite-vec was in active beta as of August 2025. Verify API stability before finalizing schema.

---

## bfsvtab Notes

- Created by Alex Garcia (same author as sqlite-vec)
- Provides `bfs(edges_table, start_node_id, max_depth)` as a SQLite virtual table
- Input: an edge table with `(from_id, to_id)` columns
- Output: rows of `(node_id, depth, path)` for BFS traversal
- **Installation:** Python package `sqlite-bfsvtab` or load the compiled `.so`/`.dll` — verify package name on PyPI before using
- **Confidence:** LOW — bfsvtab is less documented than sqlite-vec. The project must verify PyPI availability and current API. Consider fallback: implement BFS in Python using `collections.deque` and SQLite `SELECT neighbors WHERE from_id=?` queries. Python BFS over SQLite is sufficient for <100k nodes.

---

## MCP SDK Notes

- **Package:** `mcp` on PyPI — Anthropic's official Python MCP SDK
- **Key class:** `FastMCP` for decorator-based skill registration
- **Transport:** stdio (default for Claude Code integration) or SSE for browser clients
- **Schema generation:** Pydantic model parameters → JSON Schema automatically
- **Version as of August 2025:** 1.x — verify current version before pinning
- **Confidence:** HIGH — this is Anthropic's own SDK and the only correct choice for Claude Code MCP integration

---

## Embedding Model Selection

| Model | Dimensions | Size | CPU Speed | Quality | Privacy |
|-------|-----------|------|-----------|---------|---------|
| `all-MiniLM-L6-v2` | 384 | 22MB | Fast | Good for schema/code | Local |
| `all-mpnet-base-v2` | 768 | 420MB | Slower | Better semantic | Local |
| `text-embedding-3-small` | 1536 | API | API latency | Best | External |

**Recommendation:** Default to `all-MiniLM-L6-v2`. It's fast enough for CPU inference on thousands of SP embeddings, small enough to ship without warning users, and quality is sufficient for schema name / description similarity (not open-domain QA). Upgrade path to OpenAI is a config toggle.

---

## Web UI Graph Visualization

**Recommended approach:** vis.js Network (client-side) + starlette static server + `/api/graph` JSON endpoint

**Rationale:**
- codebase-memory-mcp uses a similar pattern: serve a static HTML page, query graph data from a local API endpoint
- vis.js is the de-facto standard for interactive network graphs in browser — no build step, CDN loadable
- Alternative: d3-force (more flexible but requires more code) or cytoscape.js (richer but heavier)
- pyvis generates vis.js HTML — useful for quick prototyping but produces static snapshots, not live interactive views

**Implementation sketch:**
```
starlette app:
  GET /          → serve static/index.html (vis.js CDN, vanilla JS)
  GET /api/graph → return JSON {nodes: [...], edges: [...]} from SQLite
  GET /api/node/{id} → return node detail (wiki page, SP analysis, etc.)
```

**Do NOT use:** React/Vue/Svelte for this — no build step is a hard requirement for a local-first MCP tool. The web UI must work by running one Python command.

---

## Version Compatibility Matrix

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| sqlglot 25.x | Python 3.8+ | No native deps. All Python versions fine. |
| sentence-transformers 3.x | Python 3.9+, transformers 4.x, torch 2.x | torch 2.x is a large dep (~1-2GB). Lazy-load only when embedding is requested. |
| mcp 1.x | Python 3.10+ | Uses `asyncio` features requiring 3.10+. Set minimum Python to 3.11 for project. |
| sqlite-vec 0.1.x | SQLite 3.38+ | Bundled SQLite in Python 3.11+ is 3.45+, so no issue on modern Python. |
| pyodbc 4.x | Python 3.8+, ODBC Driver 17/18 for SQL Server | On Linux: requires unixODBC. On Windows: ODBC Driver is a separate install. Document this clearly. |
| pydantic 2.x | Python 3.8+ | Do NOT use pydantic v1 — FastMCP requires v2 |

---

## Sources

- PROJECT.md + db-wiki-research.md — project constraints and architecture decisions (HIGH confidence — primary source)
- sqlglot GitHub README and issue tracker — T-SQL support status (MEDIUM — training data, August 2025; verify at https://github.com/tobymao/sqlglot)
- MCP Python SDK — https://github.com/modelcontextprotocol/python-sdk (HIGH — Anthropic official)
- sqlite-vec — https://github.com/asg017/sqlite-vec (MEDIUM — beta library, verify current version)
- bfsvtab — https://github.com/asg017/sqlite-bfsvtab (LOW — less documented, may need Python BFS fallback)
- sentence-transformers — https://www.sbert.net (HIGH — stable, mature library)
- codebase-memory-mcp architecture — analyzed in db-wiki-research.md (HIGH)
- vis.js Network — https://visjs.github.io/vis-network/ (HIGH — stable, widely used)

---
*Stack research for: Python database knowledge engine (SQL Server → SQLite knowledge graph + MCP server)*
*Researched: 2026-04-10*
