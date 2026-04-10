"""Tests for the FastMCP server structure and tool registration.

NOTE: These tests verify registration and structure only — not full server start
(which requires stdio transport). All tests are synchronous structural checks.
"""
import dataclasses
import sqlite3
from pathlib import Path

import pytest


def test_mcp_instance_name():
    """FastMCP instance is created with name 'db-wiki'."""
    from db_wiki.server.app import mcp
    from mcp.server.fastmcp import FastMCP

    assert isinstance(mcp, FastMCP)
    assert mcp.name == "db-wiki"


def test_mcp_has_lifespan():
    """MCP server has a lifespan configured."""
    from db_wiki.server.app import mcp

    # FastMCP stores lifespan in settings
    assert mcp.settings.lifespan is not None


def test_ingest_tool_registered():
    """'ingest' tool is registered in the server's tool manager."""
    from db_wiki.server.app import mcp

    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "ingest" in tool_names


def test_status_tool_registered():
    """'status' tool is registered in the server's tool manager."""
    from db_wiki.server.app import mcp

    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "status" in tool_names


def test_app_context_fields():
    """AppContext dataclass has store_path and conn fields."""
    from db_wiki.server.app import AppContext

    assert dataclasses.is_dataclass(AppContext)
    fields = {f.name: f for f in dataclasses.fields(AppContext)}
    assert "store_path" in fields
    assert "conn" in fields
    assert fields["store_path"].type == Path
    assert fields["conn"].type == sqlite3.Connection


def test_main_exists_and_callable():
    """main() function exists and is callable."""
    from db_wiki.server.app import main

    assert callable(main)


def test_app_lifespan_exists():
    """app_lifespan async context manager is defined."""
    from db_wiki.server.app import app_lifespan
    import inspect

    assert inspect.isfunction(app_lifespan) or inspect.iscoroutinefunction(app_lifespan)
