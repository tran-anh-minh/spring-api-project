"""Tests for Phase 4 CLI commands: ask, explain, define-metric, state-machine,
branch-analysis, impact, coverage, data-quality, forensics, compare (04-05).

Uses typer.testing.CliRunner. Commands are tested against in-memory stores with
sample data. Pipeline calls are mocked to avoid LLM dependency.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from db_wiki.cli.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now():
    now = datetime.now(timezone.utc)
    return now.isoformat(), int(now.timestamp())


@pytest.fixture
def store_phase4(tmp_path: Path) -> Path:
    """Create a knowledge store with Phase 4 sample data."""
    store = tmp_path / ".db-wiki"

    result = runner.invoke(app, ["init", "--store-path", str(store)])
    assert result.exit_code == 0, result.output

    db_path = store / "knowledge.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from db_wiki.core.store import init_schema
    from db_wiki.core.query_schema import init_query_schema

    init_schema(conn)
    init_query_schema(conn)

    now_iso, now_ts = _now()

    # Tables
    conn.execute(
        "INSERT INTO db_tables (table_name, schema_name, description, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?)",
        ("Orders", "dbo", "Order records", now_iso, now_ts, now_iso, now_ts),
    )
    orders_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO db_tables (table_name, schema_name, description, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?)",
        ("Customers", "dbo", "Customer records", now_iso, now_ts, now_iso, now_ts),
    )
    customers_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Columns for Orders
    for col_name, dtype, pk in [("OrderId", "INT", 1), ("CustomerId", "INT", 0), ("Status", "NVARCHAR", 0)]:
        conn.execute(
            "INSERT INTO db_columns (table_id, column_name, data_type, is_nullable, is_primary_key, "
            "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?,?,?)",
            (orders_id, col_name, dtype, 0, pk, now_iso, now_ts, now_iso, now_ts),
        )

    # Columns for Customers
    for col_name, dtype, pk in [("CustomerId", "INT", 1), ("Name", "NVARCHAR", 0)]:
        conn.execute(
            "INSERT INTO db_columns (table_id, column_name, data_type, is_nullable, is_primary_key, "
            "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?,?,?)",
            (customers_id, col_name, dtype, 0, pk, now_iso, now_ts, now_iso, now_ts),
        )

    # Procedure
    conn.execute(
        "INSERT INTO db_procedures (procedure_name, schema_name, description, body_hash, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?,?)",
        ("usp_ProcessOrder", "dbo", "Processes an order", "abc123", now_iso, now_ts, now_iso, now_ts),
    )
    proc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Relationship Orders -> Customers
    conn.execute(
        "INSERT INTO db_relationships (source_id, target_id, relationship_type, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?)",
        (orders_id, customers_id, "fk_declared", now_iso, now_ts, now_iso, now_ts),
    )

    # Procedure reads from Orders
    conn.execute(
        "INSERT INTO db_relationships (source_id, target_id, relationship_type, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?)",
        (proc_id, orders_id, "reads_from", now_iso, now_ts, now_iso, now_ts),
    )

    # SP branches
    conn.execute(
        "INSERT INTO sp_branches (procedure_id, branch_index, branch_type, condition_text, "
        "tables_touched_json, nesting_depth, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (proc_id, 0, "IF", "Status = 'New'", '["Orders"]', 1, now_iso, now_ts, now_iso, now_ts),
    )

    # SP reliability
    conn.execute(
        "INSERT INTO sp_reliability (procedure_id, parse_quality, is_degraded, has_dynamic_sql, "
        "partial_ast, has_cycle, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (proc_id, 0.95, 0, 0, 0, 0, now_iso, now_ts, now_iso, now_ts),
    )

    # State transitions
    for from_val, to_val in [("New", "Processing"), ("Processing", "Completed"), ("Processing", "Cancelled")]:
        conn.execute(
            "INSERT INTO state_transitions (table_name, column_name, from_value, to_value, "
            "confidence, source_procedure_id, "
            "valid_from, valid_from_ts, recorded_at, recorded_at_ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("Orders", "Status", from_val, to_val, 0.9, proc_id, now_iso, now_ts, now_iso, now_ts),
        )

    conn.commit()
    conn.close()
    return store


# ---------------------------------------------------------------------------
# Task 1: ask, explain, define-metric, state-machine, branch-analysis
# ---------------------------------------------------------------------------


class TestAskCommand:
    def test_ask_sql_only(self, store_phase4: Path):
        """ask --sql-only returns raw SQL."""
        mock_result = MagicMock()
        mock_result.sql = "SELECT * FROM Orders"
        mock_result.tier = "lookup"
        mock_result.attempts = 1
        mock_result.from_cache = False
        mock_result.validation_errors = []
        mock_result.execution_result = None

        with patch("db_wiki.query.pipeline.QueryPipeline") as MockPipeline:
            MockPipeline.return_value.run.return_value = mock_result
            result = runner.invoke(
                app,
                ["ask", "show orders", "--sql-only", "--store-path", str(store_phase4)],
            )

        assert result.exit_code == 0, result.output
        assert "SELECT * FROM Orders" in result.output

    def test_ask_json_output(self, store_phase4: Path):
        """ask --json returns valid JSON with expected keys."""
        mock_result = MagicMock()
        mock_result.question = "show orders"
        mock_result.sql = "SELECT * FROM Orders"
        mock_result.tier = "lookup"
        mock_result.attempts = 1
        mock_result.from_cache = False
        mock_result.validation_errors = []
        mock_result.execution_result = None

        with patch("db_wiki.query.pipeline.QueryPipeline") as MockPipeline:
            MockPipeline.return_value.run.return_value = mock_result
            result = runner.invoke(
                app,
                ["ask", "show orders", "--json", "--store-path", str(store_phase4)],
            )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "sql" in data
        assert "tier" in data
        assert "attempts" in data
        assert "from_cache" in data
        assert "validation_errors" in data

    def test_ask_default_output(self, store_phase4: Path):
        """ask default output includes SQL."""
        mock_result = MagicMock()
        mock_result.question = "show orders"
        mock_result.sql = "SELECT * FROM Orders"
        mock_result.tier = "lookup"
        mock_result.attempts = 1
        mock_result.from_cache = False
        mock_result.validation_errors = []
        mock_result.execution_result = None

        with patch("db_wiki.query.pipeline.QueryPipeline") as MockPipeline:
            MockPipeline.return_value.run.return_value = mock_result
            result = runner.invoke(
                app,
                ["ask", "show orders", "--store-path", str(store_phase4)],
            )

        assert result.exit_code == 0, result.output
        assert "Orders" in result.output

    def test_ask_no_sql_sql_only_exits_1(self, store_phase4: Path):
        """ask --sql-only exits 1 when no SQL generated."""
        mock_result = MagicMock()
        mock_result.sql = None
        mock_result.tier = "lookup"
        mock_result.attempts = 1
        mock_result.from_cache = False
        mock_result.validation_errors = []
        mock_result.execution_result = None

        with patch("db_wiki.query.pipeline.QueryPipeline") as MockPipeline:
            MockPipeline.return_value.run.return_value = mock_result
            result = runner.invoke(
                app,
                ["ask", "show orders", "--sql-only", "--store-path", str(store_phase4)],
            )

        assert result.exit_code == 1


class TestExplainCommand:
    def test_explain_orders(self, store_phase4: Path):
        """explain Orders returns wiki content with entity name."""
        result = runner.invoke(
            app,
            ["explain", "Orders", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        assert "Orders" in result.output

    def test_explain_json(self, store_phase4: Path):
        """explain --json returns JSON with content key."""
        result = runner.invoke(
            app,
            ["explain", "Orders", "--json", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "content" in data
        assert "Orders" in data["content"]

    def test_explain_not_found_exits_1(self, store_phase4: Path):
        """explain for unknown entity exits 1."""
        result = runner.invoke(
            app,
            ["explain", "NonExistentTable", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 1


class TestDefineMetricCommand:
    def test_define_metric_success(self, store_phase4: Path):
        """define-metric stores a metric and confirms success."""
        result = runner.invoke(
            app,
            [
                "define-metric",
                "revenue",
                "SUM(total_amount)",
                "--tables",
                "Orders",
                "--description",
                "Total revenue",
                "--store-path",
                str(store_phase4),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "revenue" in result.output

    def test_define_metric_invalid_sql_exits_1(self, store_phase4: Path):
        """define-metric rejects dangerous SQL keywords."""
        result = runner.invoke(
            app,
            [
                "define-metric",
                "bad",
                "DROP TABLE Orders",
                "--store-path",
                str(store_phase4),
            ],
        )
        assert result.exit_code == 1


class TestStateMachineCommand:
    def test_state_machine_mermaid(self, store_phase4: Path):
        """state-machine returns Mermaid stateDiagram-v2 output."""
        result = runner.invoke(
            app,
            ["state-machine", "Orders", "Status", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        assert "stateDiagram-v2" in result.output
        assert "New" in result.output
        assert "Processing" in result.output

    def test_state_machine_json(self, store_phase4: Path):
        """state-machine --json returns JSON with transitions list."""
        result = runner.invoke(
            app,
            ["state-machine", "Orders", "Status", "--json", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "transitions" in data
        assert len(data["transitions"]) >= 3

    def test_state_machine_no_data(self, store_phase4: Path):
        """state-machine prints message when no transitions found."""
        result = runner.invoke(
            app,
            ["state-machine", "Orders", "NoSuchColumn", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0
        assert "No state transitions" in result.output


class TestBranchAnalysisCommand:
    def test_branch_analysis_output(self, store_phase4: Path):
        """branch-analysis shows procedure name and branch count."""
        result = runner.invoke(
            app,
            ["branch-analysis", "usp_ProcessOrder", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        assert "usp_ProcessOrder" in result.output
        assert "IF" in result.output

    def test_branch_analysis_json(self, store_phase4: Path):
        """branch-analysis --json returns JSON with branch_count key."""
        result = runner.invoke(
            app,
            ["branch-analysis", "usp_ProcessOrder", "--json", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "branch_count" in data
        assert data["branch_count"] >= 1
        assert "branches" in data

    def test_branch_analysis_not_found(self, store_phase4: Path):
        """branch-analysis for unknown procedure exits 1."""
        result = runner.invoke(
            app,
            ["branch-analysis", "NonExistentProc", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Task 2: impact, coverage, data-quality, forensics, compare
# ---------------------------------------------------------------------------


class TestImpactCommand:
    def test_impact_orders(self, store_phase4: Path):
        """impact Orders returns affected entities."""
        result = runner.invoke(
            app,
            ["impact", "Orders", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        # Should show something (either table or a message)
        assert len(result.output) > 0

    def test_impact_json(self, store_phase4: Path):
        """impact --json returns JSON with affected list."""
        result = runner.invoke(
            app,
            ["impact", "Orders", "--json", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "entity" in data
        assert "affected" in data

    def test_impact_not_found(self, store_phase4: Path):
        """impact for unknown entity exits 1."""
        result = runner.invoke(
            app,
            ["impact", "NoSuchEntity", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 1


class TestCoverageCommand:
    def test_coverage_default(self, store_phase4: Path):
        """coverage shows table and procedure counts."""
        result = runner.invoke(app, ["coverage", "--store-path", str(store_phase4)])
        assert result.exit_code == 0, result.output
        # Should contain coverage info
        assert len(result.output) > 0

    def test_coverage_json(self, store_phase4: Path):
        """coverage --json returns JSON with tables/procedures/columns keys."""
        result = runner.invoke(
            app, ["coverage", "--json", "--store-path", str(store_phase4)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "tables" in data
        assert "procedures" in data
        assert "columns" in data
        assert data["tables"]["total"] >= 2
        assert data["procedures"]["total"] >= 1


class TestDataQualityCommand:
    def test_data_quality_default(self, store_phase4: Path):
        """data-quality returns a report."""
        result = runner.invoke(app, ["data-quality", "--store-path", str(store_phase4)])
        assert result.exit_code == 0, result.output
        assert len(result.output) > 0

    def test_data_quality_json(self, store_phase4: Path):
        """data-quality --json returns JSON with gaps_by_severity key."""
        result = runner.invoke(
            app, ["data-quality", "--json", "--store-path", str(store_phase4)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "gaps_by_severity" in data
        assert "low_confidence_columns" in data


class TestForensicsCommand:
    def test_forensics_both(self, store_phase4: Path):
        """forensics traces data flow in both directions."""
        result = runner.invoke(
            app,
            ["forensics", "Orders", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        assert "Orders" in result.output

    def test_forensics_upstream(self, store_phase4: Path):
        """forensics --direction upstream returns upstream trace."""
        result = runner.invoke(
            app,
            ["forensics", "Orders", "--direction", "upstream", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output

    def test_forensics_json(self, store_phase4: Path):
        """forensics --json returns JSON with flow key."""
        result = runner.invoke(
            app,
            ["forensics", "Orders", "--json", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "entity" in data
        assert "flow" in data
        assert "direction" in data

    def test_forensics_not_found(self, store_phase4: Path):
        """forensics for unknown entity exits 1."""
        result = runner.invoke(
            app,
            ["forensics", "NoSuchTable", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 1


class TestCompareCommand:
    def test_compare_two_tables(self, store_phase4: Path):
        """compare Orders Customers shows comparison."""
        result = runner.invoke(
            app,
            ["compare", "Orders", "Customers", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        assert "Orders" in result.output
        assert "Customers" in result.output

    def test_compare_json(self, store_phase4: Path):
        """compare --json returns JSON with entity_a, entity_b, shared_columns."""
        result = runner.invoke(
            app,
            ["compare", "Orders", "Customers", "--json", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "entity_a" in data
        assert "entity_b" in data
        assert "shared_columns" in data
        # CustomerId is shared
        assert "CustomerId" in data["shared_columns"]

    def test_compare_not_found_exits_1(self, store_phase4: Path):
        """compare exits 1 when first entity not found."""
        result = runner.invoke(
            app,
            ["compare", "NoSuch", "Orders", "--store-path", str(store_phase4)],
        )
        assert result.exit_code == 1
