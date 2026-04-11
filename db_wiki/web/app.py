"""Starlette web application for the db-wiki knowledge UI (Plan 05-01).

Creates a Starlette instance with:
- JSON API routes (mounted before static files to avoid shadowing)
- StaticFiles serving db_wiki/web/static/ at /
- html=True so / serves index.html automatically

Usage:
    from pathlib import Path
    from db_wiki.web.app import create_web_app
    from db_wiki.core.config import load_config

    config = load_config(Path(".db-wiki"))
    app = create_web_app(Path(".db-wiki/db.sqlite"), config)
    # Pass app to uvicorn.run(app, host=config.web.host, port=config.web.port)
"""
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from db_wiki.core.config import DBWikiConfig
from db_wiki.core.store import open_store
from db_wiki.web.routes import make_routes


def create_web_app(db_path: Path, config: DBWikiConfig) -> Starlette:
    """Create and return the Starlette web application.

    Opens its own SQLite connection (thread-safe per RESEARCH pitfall 1).
    API routes are declared before the static file mount so they are matched
    first and never shadowed by the catch-all StaticFiles handler
    (RESEARCH pitfall 2).

    Args:
        db_path: Path to the SQLite knowledge store file.
        config: Loaded DBWikiConfig instance.

    Returns:
        A configured Starlette application ready to pass to uvicorn.run().
    """
    conn = open_store(db_path)

    graph_api, wiki_api, search_api, dashboard_api, export_api = make_routes(conn, config)

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    routes = [
        Route("/api/graph", graph_api),
        Route("/api/wiki", wiki_api),
        Route("/api/search", search_api),
        Route("/api/dashboard", dashboard_api),
        Route("/api/export", export_api, methods=["POST"]),
        Mount("/", StaticFiles(directory=str(static_dir), html=True)),
    ]

    return Starlette(routes=routes)
