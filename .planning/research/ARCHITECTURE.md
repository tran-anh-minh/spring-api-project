# Architecture Research

**Domain:** Python-based database knowledge engine — MCP server + CLI tool
**Researched:** 2026-04-10
**Confidence:** HIGH (based on authoritative MCP protocol docs + deep domain research in db-wiki-research.md)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 5: MCP SERVER + CLI                     │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  MCP Server      │  │  CLI (Typer)     │  │  Web UI       │  │
│  │  (stdio/HTTP)    │  │  db-wiki <cmd>   │  │  (FastAPI     │  │
│  │  JSON-RPC 2.0    │  │  mirrors skills  │  │   + React)    │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬────────┘  │
│           │                     │                    │           │
│           └──────────────┬──────┘                    │           │
│                          ▼                           │           │
│           ┌──────────────────────────┐               │           │
│           │   Skill Router / Core    │               │           │
│           │   (shared Python logic)  │◄──────────────┘           │
│           └──────────────┬───────────┘                           │
│                          │                                       │
├──────────────────────────▼──────────────────────────────────────┤
│                    LAYER 4: QUERY ENGINE                          │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Concept  │  │  Path    │  │   SQL    │  │   Analyst Agent  │  │
│  │ Resolver │  │ Finder   │  │Generator │  │   (Tier 3-6)     │  │
│  │(vec+FTS5)│  │ (BFS)   │  │  (LLM)   │  │                  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    LAYER 3: LEARNING LOOP                         │
│                                                                   │
│  Orchestrator coordinates five phases:                           │
│  DISCOVER → INVESTIGATE → REASON → VALIDATE → CONSOLIDATE       │
│                                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  ┌──────────┐  │
│  │  Research   │  │   Review    │  │ Collector │  │ Gap Queue│  │
│  │   Agent     │  │   Agent     │  │   Agent   │  │(priority)│  │
│  └─────────────┘  └─────────────┘  └───────────┘  └──────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    LAYER 2: KNOWLEDGE STORE                       │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  knowledge.sqlite  (single file — zero infrastructure)   │    │
│  │                                                           │    │
│  │  Core schema + bi-temporal facts + wiki pages +          │    │
│  │  FTS5 full-text + sqlite-vec embeddings + bfsvtab BFS   │    │
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  ~/.db-wiki/cross.db  (cross-project patterns)           │    │
│  └──────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│                    LAYER 1: INGEST                                │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │
│  │   DDL    │  │  SP      │  │ Trigger  │  │   Metadata     │   │
│  │  Parser  │  │  Parser  │  │   &Job   │  │   Extractor    │   │
│  │          │  │(sqlglot) │  │  Parser  │  │  (sys.columns) │   │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| MCP Server | Expose skills as JSON-RPC tools over stdio/HTTP | Skill Router |
| CLI (Typer) | Mirror all MCP skills as subcommands | Skill Router |
| Web UI (FastAPI + React) | Serve graph visualization on localhost | Skill Router (REST endpoints) |
| Skill Router | Route calls to correct service layer, shared by MCP + CLI + Web | All lower layers |
| Query Engine | Resolve NL questions to SQL via 8-step pipeline | Knowledge Store, LLM API |
| Orchestrator | Coordinate the 5-phase learning loop, spawn/collect agents | All agents, Knowledge Store |
| Research Agent | Deep investigation before knowledge mutations | Knowledge Store (read), Collector Agent |
| Review Agent | Quality gate before applying proposed changes | Knowledge Store (read) |
| Analyst Agent | Decompose Tier 3-6 complex queries into sub-questions | Knowledge Store (read), Query Engine |
| Collector Agent | Execute read-only sampling queries against live DB | Live DB connection only |
| Gap Queue | Priority-scored queue of knowledge deficiencies to investigate | Orchestrator |
| Ingest Parsers | Parse SQL artifacts → structured evidence records | Knowledge Store (write) |
| Knowledge Store | SQLite file with full schema, bi-temporal facts, search infra | All layers |

## Recommended Project Structure

```
db_wiki/
├── __main__.py             # Entry point: `python -m db_wiki`
├── cli.py                  # Typer CLI — all subcommands
├── server.py               # MCP server bootstrap (stdio + HTTP transport)
├── web.py                  # FastAPI app — graph visualization endpoints
│
├── core/
│   ├── skills/             # One file per skill (ingest, ask, explain, …)
│   │   ├── ask.py
│   │   ├── explain.py
│   │   ├── ingest.py
│   │   ├── discover.py
│   │   ├── confirm.py
│   │   ├── define_metric.py
│   │   ├── teach.py
│   │   ├── lineage.py
│   │   ├── state_machine.py
│   │   ├── branch_analysis.py
│   │   ├── forensics.py
│   │   ├── coverage.py
│   │   ├── data_quality.py
│   │   ├── impact.py
│   │   ├── status.py
│   │   ├── lint.py
│   │   ├── history.py
│   │   ├── export.py
│   │   └── loop.py
│   └── router.py           # Dispatches calls from MCP/CLI/Web to skills
│
├── ingest/
│   ├── ddl_parser.py       # DDL → tables, columns, constraints, indexes
│   ├── sp_parser.py        # sqlglot AST → data flow + control flow
│   ├── trigger_parser.py   # Trigger body → same as SP parser
│   ├── job_parser.py       # SQL Agent job steps → same as SP parser
│   ├── metadata_extractor.py  # sys.columns, sys.dm_exec_procedure_stats
│   ├── dynamic_sql.py      # Detect + flag EXEC(@sql) patterns
│   └── evidence.py         # Evidence record schema + normalization
│
├── store/
│   ├── db.py               # SQLite connection, WAL mode, migration runner
│   ├── schema.py           # CREATE TABLE statements (bi-temporal model)
│   ├── migrations/         # Numbered migration files
│   │   └── 001_initial.sql
│   ├── queries/            # Named query modules (not raw SQL in Python)
│   │   ├── entities.py
│   │   ├── relationships.py
│   │   ├── wiki.py
│   │   ├── gaps.py
│   │   └── search.py
│   └── bitmask.py          # bfsvtab BFS traversal helpers
│
├── loop/
│   ├── orchestrator.py     # Coordinates 5-phase cycle, scheduling
│   ├── discover.py         # Phase 1: 12 gap detection rules + priority scoring
│   ├── investigate.py      # Phase 2: evidence gathering per gap type
│   ├── reason.py           # Phase 3: 4-op pipeline (ADD/REINFORCE/CONFLICT/NOOP)
│   ├── validate.py         # Phase 4: self-consistency checks
│   ├── consolidate.py      # Phase 5: apply changes, bi-temporal write, generate new gaps
│   └── scheduler.py        # fast/medium/deep/human loop scheduling
│
├── agents/
│   ├── base.py             # Agent interface: receives task, returns report, no DB mutations
│   ├── research.py         # Research Agent: deep investigation
│   ├── review.py           # Review Agent: quality gate
│   ├── analyst.py          # Analyst Agent: complex query decomposition
│   └── collector.py        # Collector Agent: read-only DB sampling
│
├── query/
│   ├── concept_resolver.py # NL terms → schema entities (vector + FTS5 + wiki)
│   ├── metric_resolver.py  # Business terms → derived_metrics SQL definitions
│   ├── path_finder.py      # BFS graph traversal for JOIN paths
│   ├── tier_classifier.py  # Classify query complexity (Tier 1-6)
│   ├── context_assembler.py # L0/L1/L2 tiered context loading
│   ├── sql_generator.py    # LLM call with schema context → SQL
│   ├── sql_validator.py    # sqlglot parse + knowledge store verification
│   └── self_corrector.py   # Error → rewrite → retry loop
│
├── hooks/
│   ├── registry.py         # Hook registration and dispatch
│   ├── file_watcher.py     # on_file_change (watchdog)
│   └── handlers.py         # Hook implementations
│
├── embeddings/
│   ├── provider.py         # Abstract interface: local or OpenAI
│   ├── local.py            # sentence-transformers
│   └── openai.py           # OpenAI embeddings API
│
├── config.py               # Pydantic settings (DB path, embedding provider, etc.)
└── ui/
    ├── static/             # Compiled React bundle (embedded at build time)
    └── templates/          # Jinja2 templates if needed
```

### Structure Rationale

- **`core/skills/`** — One Python file per skill. Both MCP server and CLI call these same functions through `router.py`. This is the critical boundary that prevents logic duplication.
- **`ingest/`** — Isolated from all other layers. Parsers only produce evidence records; they never write to the DB directly. This makes them independently testable.
- **`store/`** — The only layer that touches SQLite. All other layers go through store/ modules. Named query modules prevent SQL scattered across the codebase.
- **`loop/`** — Five-phase learning loop with one file per phase. Orchestrator is the only code that knows the phase order. Phases only read/write through store/.
- **`agents/`** — Agents are stateless workers: they receive a task dict, do work (reading from knowledge store), and return a report dict. They never directly mutate the knowledge store.
- **`query/`** — Pipeline steps are separate modules. This lets each step be tested in isolation and replaced independently (e.g., swap sql_generator.py for a different LLM).
- **`ui/`** — The compiled React bundle is embedded as Python package data. `web.py` (FastAPI) serves it from memory, so `db-wiki serve --ui` requires no separate npm process.

## Architectural Patterns

### Pattern 1: Shared Skill Layer (MCP + CLI + Web use same functions)

**What:** The MCP server, CLI, and web UI all call the same Python functions in `core/skills/`. The transport layer (JSON-RPC, Typer argument parsing, HTTP) is a thin adapter.

**When to use:** Any time you have multiple interfaces (MCP tool + CLI command) that do the same thing.

**Trade-offs:** Eliminates the risk of MCP and CLI drifting apart. Slightly more setup upfront. MCP tool descriptions must be written once in the skill file, not duplicated.

**Example:**
```python
# core/skills/ask.py
def ask(question: str, execute: bool = False) -> AskResult:
    """Core logic — called from MCP, CLI, and Web API."""
    ...

# server.py  (MCP adapter)
@mcp_server.tool()
def dbwiki_ask(question: str) -> dict:
    return ask(question).to_dict()

# cli.py  (Typer adapter)
@app.command()
def ask_cmd(question: str, execute: bool = False):
    result = ask(question, execute)
    console.print(result.format_terminal())
```

### Pattern 2: Agent Isolation — Read-Only Workers with Structured Reports

**What:** Agents never mutate the knowledge store directly. They receive a task, gather evidence (read-only), and return a structured report. The Orchestrator applies approved changes.

**When to use:** Any computation that involves reasoning about whether to update knowledge. The Review Agent pattern is always applied before mutations.

**Trade-offs:** Adds one round-trip (report generation → review → apply) but prevents hallucinated or premature knowledge from entering the store. Critical for correctness.

**Example:**
```python
# agents/base.py
class Agent:
    def __init__(self, db: ReadOnlyKnowledgeStore):
        self.db = db  # read-only connection

    def run(self, task: AgentTask) -> AgentReport:
        raise NotImplementedError

# loop/orchestrator.py
report = ResearchAgent(db_readonly).run(task)
approved = ReviewAgent(db_readonly).run(ReviewTask(report))
if approved.changes:
    consolidate.apply(approved.changes, db_readwrite)
```

### Pattern 3: Bi-Temporal Write Pattern (Graphiti-inspired)

**What:** Knowledge facts are never deleted — they are invalidated. Every write sets `recorded_at = now()`. Every supersession sets `superseded_by_id` on the old row and `invalidated_at = now()`. The valid_from/valid_until tracks when the fact was true in the real world (e.g., SP was written in 2022, modified in 2024).

**When to use:** Any knowledge update. This is the baseline write contract for the entire knowledge store.

**Trade-offs:** Grows the knowledge store over time. Queries for "current facts" must always filter `invalidated_at IS NULL`. Worth it for auditability (`dbwiki:history`) and conflict resolution.

**Example:**
```python
# store/queries/entities.py
def add_fact(conn, entity_type, entity_id, fact_text, confidence,
             valid_from, evidence_sources):
    conn.execute("""
        INSERT INTO knowledge_facts (
            entity_type, entity_id, fact_text, confidence,
            valid_from, valid_until, recorded_at, invalidated_at,
            evidence_sources
        ) VALUES (?, ?, ?, ?, ?, NULL, datetime('now'), NULL, ?)
    """, (entity_type, entity_id, fact_text, confidence,
          valid_from, json.dumps(evidence_sources)))

def supersede_fact(conn, old_fact_id, new_fact_id):
    conn.execute("""
        UPDATE knowledge_facts
        SET invalidated_at = datetime('now'), superseded_by_id = ?
        WHERE id = ?
    """, (new_fact_id, old_fact_id))
```

### Pattern 4: L0/L1/L2 Tiered Context Loading (OpenViking-inspired)

**What:** When generating SQL or wiki responses, load context at three granularities. L0 = one sentence per table (all related tables). L1 = columns + relationships (top 10 relevant). L2 = full wiki page + evidence (2-3 core tables). Never load L2 for everything — that blows the context window.

**When to use:** Any LLM call that needs schema context. Always.

**Trade-offs:** Requires the L0/L1/L2 tiers to be pre-computed and stored in wiki_pages. The payoff is 10x token efficiency vs loading full DDL into every prompt.

### Pattern 5: sqlglot AST Walking Pipeline

**What:** Parse each SP with sqlglot, then walk the AST with a visitor pattern to extract different signal types in a single pass. Control flow (IF/ELSE nodes), data flow (Table/Column references), mutations (INSERT/UPDATE/DELETE), dynamic SQL (Anonymous/Execute nodes), and state transitions (UPDATE SET patterns) are all extracted from the same AST traversal.

**When to use:** All SQL parsing in the ingest layer.

**Trade-offs:** sqlglot handles T-SQL dialect with high fidelity but some T-SQL-specific constructs (EXEC with variable, cursor patterns) may need special-case handling beyond the standard AST. Flag these as requiring manual review.

**Example:**
```python
# ingest/sp_parser.py
import sqlglot
from sqlglot import exp

def parse_sp(sql_body: str) -> SPAnalysis:
    ast = sqlglot.parse_one(sql_body, dialect="tsql")
    analysis = SPAnalysis()

    for node in ast.walk():
        if isinstance(node, exp.Table):
            analysis.table_refs.append(node.name)
        elif isinstance(node, exp.Join):
            analysis.joins.append(extract_join(node))
        elif isinstance(node, exp.If):
            analysis.branches.append(extract_branch(node))
        elif isinstance(node, exp.Update):
            analysis.mutations.append(extract_mutation(node))
            maybe_transition = detect_state_transition(node)
            if maybe_transition:
                analysis.state_transitions.append(maybe_transition)
        elif isinstance(node, exp.Anonymous):
            analysis.dynamic_sql_detected = True

    return analysis
```

### Pattern 6: MCP Server with Embedded Web UI

**What:** The `db-wiki serve` command starts the MCP server (stdio transport for Claude integration) AND a FastAPI web server on localhost (default port 8765) for graph visualization. The React bundle is embedded as Python package data using `importlib.resources`. No npm, no separate process — both run in the same Python process via asyncio.

**When to use:** When user runs `db-wiki serve --ui` or `db-wiki serve --port 8765`.

**Trade-offs:** Embedding a compiled React bundle in a Python package adds ~500KB to the package size. Build step needed during development (npm run build → copy to ui/static/). Worth it to avoid requiring Node.js at runtime. The pattern is established by codebase-memory-mcp.

**Example:**
```python
# web.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import importlib.resources

app = FastAPI()

# Mount embedded React bundle
static_dir = importlib.resources.files("db_wiki.ui") / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True))

# Graph API endpoints
@app.get("/api/graph")
async def get_graph(table: str = None, depth: int = 2):
    return router.call("graph_data", table=table, depth=depth)

# server.py
async def main():
    # Run MCP (stdio) + Web UI (HTTP) concurrently
    async with asyncio.TaskGroup() as tg:
        tg.create_task(run_mcp_stdio())
        tg.create_task(uvicorn.Server(config).serve())
```

## Data Flow

### Ingest Flow

```
SQL files on disk / live DB
    ↓ (DDL/SP/Trigger/Job/Metadata parsers)
Evidence records (structured, normalized)
    ↓ (store/queries/entities.py)
knowledge.sqlite — entities + relationships + raw evidence
    ↓ (loop/orchestrator.py triggers fast_loop)
Gap detection → gap_queue updated
    ↓ (async, background)
Embeddings generated → chunk_vec updated
FTS5 index updated → wiki_fts updated
```

### Query Flow (NL → SQL)

```
Natural language question (from MCP tool call or CLI)
    ↓ (core/router.py → core/skills/ask.py)
Tier classification
    ↓ if Tier 1-2: inline pipeline
    ↓ if Tier 3-6: spawn Analyst Agent
Concept Resolver  →  hybrid search (sqlite-vec + FTS5 + wiki lookup)
    ↓ entity mappings (table/column with confidence)
Metric Resolver   →  check derived_metrics for business terms
    ↓
Path Finder       →  BFS graph traversal for JOIN paths
    ↓ join graph
Context Assembler →  L0 all related, L1 relevant, L2 core tables
    ↓ schema context (token-bounded)
SQL Generator     →  LLM call with context + enum labels + aliases
    ↓ generated SQL
SQL Validator     →  sqlglot parse + verify tables/columns exist
    ↓ if invalid: Self Corrector → rewrite → retry (max 3x)
    ↓ if valid:
Result returned to user
    ↓ (side effect)
on_query_success hook → reinforce knowledge, store as template
```

### Learning Loop Flow

```
Trigger (ingest complete / idle / on_schedule / manual loop command)
    ↓
Orchestrator — Phase 1: DISCOVER
    → run 12 gap detection rules
    → score + prioritize gaps
    → update gap_queue
    ↓ top-N gaps
Orchestrator — Phase 2: INVESTIGATE
    → for each gap: spawn Research Agent (read-only)
    → Research Agent spawns Collector Agent if live DB needed
    → Research Agent returns structured report
    ↓ evidence bundles
Orchestrator — Phase 3: REASON
    → apply 4-op pipeline (ADD / REINFORCE / CONFLICT / NOOP)
    → compute proposed knowledge changes
    → spawn Review Agent to validate
    ↓ approved changes
Orchestrator — Phase 4: VALIDATE
    → self-consistency checks (relationship symmetry, enum completeness, etc.)
    → escalate unresolvable to human (queue for dbwiki:confirm)
    ↓ validated changes
Orchestrator — Phase 5: CONSOLIDATE
    → apply with bi-temporal writes (supersede old facts)
    → update wiki pages (L0/L1/L2 tiers)
    → decay confidence on unvisited facts
    → generate new gaps from discoveries
    → update maturity score
    ↓
→ next loop iteration (or sleep until next schedule trigger)
```

### Agent Communication Flow

```
Orchestrator
    │
    ├── spawn ResearchAgent(task) ──→ [read-only DB] ──→ AgentReport
    │       │
    │       └── spawn CollectorAgent(sampling_tasks) ──→ [live DB] ──→ DataSamples
    │
    ├── spawn ReviewAgent(proposed_changes) ──→ [read-only DB] ──→ ReviewVerdict
    │       { approved: [...], rejected: [...], needs_human: [...] }
    │
    ├── apply approved_changes ──→ [read-write DB]
    │
    └── on complex query: spawn AnalystAgent(question) ──→ QueryPlan
            → Query Engine executes QueryPlan
```

## Scaling Considerations

This is a local-first tool (single user, single SQLite file). Scaling concerns are not about users but about database size.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Small DB (< 500 tables, < 2K SPs) | No changes needed. SQLite handles this trivially. FTS5 and sqlite-vec fast enough inline. |
| Medium DB (500-2K tables, 2K-10K SPs) | Enable WAL mode (already recommended). Add indexes on entity_type + confidence in knowledge_facts. Run ingest in batches. Background loop scheduling essential. |
| Large DB (2K+ tables, 10K+ SPs) | Partition knowledge.sqlite by schema (one file per SQL Server schema). Lazy-load embeddings (generate on query, not on ingest). Agent parallelism important — run multiple Research Agents in asyncio. |

### Scaling Priorities

1. **First bottleneck: Embedding generation during ingest.** Solution: generate embeddings lazily (on first query for an entity) or in a background thread pool, not inline during ingest.

2. **Second bottleneck: LLM API calls in the query pipeline.** Solution: cache concept resolution results (the mapping from NL terms to schema entities is stable). Store as query_templates after first successful query. sqlite-vec similarity search is fast, LLM call is the expensive part.

3. **Third bottleneck: sqlglot parsing thousands of SPs.** Solution: hash-based change detection. Store `body_hash` per SP. Re-parse only on hash change, not on every ingest run.

## Anti-Patterns

### Anti-Pattern 1: SQL Logic Scattered Across Python Files

**What people do:** Write raw SQL strings inside service classes, skill handlers, or agent code wherever it's needed.

**Why it's wrong:** Makes queries impossible to review, optimize, or test in isolation. Bi-temporal filtering (`WHERE invalidated_at IS NULL`) gets forgotten in 30% of queries, leading to ghost facts appearing in results.

**Do this instead:** All SQL lives in `store/queries/` modules. Every function that reads current facts uses a shared `current_facts()` helper that applies the bi-temporal filter automatically. Agents and skills import query functions, never write raw SQL.

### Anti-Pattern 2: Agents That Mutate the Knowledge Store

**What people do:** Have the Research Agent or Analyst Agent write directly to knowledge_facts when they find something.

**Why it's wrong:** Bypasses the Review Agent quality gate. Results in unvalidated, potentially contradictory knowledge being applied immediately. Breaks the provenance chain (who approved this change?).

**Do this instead:** Agents are strictly read-only. Every knowledge mutation goes through the Orchestrator → Review Agent → Consolidate path. The read-only connection is enforced by passing agents a `ReadOnlyConnection` wrapper that raises on any write attempt.

### Anti-Pattern 3: Loading Full DDL Into Every LLM Prompt

**What people do:** Concatenate all table DDL into the system prompt for every `dbwiki:ask` call.

**Why it's wrong:** A 500-table database produces a 200K+ token prompt. Exceeds context limits, extremely expensive, and most of the DDL is irrelevant to the query.

**Do this instead:** L0/L1/L2 tiered loading. Use concept resolution to find the 2-5 relevant tables, load L2 only for those, L1 for related tables, L0 for everything else. The target is under 8K tokens of schema context per query.

### Anti-Pattern 4: MCP and CLI Having Separate Logic Paths

**What people do:** Implement `dbwiki:ask` as an MCP tool with its own logic, then re-implement `db-wiki ask` as a CLI command with slightly different logic.

**Why it's wrong:** They drift apart within weeks. The CLI version gets bug fixes that never reach the MCP tool. Features added to MCP aren't available from the terminal.

**Do this instead:** Both MCP tool and CLI command call the same function in `core/skills/ask.py`. The MCP server is a thin adapter that serializes/deserializes JSON. The CLI is a thin adapter that formats output for the terminal.

### Anti-Pattern 5: Deleting Knowledge Instead of Superseding

**What people do:** When a conflict is resolved, DELETE the wrong fact and INSERT the correct one.

**Why it's wrong:** Destroys the history needed for `dbwiki:history`. Cannot audit what we believed and when. Cannot recover if the deletion was wrong.

**Do this instead:** Always supersede. Mark old fact as `invalidated_at = now()`, `superseded_by_id = new_fact_id`. New fact gets a new row. Query for "current" facts always filters `WHERE invalidated_at IS NULL`. The full history is preserved.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Anthropic MCP SDK (Python) | `mcp` package, `@server.tool()` decorator pattern, stdio transport | Use for Claude Code integration. Streamable HTTP transport optional for remote use. |
| sqlglot | `sqlglot.parse_one(sql, dialect="tsql")` — returns AST for walking | Pin version; T-SQL support quality varies by release. Test against real SPs before upgrading. |
| sentence-transformers | Local embedding generation, 512-d vectors stored in sqlite-vec | Default provider. No API key needed. ~400MB model download on first use. |
| OpenAI Embeddings API | Alternative embedding provider, configured via `OPENAI_API_KEY` env var | Better quality, costs money, sends data externally. User opt-in only. |
| Live SQL Server | `pyodbc` or `pymssql` connection, read-only, used by Collector Agent | All queries SELECT only. Enforced at connection level with read-only credentials recommendation. |
| sqlite-vec | SQLite extension for vector similarity search | Load as shared library. Must match SQLite version. |
| bfsvtab | SQLite virtual table for BFS graph traversal | Compile from source or use pre-built. Replaces need for graph database. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| MCP Server ↔ Skill Router | Direct Python function calls | No serialization overhead. Both in same process. |
| CLI ↔ Skill Router | Direct Python function calls | Typer handles argument parsing, skill handles logic. |
| Web API ↔ Skill Router | FastAPI route handlers call router.call() | Async-compatible. JSON serialization at HTTP boundary. |
| Skill Router ↔ Loop Orchestrator | Direct Python calls + asyncio events | Skills can trigger loop phases (e.g., ingest triggers fast_loop). |
| Orchestrator ↔ Agents | Task dict in, Report dict out (synchronous subprocess or asyncio coroutine) | Agents are isolated. Use asyncio.gather for parallel Research Agents. |
| Agents ↔ Knowledge Store | Read-only SQLite connection (separate connection object) | Enforced by passing `ReadOnlyConn` wrapper. Mutations raise immediately. |
| Collector Agent ↔ Live DB | pyodbc/pymssql connection with query budget + timeout limits | 30s timeout, 10K max rows, configurable total query budget. |
| All services ↔ Knowledge Store | store/queries/ module functions only — no raw SQL in other layers | Bi-temporal filter applied automatically at query module level. |

## Suggested Build Order

Components must be built in dependency order. Later layers depend on earlier ones.

**Phase 1 — Foundation (build first):**
1. `store/schema.py` + `store/db.py` — the SQLite schema with bi-temporal model. Everything else reads/writes this.
2. `ingest/ddl_parser.py` — parse DDL to populate tables/columns. Simplest parser.
3. `ingest/sp_parser.py` (sqlglot) — data flow extraction (table refs, JOINs, mutations). Control flow can come later.
4. `store/queries/entities.py` + `store/queries/relationships.py` — basic read/write functions.
5. `core/skills/ingest.py` + `core/skills/explain.py` + `core/skills/search.py` — minimal skill set.
6. `server.py` (MCP bootstrap) + `cli.py` (Typer skeleton) — wire up transport layer.

**Phase 2 — Learning Loop:**
7. `loop/discover.py` — gap detection rules + priority queue.
8. `agents/collector.py` — live DB sampling (needed by investigate).
9. `agents/research.py` — evidence gathering.
10. `loop/investigate.py` — coordinate Research + Collector Agents.
11. `ingest/sp_parser.py` control flow extension — IF/ELSE branches, state transitions.
12. `loop/reason.py` — 4-op pipeline.
13. `agents/review.py` — quality gate.
14. `loop/validate.py` + `loop/consolidate.py` — complete the cycle.
15. `loop/orchestrator.py` + `loop/scheduler.py` — wire up scheduling.

**Phase 3 — Conflict Resolution:**
16. `loop/reason.py` — conflict resolution strategies (SUPERSEDE/KEEP/SPLIT/ESCALATE).
17. SP reliability scoring in `store/queries/`.
18. Confidence decay in `loop/consolidate.py`.
19. Alias cluster detection.

**Phase 4 — Query Engine:**
20. `embeddings/` + sqlite-vec integration — needed for concept resolution.
21. `query/concept_resolver.py` — hybrid search (vector + FTS5 + wiki).
22. `query/path_finder.py` — BFS via bfsvtab.
23. `query/sql_generator.py` — LLM call with L0/L1/L2 context.
24. `query/sql_validator.py` — sqlglot validation loop.
25. `agents/analyst.py` — Tier 3-6 query decomposition.
26. Remaining skills: `ask.py`, `forensics.py`, `data_quality.py`, `branch_analysis.py`.

**Phase 5 — Cross-Project + Continuous:**
27. `store/` — cross.db schema + cross-project pattern storage.
28. `loop/consolidate.py` — wiki page generation (L0/L1/L2 tiers).
29. `loop/scheduler.py` — background scheduling (fast/medium/deep/human).
30. `hooks/` — file watcher, hook registry.
31. `web.py` (FastAPI) + `ui/` (React graph visualization) — local web UI.
32. Remaining skills: `status.py`, `coverage.py`, `impact.py`, `export.py`.

## Sources

- MCP Protocol Architecture: https://modelcontextprotocol.io/docs/concepts/architecture (authoritative, fetched 2026-04-10) — HIGH confidence
- db-wiki-research.md in this repo — comprehensive prior research synthesizing 9 existing tools (codebase-memory-mcp, Mem0, Graphiti/Zep, OpenViking, LangGraph, Cognee, claude-mem, Karpathy LLM Wiki, LLM Wiki v2) — HIGH confidence
- sqlglot AST walking pattern — derived from sqlglot Python API (standard walk() + isinstance pattern) — HIGH confidence
- Bi-temporal model — Graphiti/Zep pattern, documented in db-wiki-research.md section 2.4 — HIGH confidence
- L0/L1/L2 tiered context — OpenViking pattern, documented in db-wiki-research.md section 2.5 — HIGH confidence
- 4-op update pipeline — Mem0 pattern, documented in db-wiki-research.md section 2.3 — HIGH confidence
- SQLite graph + BFS pattern — codebase-memory-mcp (DeusData), documented in db-wiki-research.md section 2.1 — HIGH confidence

---
*Architecture research for: Python database knowledge engine (db-wiki)*
*Researched: 2026-04-10*
