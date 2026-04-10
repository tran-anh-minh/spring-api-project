"""Tests for the Phase 3 learning loop schema extension and Pydantic models.

TDD RED phase: these tests define the expected behavior before implementation.
"""

import sqlite3

import pytest


class TestLearningSchemaSQL:
    """Test 1-5: LEARNING_SCHEMA_SQL constant content and structure."""

    def test_knowledge_gaps_table_exists_in_sql(self):
        """Test 1: LEARNING_SCHEMA_SQL contains CREATE TABLE IF NOT EXISTS knowledge_gaps."""
        from db_wiki.learning.schema_ext import LEARNING_SCHEMA_SQL

        assert "CREATE TABLE IF NOT EXISTS knowledge_gaps" in LEARNING_SCHEMA_SQL

    def test_agent_tasks_table_exists_in_sql(self):
        """Test 2: LEARNING_SCHEMA_SQL contains CREATE TABLE IF NOT EXISTS agent_tasks with gap_id FK."""
        from db_wiki.learning.schema_ext import LEARNING_SCHEMA_SQL

        assert "CREATE TABLE IF NOT EXISTS agent_tasks" in LEARNING_SCHEMA_SQL
        assert "gap_id" in LEARNING_SCHEMA_SQL

    def test_agent_results_table_exists_in_sql(self):
        """Test 3: LEARNING_SCHEMA_SQL contains CREATE TABLE IF NOT EXISTS agent_results with task_id FK."""
        from db_wiki.learning.schema_ext import LEARNING_SCHEMA_SQL

        assert "CREATE TABLE IF NOT EXISTS agent_results" in LEARNING_SCHEMA_SQL
        assert "task_id" in LEARNING_SCHEMA_SQL

    def test_all_tables_have_bitemporal_columns(self):
        """Test 4: All three tables have bi-temporal columns."""
        from db_wiki.learning.schema_ext import LEARNING_SCHEMA_SQL

        for col in [
            "valid_from",
            "valid_from_ts",
            "valid_until",
            "valid_until_ts",
            "recorded_at",
            "recorded_at_ts",
            "invalidated_at",
            "invalidated_at_ts",
        ]:
            assert col in LEARNING_SCHEMA_SQL, f"Missing bi-temporal column: {col}"

    def test_views_filter_active_rows(self):
        """Test 5: current_* views filter WHERE valid_until IS NULL AND invalidated_at IS NULL."""
        from db_wiki.learning.schema_ext import LEARNING_SCHEMA_SQL

        assert "current_knowledge_gaps" in LEARNING_SCHEMA_SQL
        assert "current_agent_tasks" in LEARNING_SCHEMA_SQL
        assert "current_agent_results" in LEARNING_SCHEMA_SQL
        assert "valid_until IS NULL" in LEARNING_SCHEMA_SQL
        assert "invalidated_at IS NULL" in LEARNING_SCHEMA_SQL


class TestLearningModels:
    """Test 6-7: Pydantic models for the learning loop."""

    def test_gap_info_model_fields(self):
        """Test 6: GapInfo model has required fields with correct defaults."""
        from db_wiki.learning.models import GapInfo

        g = GapInfo(
            gap_type="missing_docs",
            entity_type="table",
            entity_name="orders",
        )
        assert g.gap_type == "missing_docs"
        assert g.entity_type == "table"
        assert g.entity_id is None
        assert g.entity_name == "orders"
        assert g.description is None
        assert g.severity == 0.5

    def test_update_op_enum_values(self):
        """Test 7: UpdateOp enum has ADD, REINFORCE, CONFLICT, NOOP values."""
        from db_wiki.learning.models import UpdateOp

        assert UpdateOp.ADD == "ADD"
        assert UpdateOp.REINFORCE == "REINFORCE"
        assert UpdateOp.CONFLICT == "CONFLICT"
        assert UpdateOp.NOOP == "NOOP"


class TestInitLearningSchema:
    """Test 8: init_learning_schema function."""

    def test_init_learning_schema_creates_tables_and_views(self):
        """Test 8: init_learning_schema(conn) creates all tables and views."""
        from db_wiki.learning.schema_ext import init_learning_schema

        conn = sqlite3.connect(":memory:")
        init_learning_schema(conn)

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "knowledge_gaps" in tables
        assert "agent_tasks" in tables
        assert "agent_results" in tables

        views = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            ).fetchall()
        }
        assert "current_knowledge_gaps" in views
        assert "current_agent_tasks" in views
        assert "current_agent_results" in views

        conn.close()

    def test_init_learning_schema_knowledge_gaps_columns(self):
        """knowledge_gaps table has all required columns including cooldown and attempt fields."""
        from db_wiki.learning.schema_ext import init_learning_schema

        conn = sqlite3.connect(":memory:")
        init_learning_schema(conn)

        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(knowledge_gaps)").fetchall()
        }
        required = {
            "id", "gap_type", "entity_type", "entity_id", "entity_name",
            "description", "severity", "priority_score", "status",
            "attempt_count", "cooldown_until", "cooldown_until_ts",
            "last_attempt_at", "last_attempt_at_ts", "resolution_notes",
            "human_confirmed",
            "valid_from", "valid_from_ts", "valid_until", "valid_until_ts",
            "recorded_at", "recorded_at_ts", "invalidated_at", "invalidated_at_ts",
        }
        missing = required - cols
        assert not missing, f"Missing columns in knowledge_gaps: {missing}"

        conn.close()
