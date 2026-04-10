"""Tests for the 4-operation update pipeline (db_wiki.learning.pipeline).

Covers classify_update, apply_findings, mark_gap_resolved, and bump_attempt_count
with in-memory SQLite databases that include Phase 2 + Phase 3 schemas.
"""

from __future__ import annotations

import sqlite3

import pytest

from db_wiki.learning.models import AgentFindings, FindingItem, GapRecord, UpdateOp
from db_wiki.learning.pipeline import (
    apply_findings,
    bump_attempt_count,
    classify_update,
    find_existing_fact,
    mark_gap_resolved,
)


def _create_test_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with Phase 2 + Phase 3 tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Phase 2 tables (minimal for pipeline tests)
    conn.executescript("""
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
        SELECT * FROM enum_values
        WHERE valid_until IS NULL AND invalidated_at IS NULL;

        CREATE TABLE IF NOT EXISTS bitmask_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            bit_position INTEGER NOT NULL,
            bit_label TEXT,
            confidence REAL NOT NULL DEFAULT 0.3,
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
        CREATE VIEW IF NOT EXISTS current_bitmask_definitions AS
        SELECT * FROM bitmask_definitions
        WHERE valid_until IS NULL AND invalidated_at IS NULL;

        CREATE TABLE IF NOT EXISTS column_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            alias TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5,
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
        CREATE VIEW IF NOT EXISTS current_column_aliases AS
        SELECT * FROM column_aliases
        WHERE valid_until IS NULL AND invalidated_at IS NULL;

        CREATE TABLE IF NOT EXISTS knowledge_gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gap_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            entity_name TEXT NOT NULL,
            description TEXT,
            severity REAL NOT NULL DEFAULT 0.5,
            priority_score REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'open',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            cooldown_until TEXT,
            cooldown_until_ts INTEGER,
            last_attempt_at TEXT,
            last_attempt_at_ts INTEGER,
            resolution_notes TEXT,
            human_confirmed INTEGER NOT NULL DEFAULT 0,
            valid_from TEXT NOT NULL,
            valid_from_ts INTEGER NOT NULL,
            valid_until TEXT,
            valid_until_ts INTEGER,
            recorded_at TEXT NOT NULL,
            recorded_at_ts INTEGER NOT NULL,
            invalidated_at TEXT,
            invalidated_at_ts INTEGER
        );
        CREATE VIEW IF NOT EXISTS current_knowledge_gaps AS
        SELECT * FROM knowledge_gaps
        WHERE valid_until IS NULL AND invalidated_at IS NULL;
    """)
    return conn


def _seed_enum_row(
    conn: sqlite3.Connection,
    table: str = "Orders",
    column: str = "Status",
    value: str = "Active",
    label: str = "Active",
    confidence: float = 0.6,
    ts: int = 1000,
) -> int:
    """Insert a test enum_values row and return its id."""
    cur = conn.execute(
        """INSERT INTO enum_values
           (table_name, column_name, enum_value, enum_label,
            confidence, detection_method, source_procedure_id,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?,
                   '2025-01-01', ?, '2025-01-01', ?)""",
        (table, column, value, label, confidence, "case_when", None, ts, ts),
    )
    conn.commit()
    return cur.lastrowid


def _seed_gap(
    conn: sqlite3.Connection,
    gap_type: str = "unlabeled_enum",
    entity_type: str = "column",
    entity_name: str = "Orders.Status",
    status: str = "open",
    attempt_count: int = 0,
    ts: int = 1000,
) -> int:
    """Insert a test knowledge_gaps row and return its id."""
    cur = conn.execute(
        """INSERT INTO knowledge_gaps
           (gap_type, entity_type, entity_name, status, attempt_count,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?,
                   '2025-01-01', ?, '2025-01-01', ?)""",
        (gap_type, entity_type, entity_name, status, attempt_count, ts, ts),
    )
    conn.commit()
    return cur.lastrowid


# ── find_existing_fact ───────────────────────────────────────────


class TestFindExistingFact:
    def test_finds_enum_label(self):
        conn = _create_test_db()
        _seed_enum_row(conn)
        result = find_existing_fact(conn, "column", "Orders.Status", "enum_label")
        assert result is not None
        assert result["value"] == "Active"
        assert result["confidence"] == 0.6

    def test_returns_none_for_missing(self):
        conn = _create_test_db()
        result = find_existing_fact(conn, "column", "Orders.Status", "enum_label")
        assert result is None

    def test_returns_none_for_unknown_attribute(self):
        conn = _create_test_db()
        result = find_existing_fact(conn, "column", "Orders.Status", "unknown_attr")
        assert result is None


# ── classify_update ──────────────────────────────────────────────


class TestClassifyUpdate:
    def test_add_when_no_existing(self):
        conn = _create_test_db()
        op, existing = classify_update(
            conn, "column", "Orders.Status", "enum_label", "Active", 0.7,
        )
        assert op == UpdateOp.ADD
        assert existing is None

    def test_reinforce_when_same_value_different_confidence(self):
        conn = _create_test_db()
        _seed_enum_row(conn, confidence=0.6)
        op, existing = classify_update(
            conn, "column", "Orders.Status", "enum_label", "Active", 0.8,
        )
        assert op == UpdateOp.REINFORCE
        assert existing is not None
        assert existing["confidence"] == 0.6

    def test_conflict_when_different_value(self):
        conn = _create_test_db()
        _seed_enum_row(conn, label="Active", value="Active")
        op, existing = classify_update(
            conn, "column", "Orders.Status", "enum_label", "Enabled", 0.7,
        )
        assert op == UpdateOp.CONFLICT
        assert existing is not None

    def test_noop_when_same_value_similar_confidence(self):
        conn = _create_test_db()
        _seed_enum_row(conn, confidence=0.7)
        op, existing = classify_update(
            conn, "column", "Orders.Status", "enum_label", "Active", 0.72,
        )
        assert op == UpdateOp.NOOP
        assert existing is not None


# ── apply_findings ───────────────────────────────────────────────


class TestApplyFindings:
    def _make_gap(self, gap_id: int = 1) -> GapRecord:
        return GapRecord(
            id=gap_id,
            gap_type="unlabeled_enum",
            entity_type="column",
            entity_name="Orders.Status",
        )

    def test_add_inserts_new_row(self):
        conn = _create_test_db()
        gap = self._make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column",
                    entity_name="Orders.Priority",
                    attribute="enum_label",
                    value="High",
                    confidence=0.7,
                )
            ]
        )
        results = apply_findings(conn, gap, findings, 2000, "2025-02-01")
        assert results["add"] == 1

        row = conn.execute(
            "SELECT * FROM current_enum_values WHERE table_name='Orders' AND column_name='Priority'"
        ).fetchone()
        assert row is not None
        assert row["enum_label"] == "High"
        assert row["confidence"] == 0.7
        assert row["valid_from_ts"] == 2000

    def test_reinforce_updates_confidence(self):
        conn = _create_test_db()
        _seed_enum_row(conn, confidence=0.6)
        gap = self._make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column",
                    entity_name="Orders.Status",
                    attribute="enum_label",
                    value="Active",
                    confidence=0.8,
                )
            ]
        )
        results = apply_findings(conn, gap, findings, 2000, "2025-02-01")
        assert results["reinforce"] == 1

        # Old row should be invalidated
        old_rows = conn.execute(
            "SELECT * FROM enum_values WHERE invalidated_at IS NOT NULL"
        ).fetchall()
        assert len(old_rows) == 1

        # New row should have reinforced confidence (0.6 + 0.1 = 0.7)
        new_row = conn.execute(
            "SELECT * FROM current_enum_values WHERE table_name='Orders' AND column_name='Status'"
        ).fetchone()
        assert new_row is not None
        assert new_row["confidence"] == pytest.approx(0.7, abs=0.01)

    def test_conflict_with_supersede(self):
        conn = _create_test_db()
        # Seed a low-confidence existing fact
        _seed_enum_row(conn, confidence=0.3, ts=100)
        gap = self._make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column",
                    entity_name="Orders.Status",
                    attribute="enum_label",
                    value="Enabled",
                    confidence=0.9,
                )
            ]
        )
        results = apply_findings(conn, gap, findings, 2000, "2025-02-01")
        assert results["conflict"] == 1

        # The new value should have replaced the old one
        row = conn.execute(
            "SELECT * FROM current_enum_values WHERE table_name='Orders' AND column_name='Status'"
        ).fetchone()
        assert row is not None
        assert row["enum_label"] == "Enabled"

    def test_noop_makes_no_changes(self):
        conn = _create_test_db()
        _seed_enum_row(conn, confidence=0.7)
        gap = self._make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column",
                    entity_name="Orders.Status",
                    attribute="enum_label",
                    value="Active",
                    confidence=0.72,
                )
            ]
        )
        results = apply_findings(conn, gap, findings, 2000, "2025-02-01")
        assert results["noop"] == 1

        # Only the original row should exist
        rows = conn.execute("SELECT * FROM enum_values").fetchall()
        assert len(rows) == 1

    def test_conflict_escalate_creates_gap(self):
        conn = _create_test_db()
        _seed_gap(conn)
        # Seed with similar confidence to trigger ESCALATE
        _seed_enum_row(conn, confidence=0.5, ts=1000)
        gap = self._make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column",
                    entity_name="Orders.Status",
                    attribute="enum_label",
                    value="Enabled",
                    confidence=0.5,
                )
            ]
        )
        results = apply_findings(conn, gap, findings, 1001, "2025-02-01")
        assert results["conflict"] == 1
        assert results["escalated"] == 1

        # An escalated_conflict gap should be created
        esc_gap = conn.execute(
            "SELECT * FROM current_knowledge_gaps WHERE gap_type = 'escalated_conflict'"
        ).fetchone()
        assert esc_gap is not None
        assert "Conflict" in esc_gap["description"]

    def test_round_trip_reinforce_integration(self):
        """Integration test: seed -> apply REINFORCE -> verify bi-temporal update."""
        conn = _create_test_db()
        _seed_enum_row(conn, confidence=0.6, ts=1000)

        gap = self._make_gap()
        findings = AgentFindings(
            items=[
                FindingItem(
                    entity_type="column",
                    entity_name="Orders.Status",
                    attribute="enum_label",
                    value="Active",
                    confidence=0.8,
                )
            ]
        )

        results = apply_findings(conn, gap, findings, 2000, "2025-02-01")
        assert results["reinforce"] == 1

        # Check bi-temporal: old row invalidated, new row current
        all_rows = conn.execute(
            "SELECT * FROM enum_values WHERE table_name='Orders' AND column_name='Status' ORDER BY id"
        ).fetchall()
        assert len(all_rows) == 2
        assert all_rows[0]["invalidated_at"] is not None  # old invalidated
        assert all_rows[1]["invalidated_at"] is None       # new is current
        assert all_rows[1]["confidence"] == pytest.approx(0.7, abs=0.01)


# ── mark_gap_resolved ───────────────────────────────────────────


class TestMarkGapResolved:
    def test_resolves_gap(self):
        conn = _create_test_db()
        gap_id = _seed_gap(conn)
        mark_gap_resolved(conn, gap_id, 2000, "2025-02-01", "Fixed by agent")

        # Original should be invalidated
        old = conn.execute(
            "SELECT * FROM knowledge_gaps WHERE id = ?", (gap_id,)
        ).fetchone()
        assert old["invalidated_at"] is not None

        # New resolved row should exist
        resolved = conn.execute(
            "SELECT * FROM current_knowledge_gaps WHERE status = 'resolved'"
        ).fetchone()
        assert resolved is not None
        assert resolved["resolution_notes"] == "Fixed by agent"

    def test_noop_for_missing_gap(self):
        conn = _create_test_db()
        mark_gap_resolved(conn, 999, 2000, "2025-02-01")
        # Should not raise


# ── bump_attempt_count ───────────────────────────────────────────


class TestBumpAttemptCount:
    def test_increments_count_with_cooldown(self):
        conn = _create_test_db()
        gap_id = _seed_gap(conn, attempt_count=0)
        bump_attempt_count(
            conn, gap_id,
            cooldown_hours=[1, 4, 24],
            max_attempts_before_permanent=5,
            now_ts=2000,
            now_iso="2025-02-01",
        )

        row = conn.execute(
            "SELECT * FROM current_knowledge_gaps"
        ).fetchone()
        assert row["attempt_count"] == 1
        # Cooldown should be 1 hour = 3600 seconds from now_ts
        assert row["cooldown_until_ts"] == 2000 + 3600

    def test_marks_permanent_after_max_attempts(self):
        conn = _create_test_db()
        gap_id = _seed_gap(conn, attempt_count=4)
        bump_attempt_count(
            conn, gap_id,
            cooldown_hours=[1, 4, 24],
            max_attempts_before_permanent=5,
            now_ts=2000,
            now_iso="2025-02-01",
        )

        row = conn.execute(
            "SELECT * FROM current_knowledge_gaps"
        ).fetchone()
        assert row["attempt_count"] == 5
        assert row["status"] == "permanent"
        assert row["cooldown_until_ts"] is None

    def test_escalating_cooldown(self):
        conn = _create_test_db()
        gap_id = _seed_gap(conn, attempt_count=1)
        bump_attempt_count(
            conn, gap_id,
            cooldown_hours=[1, 4, 24],
            max_attempts_before_permanent=5,
            now_ts=2000,
            now_iso="2025-02-01",
        )

        row = conn.execute(
            "SELECT * FROM current_knowledge_gaps"
        ).fetchone()
        assert row["attempt_count"] == 2
        # Second attempt uses cooldown_hours[1] = 4 hours
        assert row["cooldown_until_ts"] == 2000 + 4 * 3600

    def test_noop_for_missing_gap(self):
        conn = _create_test_db()
        bump_attempt_count(
            conn, 999,
            cooldown_hours=[1],
            max_attempts_before_permanent=5,
            now_ts=2000,
            now_iso="2025-02-01",
        )
        # Should not raise
