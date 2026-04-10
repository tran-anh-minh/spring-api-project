"""Tests for confirm/teach logic (db_wiki.learning.confirm)."""

from __future__ import annotations

import sqlite3

import pytest

from db_wiki.learning.confirm import confirm_fact, teach_fact


def _create_test_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE enum_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL, column_name TEXT NOT NULL,
            enum_value TEXT NOT NULL, enum_label TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            detection_method TEXT NOT NULL, source_procedure_id INTEGER,
            valid_from TEXT NOT NULL, valid_from_ts INTEGER NOT NULL,
            valid_until TEXT, valid_until_ts INTEGER,
            recorded_at TEXT NOT NULL, recorded_at_ts INTEGER NOT NULL,
            invalidated_at TEXT, invalidated_at_ts INTEGER
        );
        CREATE VIEW current_enum_values AS
        SELECT * FROM enum_values WHERE valid_until IS NULL AND invalidated_at IS NULL;
    """)
    return conn


def _seed(conn, value="Active", label="Active", confidence=0.6):
    conn.execute(
        """INSERT INTO enum_values (table_name, column_name, enum_value, enum_label,
           confidence, detection_method, valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES ('Orders','Status',?,?,?,?,'2025-01-01',1000,'2025-01-01',1000)""",
        (value, label, confidence, "case_when"),
    )
    conn.commit()


class TestConfirmFact:
    def test_confirm_matching(self):
        conn = _create_test_db()
        _seed(conn)
        result = confirm_fact(conn, "column", "Orders.Status", "enum_label", "Active")
        assert "Confirmed" in result
        row = conn.execute("SELECT * FROM current_enum_values").fetchone()
        assert row["confidence"] == 1.0
        assert row["detection_method"] == "human_confirmed"

    def test_confirm_mismatch(self):
        conn = _create_test_db()
        _seed(conn)
        result = confirm_fact(conn, "column", "Orders.Status", "enum_label", "Enabled")
        assert "Value mismatch" in result

    def test_confirm_not_found(self):
        conn = _create_test_db()
        result = confirm_fact(conn, "column", "Orders.Status", "enum_label", "Active")
        assert "No existing fact" in result


class TestTeachFact:
    def test_teach_add(self):
        conn = _create_test_db()
        result = teach_fact(conn, "column", "Orders.Priority", "enum_label", "High")
        assert "Taught" in result
        row = conn.execute("SELECT * FROM current_enum_values WHERE column_name='Priority'").fetchone()
        assert row["confidence"] == 1.0

    def test_teach_reinforce(self):
        conn = _create_test_db()
        _seed(conn, confidence=0.5)
        result = teach_fact(conn, "column", "Orders.Status", "enum_label", "Active")
        assert "Taught" in result
        row = conn.execute("SELECT * FROM current_enum_values").fetchone()
        assert row["confidence"] == 1.0

    def test_teach_conflict_override(self):
        conn = _create_test_db()
        _seed(conn, value="Active", label="Active")
        result = teach_fact(conn, "column", "Orders.Status", "enum_label", "Enabled")
        assert "Taught" in result
        row = conn.execute("SELECT * FROM current_enum_values").fetchone()
        assert row["enum_label"] == "Enabled"
        assert row["confidence"] == 1.0
        old = conn.execute("SELECT * FROM enum_values WHERE invalidated_at IS NOT NULL").fetchall()
        assert len(old) == 1
