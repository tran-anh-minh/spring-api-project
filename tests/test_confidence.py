"""Unit tests for the confidence management system.

Tests for:
  - decay_confidence: time-based confidence decay (D-13, D-15)
  - reinforce_confidence: evidence-based confidence increase (LEARN-09)
  - resolve_conflict: conflict resolution with SUPERSEDE/KEEP/SPLIT/ESCALATE (D-14, LEARN-07)
  - compute_sp_reliability: SP reliability scoring (D-17, LEARN-08)
  - count_independent_sources: source counting (D-16, LEARN-12)
"""

import sqlite3

import pytest

from db_wiki.core.schema import SCHEMA_SQL
from db_wiki.learning.schema_ext import LEARNING_SCHEMA_SQL


@pytest.fixture
def conn():
    """In-memory SQLite connection with full schema."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_SQL)
    c.executescript(LEARNING_SCHEMA_SQL)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# decay_confidence tests
# ---------------------------------------------------------------------------

class TestDecayConfidence:
    def test_decay_7_days_normal(self):
        """1%/week rate: 7 days => current * ~0.99 (within 0.001)"""
        from db_wiki.learning.confidence import decay_confidence

        result = decay_confidence(1.0, 7, is_human_confirmed=False, decay_weekly=0.01)
        # Compound decay: (1 - 0.01/7)^7 ≈ 0.99004, approximately 0.99
        assert abs(result - 0.99) < 0.001

    def test_decay_human_confirmed_slower(self):
        """0.5%/month rate for human-confirmed facts."""
        from db_wiki.learning.confidence import decay_confidence

        # 30 days at 0.5%/month = 0.5%/30 per day per month factor
        result_normal = decay_confidence(1.0, 30, is_human_confirmed=False, decay_weekly=0.01)
        result_confirmed = decay_confidence(1.0, 30, is_human_confirmed=True, decay_confirmed_monthly=0.005)
        # Confirmed should decay much less (slower rate)
        assert result_confirmed > result_normal

    def test_decay_never_below_zero(self):
        """Decay is floored at 0.0."""
        from db_wiki.learning.confidence import decay_confidence

        result = decay_confidence(0.001, 100_000, is_human_confirmed=False, decay_weekly=0.5)
        assert result == 0.0

    def test_decay_7_days_exact_rate(self):
        """7 days with rate_per_day = 0.01/7 => current * (1 - 0.01/7)^7 ~ current * 0.99004"""
        from db_wiki.learning.confidence import decay_confidence

        current = 0.8
        result = decay_confidence(current, 7, is_human_confirmed=False, decay_weekly=0.01)
        expected = current * ((1.0 - 0.01 / 7.0) ** 7)
        assert abs(result - expected) < 1e-9


# ---------------------------------------------------------------------------
# reinforce_confidence tests
# ---------------------------------------------------------------------------

class TestReinforceConfidence:
    def test_reinforce_basic(self):
        """reinforce_confidence(0.7, 0.1) returns 0.8"""
        from db_wiki.learning.confidence import reinforce_confidence

        result = reinforce_confidence(0.7, 0.1)
        assert abs(result - 0.8) < 1e-9

    def test_reinforce_capped_at_one(self):
        """reinforce_confidence(0.95, 0.1) returns 1.0 (capped)"""
        from db_wiki.learning.confidence import reinforce_confidence

        result = reinforce_confidence(0.95, 0.1)
        assert result == 1.0

    def test_reinforce_exactly_one(self):
        """reinforce_confidence(1.0, 0.0) returns 1.0"""
        from db_wiki.learning.confidence import reinforce_confidence

        result = reinforce_confidence(1.0, 0.0)
        assert result == 1.0


# ---------------------------------------------------------------------------
# resolve_conflict tests
# ---------------------------------------------------------------------------

class TestResolveConflict:
    def test_escalate_when_scores_too_close(self):
        """ESCALATE when score difference < threshold."""
        from db_wiki.learning.confidence import resolve_conflict

        # Equal facts => diff = 0 < 0.1 threshold => ESCALATE
        result, rationale = resolve_conflict(
            fact_a_conf=0.7, fact_a_sources=3, fact_a_ts=100,
            fact_b_conf=0.7, fact_b_sources=3, fact_b_ts=100,
            escalate_threshold=0.1,
        )
        assert result == "ESCALATE"
        assert "threshold" in rationale.lower() or "0.1" in rationale

    def test_supersede_when_clear_winner(self):
        """SUPERSEDE_B when fact A has clearly higher score."""
        from db_wiki.learning.confidence import resolve_conflict

        result, rationale = resolve_conflict(
            fact_a_conf=0.9, fact_a_sources=10, fact_a_ts=200,
            fact_b_conf=0.1, fact_b_sources=1, fact_b_ts=100,
            escalate_threshold=0.1,
        )
        assert result == "SUPERSEDE_B"
        assert "score" in rationale.lower() or "fact" in rationale.lower()

    def test_supersede_a_when_b_wins(self):
        """SUPERSEDE_A when fact B has clearly higher score."""
        from db_wiki.learning.confidence import resolve_conflict

        result, rationale = resolve_conflict(
            fact_a_conf=0.1, fact_a_sources=1, fact_a_ts=100,
            fact_b_conf=0.9, fact_b_sources=10, fact_b_ts=200,
            escalate_threshold=0.1,
        )
        assert result == "SUPERSEDE_A"

    def test_rationale_string_explains_scoring(self):
        """Rationale includes score values."""
        from db_wiki.learning.confidence import resolve_conflict

        result, rationale = resolve_conflict(
            fact_a_conf=0.9, fact_a_sources=10, fact_a_ts=200,
            fact_b_conf=0.1, fact_b_sources=1, fact_b_ts=100,
            escalate_threshold=0.1,
        )
        # Rationale should mention scores
        assert len(rationale) > 10

    def test_keep_when_different_contexts(self):
        """KEEP when both facts have different conditions and confidence >= 0.3."""
        from db_wiki.learning.confidence import resolve_conflict

        result, rationale = resolve_conflict(
            fact_a_conf=0.6, fact_a_sources=2, fact_a_ts=100,
            fact_b_conf=0.6, fact_b_sources=2, fact_b_ts=100,
            escalate_threshold=0.1,
            fact_a_context="status=active",
            fact_b_context="status=archived",
        )
        assert result == "KEEP"
        assert "active" in rationale or "archived" in rationale

    def test_split_when_partial_overlap(self):
        """SPLIT when facts apply to different sub-contexts."""
        from db_wiki.learning.confidence import resolve_conflict

        result, rationale = resolve_conflict(
            fact_a_conf=0.6, fact_a_sources=2, fact_a_ts=100,
            fact_b_conf=0.6, fact_b_sources=2, fact_b_ts=100,
            escalate_threshold=0.1,
            fact_a_context="region=north",
            fact_b_context="region=south",
        )
        # With equal contexts both present, KEEP or SPLIT are both valid
        # The plan says KEEP first then SPLIT - let's check KEEP applies here
        assert result in ("KEEP", "SPLIT")


# ---------------------------------------------------------------------------
# compute_sp_reliability tests
# ---------------------------------------------------------------------------

class TestComputeSpReliability:
    def _seed_procedure(self, conn, proc_id=1, procedure_name="sp_test", valid_from_ts=0):
        conn.execute(
            """INSERT INTO db_procedures
               (id, procedure_name, valid_from, valid_from_ts,
                recorded_at, recorded_at_ts)
               VALUES (?, ?, '2020-01-01', ?, '2020-01-01', ?)""",
            (proc_id, procedure_name, valid_from_ts, valid_from_ts),
        )

    def _seed_reliability(self, conn, proc_id=1, has_dynamic_sql=0, partial_ast=0, parse_quality=1.0):
        conn.execute(
            """INSERT INTO sp_reliability
               (procedure_id, has_dynamic_sql, partial_ast, parse_quality,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, ?, ?, '2020-01-01', 0, '2020-01-01', 0)""",
            (proc_id, has_dynamic_sql, partial_ast, parse_quality),
        )

    def test_baseline_when_no_special_conditions(self, conn):
        """compute_sp_reliability returns baseline ~0.5 with no dynamic SQL."""
        from db_wiki.learning.confidence import compute_sp_reliability

        now_ts = 60 * 86400  # 60 days from epoch
        self._seed_procedure(conn, valid_from_ts=0)
        self._seed_reliability(conn)

        result = compute_sp_reliability(conn, proc_id=1, now_ts=now_ts)
        # Baseline 0.5 + 0.1 (proc is 60 days old, valid_from 0 => (60 days - 0) < 30? No)
        # valid_from_ts=0, now_ts=60*86400 => diff = 60 days > 30 days => no +0.1
        # No callers => no additional score
        # Result should be 0.5
        assert abs(result - 0.5) < 0.01

    def test_dynamic_sql_penalty(self, conn):
        """Dynamic SQL deducts 0.2 from score."""
        from db_wiki.learning.confidence import compute_sp_reliability

        now_ts = 60 * 86400
        self._seed_procedure(conn, valid_from_ts=0)
        self._seed_reliability(conn, has_dynamic_sql=1)

        result = compute_sp_reliability(conn, proc_id=1, now_ts=now_ts)
        # 0.5 - 0.2 (dynamic SQL) = 0.3
        assert abs(result - 0.3) < 0.01

    def test_caller_bonus(self, conn):
        """Each caller adds 0.05 to score."""
        from db_wiki.learning.confidence import compute_sp_reliability

        now_ts = 60 * 86400
        # Seed callee
        self._seed_procedure(conn, proc_id=1, valid_from_ts=0)
        self._seed_reliability(conn)

        # Seed callers (2 callers => +0.10)
        for caller_id in [10, 11]:
            conn.execute(
                """INSERT INTO db_procedures
                   (id, procedure_name, valid_from, valid_from_ts,
                    recorded_at, recorded_at_ts)
                   VALUES (?, ?, '2020-01-01', 0, '2020-01-01', 0)""",
                (caller_id, f"sp_caller_{caller_id}"),
            )
            conn.execute(
                """INSERT INTO sp_call_chains
                   (caller_id, callee_id, callee_name_raw,
                    valid_from, valid_from_ts, recorded_at, recorded_at_ts)
                   VALUES (?, 1, 'sp_test', '2020-01-01', 0, '2020-01-01', 0)""",
                (caller_id,),
            )

        result = compute_sp_reliability(conn, proc_id=1, now_ts=now_ts)
        # 0.5 + min(0.25, 2 * 0.05) = 0.5 + 0.10 = 0.60
        assert abs(result - 0.60) < 0.01

    def test_no_row_returns_baseline(self, conn):
        """When no reliability row exists, return 0.5 baseline."""
        from db_wiki.learning.confidence import compute_sp_reliability

        # No rows seeded at all
        result = compute_sp_reliability(conn, proc_id=999, now_ts=1000)
        assert result == 0.5

    def test_clamped_to_zero_one(self, conn):
        """Result is always in [0.0, 1.0]."""
        from db_wiki.learning.confidence import compute_sp_reliability

        now_ts = 60 * 86400
        self._seed_procedure(conn, valid_from_ts=0)
        # Seed extreme dynamic SQL + partial AST
        self._seed_reliability(conn, has_dynamic_sql=1, partial_ast=1, parse_quality=0.1)

        result = compute_sp_reliability(conn, proc_id=1, now_ts=now_ts)
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# count_independent_sources tests
# ---------------------------------------------------------------------------

class TestCountIndependentSources:
    def test_count_enum_sources(self, conn):
        """count_independent_sources for enum_label counts DISTINCT source_procedure_id."""
        from db_wiki.learning.confidence import count_independent_sources

        # Insert two enum_values rows for same table.column from different SPs
        for i, sp_id in enumerate([10, 11]):
            conn.execute(
                """INSERT INTO enum_values
                   (table_name, column_name, enum_value, enum_label,
                    confidence, detection_method,
                    valid_from, valid_from_ts, recorded_at, recorded_at_ts,
                    source_procedure_id)
                   VALUES ('orders', 'status', ?, 'Label', 0.8, 'case_when',
                           '2020-01-01', 0, '2020-01-01', 0, ?)""",
                (str(i), sp_id),
            )

        count = count_independent_sources(conn, "column", "orders.status", "enum_label")
        assert count == 2

    def test_count_unknown_attribute_returns_one(self, conn):
        """Unknown attribute type returns 1 as default."""
        from db_wiki.learning.confidence import count_independent_sources

        count = count_independent_sources(conn, "column", "some.thing", "unknown_attr")
        assert count == 1
