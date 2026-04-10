"""Gap priority scoring formula for the learning loop's Discover phase (D-12).

Implements the weighted scoring formula:
  priority = severity*0.3 + connectivity*0.25 + query_frequency*0.20
             + staleness*0.15 + solvability*0.10

All weights are configurable via LearningGapWeightsConfig.
"""

import logging
import sqlite3
import time

from db_wiki.core.config import LearningConfig, LearningGapWeightsConfig
from db_wiki.learning.models import GapInfo, GapRecord

logger = logging.getLogger(__name__)

# Gap types that benefit from live DB sampling -- scored higher for solvability.
SOLVABLE_WITH_SAMPLING: set[str] = {
    "unlabeled_enum",
    "missing_fk",
    "stale_fact",
    "low_confidence_fact",
    "alias_cluster",
}


def score_gap(
    conn: sqlite3.Connection,
    gap: GapInfo,
    weights: LearningGapWeightsConfig,
    gap_recorded_at_ts: int = 0,
) -> float:
    """Compute a priority score for a knowledge gap.

    Args:
        conn: SQLite connection (used for connectivity BFS).
        gap: The gap to score.
        weights: Configurable weight coefficients for each dimension.
        gap_recorded_at_ts: Epoch seconds when the gap was recorded.
            Used to compute staleness. Default 0 = gap is new (staleness=0).

    Returns:
        Float in [0.0, 1.0] representing priority. Higher = more urgent.
    """
    # -- Severity (already normalised 0.0-1.0 by caller) -------------------
    severity = float(gap.severity)

    # -- Connectivity: BFS hop count from entity, normalized by 20 ---------
    connectivity = 0.0
    if gap.entity_id is not None:
        try:
            from db_wiki.graph.bfs import bfs_graph
            hops = bfs_graph(conn, gap.entity_id, max_depth=2)
            # Subtract 1 for the start node itself; cap at 1.0
            connectivity = min(1.0, max(0.0, len(hops) - 1) / 20.0)
        except Exception:
            logger.debug(
                "bfs_graph failed for entity_id=%s -- using connectivity=0.0",
                gap.entity_id,
            )
            connectivity = 0.0

    # -- Query frequency: neutral default (Phase 4 adds real query logs) ----
    query_frequency = 0.5

    # -- Staleness: age of the gap in days, capped at 30 days ---------------
    age_days = (int(time.time()) - gap_recorded_at_ts) / 86400.0
    staleness = min(1.0, max(0.0, age_days / 30.0))

    # -- Solvability: higher for gap types that benefit from live sampling --
    solvability = 0.7 if gap.gap_type in SOLVABLE_WITH_SAMPLING else 0.3

    score = (
        weights.severity * severity
        + weights.connectivity * connectivity
        + weights.query_frequency * query_frequency
        + weights.staleness * staleness
        + weights.solvability * solvability
    )
    # Clamp to [0.0, 1.0] to handle floating-point edge cases
    return min(1.0, max(0.0, score))


def score_and_prioritize(
    conn: sqlite3.Connection,
    config: LearningConfig,
) -> list[GapRecord]:
    """Score all open gaps and return top-N by priority.

    Queries current_knowledge_gaps for open gaps, computes score_gap() for
    each, writes the computed priority_score back to the table, then returns
    the top config.max_gaps_per_run gaps sorted by priority_score DESC.

    Args:
        conn: SQLite connection.
        config: Learning loop configuration (weights, max_gaps_per_run).

    Returns:
        List of GapRecord objects sorted by priority_score DESC, capped at
        config.max_gaps_per_run.
    """
    rows = conn.execute(
        "SELECT * FROM current_knowledge_gaps WHERE status = 'open'"
    ).fetchall()

    scored: list[tuple[float, GapRecord]] = []

    for row in rows:
        gap_info = GapInfo(
            gap_type=row["gap_type"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            description=row["description"],
            severity=row["severity"],
        )
        priority = score_gap(
            conn,
            gap_info,
            config.gap_weights,
            gap_recorded_at_ts=row["recorded_at_ts"],
        )

        # Persist the updated priority_score
        conn.execute(
            "UPDATE knowledge_gaps SET priority_score = ? WHERE id = ?",
            (priority, row["id"]),
        )

        gap_record = GapRecord(
            id=row["id"],
            gap_type=row["gap_type"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            description=row["description"],
            severity=row["severity"],
            priority_score=priority,
            status=row["status"],
            attempt_count=row["attempt_count"],
            cooldown_until=row["cooldown_until"],
            cooldown_until_ts=row["cooldown_until_ts"],
            last_attempt_at=row["last_attempt_at"],
            human_confirmed=bool(row["human_confirmed"]),
            recorded_at_ts=row["recorded_at_ts"],
        )
        scored.append((priority, gap_record))

    conn.commit()

    # Sort by priority DESC, return top-N
    scored.sort(key=lambda t: t[0], reverse=True)
    return [rec for _, rec in scored[: config.max_gaps_per_run]]


def get_eligible_gaps(
    conn: sqlite3.Connection,
    max_gaps: int,
    now_ts: int,
) -> list[GapRecord]:
    """Fetch gaps eligible for investigation (open, cooldown expired).

    Args:
        conn: SQLite connection.
        max_gaps: Maximum number of gaps to return.
        now_ts: Current epoch seconds for cooldown comparison.

    Returns:
        List of GapRecord objects ordered by priority_score DESC.
    """
    rows = conn.execute(
        """
        SELECT * FROM current_knowledge_gaps
        WHERE status = 'open'
          AND (cooldown_until_ts IS NULL OR cooldown_until_ts <= ?)
        ORDER BY priority_score DESC
        LIMIT ?
        """,
        (now_ts, max_gaps),
    ).fetchall()

    results: list[GapRecord] = []
    for row in rows:
        results.append(GapRecord(
            id=row["id"],
            gap_type=row["gap_type"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            description=row["description"],
            severity=row["severity"],
            priority_score=row["priority_score"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            cooldown_until=row["cooldown_until"],
            cooldown_until_ts=row["cooldown_until_ts"],
            last_attempt_at=row["last_attempt_at"],
            human_confirmed=bool(row["human_confirmed"]),
            recorded_at_ts=row["recorded_at_ts"],
        ))
    return results
