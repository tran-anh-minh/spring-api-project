"""Tests for Phase 4 MCP tool registration and structure.

Verifies all MCP-04 and MCP-05 tools are registered with correct signatures,
and that AppContext includes the QueryPipeline field.
"""
import dataclasses
import inspect
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


def _tool_names():
    from db_wiki.server.app import mcp

    return [t.name for t in mcp._tool_manager.list_tools()]


class TestToolRegistration:
    """All Phase 4 tools are registered in the MCP server."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "ask",
            "explain",
            "define_metric",
            "state_machine",
            "branch_analysis",
            "impact",
            "coverage",
            "data_quality",
            "forensics",
            "compare",
        ],
    )
    def test_tool_registered(self, tool_name):
        assert tool_name in _tool_names()

    def test_existing_tools_still_registered(self):
        names = _tool_names()
        for existing in ["ingest", "status", "search", "lineage", "sp_info", "discover", "confirm", "teach"]:
            assert existing in names, f"Existing tool '{existing}' missing after Phase 4 extension"


# ---------------------------------------------------------------------------
# AppContext extension
# ---------------------------------------------------------------------------


class TestAppContextExtension:
    def test_pipeline_field_exists(self):
        from db_wiki.server.app import AppContext

        fields = {f.name for f in dataclasses.fields(AppContext)}
        assert "pipeline" in fields

    def test_pipeline_default_none(self):
        from db_wiki.server.app import AppContext

        ctx = AppContext(store_path=Path("."), conn=MagicMock())
        assert ctx.pipeline is None


# ---------------------------------------------------------------------------
# Tool function signatures
# ---------------------------------------------------------------------------


class TestToolSignatures:
    def test_ask_has_execute_param(self):
        from db_wiki.server.app import ask

        sig = inspect.signature(ask)
        assert "execute" in sig.parameters
        assert sig.parameters["execute"].default is False

    def test_explain_has_entity_type_param(self):
        from db_wiki.server.app import explain

        sig = inspect.signature(explain)
        assert "entity_type" in sig.parameters
        assert sig.parameters["entity_type"].default == "table"

    def test_impact_has_max_depth_param(self):
        from db_wiki.server.app import impact

        sig = inspect.signature(impact)
        assert "max_depth" in sig.parameters
        assert sig.parameters["max_depth"].default == 3

    def test_forensics_has_direction_param(self):
        from db_wiki.server.app import forensics

        sig = inspect.signature(forensics)
        assert "direction" in sig.parameters
        assert sig.parameters["direction"].default == "both"

    def test_compare_has_two_entity_params(self):
        from db_wiki.server.app import compare

        sig = inspect.signature(compare)
        assert "entity_a" in sig.parameters
        assert "entity_b" in sig.parameters


# ---------------------------------------------------------------------------
# ask tool behaviour
# ---------------------------------------------------------------------------


class TestAskTool:
    @pytest.fixture()
    def mock_ctx(self):
        """Create a mock MCP Context with AppContext containing a pipeline."""
        from db_wiki.query.pipeline import QueryResult

        pipeline = MagicMock()
        pipeline.run.return_value = QueryResult(
            question="show orders",
            tier="LOOKUP",
            sql="SELECT * FROM Orders",
            attempts=1,
            from_cache=False,
            context_tokens=500,
        )

        app_ctx = MagicMock()
        app_ctx.pipeline = pipeline

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx
        return ctx

    @pytest.mark.asyncio
    async def test_ask_returns_sql(self, mock_ctx):
        from db_wiki.server.app import ask

        result = await ask("show orders", mock_ctx)
        assert "SELECT * FROM Orders" in result
        assert "LOOKUP" in result

    @pytest.mark.asyncio
    async def test_ask_no_pipeline(self):
        from db_wiki.server.app import ask

        app_ctx = MagicMock()
        app_ctx.pipeline = None
        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await ask("test", ctx)
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_ask_no_sql_generated(self, mock_ctx):
        from db_wiki.query.pipeline import QueryResult
        from db_wiki.server.app import ask

        mock_ctx.request_context.lifespan_context.pipeline.run.return_value = QueryResult(
            question="impossible query",
            tier="EXPERT",
            sql=None,
            attempts=3,
        )
        result = await ask("impossible query", mock_ctx)
        assert "Could not generate SQL" in result

    @pytest.mark.asyncio
    async def test_ask_with_validation_errors(self, mock_ctx):
        from db_wiki.query.pipeline import QueryResult
        from db_wiki.server.app import ask

        mock_ctx.request_context.lifespan_context.pipeline.run.return_value = QueryResult(
            question="test",
            tier="JOIN_REQUIRED",
            sql="SELECT x FROM y",
            validation_errors=["Unknown column x"],
            attempts=1,
        )
        result = await ask("test", mock_ctx)
        assert "Warnings" in result
        assert "Unknown column x" in result

    @pytest.mark.asyncio
    async def test_ask_with_execution_result(self, mock_ctx):
        from db_wiki.query.pipeline import QueryResult
        from db_wiki.server.app import ask

        mock_ctx.request_context.lifespan_context.pipeline.run.return_value = QueryResult(
            question="test",
            tier="LOOKUP",
            sql="SELECT 1",
            attempts=1,
            execution_result={"columns": ["val"], "rows": [[1]], "error": None},
        )
        result = await ask("test", mock_ctx, execute=True)
        assert "Results" in result
        assert "1 row(s)" in result


# ---------------------------------------------------------------------------
# explain tool behaviour
# ---------------------------------------------------------------------------


class TestExplainTool:
    @pytest.mark.asyncio
    async def test_explain_table_found(self):
        from db_wiki.server.app import explain

        app_ctx = MagicMock()
        app_ctx.conn.execute.return_value.fetchone.return_value = (1,)

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        with patch("db_wiki.query.wiki.generate_wiki_markdown", return_value="# Orders\nWiki content"):
            result = await explain("Orders", ctx)
            assert "Orders" in result

    @pytest.mark.asyncio
    async def test_explain_entity_not_found(self):
        from db_wiki.server.app import explain

        app_ctx = MagicMock()
        app_ctx.conn.execute.return_value.fetchone.return_value = None

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await explain("NonExistent", ctx)
        assert "not found" in result


# ---------------------------------------------------------------------------
# define_metric tool
# ---------------------------------------------------------------------------


class TestDefineMetricTool:
    @pytest.mark.asyncio
    async def test_define_metric_success(self):
        from db_wiki.server.app import define_metric

        app_ctx = MagicMock()
        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        with patch("db_wiki.query.resolver.define_metric", return_value=1):
            result = await define_metric("revenue", "SUM(amount)", "Orders,OrderItems", ctx)
            assert "defined successfully" in result

    @pytest.mark.asyncio
    async def test_define_metric_error(self):
        from db_wiki.server.app import define_metric

        app_ctx = MagicMock()
        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        with patch("db_wiki.query.resolver.define_metric", side_effect=ValueError("forbidden keyword")):
            result = await define_metric("bad", "DROP TABLE", "x", ctx)
            assert "Error" in result


# ---------------------------------------------------------------------------
# state_machine tool
# ---------------------------------------------------------------------------


class TestStateMachineTool:
    @pytest.mark.asyncio
    async def test_state_machine_returns_mermaid(self):
        from db_wiki.server.app import state_machine

        app_ctx = MagicMock()
        # First call: transitions, second call: enum labels
        app_ctx.conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[
                ("New", "Active", "sp_Activate"),
                ("Active", "Closed", "sp_Close"),
            ])),
            MagicMock(fetchall=MagicMock(return_value=[])),
        ]

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await state_machine("Orders", "Status", ctx)
        assert "mermaid" in result
        assert "stateDiagram" in result
        assert "New" in result
        assert "Active" in result

    @pytest.mark.asyncio
    async def test_state_machine_not_found(self):
        from db_wiki.server.app import state_machine

        app_ctx = MagicMock()
        app_ctx.conn.execute.return_value.fetchall.return_value = []

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await state_machine("NoTable", "NoCol", ctx)
        assert "No state transitions" in result


# ---------------------------------------------------------------------------
# branch_analysis tool
# ---------------------------------------------------------------------------


class TestBranchAnalysisTool:
    @pytest.mark.asyncio
    async def test_branch_analysis_returns_report(self):
        from db_wiki.server.app import branch_analysis

        app_ctx = MagicMock()
        # First call: proc lookup, second call: branches
        app_ctx.conn.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=(1,))),
            MagicMock(fetchall=MagicMock(return_value=[
                ("IF", "@status = 1", '["Orders"]', 0),
                ("ELSE", None, '["Audit"]', 0),
            ])),
        ]

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await branch_analysis("sp_Process", ctx)
        assert "Branch Analysis" in result
        assert "Branch 1" in result

    @pytest.mark.asyncio
    async def test_branch_analysis_proc_not_found(self):
        from db_wiki.server.app import branch_analysis

        app_ctx = MagicMock()
        app_ctx.conn.execute.return_value.fetchone.return_value = None

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await branch_analysis("NonExistent", ctx)
        assert "not found" in result


# ---------------------------------------------------------------------------
# impact tool
# ---------------------------------------------------------------------------


class TestImpactTool:
    @pytest.mark.asyncio
    async def test_impact_returns_affected_entities(self):
        from db_wiki.server.app import impact

        with patch("db_wiki.core.queries.find_entity_by_name", return_value=(1, "table")), \
             patch("db_wiki.graph.bfs.bfs_graph", return_value=[
                 {"node_id": 1, "depth": 0, "edge_type": None},
                 {"node_id": 2, "depth": 1, "edge_type": "fk_declared"},
                 {"node_id": 3, "depth": 2, "edge_type": "reads_from"},
             ]), \
             patch("db_wiki.core.queries.lookup_entity_name", side_effect=lambda conn, nid: f"entity_{nid}"):

            app_ctx = MagicMock()
            ctx = MagicMock()
            ctx.request_context.lifespan_context = app_ctx

            result = await impact("Orders", ctx)
            assert "Impact Analysis" in result
            assert "entity_2" in result
            assert "entity_3" in result

    @pytest.mark.asyncio
    async def test_impact_entity_not_found(self):
        from db_wiki.server.app import impact

        with patch("db_wiki.core.queries.find_entity_by_name", return_value=(None, None)):
            ctx = MagicMock()
            ctx.request_context.lifespan_context = MagicMock()
            result = await impact("NonExistent", ctx)
            assert "not found" in result


# ---------------------------------------------------------------------------
# coverage tool
# ---------------------------------------------------------------------------


class TestCoverageTool:
    @pytest.mark.asyncio
    async def test_coverage_returns_report(self):
        from db_wiki.server.app import coverage

        app_ctx = MagicMock()
        # Mock sequential execute calls
        app_ctx.conn.execute.return_value.fetchone.return_value = (10,)

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await coverage(ctx)
        assert "Knowledge Coverage" in result
        assert "Tables" in result


# ---------------------------------------------------------------------------
# data_quality tool
# ---------------------------------------------------------------------------


class TestDataQualityTool:
    @pytest.mark.asyncio
    async def test_data_quality_returns_report(self):
        from db_wiki.server.app import data_quality

        app_ctx = MagicMock()
        app_ctx.conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[("high", 3), ("medium", 5)])),
            MagicMock(fetchone=MagicMock(return_value=(2,))),
        ]

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await data_quality(ctx)
        assert "Data Quality" in result
        assert "Open Gaps" in result


# ---------------------------------------------------------------------------
# forensics tool
# ---------------------------------------------------------------------------


class TestForensicsTool:
    @pytest.mark.asyncio
    async def test_forensics_returns_data_flow(self):
        from db_wiki.server.app import forensics

        with patch("db_wiki.core.queries.find_entity_by_name", return_value=(1, "table")), \
             patch("db_wiki.graph.bfs.bfs_graph", return_value=[
                 {"node_id": 1, "depth": 0, "edge_type": None},
                 {"node_id": 2, "depth": 1, "edge_type": "reads_from"},
                 {"node_id": 3, "depth": 1, "edge_type": "writes_to"},
             ]), \
             patch("db_wiki.core.queries.lookup_entity_name", side_effect=lambda conn, nid: f"entity_{nid}"):

            ctx = MagicMock()
            ctx.request_context.lifespan_context = MagicMock()

            result = await forensics("Orders", ctx)
            assert "Data Forensics" in result

    @pytest.mark.asyncio
    async def test_forensics_entity_not_found(self):
        from db_wiki.server.app import forensics

        with patch("db_wiki.core.queries.find_entity_by_name", return_value=(None, None)):
            ctx = MagicMock()
            ctx.request_context.lifespan_context = MagicMock()
            result = await forensics("NonExistent", ctx)
            assert "not found" in result


# ---------------------------------------------------------------------------
# compare tool
# ---------------------------------------------------------------------------


class TestCompareTool:
    @pytest.mark.asyncio
    async def test_compare_two_tables(self):
        from db_wiki.server.app import compare

        app_ctx = MagicMock()

        def mock_execute(sql, params=None):
            m = MagicMock()
            if "current_db_tables" in sql:
                name = params[0] if params else ""
                if name == "Orders":
                    m.fetchone.return_value = (1, "Orders", "Order table")
                elif name == "Customers":
                    m.fetchone.return_value = (2, "Customers", "Customer table")
                else:
                    m.fetchone.return_value = None
            elif "COUNT" in sql and "current_db_columns" in sql:
                m.fetchone.return_value = (5,)
            elif "COUNT" in sql and "current_db_relationships" in sql:
                m.fetchone.return_value = (3,)
            elif "COUNT" in sql and "current_enum_values" in sql:
                m.fetchone.return_value = (1,)
            elif "column_name" in sql and "current_db_columns" in sql:
                m.fetchall.return_value = [("id",), ("name",), ("created_at",)]
            else:
                m.fetchone.return_value = (0,)
                m.fetchall.return_value = []
            return m

        app_ctx.conn.execute = mock_execute
        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await compare("Orders", "Customers", ctx)
        assert "Comparison" in result
        assert "Orders" in result
        assert "Customers" in result

    @pytest.mark.asyncio
    async def test_compare_entity_not_found(self):
        from db_wiki.server.app import compare

        app_ctx = MagicMock()
        app_ctx.conn.execute.return_value.fetchone.return_value = None

        ctx = MagicMock()
        ctx.request_context.lifespan_context = app_ctx

        result = await compare("Missing", "AlsoMissing", ctx)
        assert "not found" in result


# ---------------------------------------------------------------------------
# D-10: search enhancement
# ---------------------------------------------------------------------------


class TestSearchEnhancement:
    def test_search_tool_still_registered(self):
        assert "search" in _tool_names()

    def test_lineage_tool_still_registered(self):
        assert "lineage" in _tool_names()
