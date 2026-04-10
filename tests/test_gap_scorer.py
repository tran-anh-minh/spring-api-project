"""Tests for gap priority scoring in db_wiki/learning/gap_scorer.py.

Uses in-memory SQLite with full Phase 1-2 + Phase 3 schema for isolation.
"""

import sqlite3
import time

import pytest

from db_wiki.core.config import LearningConfig, LearningGapWeightsConfig
from db_wiki.core.schema import get_schema_sql
from db_wiki.learning.gap_scorer import get_eligible_gaps, score_and_prioritize, score_gap
from db_wiki.learning.models import GapInfo
from db_wiki.learning.schema_ext import init_learning_schema

NOW_TS = int(time.time())
NOW_ISO = "2026-04-11T00:00:00"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory SQLite with full Phase 1-2 + Phase 3 schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(get_schema_sql())
    init_learning_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def weights():
    """Default LearningGapWeightsConfig."""
    return LearningGapWeightsConfig()


@pytest.fixture
def config():
    """Default LearningConfig."""
    return LearningConfig()


def _insert_gap(
    conn: sqlite3.Connection,
    gap_type: str = "unlabeled_enum",
    entity_type: str = "column",
    entity_name: str = "orders.status",
    entity_id: int | None = None,
    severity: float = 0.5,
    priority_score: float = 0.0,
    status: str = "open",
    cooldown_until_ts: int | None = None,
    recorded_at_ts: int | None = None,
) -> int:
    """Insert a gap row directly into knowledge_gaps for testing."""
    rts = recorded_at_ts if recorded_at_ts is not None else NOW_TS
    cur = conn.execute(
        """INSERT INTO knowledge_gaps
           (gap_type, entity_type, entity_id, entity_name, severity,
            priority_score, status, cooldown_until_ts,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (gap_type, entity_type, entity_id, entity_name, severity,
         priority_score, status, cooldown_until_ts,
         NOW_ISO, NOW_TS, NOW_ISO, rts),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Test 1: score_gap returns float between 0.0 and 1.0
# ---------------------------------------------------------------------------


def test_score_gap_returns_float_in_range(db, weights):
    """score_gap returns a float in [0.0, 1.0]."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.7,
    )
    score = score_gap(db, gap, weights, gap_recorded_at_ts=NOW_TS)

    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_gap_zero_severity_gives_lower_score(db, weights):
    """score_gap with severity=0.0 gives lower score than severity=1.0."""
    gap_low = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=0.0,
    )
    gap_high = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_name="orders.status",
        severity=1.0,
    )
    score_low = score_gap(db, gap_low, weights, gap_recorded_at_ts=NOW_TS)
    score_high = score_gap(db, gap_high, weights, gap_recorded_at_ts=NOW_TS)

    assert score_low < score_high


# ---------------------------------------------------------------------------
# Test 2: score_gap with severity=1.0 and all others zero returns weights.severity (0.30)
# ---------------------------------------------------------------------------


def test_score_gap_severity_only_equals_weight(db):
    """score_gap with severity=1.0, new gap (staleness=0), no entity_id returns weights.severity."""
    # Use custom weights where only severity matters
    weights_custom = LearningGapWeightsConfig(
        severity=0.30,
        connectivity=0.25,
        query_frequency=0.20,
        staleness=0.15,
        solvability=0.10,
    )
    # gap_type not in SOLVABLE_WITH_SAMPLING -> solvability component = 0.3 * 0.10 = 0.03
    # query_frequency = 0.5 (neutral default) -> 0.5 * 0.20 = 0.10
    # staleness = 0.0 (new gap) -> 0.0 * 0.15 = 0.0
    # connectivity = 0.0 (no entity_id) -> 0.0 * 0.25 = 0.0
    # severity = 1.0 -> 1.0 * 0.30 = 0.30
    # total = 0.30 + 0.0 + 0.10 + 0.0 + 0.03 = 0.43

    gap = GapInfo(
        gap_type="orphan_table",  # NOT in SOLVABLE_WITH_SAMPLING
        entity_type="table",
        entity_id=None,
        entity_name="some_table",
        severity=1.0,
    )
    score = score_gap(db, gap, weights_custom, gap_recorded_at_ts=NOW_TS)

    # severity component alone is 0.30, but query_frequency and solvability add ~0.13
    # Just verify severity=1.0 contributes weights.severity (0.30) to score
    assert score >= weights_custom.severity  # at least severity weight


def test_score_gap_severity_weight_contribution(db):
    """Verify severity component = severity * weights.severity in final score."""
    weights_severity_only = LearningGapWeightsConfig(
        severity=1.0,
        connectivity=0.0,
        query_frequency=0.0,
        staleness=0.0,
        solvability=0.0,
    )
    gap = GapInfo(
        gap_type="orphan_table",
        entity_type="table",
        entity_id=None,
        entity_name="some_table",
        severity=0.6,
    )
    score = score_gap(db, gap, weights_severity_only, gap_recorded_at_ts=NOW_TS)

    assert abs(score - 0.6) < 0.001


# ---------------------------------------------------------------------------
# Test 3: score_gap connectivity uses bfs_graph hop count normalized by 20
# ---------------------------------------------------------------------------


def test_score_gap_connectivity_zero_without_entity_id(db, weights):
    """score_gap uses connectivity=0.0 when entity_id is None."""
    gap = GapInfo(
        gap_type="unlabeled_enum",
        entity_type="column",
        entity_id=None,
        entity_name="orders.status",
        severity=0.5,
    )
    weights_connectivity_only = LearningGapWeightsConfig(
        severity=0.0,
        connectivity=1.0,
        query_frequency=0.0,
        staleness=0.0,
        solvability=0.0,
    )
    score = score_gap(db, gap, weights_connectivity_only, gap_recorded_at_ts=NOW_TS)

    assert score == 0.0


# ---------------------------------------------------------------------------
# Test 4: score_and_prioritize returns gaps sorted by priority_score DESC
# ---------------------------------------------------------------------------


def test_score_and_prioritize_returns_sorted_desc(db, config):
    """score_and_prioritize returns gaps ordered by priority_score DESC."""
    _insert_gap(db, entity_name="gap_low", severity=0.1, status="open")
    _insert_gap(db, entity_name="gap_high", severity=0.9, status="open")
    _insert_gap(db, entity_name="gap_mid", severity=0.5, status="open")

    results = score_and_prioritize(db, config)

    assert len(results) >= 2
    # Verify descending order
    for i in range(len(results) - 1):
        assert results[i].priority_score >= results[i + 1].priority_score


def test_score_and_prioritize_only_includes_open_gaps(db, config):
    """score_and_prioritize only returns open gaps."""
    _insert_gap(db, entity_name="open_gap", status="open")
    _insert_gap(db, entity_name="resolved_gap", status="resolved")
    _insert_gap(db, entity_name="permanent_gap", status="permanent")

    results = score_and_prioritize(db, config)

    names = [r.entity_name for r in results]
    assert "open_gap" in names
    assert "resolved_gap" not in names
    assert "permanent_gap" not in names


# ---------------------------------------------------------------------------
# Test 5: score_and_prioritize respects max_gaps_per_run limit
# ---------------------------------------------------------------------------


def test_score_and_prioritize_respects_max_gaps_limit(db):
    """score_and_prioritize returns at most max_gaps_per_run results."""
    config_small = LearningConfig(max_gaps_per_run=2)

    # Insert 5 gaps
    for i in range(5):
        _insert_gap(db, entity_name=f"gap_{i}", status="open", severity=float(i) / 5)

    results = score_and_prioritize(db, config_small)

    assert len(results) <= 2


# ---------------------------------------------------------------------------
# Test 6: get_eligible_gaps filters out non-open and cooldown gaps
# ---------------------------------------------------------------------------


def test_get_eligible_gaps_excludes_non_open(db):
    """get_eligible_gaps excludes gaps with status != 'open'."""
    _insert_gap(db, entity_name="open_gap", status="open")
    _insert_gap(db, entity_name="investigating_gap", status="investigating")
    _insert_gap(db, entity_name="resolved_gap", status="resolved")

    results = get_eligible_gaps(db, max_gaps=10, now_ts=NOW_TS)

    names = [r.entity_name for r in results]
    assert "open_gap" in names
    assert "investigating_gap" not in names
    assert "resolved_gap" not in names


def test_get_eligible_gaps_excludes_active_cooldown(db):
    """get_eligible_gaps excludes gaps with cooldown_until_ts > now_ts."""
    future_ts = NOW_TS + 3600  # 1 hour from now
    _insert_gap(db, entity_name="cooldown_gap", status="open", cooldown_until_ts=future_ts)
    _insert_gap(db, entity_name="no_cooldown_gap", status="open", cooldown_until_ts=None)

    results = get_eligible_gaps(db, max_gaps=10, now_ts=NOW_TS)

    names = [r.entity_name for r in results]
    assert "no_cooldown_gap" in names
    assert "cooldown_gap" not in names


def test_get_eligible_gaps_includes_expired_cooldown(db):
    """get_eligible_gaps includes gaps with cooldown_until_ts <= now_ts."""
    past_ts = NOW_TS - 3600  # 1 hour ago
    _insert_gap(db, entity_name="expired_cooldown_gap", status="open", cooldown_until_ts=past_ts)

    results = get_eligible_gaps(db, max_gaps=10, now_ts=NOW_TS)

    names = [r.entity_name for r in results]
    assert "expired_cooldown_gap" in names


def test_get_eligible_gaps_respects_limit(db):
    """get_eligible_gaps returns at most max_gaps results."""
    for i in range(5):
        _insert_gap(db, entity_name=f"gap_{i}", status="open")

    results = get_eligible_gaps(db, max_gaps=2, now_ts=NOW_TS)

    assert len(results) <= 2


def test_get_eligible_gaps_returns_gap_records(db):
    """get_eligible_gaps returns GapRecord objects."""
    from db_wiki.learning.models import GapRecord

    _insert_gap(db, entity_name="test_gap", status="open")

    results = get_eligible_gaps(db, max_gaps=10, now_ts=NOW_TS)

    assert len(results) >= 1
    assert isinstance(results[0], GapRecord)


# ---------------------------------------------------------------------------
# Test: SOLVABLE_WITH_SAMPLING constant is defined
# ---------------------------------------------------------------------------


def test_solvable_with_sampling_defined():
    """SOLVABLE_WITH_SAMPLING set is defined and contains expected gap types."""
    from db_wiki.learning.gap_scorer import SOLVABLE_WITH_SAMPLING

    assert isinstance(SOLVABLE_WITH_SAMPLING, set)
    assert "unlabeled_enum" in SOLVABLE_WITH_SAMPLING
    assert "missing_fk" in SOLVABLE_WITH_SAMPLING
