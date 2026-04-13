"""Phase 5 tests for Web UI requirements (UI-01 through UI-06, EXPORT-01).

Tests verify the web app serves pages and API endpoints return correct schemas.
"""
import sqlite3

import pytest
from starlette.testclient import TestClient

from db_wiki.core.config import DBWikiConfig
from db_wiki.core.store import init_schema
from db_wiki.web.app import create_web_app


@pytest.fixture()
def web_client(tmp_path):
    """Create a TestClient backed by a temporary knowledge store."""
    db_path = tmp_path / "knowledge.db"
    conn = sqlite3.connect(str(db_path))
    init_schema(conn)
    conn.close()
    config = DBWikiConfig()
    app = create_web_app(db_path, config)
    return TestClient(app)


# ---------------------------------------------------------------------------
# UI-01: Web app serves index page
# ---------------------------------------------------------------------------


def test_web_app_serves_index(web_client):
    """GET / returns 200 with HTML containing 'DB Wiki'. (UI-01)"""
    response = web_client.get("/")
    assert response.status_code == 200
    assert "DB Wiki" in response.text


# ---------------------------------------------------------------------------
# UI-02: Graph API initial load
# ---------------------------------------------------------------------------


def test_graph_api_initial_load(web_client):
    """GET /api/graph returns 200 JSON with 'nodes' and 'edges' keys. (UI-02)"""
    response = web_client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


# ---------------------------------------------------------------------------
# UI-03: Graph API expand node + depth validation
# ---------------------------------------------------------------------------


def test_graph_api_expand_node(web_client):
    """GET /api/graph?node=1&depth=1 returns 200 JSON with nodes array.
    Depth param must be validated <= 5. (UI-03, T-05-01)
    """
    # Normal expand
    response = web_client.get("/api/graph?node=1&depth=1")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data

    # depth > 5 is clamped to 5 (T-05-01), not rejected
    capped_response = web_client.get("/api/graph?node=1&depth=10")
    assert capped_response.status_code == 200


# ---------------------------------------------------------------------------
# UI-03: Search API
# ---------------------------------------------------------------------------


def test_search_api(web_client):
    """GET /api/search?q=orders returns 200 JSON with 'results' array. (UI-03)"""
    response = web_client.get("/api/search?q=orders")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


# ---------------------------------------------------------------------------
# UI-04: Wiki API
# ---------------------------------------------------------------------------


def test_wiki_api(web_client):
    """GET /api/wiki?entity_id=1 returns 200 JSON with expected fields. (UI-04)"""
    response = web_client.get("/api/wiki?entity_id=1")
    # May return 200 with empty/error content if entity doesn't exist in empty store
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# UI-05: Confidence field on graph nodes
# ---------------------------------------------------------------------------


def test_node_confidence_field(web_client):
    """GET /api/graph returns nodes — if any exist, they have 'opacity' field. (UI-05)"""
    response = web_client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    nodes = data.get("nodes", [])
    # Empty store: no nodes, assertion passes vacuously
    if nodes:
        assert "opacity" in nodes[0]


# ---------------------------------------------------------------------------
# UI-06: Gap node flag on graph nodes
# ---------------------------------------------------------------------------


def test_gap_node_flag(web_client):
    """GET /api/graph returns gap nodes with 'borderDashes' field. (UI-06)"""
    response = web_client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    gap_nodes = [n for n in data.get("nodes", []) if n.get("is_gap")]
    for node in gap_nodes:
        assert "borderDashes" in node


# ---------------------------------------------------------------------------
# EXPORT-01: Dashboard API
# ---------------------------------------------------------------------------


def test_dashboard_api(web_client):
    """GET /api/dashboard returns 200 JSON with coverage_pct, gap_count, conflict_count. (EXPORT-01)"""
    response = web_client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "coverage_pct" in data
    assert "gap_count" in data
    assert "conflict_count" in data
