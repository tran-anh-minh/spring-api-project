"""Concept resolver: hybrid search + BFS JOIN paths + derived metrics.

Provides the core resolution primitives for the Phase 4 query engine:
  - resolve_concepts(): map NL terms to knowledge store entity IDs
  - find_join_paths(): find JOIN paths between two tables via BFS
  - define_metric(): register a named business metric (SQL expression)
  - get_metric() / get_all_metrics(): retrieve defined metrics

Security (T-04-01): define_metric validates sql_fragment via sqlglot and
rejects dangerous DML/DDL keywords.
"""
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

import sqlglot

from db_wiki.graph.bfs import bfs_graph
from db_wiki.search.hybrid import hybrid_search

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ResolvedEntity:
    """An entity resolved from a natural language query via hybrid search."""

    entity_type: str      # "table" | "procedure" | "column"
    entity_id: int
    name: str
    score: float


@dataclass
class JoinStep:
    """One hop in a JOIN path between two tables."""

    from_table: str
    to_table: str
    join_type: str        # relationship_type value (e.g. "fk_declared")
    edge_type: str        # alias for join_type (for compatibility)
    from_column: str | None = None
    to_column: str | None = None


@dataclass
class MetricDefinition:
    """A user-defined derived metric (business concept → SQL expression)."""

    name: str
    sql_fragment: str
    source_tables: list[str] = field(default_factory=list)
    description: str | None = None


# ---------------------------------------------------------------------------
# Forbidden SQL keywords for metric fragment validation (T-04-01)
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYWORDS = frozenset([
    "DROP", "INSERT", "DELETE", "EXEC", "EXECUTE", "UPDATE",
    "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE",
])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _lookup_table_name(conn: sqlite3.Connection, entity_id: int) -> str | None:
    row = conn.execute(
        "SELECT table_name FROM current_db_tables WHERE id = ?", (entity_id,)
    ).fetchone()
    return row[0] if row else None


def _lookup_procedure_name(conn: sqlite3.Connection, entity_id: int) -> str | None:
    row = conn.execute(
        "SELECT procedure_name FROM current_db_procedures WHERE id = ?", (entity_id,)
    ).fetchone()
    return row[0] if row else None


def _lookup_column_name(conn: sqlite3.Connection, entity_id: int) -> str | None:
    row = conn.execute(
        "SELECT column_name FROM current_db_columns WHERE id = ?", (entity_id,)
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_concepts(
    conn: sqlite3.Connection,
    query: str,
    embedding_config,
    limit: int = 10,
) -> list[ResolvedEntity]:
    """Map a natural language query to scored knowledge store entities.

    Calls hybrid_search() (FTS5 + vector similarity) and fetches entity
    names from the current_* views. Results are sorted by score descending.

    Args:
        conn: SQLite connection with initialized schema.
        query: Natural language query text.
        embedding_config: EmbeddingConfig instance.
        limit: Maximum number of results to return (default 10).

    Returns:
        List of ResolvedEntity sorted by score descending.
    """
    raw_results = hybrid_search(conn, query, embedding_config, limit=limit)
    resolved: list[ResolvedEntity] = []

    for entity_type, entity_id, score in raw_results:
        if entity_type == "table":
            name = _lookup_table_name(conn, entity_id)
        elif entity_type == "procedure":
            name = _lookup_procedure_name(conn, entity_id)
        elif entity_type == "column":
            name = _lookup_column_name(conn, entity_id)
        else:
            name = None

        if name is None:
            continue  # entity no longer in current view — skip

        resolved.append(ResolvedEntity(
            entity_type=entity_type,
            entity_id=entity_id,
            name=name,
            score=score,
        ))

    return sorted(resolved, key=lambda r: -r.score)


def find_join_paths(
    conn: sqlite3.Connection,
    start_table_id: int,
    end_table_id: int,
    max_depth: int = 4,
) -> list[JoinStep]:
    """Find JOIN paths between two tables using BFS graph traversal.

    Only follows FK and join edges (fk_declared, fk_inferred, joins_with).
    Looks up column names from current_db_relationships for each hop.

    Args:
        conn: SQLite connection with initialized schema.
        start_table_id: Source table entity ID.
        end_table_id: Target table entity ID.
        max_depth: Maximum BFS depth (default 4).

    Returns:
        List of JoinStep representing the path, or empty list if not found.
    """
    edge_types = ["fk_declared", "fk_inferred", "joins_with"]
    bfs_results = bfs_graph(
        conn,
        start_table_id,
        max_depth=max_depth,
        edge_types=edge_types,
        bidirectional=True,
    )

    # Find the node for end_table_id in BFS results
    target_node = None
    for node in bfs_results:
        if node["node_id"] == end_table_id:
            target_node = node
            break

    if target_node is None:
        return []

    path = target_node["path"]  # list of node IDs from start to end
    if len(path) < 2:
        return []

    steps: list[JoinStep] = []
    for i in range(len(path) - 1):
        from_id = path[i]
        to_id = path[i + 1]

        # Look up table names
        from_name = _lookup_table_name(conn, from_id) or str(from_id)
        to_name = _lookup_table_name(conn, to_id) or str(to_id)

        # Look up relationship details from current_db_relationships
        rel = conn.execute(
            "SELECT relationship_type, source_column, target_column "
            "FROM current_db_relationships "
            "WHERE (source_id = ? AND target_id = ?) "
            "   OR (source_id = ? AND target_id = ?) "
            "LIMIT 1",
            (from_id, to_id, to_id, from_id),
        ).fetchone()

        if rel:
            join_type = rel["relationship_type"]
            from_col = rel["source_column"]
            to_col = rel["target_column"]
        else:
            join_type = "joins_with"
            from_col = None
            to_col = None

        steps.append(JoinStep(
            from_table=from_name,
            to_table=to_name,
            join_type=join_type,
            edge_type=join_type,
            from_column=from_col,
            to_column=to_col,
        ))

    return steps


def _validate_sql_fragment(sql_fragment: str) -> None:
    """Validate a SQL fragment for use as a derived metric expression.

    Security (T-04-01): rejects fragments with semicolons or dangerous DML/DDL
    keywords. Also validates that sqlglot can parse it as an expression.

    Raises:
        ValueError: if the fragment is invalid or contains forbidden constructs.
    """
    # Reject semicolons (multi-statement injection)
    if ";" in sql_fragment:
        raise ValueError(
            "Invalid sql_fragment: semicolons are not allowed. "
            "Only single SQL expressions are accepted."
        )

    # Reject forbidden DML/DDL keywords (case-insensitive, word-boundary match)
    upper = sql_fragment.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        # Use word boundary to avoid false positives (e.g., "EXECUTOR" for "EXEC")
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, upper):
            raise ValueError(
                f"Invalid sql_fragment: forbidden keyword '{keyword}' detected. "
                "Only SQL expressions (aggregates, arithmetic, CASE) are accepted."
            )

    # Validate with sqlglot — wrap in SELECT to parse as expression
    try:
        sqlglot.parse_one(f"SELECT {sql_fragment}", dialect="tsql")
    except Exception as exc:
        raise ValueError(
            f"Invalid sql_fragment: could not parse as SQL expression: {exc}"
        ) from exc


def define_metric(
    conn: sqlite3.Connection,
    name: str,
    sql_fragment: str,
    source_tables: list[str],
    description: str | None = None,
) -> int:
    """Register a derived metric (business concept → SQL expression mapping).

    Validates the sql_fragment before storing. Inserts into derived_metrics
    with bi-temporal timestamps.

    Security (T-04-01): sql_fragment is validated against forbidden keywords
    and parsed by sqlglot before storage.

    Args:
        conn: SQLite connection.
        name: Unique metric name (e.g. "revenue").
        sql_fragment: SQL expression (e.g. "SUM(order_total)").
        source_tables: List of table names the expression references.
        description: Optional human-readable description.

    Returns:
        The new row ID in derived_metrics.

    Raises:
        ValueError: if sql_fragment is invalid or contains forbidden SQL.
    """
    _validate_sql_fragment(sql_fragment)

    now_iso = _now_iso()
    now_ts = _now_ts()
    source_tables_json = json.dumps(source_tables)

    cur = conn.execute(
        "INSERT INTO derived_metrics "
        "(metric_name, sql_fragment, source_tables, description, "
        " valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, sql_fragment, source_tables_json, description,
         now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()
    return cur.lastrowid


def get_metric(conn: sqlite3.Connection, name: str) -> MetricDefinition | None:
    """Retrieve a derived metric by name.

    Args:
        conn: SQLite connection.
        name: The metric name to look up.

    Returns:
        MetricDefinition or None if not found.
    """
    row = conn.execute(
        "SELECT metric_name, sql_fragment, source_tables, description "
        "FROM current_derived_metrics WHERE metric_name = ?",
        (name,),
    ).fetchone()

    if row is None:
        return None

    source_tables = json.loads(row["source_tables"]) if row["source_tables"] else []
    return MetricDefinition(
        name=row["metric_name"],
        sql_fragment=row["sql_fragment"],
        source_tables=source_tables,
        description=row["description"],
    )


def get_all_metrics(conn: sqlite3.Connection) -> list[MetricDefinition]:
    """Return all current derived metrics.

    Args:
        conn: SQLite connection.

    Returns:
        List of MetricDefinition.
    """
    rows = conn.execute(
        "SELECT metric_name, sql_fragment, source_tables, description "
        "FROM current_derived_metrics ORDER BY metric_name"
    ).fetchall()

    result = []
    for row in rows:
        source_tables = json.loads(row["source_tables"]) if row["source_tables"] else []
        result.append(MetricDefinition(
            name=row["metric_name"],
            sql_fragment=row["sql_fragment"],
            source_tables=source_tables,
            description=row["description"],
        ))
    return result


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version as max recorded_at_ts across key tables.

    Used for wiki page cache invalidation — if any entity was added/updated
    since the cached page was generated, the cache is stale.

    Returns:
        MAX(recorded_at_ts) across db_tables, db_columns, db_relationships.
        Returns 0 if all tables are empty.
    """
    row = conn.execute(
        """
        SELECT MAX(max_ts) FROM (
            SELECT MAX(recorded_at_ts) AS max_ts FROM db_tables
            UNION ALL
            SELECT MAX(recorded_at_ts) AS max_ts FROM db_columns
            UNION ALL
            SELECT MAX(recorded_at_ts) AS max_ts FROM db_relationships
        )
        """
    ).fetchone()
    return row[0] if row and row[0] is not None else 0
