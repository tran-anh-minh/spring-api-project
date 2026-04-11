"""Phase 5 MCP tools tests (MCP-06).

Tests verify the contracts for Phase 5 MCP tool implementations:
lint, history, export_knowledge, loop.
"""
import inspect

import pytest


def _get_tool_fn(tool_name: str):
    """Get a registered MCP tool function by name."""
    from db_wiki.server.app import mcp

    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert tool_name in tools, f"Tool '{tool_name}' not registered"
    return tools[tool_name].fn


# ---------------------------------------------------------------------------
# MCP-06: lint tool registered
# ---------------------------------------------------------------------------


def test_lint_tool_registered():
    """MCP 'lint' tool is registered in the FastMCP server. (MCP-06)"""
    fn = _get_tool_fn("lint")
    assert callable(fn)
    assert inspect.iscoroutinefunction(fn)


# ---------------------------------------------------------------------------
# MCP-06: history tool registered
# ---------------------------------------------------------------------------


def test_history_tool_registered():
    """MCP 'history' tool is registered in the FastMCP server. (MCP-06)"""
    fn = _get_tool_fn("history")
    assert callable(fn)
    assert inspect.iscoroutinefunction(fn)


# ---------------------------------------------------------------------------
# MCP-06: export_knowledge tool registered
# ---------------------------------------------------------------------------


def test_export_knowledge_tool_registered():
    """MCP 'export_knowledge' tool is registered in the FastMCP server. (MCP-06)"""
    fn = _get_tool_fn("export_knowledge")
    assert callable(fn)
    assert inspect.iscoroutinefunction(fn)


# ---------------------------------------------------------------------------
# MCP-06: loop tool registered
# ---------------------------------------------------------------------------


def test_loop_tool_registered():
    """MCP 'loop' tool is registered in the FastMCP server. (MCP-06)"""
    fn = _get_tool_fn("loop")
    assert callable(fn)
    assert inspect.iscoroutinefunction(fn)
