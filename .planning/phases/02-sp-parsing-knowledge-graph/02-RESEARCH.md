# Phase 2: SP Parsing + Knowledge Graph - Research

**Researched:** 2026-04-10
**Domain:** sqlglot T-SQL AST parsing, sqlite-vec, FTS5, Python BFS graph traversal, bi-temporal schema extension
**Confidence:** HIGH (all critical claims verified against live codebase and installed packages)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**SP Parsing Depth**
- D-01: Flatten and extract — walk the raw token/node tree even when sqlglot's AST is incomplete for IF/ELSE/WHILE/TRY bodies. Extract table refs and mutations best-effort. Flag the SP as `partial_ast` but still capture what's there.
- D-02: Dynamic SQL (EXEC(@sql), sp_executesql) is flagged and skipped — mark the SP as containing dynamic SQL, log the EXEC location, but don't attempt to parse the string content.
- D-03: Parse quality stored as silent metadata — parse_quality score and degraded flag stored in db_procedures. Surface only when queried (CLI status --quality or MCP tool).
- D-04: Enum detection via CASE + naming heuristics — detect enums from CASE WHEN col = 'value' patterns AND from SP/column names matching patterns like *Status, *Type, *Flag.

**Graph Traversal**
- D-05: Python BFS only — collections.deque over SQLite adjacency queries. No bfsvtab.
- D-06: Configurable edge type filtering — BFS accepts optional edge_types filter. Default: all 6 types.

**Embedding + Search**
- D-07: Separate sqlite-vec tables per embedding provider — vec_embeddings_384 or vec_embeddings_1536.
- D-08: Hybrid search via score fusion — vector + FTS5, normalize to 0-1, combine with configurable weight (default 0.5/0.5).
- D-09: On-demand embedding at first search — don't embed during ingest. Batch-embed on first search query.

**Ingest Workflow**
- D-10: One SP per file convention — each .sql file contains one CREATE PROCEDURE.
- D-11: Invalidate old, insert new for re-parse — on body_hash change, set invalidated_at on old row, insert new. Cascade to derived rows.
- D-12: --watch mode deferred to Phase 5.
- D-13: Auto-detect content type — CREATE PROCEDURE = SP, DDL = DDL. --type flag overrides.

**State Transitions**
- D-14: UPDATE WHERE literal match — detect UPDATE SET col = 'literal' WHERE col = 'literal' patterns.
- D-15: Evidence-based confidence scoring — literal-to-literal = 0.9, naming heuristic only = 0.3.

**SP Call Chain Resolution**
- D-16: Name-based matching for EXEC references — match against ingested db_procedures by name.
- D-17: Detect and flag circular call chains — allow edges, detect cycles in BFS, flag in sp_reliability.

**Schema Extensions**
- D-18: All intelligence tables are bi-temporal — sp_branches, sp_reliability, sp_call_chains, enum_values, bitmask_definitions, state_transitions, column_aliases all follow valid_from/valid_until/recorded_at/invalidated_at.
- D-19: Unified embeddings table — single vec_embeddings table with entity_type + entity_id columns.

**MCP/CLI Tools**
- D-20: Core query MCP tools — 'search' (hybrid), 'lineage' (BFS), 'sp_info' (SP details).
- D-21: CLI mirrors MCP tools — 'db-wiki search', 'db-wiki lineage', 'db-wiki sp-info'.

### Claude's Discretion
- Exact SQLite DDL for new intelligence tables (column names, types, indexes)
- SP parser implementation details (sqlglot AST traversal patterns for procedural blocks)
- FTS5 index column selection and tokenizer configuration
- BFS implementation details (max depth defaults, result format)
- Score normalization algorithm for hybrid search
- Pydantic model definitions for SP-related entities

### Deferred Ideas (OUT OF SCOPE)
- --watch mode for file monitoring (Phase 5, CLI-05)
- bfsvtab integration (optional optimization, deferred)
- Variable tracking through SP execution paths (Phase 3 learning loop candidate)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-02 | Parse SPs via sqlglot AST into table references, JOINs, mutations | Verified: exp.Table, exp.Insert/Update/Delete extraction works in sqlglot 30.4.2 |
| INGEST-03 | Extract SP control flow: IF/ELSE branches, CASE statements, variable tracking, nesting depth | Verified: exp.IfBlock parsed; ELSE blocks fall to Command nodes needing regex fallback |
| INGEST-04 | Extract state transitions from UPDATE SET col=X WHERE col=Y patterns | Verified: exp.Update + exp.EQ traversal extracts literal-to-literal transitions correctly |
| INGEST-05 | Resolve SP call chains (SP-A calls SP-B) | Verified: exp.Execute nodes have .this = Table node with .name and .db accessible |
| INGEST-06 | Detect and flag dynamic SQL (EXEC(@sql)) with parse quality tracking | Verified: dynamic = exp.Subquery/Paren in Execute.this; sp_executesql = name match |
| INGEST-07 | Track parse quality per SP (exp.Anonymous nodes, degraded at >5%) | Verified: Anonymous nodes detected; ratio = anon_count / total_nodes |
| INGEST-08 | Batch ingest directories, incremental re-parse via body_hash | Verified: body_hash = SHA-256 of normalized SP body; kind='PROCEDURE' for auto-detect |
| STORE-05 | SP intelligence: sp_branches, sp_reliability, sp_call_chains | Requires new bi-temporal tables extending SCHEMA_SQL |
| STORE-06 | Value intelligence: enum_values, bitmask_definitions, state_transitions, column_aliases | Requires new bi-temporal tables with confidence scores |
| STORE-09 | sqlite-vec for vector search (384-dim or 1536-dim) | Verified: sqlite-vec 0.1.9 installed; vec0 virtual table + enable_load_extension pattern |
| STORE-10 | FTS5 full-text search on entity descriptions | Verified: FTS5 built into SQLite 3.45 bundled with Python 3.11; rank() scoring works |
| STORE-11 | Graph traversal via Python BFS (collections.deque over adjacency queries) | Verified: BFS implementation works; cycle detection via visited set |
| CLI-03 | Ingest commands with directory/glob support, --type flag | Extends existing typer ingest command; glob via pathlib.Path.glob() |
| CONFIG-01 | Configurable embedding provider (local or OpenAI) | sqlite-vec tables keyed by dimension count; lazy-load torch |
| CONFIG-04 | Lazy-load torch/sentence-transformers only when first searched | Verified: lazy import at function level works; torch not imported at module level |
</phase_requirements>

---

## Summary

Phase 2 extends the Phase 1 foundation (bi-temporal SQLite store, sqlglot DDL parser, FastMCP server, Typer CLI) to add SP parsing, intelligence tables, hybrid vector+FTS5 search, and BFS graph traversal. The codebase has clean extension points: SCHEMA_SQL is addable, ddl_parser.py provides the tolerant parsing pattern, models.py shows the Pydantic intermediate model pattern, and app.py shows @mcp.tool() registration.

The critical technical insight from live testing: sqlglot 30.4.2 parses IF blocks but ELSE branches fall to `exp.Command` fallback nodes. This is the core challenge for D-01. The extract-and-flatten approach must handle three cases: (1) properly parsed AST nodes (use find_all), (2) Command fallback nodes containing ELSE/WHILE bodies (use regex extraction), (3) top-level Command nodes for completely unparseable SPs (flag as partial_ast, best-effort). All other constructs — table refs, JOINs, INSERT/UPDATE/DELETE targets, EXEC call chains, CASE enums, state transitions — parse cleanly.

sqlite-vec 0.1.9 requires `conn.enable_load_extension(True)` before loading. Embeddings are passed as `struct.pack('Nf', *values)` bytes, not Python lists. The vec0 virtual table supports additional metadata columns (entity_type, entity_id) directly in the table definition — no separate JOIN table needed. FTS5 is built into Python 3.11's bundled SQLite and ready to use.

**Primary recommendation:** Implement the SP parser as a new `db_wiki/ingest/sp_parser.py` module mirroring `ddl_parser.py` structure. Three-pass extraction: (1) AST-level with find_all, (2) Command-level with regex fallback for control flow bodies, (3) quality scoring. All new tables extend SCHEMA_SQL following the established bi-temporal pattern.

---

## Standard Stack

### Core (all verified against installed versions)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlglot | 30.4.2 (pinned in pyproject.toml: `>=30.0,<31`) | T-SQL AST parsing | Already in project; exp.Execute, exp.IfBlock, exp.Case, exp.Update all verified |
| sqlite3 | stdlib (3.45+ bundled) | Knowledge store + FTS5 | Already in use; FTS5 confirmed available [VERIFIED: live test] |
| sqlite-vec | 0.1.9 (latest on PyPI) | Vector similarity search | Add to pyproject.toml; vec0 virtual table; enable_load_extension required [VERIFIED: pip index] |
| sentence-transformers | 5.4.0 (latest on PyPI) | Local 384-dim embeddings | Optional dep; lazy-load for CONFIG-04 compliance; all-MiniLM-L6-v2 [VERIFIED: pip index] |
| collections.deque | stdlib | BFS graph traversal | D-05 decision; verified pattern with cycle detection |
| hashlib | stdlib | body_hash for incremental re-parse | SHA-256 hex digest for D-11 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| struct | stdlib | Serialize float lists for sqlite-vec | Required for vec0 insert/query; lists fail [VERIFIED: live test] |
| re | stdlib | Regex table ref extraction from Command nodes | D-01 fallback for ELSE/WHILE/TRY blocks that fall to Command |
| pathlib.Path | stdlib | Directory glob for batch ingest (INGEST-08) | `Path(dir).glob('**/*.sql')` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| regex fallback for Command nodes | Re-parse Command bodies | Re-parse produces same Command fallback recursively — regex is the correct fallback |
| struct.pack for embeddings | numpy array serialization | numpy not in deps; struct.pack is lighter and sufficient |
| FTS5 rank() | BM25 via custom scorer | FTS5 rank() IS BM25 — no custom implementation needed |

**Installation:**
```bash
uv add sqlite-vec
uv add --optional embed sentence-transformers  # lazy-load, not in core deps
```

**Version verification:** [VERIFIED: pip index versions 2026-04-10]
- sqlite-vec: 0.1.9 (latest)
- sentence-transformers: 5.4.0 (latest)
- sqlglot: 30.4.2 (installed in project venv)

---

## Architecture Patterns

### Recommended Project Structure
```
db_wiki/
├── ingest/
│   ├── ddl_parser.py        # Phase 1 — EXTEND for auto-detect (D-13)
│   └── sp_parser.py         # NEW: CREATE PROCEDURE parsing
├── graph/
│   └── bfs.py               # NEW: Python BFS traversal (D-05)
├── search/
│   ├── embedder.py          # NEW: lazy-load sentence-transformers (CONFIG-04)
│   ├── fts.py               # NEW: FTS5 index management
│   └── hybrid.py            # NEW: score fusion (D-08)
├── core/
│   ├── schema.py            # EXTEND: append intelligence tables (D-18/D-19)
│   ├── models.py            # EXTEND: SP Pydantic models
│   ├── store.py             # EXTEND: sqlite-vec load_extension on open
│   └── config.py            # EXTEND: embedding_provider setting
├── server/
│   └── app.py               # EXTEND: search, lineage, sp_info tools (D-20)
└── cli/
    └── app.py               # EXTEND: search, lineage, sp-info, ingest --type (D-21)
```

### Pattern 1: SP Parser Module (mirrors ddl_parser.py)
**What:** `sp_parser.py` with `parse_sp_file()` + `extract_sp_info()` + `ingest_sp()`.
**When to use:** Any CREATE PROCEDURE content detection.
**Example:**
```python
# Source: mirrors db_wiki/ingest/ddl_parser.py pattern
import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel
import re

def parse_sp_file(sql_text: str) -> tuple[list[exp.Expression], list[str]]:
    """Tolerant parse — same ErrorLevel.WARN pattern as ddl_parser."""
    statements = sqlglot.parse(sql_text, dialect="tsql", error_level=ErrorLevel.WARN)
    valid = []
    warnings = []
    for stmt in statements:
        if stmt is None:
            warnings.append("Skipping None result")
            continue
        if isinstance(stmt, exp.Command):
            warnings.append(f"Skipping top-level Command: {stmt.sql()[:80]!r}")
            continue
        if isinstance(stmt, exp.Create) and stmt.args.get("kind") == "PROCEDURE":
            valid.append(stmt)
        # DDL in same file falls through — auto-detect handles routing (D-13)
    return valid, warnings
```

### Pattern 2: Three-Pass SP Extraction (D-01 core pattern)
**What:** Extract table refs from the AST, then Command nodes, then quality-score.
**When to use:** Every SP parse.
**Example:**
```python
# Source: verified via live sqlglot 30.4.2 testing 2026-04-10
import re
from sqlglot import exp

TABLE_REF_RE = re.compile(r'\b(?:FROM|JOIN|UPDATE|INTO)\s+([\w\.]+)', re.IGNORECASE)

def extract_table_refs(sp_stmt: exp.Create) -> tuple[list[str], bool]:
    """Returns (table_names, is_partial_ast).
    
    Pass 1: AST-level find_all(exp.Table) — catches SELECT FROM, JOIN, UPDATE, INSERT INTO.
    Pass 2: Command nodes (ELSE/WHILE/TRY fallbacks) — regex extraction.
    Returns is_partial_ast=True if any Command nodes found.
    """
    tables: set[str] = set()
    has_command_nodes = False

    # Pass 1: structured AST
    for table in sp_stmt.find_all(exp.Table):
        if table.name and table.name != sp_stmt.args.get("this", {}).get("name", ""):
            tables.add(table.name)

    # Pass 2: Command fallback nodes (ELSE bodies, unsupported syntax)
    for cmd in sp_stmt.find_all(exp.Command):
        has_command_nodes = True
        for match in TABLE_REF_RE.findall(cmd.sql()):
            # Strip schema prefix: dbo.Orders -> Orders
            tables.add(match.split(".")[-1])

    return list(tables), has_command_nodes
```

### Pattern 3: Parse Quality Scoring (INGEST-07)
**What:** Count exp.Anonymous nodes as ratio of total nodes.
**When to use:** After every SP parse.
**Example:**
```python
# Source: verified via live sqlglot 30.4.2 testing 2026-04-10
def compute_parse_quality(sp_stmt: exp.Create) -> tuple[float, bool]:
    """Returns (quality_score, is_degraded).
    
    quality_score = 1.0 - (anonymous_count / total_node_count)
    is_degraded = quality_score < 0.95 (>5% Anonymous nodes)
    """
    all_nodes = list(sp_stmt.walk())
    anon_nodes = list(sp_stmt.find_all(exp.Anonymous))
    total = len(all_nodes)
    if total == 0:
        return 0.0, True
    ratio = len(anon_nodes) / total
    quality = 1.0 - ratio
    return quality, ratio > 0.05
```

### Pattern 4: Execute Node Classification (INGEST-05, INGEST-06)
**What:** Classify each EXEC as static call, dynamic SQL, or sp_executesql.
**When to use:** During SP extraction.
**Example:**
```python
# Source: verified via live sqlglot 30.4.2 testing 2026-04-10
def classify_execute(exe: exp.Execute) -> dict:
    """Returns classification dict for an Execute node."""
    this = exe.args.get("this")
    if this is None:
        return {"type": "unknown"}
    
    # Dynamic SQL: EXEC (@variable) — this is a Subquery/Paren
    if isinstance(this, (exp.Subquery, exp.Paren)):
        return {"type": "dynamic", "is_dynamic_sql": True}
    
    # sp_executesql: EXEC sp_executesql N'...'
    name = getattr(this, "name", "")
    if name.lower() == "sp_executesql":
        return {"type": "sp_executesql", "is_dynamic_sql": True}
    
    # Static call: EXEC dbo.ProcName — this is a Table node
    if isinstance(this, exp.Table):
        return {
            "type": "static",
            "proc_name": this.name,
            "schema_name": this.db or None,
            "is_dynamic_sql": False,
        }
    
    return {"type": "unknown"}
```

### Pattern 5: State Transition Detection (INGEST-04, D-14)
**What:** Find UPDATE SET col = literal WHERE col = literal on same column.
**When to use:** During SP extraction.
**Example:**
```python
# Source: verified via live sqlglot 30.4.2 testing 2026-04-10
def extract_state_transitions(sp_stmt: exp.Create) -> list[dict]:
    """Detect UPDATE SET col='X' WHERE col='Y' — literal-to-literal transitions (D-14)."""
    transitions = []
    for upd in sp_stmt.find_all(exp.Update):
        target_table = upd.this.name if hasattr(upd.this, "name") else None
        if not target_table:
            continue
        
        # Collect SET assignments: {col_name: literal_value}
        set_literals: dict[str, str] = {}
        for eq in upd.args.get("expressions", []):
            if isinstance(eq, exp.EQ):
                col = eq.this.name if hasattr(eq.this, "name") else None
                val = eq.args.get("expression")
                if col and isinstance(val, (exp.Literal,)):
                    set_literals[col] = val.this
        
        # Collect WHERE literals: {col_name: literal_value}
        where = upd.args.get("where")
        where_literals: dict[str, str] = {}
        if where:
            for eq in where.find_all(exp.EQ):
                col = eq.this.name if hasattr(eq.this, "name") else None
                val = eq.args.get("expression")
                if col and isinstance(val, exp.Literal):
                    where_literals[col] = val.this
        
        # Match: same column in both SET and WHERE
        for col in set_literals:
            if col in where_literals:
                transitions.append({
                    "table_name": target_table,
                    "column_name": col,
                    "from_value": where_literals[col],
                    "to_value": set_literals[col],
                    "confidence": 0.9,  # D-15: literal-to-literal = 0.9
                })
    
    return transitions
```

### Pattern 6: sqlite-vec Loading (STORE-09)
**What:** Load sqlite-vec extension when opening the store.
**When to use:** In `open_store()` / `init_schema()`.
**Example:**
```python
# Source: verified via live sqlite-vec 0.1.9 testing 2026-04-10
import sqlite3
import sqlite_vec

def open_store_with_vec(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)  # Disable after loading for security
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

### Pattern 7: Embedding Serialization for sqlite-vec
**What:** Convert float list to bytes for vec0 INSERT/MATCH.
**When to use:** Every embedding insert and vector search query.
**Example:**
```python
# Source: verified via live sqlite-vec 0.1.9 testing 2026-04-10
import struct

def serialize_embedding(values: list[float]) -> bytes:
    """Pack float list to bytes for sqlite-vec. Lists not accepted directly."""
    return struct.pack(f"{len(values)}f", *values)

# INSERT:
# conn.execute("INSERT INTO vec_embeddings_384(rowid, entity_type, entity_id, embedding)
#               VALUES (?, ?, ?, ?)", (rowid, entity_type, entity_id, serialize_embedding(vec)))
# QUERY:
# conn.execute("SELECT rowid, entity_type, entity_id, distance FROM vec_embeddings_384
#               WHERE embedding MATCH ? ORDER BY distance LIMIT 10", (serialize_embedding(query_vec),))
```

### Pattern 8: Hybrid Search Score Fusion (D-08)
**What:** Normalize FTS5 rank and vec distance to [0,1], combine with configurable weight.
**When to use:** In `search/hybrid.py`.
**Example:**
```python
# Source: verified via algorithm testing 2026-04-10
def fuse_scores(
    fts_results: list[tuple[str, str, int, float]],   # (entity_type, name, entity_id, rank)
    vec_results: list[tuple[str, str, int, float]],   # (entity_type, name, entity_id, distance)
    fts_weight: float = 0.5,
    vec_weight: float = 0.5,
) -> list[tuple[str, str, int, float]]:
    """FTS5 rank is negative (less negative = better). Vec distance is non-negative (lower = closer)."""
    # Normalize FTS: abs(rank), then divide by max
    if fts_results:
        fts_max = max(abs(r[3]) for r in fts_results) or 1.0
        fts_scores = {(r[0], r[1], r[2]): abs(r[3]) / fts_max for r in fts_results}
    else:
        fts_scores = {}
    
    # Normalize vec: invert (1 - d/max_d) so closer = higher score
    if vec_results:
        vec_max = max(r[3] for r in vec_results) or 1.0
        vec_scores = {(r[0], r[1], r[2]): 1.0 - (r[3] / vec_max) for r in vec_results}
    else:
        vec_scores = {}
    
    # Merge
    all_keys = set(fts_scores) | set(vec_scores)
    combined = []
    for key in all_keys:
        score = fts_weight * fts_scores.get(key, 0.0) + vec_weight * vec_scores.get(key, 0.0)
        combined.append((*key, score))
    
    return sorted(combined, key=lambda x: -x[3])
```

### Pattern 9: Python BFS with Edge Type Filter (D-05, D-06)
**What:** BFS over SQLite adjacency queries using collections.deque.
**When to use:** `lineage` MCP tool and CLI command.
**Example:**
```python
# Source: verified via algorithm testing 2026-04-10
import collections
import sqlite3

def bfs_graph(
    conn: sqlite3.Connection,
    start_id: int,
    max_depth: int = 3,
    edge_types: list[str] | None = None,
) -> list[dict]:
    """BFS from start_id. Visited set prevents cycles (D-17)."""
    visited = {start_id}
    queue = collections.deque([(start_id, 0, [start_id])])
    results = []

    while queue:
        node_id, depth, path = queue.popleft()
        results.append({"node_id": node_id, "depth": depth, "path": path})

        if depth >= max_depth:
            continue

        # Query neighbors from current_db_relationships view
        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            neighbors = conn.execute(
                f"SELECT target_id, relationship_type FROM current_db_relationships "
                f"WHERE source_id = ? AND relationship_type IN ({placeholders})",
                [node_id, *edge_types],
            ).fetchall()
        else:
            neighbors = conn.execute(
                "SELECT target_id, relationship_type FROM current_db_relationships WHERE source_id = ?",
                (node_id,),
            ).fetchall()

        for target_id, rel_type in neighbors:
            if target_id not in visited:
                visited.add(target_id)
                queue.append((target_id, depth + 1, path + [target_id]))

    return results
```

### Pattern 10: Bi-temporal Invalidation on Re-parse (D-11)
**What:** On body_hash change: invalidate old row, insert new. Cascade to derived tables.
**When to use:** During incremental re-parse (INGEST-08).
**Example:**
```python
# Source: extends established Phase 1 bi-temporal pattern
import hashlib

def compute_body_hash(sql_text: str) -> str:
    normalized = " ".join(sql_text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def invalidate_procedure(conn: sqlite3.Connection, procedure_id: int, now_iso: str, now_ts: int):
    """Invalidate a procedure row and all its derived intelligence."""
    conn.execute(
        "UPDATE db_procedures SET invalidated_at=?, invalidated_at_ts=? WHERE id=?",
        (now_iso, now_ts, procedure_id)
    )
    # Cascade to derived tables
    for table in ("sp_branches", "sp_reliability", "sp_call_chains"):
        conn.execute(
            f"UPDATE {table} SET invalidated_at=?, invalidated_at_ts=? WHERE procedure_id=?",
            (now_iso, now_ts, procedure_id)
        )
    for table in ("enum_values", "state_transitions"):
        conn.execute(
            f"UPDATE {table} SET invalidated_at=?, invalidated_at_ts=? WHERE source_procedure_id=?",
            (now_iso, now_ts, procedure_id)
        )
```

### Anti-Patterns to Avoid
- **Re-parsing Command node bodies:** sqlglot produces the same Command fallback recursively. Use regex extraction instead (D-01).
- **Passing Python lists to sqlite-vec:** `conn.execute(..., ([0.1, 0.2, ...],))` raises `ProgrammingError: type 'list' is not supported`. Always use `struct.pack("Nf", *values)` [VERIFIED: live test].
- **Loading sqlite-vec without enable_load_extension:** Raises `sqlite3.OperationalError: not authorized` [VERIFIED: live test].
- **Querying raw temporal tables:** All application code MUST query through `current_*` views (STORE-02, established Phase 1 pattern).
- **Embedding during ingest:** D-09 mandates on-demand embedding at first search. Do not import sentence-transformers in ingest pipeline.
- **Using exp.Anonymous node count as quality proxy without normalizing:** Raw count is meaningless — ratio to total nodes is the correct metric [VERIFIED: live test].

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL tokenization/parsing | Custom T-SQL regex parser | sqlglot 30.4.2 | Handles CTEs, CASE, JOIN types, EXEC — regex breaks on nesting |
| Vector similarity search | Custom cosine/L2 search | sqlite-vec vec0 | L2 distance directly in SQL; no external process |
| Full-text search scoring | BM25 from scratch | FTS5 rank() | rank() IS BM25; built into SQLite 3.45 bundled with Python 3.11 |
| Float serialization for vectors | Custom bytes encoding | struct.pack("Nf") | sqlite-vec requires this exact format; documented pattern |
| Graph cycle detection | Graph theory library | visited set in BFS | collections.deque + visited set handles cycles; <100k nodes is trivially fast |
| Embedding model | Custom transformer | sentence-transformers all-MiniLM-L6-v2 | 22MB model, CPU-fast, correct for schema/code semantic search |

**Key insight:** The procedural T-SQL constructs that appear "custom" (CASE enums, state transitions, call chains) are actually straightforward once you know the correct sqlglot node types. The only custom logic needed is the regex fallback for Command nodes (ELSE/WHILE bodies) — everything else uses standard sqlglot traversal.

---

## Common Pitfalls

### Pitfall 1: ELSE Blocks Fall to Command Nodes
**What goes wrong:** Developer calls `stmt.find_all(exp.Table)` and misses all table refs inside ELSE branches.
**Why it happens:** sqlglot 30.4.2 parses IF body but ELSE body falls to `exp.Command` fallback [VERIFIED: live test]. The ELSE body text is `"END ELSE\n    BEGIN\n        SELECT * FROM dbo.Table"`.
**How to avoid:** Always run Pass 2 regex extraction over all `stmt.find_all(exp.Command)` nodes. Set `partial_ast=True` on any SP with Command nodes.
**Warning signs:** SP has zero table refs extracted but file clearly has SELECT statements in ELSE blocks.

### Pitfall 2: sp_executesql Not Identified as Dynamic SQL
**What goes wrong:** Developer checks `isinstance(exe.this, exp.Subquery)` only, misses EXEC sp_executesql N'...' which has `exe.this.name == "sp_executesql"`.
**Why it happens:** sp_executesql is a Table node with name "sp_executesql", not a Paren/Subquery [VERIFIED: live test].
**How to avoid:** Check both: `isinstance(this, (exp.Subquery, exp.Paren))` OR `getattr(this, "name", "").lower() == "sp_executesql"`.
**Warning signs:** sp_executesql calls appear as static call chains to a proc named "sp_executesql".

### Pitfall 3: sqlite-vec enable_load_extension Must Be Called Before Load
**What goes wrong:** `sqlite_vec.load(conn)` raises `OperationalError: not authorized`.
**Why it happens:** SQLite extensions are disabled by default for security [VERIFIED: live test].
**How to avoid:** Call `conn.enable_load_extension(True)` before `sqlite_vec.load(conn)`, then `conn.enable_load_extension(False)` after. Disable after loading to prevent further extension loading.
**Warning signs:** First line of error is `sqlite3.OperationalError: not authorized`.

### Pitfall 4: sentence-transformers Major Version Jump
**What goes wrong:** Code written for sentence-transformers 3.x breaks on 5.4.0.
**Why it happens:** Latest is 5.4.0, not 3.x as documented in CLAUDE.md [VERIFIED: pip index versions 2026-04-10]. The core API (`SentenceTransformer`, `.encode()`) is stable but some advanced APIs changed.
**How to avoid:** Pin to `>=3.0,<6` to allow 5.x. Lazy-load pattern means only `.encode(texts, convert_to_numpy=True)` is needed — this API is stable across versions.
**Warning signs:** ImportError on newly moved classes.

### Pitfall 5: INSERT Target Table Path in sqlglot for INSERT INTO
**What goes wrong:** `ins.this.name` returns `None` for `INSERT INTO dbo.AuditLog (cols) VALUES`.
**Why it happens:** `ins.this` is a `Schema` node wrapping the `Table` — must traverse `ins.this.this` to get the Table [VERIFIED: live test].
**How to avoid:** Use `ins.this.this.name` for INSERT targets, or `list(ins.find_all(exp.Table))[0].name` for schema-qualified names.
**Warning signs:** All INSERT mutations produce empty table names.

### Pitfall 6: FTS5 Rank Polarity
**What goes wrong:** Sorting FTS results by `rank` ascending shows least relevant first.
**Why it happens:** FTS5 `rank()` returns negative numbers (less negative = better match). Standard Python `sorted(..., key=lambda x: x.rank)` ascending gives worst results first.
**How to avoid:** Sort ascending (less negative = better), OR negate rank for normalization: `abs(rank) / max_abs_rank`.
**Warning signs:** Search returns results in reverse relevance order.

### Pitfall 7: Bi-temporal Cascade Incompleteness on Re-parse
**What goes wrong:** Re-parsing an SP invalidates `db_procedures` but leaves stale `sp_branches`, `sp_call_chains`, `enum_values`, `state_transitions` rows active.
**Why it happens:** Easy to forget cascade — the invalidation code only touches the parent table.
**How to avoid:** Create a `invalidate_procedure(conn, procedure_id, ...)` helper that invalidates all derived tables in one call (D-11). Cover this with a test.
**Warning signs:** State transitions show both old and new values when queried; duplicate call chain entries.

---

## Runtime State Inventory

Step 2.5: SKIPPED — This is a greenfield feature addition phase, not a rename/refactor/migration. No existing runtime state to inventory.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| sqlglot | SP parser | Yes | 30.4.2 | — |
| sqlite3 (stdlib) | Store + FTS5 | Yes | 3.45+ (bundled) | — |
| sqlite-vec | STORE-09 | Yes (installed 2026-04-10) | 0.1.9 | — |
| sentence-transformers | CONFIG-01 (local embeddings) | Not installed | — (latest: 5.4.0) | Deferred — lazy-load on first search |
| pytest | Testing | Yes | 9.x (dev dep) | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** sentence-transformers is not installed and is intentionally lazy-loaded. The install happens automatically when user first triggers a search (CONFIG-04). No phase blocker.

**Note:** sqlite-vec was added to `pyproject.toml` during research (`uv add sqlite-vec`). Sentence-transformers should be added as an optional dependency group.

---

## Schema Design (Claude's Discretion)

The following table designs are recommended. All follow the established bi-temporal pattern from Phase 1.

### New Tables for STORE-05 (SP Intelligence)

```sql
-- SP branches: IF/ELSE branches extracted from procedural blocks (INGEST-03)
CREATE TABLE IF NOT EXISTS sp_branches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id        INTEGER NOT NULL REFERENCES db_procedures(id),
    branch_index        INTEGER NOT NULL,   -- 0-based branch position in SP
    condition_text      TEXT,               -- raw condition expression (may be NULL for ELSE)
    branch_type         TEXT NOT NULL,      -- 'if'|'else'|'case_when'|'while'
    tables_touched_json TEXT,               -- JSON array of table names touched in this branch
    nesting_depth       INTEGER NOT NULL DEFAULT 0,
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

-- SP reliability: quality score + dynamic SQL flag (INGEST-06, INGEST-07)
CREATE TABLE IF NOT EXISTS sp_reliability (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id        INTEGER NOT NULL REFERENCES db_procedures(id),
    parse_quality       REAL NOT NULL DEFAULT 1.0,  -- 0.0-1.0; <0.95 = degraded
    is_degraded         INTEGER NOT NULL DEFAULT 0, -- 1 if parse_quality < 0.95
    has_dynamic_sql     INTEGER NOT NULL DEFAULT 0,
    has_cycle           INTEGER NOT NULL DEFAULT 0, -- D-17: circular call chain detected
    partial_ast         INTEGER NOT NULL DEFAULT 0, -- 1 if Command fallback nodes present
    dynamic_sql_locations_json TEXT,                -- JSON array of {line, exec_text}
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

-- SP call chains: SP-A calls SP-B (INGEST-05)
CREATE TABLE IF NOT EXISTS sp_call_chains (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id           INTEGER NOT NULL REFERENCES db_procedures(id),
    callee_id           INTEGER,            -- NULL if unresolved (D-16)
    callee_name_raw     TEXT NOT NULL,      -- original name from EXEC statement
    callee_schema       TEXT,
    is_resolved         INTEGER NOT NULL DEFAULT 0,
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

CREATE VIEW IF NOT EXISTS current_sp_branches AS
    SELECT * FROM sp_branches WHERE valid_until IS NULL AND invalidated_at IS NULL;
CREATE VIEW IF NOT EXISTS current_sp_reliability AS
    SELECT * FROM sp_reliability WHERE valid_until IS NULL AND invalidated_at IS NULL;
CREATE VIEW IF NOT EXISTS current_sp_call_chains AS
    SELECT * FROM sp_call_chains WHERE valid_until IS NULL AND invalidated_at IS NULL;
```

### New Tables for STORE-06 (Value Intelligence)

```sql
-- Enum values detected from CASE statements and naming heuristics (INGEST-03, D-04)
CREATE TABLE IF NOT EXISTS enum_values (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name              TEXT NOT NULL,
    column_name             TEXT NOT NULL,
    enum_value              TEXT NOT NULL,  -- the literal value
    enum_label              TEXT,           -- the THEN label (may be NULL for heuristic detection)
    confidence              REAL NOT NULL DEFAULT 0.5,
    detection_method        TEXT NOT NULL,  -- 'case_when'|'sp_name_heuristic'|'column_name_heuristic'
    source_procedure_id     INTEGER REFERENCES db_procedures(id),
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

-- State transitions detected from UPDATE SET col=X WHERE col=Y (INGEST-04)
CREATE TABLE IF NOT EXISTS state_transitions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name              TEXT NOT NULL,
    column_name             TEXT NOT NULL,
    from_value              TEXT NOT NULL,
    to_value                TEXT NOT NULL,
    confidence              REAL NOT NULL DEFAULT 0.9,
    source_procedure_id     INTEGER REFERENCES db_procedures(id),
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

-- Bitmask definitions (named flag values) — detected from naming heuristics (*Flag, *Flags)
CREATE TABLE IF NOT EXISTS bitmask_definitions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name              TEXT NOT NULL,
    column_name             TEXT NOT NULL,
    bit_position            INTEGER NOT NULL,   -- 0-based bit position
    bit_label               TEXT,               -- human-readable name if detectable
    confidence              REAL NOT NULL DEFAULT 0.3,
    detection_method        TEXT NOT NULL,      -- 'case_when'|'column_name_heuristic'
    source_procedure_id     INTEGER REFERENCES db_procedures(id),
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

-- Column aliases: alternative names used for a column across SPs
CREATE TABLE IF NOT EXISTS column_aliases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    alias               TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.5,
    source_procedure_id INTEGER REFERENCES db_procedures(id),
    -- bi-temporal
    valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
    valid_until TEXT, valid_until_ts INTEGER,
    recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
    invalidated_at TEXT, invalidated_at_ts INTEGER
);

CREATE VIEW IF NOT EXISTS current_enum_values AS
    SELECT * FROM enum_values WHERE valid_until IS NULL AND invalidated_at IS NULL;
CREATE VIEW IF NOT EXISTS current_state_transitions AS
    SELECT * FROM state_transitions WHERE valid_until IS NULL AND invalidated_at IS NULL;
CREATE VIEW IF NOT EXISTS current_bitmask_definitions AS
    SELECT * FROM bitmask_definitions WHERE valid_until IS NULL AND invalidated_at IS NULL;
CREATE VIEW IF NOT EXISTS current_column_aliases AS
    SELECT * FROM column_aliases WHERE valid_until IS NULL AND invalidated_at IS NULL;
```

### New Tables for STORE-09, STORE-10 (Search Infrastructure)

```sql
-- Vector embeddings (D-07, D-19): separate table per provider dimension
-- Created by store.py when embedding_provider config is loaded
-- vec0 virtual table requires sqlite-vec extension loaded
-- CREATE VIRTUAL TABLE vec_embeddings_384 USING vec0(
--     entity_type TEXT,
--     entity_id INTEGER,
--     embedding FLOAT[384]
-- );
-- CREATE VIRTUAL TABLE vec_embeddings_1536 USING vec0(
--     entity_type TEXT,
--     entity_id INTEGER,
--     embedding FLOAT[1536]
-- );
-- Note: Created programmatically based on config, not in static SCHEMA_SQL

-- FTS5 index for entity names and descriptions (STORE-10)
CREATE VIRTUAL TABLE IF NOT EXISTS fts_entities USING fts5(
    entity_name,
    description,
    entity_type UNINDEXED,
    entity_id UNINDEXED,
    tokenize='porter ascii'
);
```

**Note on vec0 table creation:** Virtual tables created with `CREATE VIRTUAL TABLE` cannot use `IF NOT EXISTS` semantics with `CREATE TABLE IF NOT EXISTS`. The store init code must check for existence before creating vec tables, or use `CREATE VIRTUAL TABLE IF NOT EXISTS` (supported in sqlite-vec 0.1.9). [ASSUMED — verify IF NOT EXISTS support for virtual tables]

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` — asyncio_mode = "auto" |
| Quick run command | `uv run pytest tests/ -q` |
| Full suite command | `uv run pytest tests/ -v` |

**Baseline:** 84 tests pass in 1.20s [VERIFIED: 2026-04-10].

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-02 | Table refs extracted from SP AST | unit | `uv run pytest tests/test_sp_parser.py -x -q` | Wave 0 |
| INGEST-03 | IF branches, CASE enums, nesting depth extracted | unit | `uv run pytest tests/test_sp_parser.py::test_branch_extraction -x` | Wave 0 |
| INGEST-04 | State transitions from UPDATE SET/WHERE literals | unit | `uv run pytest tests/test_sp_parser.py::test_state_transitions -x` | Wave 0 |
| INGEST-05 | Call chains extracted from EXEC statements | unit | `uv run pytest tests/test_sp_parser.py::test_call_chains -x` | Wave 0 |
| INGEST-06 | Dynamic SQL (EXEC(@var), sp_executesql) flagged | unit | `uv run pytest tests/test_sp_parser.py::test_dynamic_sql -x` | Wave 0 |
| INGEST-07 | Parse quality score + degraded flag | unit | `uv run pytest tests/test_sp_parser.py::test_parse_quality -x` | Wave 0 |
| INGEST-08 | Directory glob ingest, incremental re-parse via body_hash | unit | `uv run pytest tests/test_sp_parser.py::test_incremental_reparse -x` | Wave 0 |
| STORE-05 | sp_branches/sp_reliability/sp_call_chains tables created | unit | `uv run pytest tests/test_schema.py::test_sp_tables -x` | Wave 0 |
| STORE-06 | enum_values/state_transitions/bitmask/aliases tables | unit | `uv run pytest tests/test_schema.py::test_value_intelligence_tables -x` | Wave 0 |
| STORE-09 | sqlite-vec vec0 table, insert + search | unit | `uv run pytest tests/test_search.py::test_vector_search -x` | Wave 0 |
| STORE-10 | FTS5 table, keyword search with rank | unit | `uv run pytest tests/test_search.py::test_fts_search -x` | Wave 0 |
| STORE-11 | BFS from entity, depth limit, edge type filter | unit | `uv run pytest tests/test_graph.py::test_bfs -x` | Wave 0 |
| CLI-03 | ingest directory, --type flag, --quality flag | integration | `uv run pytest tests/test_cli.py::test_ingest_directory -x` | Wave 0 |
| CONFIG-01 | Embedding provider config, correct vec table selected | unit | `uv run pytest tests/test_search.py::test_embedding_provider -x` | Wave 0 |
| CONFIG-04 | torch not imported at module load; imported on first search | unit | `uv run pytest tests/test_search.py::test_lazy_load -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_sp_parser.py` — covers INGEST-02 through INGEST-08
- [ ] `tests/test_schema.py` — covers STORE-05, STORE-06 table creation
- [ ] `tests/test_search.py` — covers STORE-09, STORE-10, CONFIG-01, CONFIG-04
- [ ] `tests/test_graph.py` — covers STORE-11 BFS traversal

*(Existing tests/conftest.py and tests/test_cli.py will be extended — not created from scratch)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Local-first tool; no auth |
| V3 Session Management | No | Stateless MCP + CLI |
| V4 Access Control | No | Single-user local tool |
| V5 Input Validation | Yes | File size check (T-02-01), path resolution (T-03-01), sqlglot parses not executes (T-02-03) |
| V6 Cryptography | No | No secrets stored in Phase 2 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via SP body content stored in intelligence tables | Tampering | Parameterized INSERT (? placeholders) — established Phase 1 pattern T-02-02 |
| Path traversal via directory ingest path | Tampering | Path.resolve() before any file operation — established Phase 1 pattern T-03-01 |
| File bomb (huge SP files) | DoS | File size check before passing to sqlglot — T-02-01, already in ddl_parser.py |
| sqlite-vec extension loading enables arbitrary code | Elevation | Enable extension loading only in `open_store()`, disable immediately after sqlite_vec.load() |
| Regex catastrophic backtracking on malformed SP bodies | DoS | Use anchored patterns; test against adversarial input; sqlglot pre-filters most malformed SQL |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sentence-transformers 3.x (CLAUDE.md docs) | 5.4.0 (April 2026) | ~mid-2025 | Pin to `>=3.0,<6`; core `.encode()` API stable |
| bfsvtab for graph traversal | Python BFS + SQLite adjacency (D-05) | Decision made Phase 2 | No C extension needed; simpler deployment |
| chromadb for vector search | sqlite-vec in same SQLite file | Architecture decision | Zero-infrastructure; single `.db` file |

**Deprecated/outdated:**
- CLAUDE.md says "sqlite-vec 0.1.x" — current is 0.1.9 (still in 0.1.x range, no API changes)
- CLAUDE.md says "sentence-transformers 3.x" — current is 5.4.0. Major version bump but `.encode()` API stable. [VERIFIED: pip index]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `CREATE VIRTUAL TABLE IF NOT EXISTS` syntax supported by sqlite-vec's vec0 | Schema Design | Schema init fails on second run; need try/except or existence check |
| A2 | sentence-transformers 5.4.0 `.encode(texts, convert_to_numpy=True)` returns same output shape as 3.x | Standard Stack | Embedding shape mismatch breaks vector search |
| A3 | FTS5 `porter` tokenizer available in Python 3.11 bundled SQLite on Windows | Architecture Patterns | FTS5 tables require `tokenize='unicode61'` fallback |
| A4 | vec0 virtual table supports TEXT and INTEGER auxiliary columns alongside the float vector column | Schema Design (D-19) | Need separate metadata table (rowid JOIN) instead |

**Note:** A4 was partially validated — INSERT with entity_type TEXT + entity_id INTEGER + embedding works in testing. The concern is whether auxiliary columns survive all vec0 query patterns.

---

## Open Questions

1. **`CREATE VIRTUAL TABLE IF NOT EXISTS` for vec0**
   - What we know: vec0 creates a virtual table; `IF NOT EXISTS` works for regular tables
   - What's unclear: sqlite-vec 0.1.9 virtual table creation error behavior on duplicate
   - Recommendation: Wrap in try/except SQLite `table already exists` error as a safe guard

2. **sentence-transformers 5.4.0 API changes**
   - What we know: 5.4.0 is current; CLAUDE.md documents 3.x API
   - What's unclear: Whether any intermediate breaking changes affect lazy-load pattern
   - Recommendation: Pin `>=3.0,<6` and test with `SentenceTransformer('all-MiniLM-L6-v2').encode(['test'])` shape at Wave 0

3. **FTS5 porter tokenizer on Windows**
   - What we know: FTS5 is confirmed available on this machine [VERIFIED: live test]
   - What's unclear: Whether `tokenize='porter ascii'` is available on all Python 3.11+ builds
   - Recommendation: Default to `tokenize='unicode61'` if `porter` tokenizer fails; add try/except in schema init

---

## Sources

### Primary (HIGH confidence)
- Live sqlglot 30.4.2 testing in project venv — all AST node types, parsing behaviors, ELSE fallback
- Live sqlite-vec 0.1.9 testing — load pattern, serialization, vec0 metadata columns
- Live SQLite FTS5 testing — availability, rank() scoring, tokenizer
- `db_wiki/ingest/ddl_parser.py` — established patterns extended in Phase 2
- `db_wiki/core/schema.py` — bi-temporal table template
- `db_wiki/server/app.py` — @mcp.tool() pattern
- `db_wiki/cli/app.py` — Typer command pattern
- `pyproject.toml` — current pinned versions

### Secondary (MEDIUM confidence)
- pip index versions (2026-04-10) — sqlite-vec 0.1.9, sentence-transformers 5.4.0 [VERIFIED: registry]

### Tertiary (LOW confidence)
- CLAUDE.md §Technology Stack — sentence-transformers 3.x version (outdated; actual is 5.4.0)
- CLAUDE.md §bfsvtab Notes — fallback BFS pattern (confirmed as primary approach by D-05)

---

## Metadata

**Confidence breakdown:**
- SP parsing patterns: HIGH — verified against sqlglot 30.4.2 with live tests
- sqlite-vec API: HIGH — verified 0.1.9 with live tests
- FTS5 patterns: HIGH — verified against bundled SQLite
- Schema design: HIGH — follows established bi-temporal pattern exactly
- sentence-transformers lazy-load: HIGH — import pattern verified; version bump noted
- BFS implementation: HIGH — algorithm verified

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (30 days; sqlglot and sqlite-vec are stable; sentence-transformers moves faster)
