"""JSON API route handlers for the db-wiki web UI (Plan 05-01).

All blocking DB calls are wrapped in anyio.to_thread.run_sync() to avoid
blocking the async event loop (RESEARCH anti-pattern avoidance).

Threat mitigations applied:
- T-05-01: depth param capped at 5 to prevent deep BFS traversal (DoS)
- T-05-03: generic error messages — no stack traces or SQL in responses
- T-05-04: node param parsed as int; 400 returned on non-integer (prevents SQL injection)
"""
import logging
import sqlite3
from pathlib import Path

import anyio
from starlette.requests import Request
from starlette.responses import JSONResponse

from db_wiki.core.config import DBWikiConfig

logger = logging.getLogger(__name__)


def make_routes(conn: sqlite3.Connection, config: DBWikiConfig):
    """Return (graph_api, wiki_api, search_api, dashboard_api, export_api) closures
    that capture the connection and config via closure.
    """

    # ------------------------------------------------------------------
    # graph_api
    # ------------------------------------------------------------------

    async def graph_api(request: Request) -> JSONResponse:
        """GET /api/graph — return all nodes+edges, or BFS subgraph for ?node=X."""
        node_param = request.query_params.get("node")
        depth_param = request.query_params.get("depth", "2")

        # T-05-04: validate node param
        if node_param is not None:
            try:
                node_id = int(node_param)
            except (ValueError, TypeError):
                return JSONResponse(
                    {"error": "Invalid node parameter — must be an integer."},
                    status_code=400,
                )
            # T-05-01: cap depth at 5
            try:
                depth = min(int(depth_param), 5)
            except (ValueError, TypeError):
                depth = 2

            try:
                result = await anyio.to_thread.run_sync(
                    lambda: _bfs_subgraph(conn, node_id, depth)
                )
            except Exception:
                logger.exception("Error in graph_api BFS")
                return JSONResponse(
                    {"error": "Could not load subgraph data."},
                    status_code=500,
                )
            return JSONResponse(result)

        # Initial full-graph load
        try:
            result = await anyio.to_thread.run_sync(lambda: _full_graph(conn))
        except Exception:
            logger.exception("Error in graph_api full load")
            return JSONResponse(
                {"error": "Could not load graph data."},
                status_code=500,
            )
        return JSONResponse(result)

    # ------------------------------------------------------------------
    # wiki_api
    # ------------------------------------------------------------------

    async def wiki_api(request: Request) -> JSONResponse:
        """GET /api/wiki?entity_id=X — return L1/L2 wiki content for an entity."""
        entity_id_param = request.query_params.get("entity_id")
        if entity_id_param is None:
            return JSONResponse(
                {"error": "entity_id query parameter is required."},
                status_code=400,
            )
        try:
            entity_id = int(entity_id_param)
        except (ValueError, TypeError):
            return JSONResponse(
                {"error": "entity_id must be an integer."},
                status_code=400,
            )

        try:
            result = await anyio.to_thread.run_sync(
                lambda: _get_wiki_data(conn, entity_id)
            )
        except Exception:
            logger.exception("Error in wiki_api")
            return JSONResponse(
                {"error": "Could not load entity detail."},
                status_code=500,
            )
        return JSONResponse(result)

    # ------------------------------------------------------------------
    # search_api
    # ------------------------------------------------------------------

    async def search_api(request: Request) -> JSONResponse:
        """GET /api/search?q=... — hybrid search over knowledge store."""
        q = request.query_params.get("q")
        if not q:
            return JSONResponse(
                {"error": "q query parameter is required."},
                status_code=400,
            )

        try:
            result = await anyio.to_thread.run_sync(
                lambda: _run_search(conn, config, q)
            )
        except Exception:
            logger.exception("Error in search_api")
            return JSONResponse(
                {"error": "Search failed."},
                status_code=500,
            )
        return JSONResponse(result)

    # ------------------------------------------------------------------
    # dashboard_api
    # ------------------------------------------------------------------

    async def dashboard_api(request: Request) -> JSONResponse:
        """GET /api/dashboard — coverage metrics and gap summary."""
        try:
            result = await anyio.to_thread.run_sync(
                lambda: _get_dashboard_data(conn)
            )
        except Exception:
            logger.exception("Error in dashboard_api")
            return JSONResponse(
                {"error": "Could not load dashboard data."},
                status_code=500,
            )
        return JSONResponse(result)

    # ------------------------------------------------------------------
    # export_api
    # ------------------------------------------------------------------

    async def export_api(request: Request) -> JSONResponse:
        """POST /api/export — run export for requested format/entity.

        Request body (JSON):
          {
            "format": "markdown|mermaid|json|ddl",  # optional, default all
            "entity_type": "table|procedure",        # optional, default table
            "entity_name": "optional entity name"    # optional, default all
          }
        """
        from db_wiki.export.runner import ALL_FORMATS, run_export

        try:
            body = await request.json()
        except Exception:
            body = {}

        fmt = body.get("format")
        entity_type = body.get("entity_type", "table")
        entity_name = body.get("entity_name") or None

        # Validate format if provided
        if fmt and fmt not in ALL_FORMATS:
            return JSONResponse(
                {"error": f"Invalid format '{fmt}'. Valid: {ALL_FORMATS}"},
                status_code=400,
            )

        formats = [fmt] if fmt else None
        # Derive store dir from the connection's database file path
        db_file = conn.execute("PRAGMA database_list").fetchone()[2]
        output_dir = Path(db_file).parent / "export" if db_file else Path(".db-wiki/export")

        try:
            results = await anyio.to_thread.run_sync(
                lambda: run_export(conn, output_dir, formats, entity_name, entity_type)
            )
        except Exception:
            logger.exception("Error in export_api")
            return JSONResponse(
                {"error": "Export failed."},
                status_code=500,
            )

        return JSONResponse({
            "status": "ok",
            "files_written": len(results),
            "paths": list(results.keys()),
        })

    return graph_api, wiki_api, search_api, dashboard_api, export_api


# ---------------------------------------------------------------------------
# Sync helper functions (run inside anyio thread pool)
# ---------------------------------------------------------------------------


def _full_graph(conn: sqlite3.Connection) -> dict:
    """Build nodes+edges for the full schema graph (initial load)."""
    nodes = []
    edges = []

    # Fetch all tables
    table_rows = conn.execute(
        "SELECT id, table_name, description FROM current_db_tables"
    ).fetchall()

    # Fetch gap node IDs (unresolved) for dashed-border styling
    gap_ids: set[int] = set()
    try:
        gap_rows = conn.execute(
            "SELECT entity_id FROM knowledge_gaps WHERE resolution IS NULL AND entity_type = 'table'"
        ).fetchall()
        gap_ids = {row[0] for row in gap_rows}
    except Exception:
        pass  # knowledge_gaps table may not exist yet

    for row in table_rows:
        node_id = row["id"]
        is_gap = node_id in gap_ids
        node: dict = {
            "id": f"t_{node_id}",
            "label": row["table_name"],
            "title": row["description"] or "",
            "group": "table",
            "confidence": 1.0,
            "opacity": 1.0,
            "is_gap": is_gap,
        }
        if is_gap:
            node["borderDashes"] = [6, 3]
        nodes.append(node)

    # Fetch all FK relationships
    rel_rows = conn.execute(
        "SELECT source_id, target_id, relationship_type FROM current_db_relationships"
    ).fetchall()
    for rel in rel_rows:
        edges.append({
            "from": f"t_{rel['source_id']}",
            "to": f"t_{rel['target_id']}",
            "label": rel["relationship_type"],
            "confidence": 1.0,
        })

    return {"nodes": nodes, "edges": edges}


def _bfs_subgraph(conn: sqlite3.Connection, node_id: int, depth: int) -> dict:
    """BFS expansion from a given node ID."""
    from db_wiki.graph.bfs import bfs_graph

    bfs_results = bfs_graph(conn, node_id, max_depth=depth)

    # Fetch gap ids for these nodes
    node_ids = [r["node_id"] for r in bfs_results]
    gap_ids: set[int] = set()
    if node_ids:
        try:
            placeholders = ",".join("?" * len(node_ids))
            gap_rows = conn.execute(
                f"SELECT entity_id FROM knowledge_gaps "
                f"WHERE resolution IS NULL AND entity_type = 'table' "
                f"AND entity_id IN ({placeholders})",
                node_ids,
            ).fetchall()
            gap_ids = {row[0] for row in gap_rows}
        except Exception:
            pass

    nodes = []
    seen_edges: set[tuple[int, int]] = set()
    edges = []

    for r in bfs_results:
        nid = r["node_id"]
        is_gap = nid in gap_ids

        # Look up table name
        table_row = conn.execute(
            "SELECT table_name, description FROM current_db_tables WHERE id = ?",
            (nid,),
        ).fetchone()
        label = table_row["table_name"] if table_row else f"#{nid}"
        title = (table_row["description"] or "") if table_row else ""

        node: dict = {
            "id": f"t_{nid}",
            "label": label,
            "title": title,
            "group": "table",
            "confidence": 1.0,
            "opacity": 1.0,
            "is_gap": is_gap,
        }
        if is_gap:
            node["borderDashes"] = [6, 3]
        nodes.append(node)

        # Add edge from path if not start node
        if len(r["path"]) >= 2:
            src = r["path"][-2]
            tgt = r["path"][-1]
            edge_key = (min(src, tgt), max(src, tgt))
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({
                    "from": f"t_{src}",
                    "to": f"t_{tgt}",
                    "label": r["edge_type"] or "",
                    "confidence": 1.0,
                })

    return {"nodes": nodes, "edges": edges}


def _get_wiki_data(conn: sqlite3.Connection, entity_id: int) -> dict:
    """Fetch wiki content and metadata for an entity."""
    from db_wiki.query.wiki import get_wiki_page

    # Determine entity type
    table_row = conn.execute(
        "SELECT id, table_name FROM current_db_tables WHERE id = ?",
        (entity_id,),
    ).fetchone()

    if table_row:
        entity_type = "table"
        name = table_row["table_name"]
    else:
        proc_row = conn.execute(
            "SELECT id, procedure_name FROM current_db_procedures WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if proc_row:
            entity_type = "procedure"
            name = proc_row["procedure_name"]
        else:
            return {
                "name": f"entity#{entity_id}",
                "type": "unknown",
                "l1_content": "",
                "l2_content": "",
                "confidence": 1.0,
                "gaps": [],
            }

    l1_content = get_wiki_page(conn, entity_type, entity_id, "L1")
    l2_content = get_wiki_page(conn, entity_type, entity_id, "L2")

    # Fetch gaps for this entity
    gaps = []
    try:
        gap_rows = conn.execute(
            "SELECT gap_type, description, severity FROM knowledge_gaps "
            "WHERE entity_type = ? AND entity_id = ? AND resolution IS NULL",
            (entity_type, entity_id),
        ).fetchall()
        gaps = [
            {"gap_type": g["gap_type"], "description": g["description"], "severity": g["severity"]}
            for g in gap_rows
        ]
    except Exception:
        pass

    return {
        "name": name,
        "type": entity_type,
        "l1_content": l1_content,
        "l2_content": l2_content,
        "confidence": 1.0,
        "gaps": gaps,
    }


def _run_search(conn: sqlite3.Connection, config: DBWikiConfig, q: str) -> dict:
    """Run hybrid search and enrich results with entity names."""
    from db_wiki.search.hybrid import hybrid_search

    raw_results = hybrid_search(conn, q, config.embedding, limit=20)
    results = []
    for entity_type, entity_id, score in raw_results:
        name = _lookup_entity_name(conn, entity_type, entity_id)
        results.append({
            "entity_id": entity_id,
            "name": name,
            "type": entity_type,
            "score": round(score, 4),
        })
    return {"results": results}


def _lookup_entity_name(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> str:
    """Look up a display name for an entity."""
    if entity_type == "table":
        row = conn.execute(
            "SELECT table_name FROM current_db_tables WHERE id = ?", (entity_id,)
        ).fetchone()
        return row["table_name"] if row else f"table#{entity_id}"
    elif entity_type == "procedure":
        row = conn.execute(
            "SELECT procedure_name FROM current_db_procedures WHERE id = ?", (entity_id,)
        ).fetchone()
        return row["procedure_name"] if row else f"procedure#{entity_id}"
    elif entity_type == "column":
        row = conn.execute(
            "SELECT column_name FROM current_db_columns WHERE id = ?", (entity_id,)
        ).fetchone()
        return row["column_name"] if row else f"column#{entity_id}"
    return f"{entity_type}#{entity_id}"


def _get_dashboard_data(conn: sqlite3.Connection) -> dict:
    """Query coverage metrics and gap summary for the dashboard."""
    # Total tables
    total_tables = conn.execute(
        "SELECT COUNT(*) FROM current_db_tables"
    ).fetchone()[0]

    # Total columns
    total_columns = conn.execute(
        "SELECT COUNT(*) FROM current_db_columns"
    ).fetchone()[0]

    # Gap counts
    gap_count = 0
    conflict_count = 0
    top_gaps = []
    try:
        gap_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_gaps WHERE resolution IS NULL"
        ).fetchone()[0]

        conflict_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_gaps WHERE resolution = 'conflict'"
        ).fetchone()[0]

        top_gap_rows = conn.execute(
            "SELECT gap_type, description, severity, attempts, last_attempted_at "
            "FROM knowledge_gaps WHERE resolution IS NULL "
            "ORDER BY severity DESC, attempts ASC "
            "LIMIT 10"
        ).fetchall()
        top_gaps = [
            {
                "gap_type": g["gap_type"],
                "description": g["description"],
                "severity": g["severity"],
                "attempts": g["attempts"],
                "last_attempted": g["last_attempted_at"],
            }
            for g in top_gap_rows
        ]
    except Exception:
        pass

    # Coverage: tables with confidence >= 0.5 (using wiki_pages as proxy)
    covered = 0
    try:
        covered = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM current_wiki_pages "
            "WHERE entity_type = 'table'"
        ).fetchone()[0]
    except Exception:
        pass

    coverage_pct = round((covered / total_tables * 100) if total_tables > 0 else 0.0, 1)

    return {
        "coverage_pct": coverage_pct,
        "total_tables": total_tables,
        "total_columns": total_columns,
        "gap_count": gap_count,
        "conflict_count": conflict_count,
        "top_gaps": top_gaps,
        "history": [],
    }
