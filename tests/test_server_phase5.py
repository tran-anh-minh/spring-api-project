"""Phase 5 Wave 0 test stubs for Phase 5 MCP tools (MCP-06).

All tests are marked xfail — they verify the contracts that the Phase 5
MCP tool implementation must satisfy.
"""
import inspect

import pytest


XFAIL_REASON = "Phase 5 Wave 0 stub — not yet implemented"


def _call_tool(tool_name: str, **kwargs):
    """Invoke a registered MCP tool by name and return its result."""
    from db_wiki.server.app import mcp

    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert tool_name in tools, f"Tool '{tool_name}' not registered"
    tool = tools[tool_name]
    fn = tool.fn
    if inspect.iscoroutinefunction(fn):
        import asyncio
        return asyncio.run(fn(**kwargs))
    return fn(**kwargs)


# ---------------------------------------------------------------------------
# MCP-06: lint tool
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_lint_tool():
    """MCP 'lint' tool returns a non-empty string. (MCP-06)"""
    result = _call_tool("lint")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# MCP-06: history tool
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_history_tool():
    """MCP 'history' tool returns a non-empty string. (MCP-06)"""
    result = _call_tool("history")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# MCP-06: export tool
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_export_tool():
    """MCP 'export' tool returns a string containing an export path. (MCP-06)"""
    result = _call_tool("export", format="markdown")
    assert isinstance(result, str)
    # The tool must report where the export was written
    assert len(result) > 0


# ---------------------------------------------------------------------------
# MCP-06: loop tool
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_loop_tool():
    """MCP 'loop' tool returns a learning loop summary string. (MCP-06)"""
    result = _call_tool("loop")
    assert isinstance(result, str)
    assert len(result) > 0
