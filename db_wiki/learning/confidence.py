"""Confidence management system for the db-wiki learning loop.

Implements:
  - decay_confidence: time-based confidence decay (D-13, D-15, LEARN-09)
  - reinforce_confidence: evidence-based confidence increase (LEARN-09)
  - resolve_conflict: conflict resolution with SUPERSEDE/KEEP/SPLIT/ESCALATE (D-14, LEARN-07)
  - compute_sp_reliability: SP reliability scoring formula (D-17, LEARN-08)
  - count_independent_sources: simple SP source counting (D-16, LEARN-12)

All functions are pure or accept a sqlite3.Connection for DB-backed scoring.
"""

from __future__ import annotations

import sqlite3


def decay_confidence(
    current: float,
    days_since_update: float,
    is_human_confirmed: bool,
    decay_weekly: float = 0.01,
    decay_confirmed_monthly: float = 0.005,
) -> float:
    """Apply time-based confidence decay.

    Uses compound decay: current * (1 - rate_per_day)^days.

    Rates (D-13, D-15):
      - Normal facts: 1% per week => rate_per_day = 0.01 / 7
      - Human-confirmed facts: 0.5% per month => rate_per_day = 0.005 / 30

    Args:
        current: Current confidence score in [0.0, 1.0].
        days_since_update: Number of days elapsed since last update.
        is_human_confirmed: Whether the fact was confirmed by a human.
        decay_weekly: Weekly decay rate for normal facts (default 1%).
        decay_confirmed_monthly: Monthly decay rate for confirmed facts (default 0.5%).

    Returns:
        Decayed confidence score, floored at 0.0.
    """
    if is_human_confirmed:
        rate_per_day = decay_confirmed_monthly / 30.0
    else:
        rate_per_day = decay_weekly / 7.0

    decayed = current * ((1.0 - rate_per_day) ** days_since_update)
    return max(0.0, decayed)


def reinforce_confidence(current: float, evidence_weight: float = 0.1) -> float:
    """Increase confidence by adding evidence weight, capped at 1.0.

    Args:
        current: Current confidence score.
        evidence_weight: Amount to add (default 0.1 per additional source).

    Returns:
        Updated confidence score, capped at 1.0.
    """
    return min(1.0, current + evidence_weight)


def resolve_conflict(
    fact_a_conf: float,
    fact_a_sources: int,
    fact_a_ts: int,
    fact_b_conf: float,
    fact_b_sources: int,
    fact_b_ts: int,
    escalate_threshold: float = 0.1,
    fact_a_context: str | None = None,
    fact_b_context: str | None = None,
) -> tuple[str, str]:
    """Resolve a conflict between two competing facts.

    Scoring formula (D-14):
      score = confidence * 0.6 + min(1.0, sources / 5.0) * 0.3 + recency * 0.1

    Resolution strategies:
      - KEEP: both facts coexist under different conditions (both conf >= 0.3)
      - SPLIT: facts apply to different sub-contexts (both contexts present)
      - ESCALATE: score difference < threshold => human review needed
      - SUPERSEDE_B: fact A score > fact B score
      - SUPERSEDE_A: fact B score > fact A score

    Args:
        fact_a_conf: Confidence of fact A.
        fact_a_sources: Number of independent sources supporting fact A.
        fact_a_ts: Timestamp (epoch seconds) of fact A.
        fact_b_conf: Confidence of fact B.
        fact_b_sources: Number of independent sources supporting fact B.
        fact_b_ts: Timestamp (epoch seconds) of fact B.
        escalate_threshold: Minimum score difference before escalating (D-14).
        fact_a_context: Optional context condition for fact A (e.g. "status=active").
        fact_b_context: Optional context condition for fact B (e.g. "status=archived").

    Returns:
        Tuple of (resolution_strategy, rationale_string).
    """
    # Compute composite scores (D-14 weights: 0.6 confidence, 0.3 sources, 0.1 recency)
    score_a = (
        fact_a_conf * 0.6
        + min(1.0, fact_a_sources / 5.0) * 0.3
        + (1.0 if fact_a_ts > fact_b_ts else 0.0) * 0.1
    )
    score_b = (
        fact_b_conf * 0.6
        + min(1.0, fact_b_sources / 5.0) * 0.3
        + (1.0 if fact_b_ts > fact_a_ts else 0.0) * 0.1
    )

    # KEEP: both facts are valid under different conditions
    if (
        fact_a_context
        and fact_b_context
        and fact_a_context != fact_b_context
        and fact_a_conf >= 0.3
        and fact_b_conf >= 0.3
    ):
        return (
            "KEEP",
            f"Facts coexist under different conditions: A={fact_a_context}, B={fact_b_context}",
        )

    # SPLIT: facts apply to different sub-contexts (both contexts present but non-empty)
    if fact_a_context and fact_b_context:
        return (
            "SPLIT",
            f"Facts split into sub-contexts: A={fact_a_context}, B={fact_b_context}",
        )

    # ESCALATE: score difference is too small to decide
    diff = abs(score_a - score_b)
    if diff < escalate_threshold:
        return (
            "ESCALATE",
            f"Score difference {diff:.3f} < threshold {escalate_threshold}",
        )

    # SUPERSEDE: clear winner
    if score_a > score_b:
        return (
            "SUPERSEDE_B",
            f"Fact A score {score_a:.3f} > Fact B {score_b:.3f}",
        )
    else:
        return (
            "SUPERSEDE_A",
            f"Fact B score {score_b:.3f} > Fact A {score_a:.3f}",
        )


def compute_sp_reliability(
    conn: sqlite3.Connection,
    proc_id: int,
    now_ts: int,
) -> float:
    """Compute a reliability score for a stored procedure.

    Formula (D-17):
      baseline = 0.5
      - 0.2  if has_dynamic_sql
      - 0.05 if partial_ast
      + 0.1  if procedure is recent (< 30 days old)
      + 0.05 per unique caller (capped at +0.25)
      - 0.1  per contradiction in agent_results (capped at -0.5)

    Args:
        conn: SQLite connection.
        proc_id: ID of the stored procedure.
        now_ts: Current epoch timestamp (for recency check).

    Returns:
        Reliability score clamped to [0.0, 1.0].
        Returns 0.5 (baseline) if no reliability row exists.
    """
    score = 0.5  # baseline (D-17)

    # Fetch reliability row
    row = conn.execute(
        """SELECT has_dynamic_sql, partial_ast, parse_quality
           FROM current_sp_reliability
           WHERE procedure_id = ?""",
        (proc_id,),
    ).fetchone()

    if row is None:
        return 0.5

    if row["has_dynamic_sql"]:
        score -= 0.2

    if row["partial_ast"]:
        score -= 0.05

    # Recency bonus: procedure less than 30 days old
    proc_row = conn.execute(
        "SELECT valid_from_ts FROM current_db_procedures WHERE id = ?",
        (proc_id,),
    ).fetchone()
    if proc_row is not None:
        age_seconds = now_ts - proc_row["valid_from_ts"]
        if age_seconds < 30 * 86400:
            score += 0.1

    # Caller count bonus: +0.05 per caller, capped at +0.25
    caller_count_row = conn.execute(
        "SELECT COUNT(DISTINCT caller_id) AS cnt FROM current_sp_call_chains WHERE callee_id = ?",
        (proc_id,),
    ).fetchone()
    if caller_count_row is not None:
        caller_count = caller_count_row["cnt"]
        score += min(0.25, caller_count * 0.05)

    # Contradiction penalty: -0.1 per rejected agent result, capped at -0.5
    contradiction_row = conn.execute(
        """SELECT COUNT(*) AS cnt
           FROM current_agent_results ar
           JOIN current_agent_tasks at ON ar.task_id = at.id
           WHERE at.gap_id IN (
               SELECT id FROM current_knowledge_gaps WHERE entity_id = ?
           )
           AND ar.approved = 0""",
        (proc_id,),
    ).fetchone()
    if contradiction_row is not None:
        contradictions = contradiction_row["cnt"]
        score -= min(0.5, contradictions * 0.1)

    return max(0.0, min(1.0, score))


def count_independent_sources(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_name: str,
    attribute: str,
) -> int:
    """Count independent sources supporting a fact.

    Per D-16: simple source counting — each SP is one independent source.

    Args:
        conn: SQLite connection.
        entity_type: Type of entity (e.g. "column", "table", "sp").
        entity_name: Entity identifier, typically "table_name.column_name".
        attribute: Attribute type (e.g. "enum_label", "bitmask_label", "alias").

    Returns:
        Count of distinct source SPs. Returns 1 for unknown attribute types.
    """
    if attribute == "enum_label":
        # Parse "table_name.column_name" from entity_name
        parts = entity_name.split(".", 1)
        if len(parts) == 2:
            table_name, column_name = parts
        else:
            table_name, column_name = entity_name, ""

        row = conn.execute(
            """SELECT COUNT(DISTINCT source_procedure_id) AS cnt
               FROM current_enum_values
               WHERE table_name = ? AND column_name = ?
                 AND source_procedure_id IS NOT NULL""",
            (table_name, column_name),
        ).fetchone()
        return row["cnt"] if row else 1

    # Default: 1 source (per D-16 simple counting fallback)
    return 1
