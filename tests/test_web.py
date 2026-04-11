"""Phase 5 Wave 0 test stubs for Web UI requirements (UI-01 through UI-06).

All tests are marked xfail — they verify the contracts that the Phase 5 web
UI implementation must satisfy.  Running pytest on this file without the
implementation present produces xfail results, not errors.
"""
import pytest


XFAIL_REASON = "Phase 5 Wave 0 stub — not yet implemented"


# ---------------------------------------------------------------------------
# UI-01: Web app serves index page
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_web_app_serves_index():
    """GET / returns 200 with HTML containing 'DB Wiki'. (UI-01)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "DB Wiki" in response.text


# ---------------------------------------------------------------------------
# UI-02: Graph API initial load
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_graph_api_initial_load():
    """GET /api/graph returns 200 JSON with 'nodes' and 'edges' keys. (UI-02)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


# ---------------------------------------------------------------------------
# UI-03: Graph API expand node + depth validation
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_graph_api_expand_node():
    """GET /api/graph?node=1&depth=1 returns 200 JSON with nodes array.
    Depth param must be validated <= 5. (UI-03, T-05-01)
    """
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)

    # Normal expand
    response = client.get("/api/graph?node=1&depth=1")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data

    # depth > 5 must be rejected
    bad_response = client.get("/api/graph?node=1&depth=10")
    assert bad_response.status_code == 400


# ---------------------------------------------------------------------------
# UI-03: Search API
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_search_api():
    """GET /api/search?q=orders returns 200 JSON with 'results' array. (UI-03)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/api/search?q=orders")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


# ---------------------------------------------------------------------------
# UI-04: Wiki API
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_wiki_api():
    """GET /api/wiki?entity_id=1 returns 200 JSON with name, type, l1_content. (UI-04)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/api/wiki?entity_id=1")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "type" in data
    assert "l1_content" in data


# ---------------------------------------------------------------------------
# UI-05: Confidence field on graph nodes
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_node_confidence_field():
    """GET /api/graph returns nodes with 'opacity' field present. (UI-05)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    nodes = data.get("nodes", [])
    assert len(nodes) >= 0  # may be empty store
    if nodes:
        assert "opacity" in nodes[0]


# ---------------------------------------------------------------------------
# UI-06: Gap node flag on graph nodes
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_gap_node_flag():
    """GET /api/graph returns gap nodes with 'borderDashes' field. (UI-06)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    # The graph serializer must include borderDashes on gap nodes;
    # we verify the API contract by checking the schema on any gap node.
    # If no gap nodes exist the assertion still passes (empty list case).
    gap_nodes = [n for n in data.get("nodes", []) if n.get("is_gap")]
    for node in gap_nodes:
        assert "borderDashes" in node


# ---------------------------------------------------------------------------
# EXPORT-01: Dashboard API
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_dashboard_api():
    """GET /api/dashboard returns 200 JSON with coverage_pct, gap_count, conflict_count. (EXPORT-01)"""
    from starlette.testclient import TestClient

    from db_wiki.web.app import create_web_app

    app = create_web_app()
    client = TestClient(app)
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "coverage_pct" in data
    assert "gap_count" in data
    assert "conflict_count" in data
