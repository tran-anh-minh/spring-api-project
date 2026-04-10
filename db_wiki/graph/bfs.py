"""Python BFS graph traversal over SQLite adjacency (D-05, D-06, D-17).

Uses collections.deque for BFS and a visited set for cycle detection.
Queries current_db_relationships view (STORE-02 compliance).
Supports configurable edge type filtering (D-06).
"""
import collections
import logging
import sqlite3

logger = logging.getLogger(__name__)


def bfs_graph(
    conn: sqlite3.Connection,
    start_id: int,
    max_depth: int = 3,
    edge_types: list[str] | None = None,
    bidirectional: bool = True,
) -> list[dict]:
    """BFS traversal from start_id through the relationship graph.

    Args:
        conn: SQLite connection with current_db_relationships view.
        start_id: Entity ID to start traversal from.
        max_depth: Maximum BFS depth (default 3). 0 = start node only.
        edge_types: Optional list of relationship types to follow.
            Default None = all types (fk_declared, fk_inferred, joins_with,
            reads_from, writes_to, feeds_into). Per D-06.
        bidirectional: If True, follow edges in both directions (source->target
            and target->source). Default True.

    Returns:
        List of dicts: [{"node_id": int, "depth": int, "path": list[int],
                         "edge_type": str|None}]
        The start node is always first with depth=0 and edge_type=None.
        Cycle detection via visited set prevents infinite loops (D-17).
    """
    visited: set[int] = {start_id}
    queue: collections.deque[tuple[int, int, list[int], str | None]] = (
        collections.deque()
    )
    queue.append((start_id, 0, [start_id], None))
    results: list[dict] = []

    while queue:
        node_id, depth, path, edge_type = queue.popleft()
        results.append({
            "node_id": node_id,
            "depth": depth,
            "path": path,
            "edge_type": edge_type,
        })

        if depth >= max_depth:
            continue

        # Query outgoing edges (source_id = node_id)
        neighbors = _get_neighbors(
            conn, node_id, edge_types, "source_id", "target_id"
        )

        # Query incoming edges if bidirectional (target_id = node_id)
        if bidirectional:
            neighbors.extend(
                _get_neighbors(
                    conn, node_id, edge_types, "target_id", "source_id"
                )
            )

        for neighbor_id, rel_type in neighbors:
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                queue.append((
                    neighbor_id,
                    depth + 1,
                    path + [neighbor_id],
                    rel_type,
                ))

    return results


def _get_neighbors(
    conn: sqlite3.Connection,
    node_id: int,
    edge_types: list[str] | None,
    match_col: str,
    return_col: str,
) -> list[tuple[int, str]]:
    """Query neighbors from current_db_relationships.

    Args:
        conn: SQLite connection.
        node_id: The node to find neighbors for.
        edge_types: Optional filter on relationship_type.
        match_col: Column to match node_id against ("source_id" or "target_id").
        return_col: Column to return as neighbor ("target_id" or "source_id").

    Returns:
        List of (neighbor_id, relationship_type) tuples.
    """
    if edge_types:
        placeholders = ",".join("?" * len(edge_types))
        rows = conn.execute(
            f"SELECT {return_col}, relationship_type FROM current_db_relationships "
            f"WHERE {match_col} = ? AND relationship_type IN ({placeholders})",
            [node_id, *edge_types],
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {return_col}, relationship_type FROM current_db_relationships "
            f"WHERE {match_col} = ?",
            (node_id,),
        ).fetchall()
    return [(row[0], row[1]) for row in rows]
