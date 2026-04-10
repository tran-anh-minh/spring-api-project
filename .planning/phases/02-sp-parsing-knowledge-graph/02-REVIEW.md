---
phase: 02-sp-parsing-knowledge-graph
reviewed: 2026-04-10T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - db_wiki/cli/app.py
  - db_wiki/core/config.py
  - db_wiki/core/models.py
  - db_wiki/core/queries.py
  - db_wiki/core/schema.py
  - db_wiki/core/store.py
  - db_wiki/graph/bfs.py
  - db_wiki/ingest/sp_parser.py
  - db_wiki/search/embedder.py
  - db_wiki/search/fts.py
  - db_wiki/search/hybrid.py
  - db_wiki/server/app.py
findings:
  critical: 1
  warning: 5
  info: 2
  total: 8
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-04-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed all 12 source files in the db-wiki codebase covering CLI, core data layer, graph traversal, SP parsing, search, and MCP server. The code is generally well-structured with good security practices (safe YAML loading, parameterized SQL for user data, path resolution). One critical SQL injection vector was found in the BFS module, along with several warnings around dangling foreign keys, missing FTS input sanitization, and resource leak patterns.

## Critical Issues

### CR-01: SQL Injection via Column Name Interpolation in BFS Module

**File:** `db_wiki/graph/bfs.py:105-113`
**Issue:** `_get_neighbors()` interpolates `match_col` and `return_col` directly into SQL using f-strings. While current callers only pass the fixed strings `"source_id"` and `"target_id"`, this function is public (no underscore convention enforced at module boundary) and any future caller passing user-controlled values would create a SQL injection vulnerability. The `edge_types` values from CLI (`--edge-types` flag) flow through `bfs_graph` and are correctly parameterized, but the column names are not.
**Fix:** Validate column names against an allowlist:
```python
_VALID_COLUMNS = {"source_id", "target_id"}

def _get_neighbors(
    conn: sqlite3.Connection,
    node_id: int,
    edge_types: list[str] | None,
    match_col: str,
    return_col: str,
) -> list[tuple[int, str]]:
    if match_col not in _VALID_COLUMNS or return_col not in _VALID_COLUMNS:
        raise ValueError(f"Invalid column name: {match_col}, {return_col}")
    # ... rest of function unchanged
```

## Warnings

### WR-01: Dangling Foreign Key (target_id=0) for Unresolved Relationship Targets

**File:** `db_wiki/ingest/sp_parser.py:896-915`
**Issue:** When `ingest_sp` inserts a `db_relationships` row and the target table is not found in `current_db_tables`, it sets `target_id` to `0` instead of `NULL`. There is no entity with `id=0` in any table (AUTOINCREMENT starts at 1), so this creates a dangling reference. The `PRAGMA foreign_keys=ON` does not catch this because `db_relationships.target_id` has no `REFERENCES` constraint in the schema DDL. Downstream queries (e.g., the sp-info JOIN on `target_id = t.id`) silently skip these rows, hiding unresolved relationships from users.
**Fix:** Use `NULL` for unresolved targets and handle it in display logic:
```python
target_id = target_row["id"] if target_row else None

conn.execute(
    """INSERT INTO db_relationships (
        source_id, target_id, relationship_type, confidence, ...
    ) VALUES (?, ?, ?, ?, ...)""",
    (proc_id, target_id, rel.relationship_type, rel.confidence, ...),
)
```

### WR-02: FTS5 Query Not Sanitized Against Special Syntax

**File:** `db_wiki/search/fts.py:73-79`
**Issue:** The `search_fts()` function passes the user query directly to `FTS5 MATCH ?`. FTS5 has its own query syntax (e.g., `OR`, `AND`, `NOT`, `NEAR`, column filters with `:`). Malformed queries like `"table OR"` or queries containing `*` will raise `sqlite3.OperationalError`. This affects both the CLI `search` command and the MCP `search` tool.
**Fix:** Wrap the query in double quotes to force FTS5 to treat it as a phrase, or catch the OperationalError:
```python
def search_fts(conn, query, limit=20):
    # Escape double quotes in query and wrap as phrase
    safe_query = '"' + query.replace('"', '""') + '"'
    rows = conn.execute(
        "SELECT entity_type, entity_name, entity_id, rank "
        "FROM fts_entities WHERE fts_entities MATCH ? "
        "ORDER BY rank LIMIT ?",
        (safe_query, limit),
    ).fetchall()
    return [(row[0], row[1], row[2], row[3]) for row in rows]
```

### WR-03: Connection Resource Leak in CLI Commands

**File:** `db_wiki/cli/app.py:291-323` and `db_wiki/cli/app.py:349-373`
**Issue:** The `search` and `lineage` CLI commands open a database connection with `open_store()` but close it with a bare `conn.close()` call at the end. If any operation between open and close raises an exception (e.g., `hybrid_search` fails, `bfs_graph` fails), the connection is leaked. The `ingest` command correctly uses `try/finally` for this.
**Fix:** Use `try/finally` or a context manager pattern:
```python
conn = open_store(db_path)
try:
    init_schema(conn)
    # ... operations ...
finally:
    conn.close()
```

### WR-04: FTS Normalization Inverted (Higher abs(rank) Scored Higher)

**File:** `db_wiki/search/hybrid.py:33-36`
**Issue:** FTS5 `rank` returns negative values where less negative means better match (e.g., -1.5 is better than -10.0). The normalization `abs(r[3]) / max_abs` assigns the highest normalized score to the result with the largest absolute rank value, which is the *worst* FTS match. This inverts the FTS ranking in the fused score.
**Fix:** Invert the normalization so less negative (better) matches get higher scores:
```python
if fts_results:
    max_abs = max(abs(r[3]) for r in fts_results) or 1.0
    for r in fts_results:
        key = (r[0], r[2])
        # Less negative = better, so invert: 1 - (abs(rank) / max_abs)
        fts_scores[key] = 1.0 - (abs(r[3]) / max_abs)
        fts_names[key] = r[1]
```

### WR-05: f-string SQL Table Name Construction in Embedder

**File:** `db_wiki/search/embedder.py:87-91` and `db_wiki/search/embedder.py:106-112`
**Issue:** The `Embedder` class constructs SQL using `f"INSERT INTO {self.vec_table_name}..."` and `f"SELECT ... FROM {self.vec_table_name}..."`. The `vec_table_name` is derived from `self.dimensions` (an integer from config), so it cannot currently be injected. However, if config parsing is ever loosened or `dimensions` comes from an untrusted source, this becomes an injection vector. The pattern is inconsistent with the parameterized approach used elsewhere.
**Fix:** Validate the table name against expected format:
```python
@property
def vec_table_name(self) -> str:
    name = f"vec_embeddings_{self.dimensions}"
    if not name.isidentifier():
        raise ValueError(f"Invalid vec table name: {name}")
    return name
```

## Info

### IN-01: Unused `fts_names` Dict in Score Fusion

**File:** `db_wiki/search/hybrid.py:30,36`
**Issue:** The `fts_names` dictionary is populated in `fuse_scores()` but never read. It maps `(entity_type, entity_id)` to entity names from FTS results but is not used in the returned data or anywhere else.
**Fix:** Remove the `fts_names` dictionary and the line that populates it.

### IN-02: Duplicate sp-info Logic Between CLI and MCP Server

**File:** `db_wiki/cli/app.py:376-465` and `db_wiki/server/app.py:244-326`
**Issue:** The `sp_info` command is implemented nearly identically in both the CLI (`cli/app.py`) and MCP server (`server/app.py`). The same four SQL queries (procedure lookup, reliability, branches, call chains, relationships) are duplicated. If the schema changes, both must be updated. The `search` and `lineage` commands share code via `db_wiki/core/queries.py` and `db_wiki/graph/bfs.py`, but `sp_info` does not follow this pattern.
**Fix:** Extract the query logic into a shared function in `db_wiki/core/queries.py` that returns structured data, then have both CLI and MCP server format the output for their respective interfaces.

---

_Reviewed: 2026-04-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
