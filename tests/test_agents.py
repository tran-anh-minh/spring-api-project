"""Tests for learning loop agents (Collector, Research, Review).

Covers:
  AGENT-01: Research Agent works without LLM (heuristic mode)
  AGENT-02: Review Agent quality gate
  AGENT-04: Collector Agent falls back when no DB connection
  AGENT-05: Orchestrator stubs (awaiting Plan 05)
"""

from __future__ import annotations

import sqlite3

import pytest

from db_wiki.core.config import DBWikiConfig
from db_wiki.learning.agents.base import create_task_record, save_result_record
from db_wiki.learning.agents.collector import collect_evidence
from db_wiki.learning.agents.research import research_gap
from db_wiki.learning.agents.review import review_findings
from db_wiki.learning.models import AgentFindings, FindingItem, GapRecord


def _create_test_db() -> sqlite3.Connection:
    """Create in-memory SQLite with Phase 2 + Phase 3 schemas."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS db_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_from_ts INTEGER NOT NULL,
            valid_until TEXT,
            valid_until_ts INTEGER,
            recorded_at TEXT NOT NULL,
            recorded_at_ts INTEGER NOT NULL,
            invalidated_at TEXT,
            invalidated_at_ts INTEGER
        );
        CREATE VIEW IF NOT EXISTS current_db_tables AS
        SELECT * FROM db_tables WHERE valid_until IS NULL AND invalidated_at IS NULL;

        CREATE TABLE IF NOT EXISTS enum_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            enum_value TEXT NOT NULL,
            enum_label TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            detection_method TEXT NOT NULL,
            source_procedure_id INTEGER,
            valid_from TEXT NOT NULL,
            valid_from_ts INTEGER NOT NULL,
            valid_until TEXT,
            valid_until_ts INTEGER,
            recorded_at TEXT NOT NULL,
            recorded_at_ts INTEGER NOT NULL,
            invalidated_at TEXT,
            invalidated_at_ts INTEGER
        );
        CREATE VIEW IF NOT EXISTS current_enum_values AS
        SELECT * FROM enum_values WHERE valid_until IS NULL AND invalidated_at IS NULL;

        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gap_id INTEGER NOT NULL,
            agent_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            input_json TEXT,
            valid_from TEXT NOT NULL,
            valid_from_ts INTEGER NOT NULL,
            valid_until TEXT,
            valid_until_ts INTEGER,
            recorded_at TEXT NOT NULL,
            recorded_at_ts INTEGER NOT NULL,
            invalidated_at TEXT,
            invalidated_at_ts INTEGER
        );
        CREATE VIEW IF NOT EXISTS current_agent_tasks AS
        SELECT * FROM agent_tasks WHERE valid_until IS NULL AND invalidated_at IS NULL;

        CREATE TABLE IF NOT EXISTS agent_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            agent_type TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0,
            findings_json TEXT,
            rationale TEXT,
            approved INTEGER,
            valid_from TEXT NOT NULL,
            valid_from_ts INTEGER NOT NULL,
            valid_until TEXT,
            valid_until_ts INTEGER,
            recorded_at TEXT NOT NULL,
            recorded_at_ts INTEGER NOT NULL,
            invalidated_at TEXT,
            invalidated_at_ts INTEGER
        );
        CREATE VIEW IF NOT EXISTS current_agent_results AS
        SELECT * FROM agent_results WHERE valid_until IS NULL AND invalidated_at IS NULL;
    """)
    return conn


def _make_gap(**kwargs) -> GapRecord:
    defaults = dict(
        id=1,
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="Orders.Status",
        recorded_at_ts=0,
    )
    defaults.update(kwargs)
    return GapRecord(**defaults)


# ── Collector Agent ──────────────────────────────────────────────


class TestCollector:
    def test_no_db_returns_empty(self):
        """AGENT-04: Collector falls back when no DB connection."""
        config = DBWikiConfig()
        gap = _make_gap()
        result = collect_evidence(None, gap, config)
        assert len(result.items) == 0
        assert result.evidence_quality == 0.0
        assert "No live DB" in result.summary

    def test_unknown_gap_type_returns_empty(self):
        config = DBWikiConfig()
        config.database.connection_string = "fake"
        gap = _make_gap(gap_type="unknown_type")
        result = collect_evidence(None, gap, config)
        assert len(result.items) == 0
        assert "No sampling strategy" in result.summary


# ── Research Agent ───────────────────────────────────────────────


class TestResearch:
    def test_heuristic_unlabeled_enum(self):
        """AGENT-01: Research works without LLM for unlabeled_enum."""
        conn = _create_test_db()
        config = DBWikiConfig()  # No LLM configured = offline mode
        gap = _make_gap(gap_type="unlabeled_enum")
        evidence = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Active", confidence=0.5,
                ),
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Inactive", confidence=0.5,
                ),
            ],
            summary="2 samples",
            evidence_quality=0.5,
        )
        result = research_gap(conn, gap, evidence, config)
        assert len(result.items) == 2
        assert result.evidence_quality == 0.3  # heuristic quality
        assert all(item.attribute == "enum_label" for item in result.items)

    def test_heuristic_orphan_table(self):
        conn = _create_test_db()
        config = DBWikiConfig()
        gap = _make_gap(gap_type="orphan_table", entity_type="table", entity_name="OldArchive")
        evidence = AgentFindings(summary="no evidence", evidence_quality=0.0)
        result = research_gap(conn, gap, evidence, config)
        assert len(result.items) == 1
        assert "unused" in result.items[0].value.lower()

    def test_heuristic_unknown_type_empty(self):
        conn = _create_test_db()
        config = DBWikiConfig()
        gap = _make_gap(gap_type="exotic_unknown_type")
        evidence = AgentFindings(summary="no evidence", evidence_quality=0.0)
        result = research_gap(conn, gap, evidence, config)
        assert len(result.items) == 0
        assert "No heuristic" in result.summary


# ── Review Agent ─────────────────────────────────────────────────


class TestReview:
    def test_rejects_low_evidence_quality(self):
        """AGENT-02: Review rejects all when evidence_quality < 0.2."""
        conn = _create_test_db()
        config = DBWikiConfig()
        gap = _make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Active", confidence=0.5,
                ),
            ],
            summary="test",
            evidence_quality=0.1,  # Below 0.2 threshold
        )
        result = review_findings(conn, gap, findings, config)
        assert len(result.items) == 0
        assert "Rejected" in result.summary

    def test_filters_low_confidence_items(self):
        conn = _create_test_db()
        config = DBWikiConfig()
        gap = _make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Active", confidence=0.05,
                ),
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Inactive", confidence=0.5,
                ),
            ],
            summary="test",
            evidence_quality=0.5,
        )
        result = review_findings(conn, gap, findings, config)
        assert len(result.items) == 1
        assert result.items[0].value == "Inactive"

    def test_keeps_valid_items(self):
        conn = _create_test_db()
        config = DBWikiConfig()
        gap = _make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Active", confidence=0.6,
                ),
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Inactive", confidence=0.7,
                ),
            ],
            summary="test",
            evidence_quality=0.7,
        )
        result = review_findings(conn, gap, findings, config)
        assert len(result.items) == 2
        assert "Approved 2" in result.summary

    def test_rejects_empty_values(self):
        conn = _create_test_db()
        config = DBWikiConfig()
        gap = _make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="", confidence=0.5,
                ),
                FindingItem(
                    entity_type="column", entity_name="Orders.Status",
                    attribute="enum_label", value="Valid", confidence=0.5,
                ),
            ],
            summary="test",
            evidence_quality=0.5,
        )
        result = review_findings(conn, gap, findings, config)
        assert len(result.items) == 1
        assert result.items[0].value == "Valid"


# ── Base Infrastructure ──────────────────────────────────────────


class TestBaseInfra:
    def test_create_task_record(self):
        conn = _create_test_db()
        task_id = create_task_record(conn, 1, "research", {"query": "test"}, 1000, "2025-01-01")
        assert task_id > 0
        row = conn.execute("SELECT * FROM current_agent_tasks WHERE id = ?", (task_id,)).fetchone()
        assert row["status"] == "running"
        assert row["agent_type"] == "research"

    def test_save_result_record(self):
        conn = _create_test_db()
        task_id = create_task_record(conn, 1, "research", None, 1000, "2025-01-01")
        findings = AgentFindings(
            items=[FindingItem(entity_type="column", entity_name="T.C", attribute="enum_label", value="X", confidence=0.5)],
            summary="test",
        )
        result_id = save_result_record(conn, task_id, "research", findings, True, 1000, "2025-01-01")
        assert result_id > 0
        row = conn.execute("SELECT * FROM current_agent_results WHERE id = ?", (result_id,)).fetchone()
        assert row["success"] == 1
        assert row["approved"] == 1


# ── Orchestrator stubs (awaiting Plan 05) ────────────────────────


@pytest.mark.xfail(reason="Awaiting Plan 05 implementation")
class TestOrchestrator:
    def test_orchestrator_full_cycle(self):
        from db_wiki.learning.orchestrator import run_learning_loop

    def test_orchestrator_empty_store(self):
        from db_wiki.learning.orchestrator import run_learning_loop
