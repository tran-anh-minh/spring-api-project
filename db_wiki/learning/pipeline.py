"""4-operation update pipeline for the learning loop.

Classifies every proposed fact mutation as ADD/REINFORCE/CONFLICT/NOOP,
then applies it to the appropriate Phase 2 table with bi-temporal versioning.

Exports:
  - find_existing_fact: look up current knowledge for an entity+attribute
  - classify_update: determine what operation a new finding requires
  - apply_findings: execute all findings from an agent run
  - mark_gap_resolved: close a knowledge gap after successful investigation
  - bump_attempt_count: increment attempts with cooldown backoff (D-11)
"""

from __future__ import annotations

import json
import sqlite3

from db_wiki.learning.confidence import reinforce_confidence, resolve_conflict
from db_wiki.learning.models import AgentFindings, GapRecord, UpdateOp


def find_existing_fact(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_name: str,
    attribute: str,
) -> dict | None:
    """Look up an existing fact in the Phase 2 current_* views.

    Args:
        conn: SQLite connection with row_factory = sqlite3.Row.
        entity_type: "table", "column", "sp", etc.
        entity_name: dot-separated identifier (e.g. "Orders.Status").
        attribute: what kind of fact ("enum_label", "bitmask_label", "alias").

    Returns:
        Dict with id, value, confidence, and source fields, or None.
    """
    parts = entity_name.split(".", 1)
    table_name = parts[0]
    column_name = parts[1] if len(parts) == 2 else ""

    if attribute == "enum_label":
        row = conn.execute(
            """SELECT id, enum_label AS value, confidence,
                      source_procedure_id, valid_from_ts,
                      COALESCE(enum_value, '') AS enum_value
               FROM current_enum_values
               WHERE table_name = ? AND column_name = ?
               ORDER BY confidence DESC
               LIMIT 1""",
            (table_name, column_name),
        ).fetchone()
        if row:
            return dict(row)
        return None

    if attribute == "bitmask_label":
        row = conn.execute(
            """SELECT id, bit_label AS value, confidence,
                      source_procedure_id, valid_from_ts
               FROM current_bitmask_definitions
               WHERE table_name = ? AND column_name = ?
               ORDER BY confidence DESC
               LIMIT 1""",
            (table_name, column_name),
        ).fetchone()
        if row:
            return dict(row)
        return None

    if attribute == "alias":
        row = conn.execute(
            """SELECT id, alias AS value, confidence,
                      source_procedure_id, valid_from_ts
               FROM current_column_aliases
               WHERE table_name = ? AND column_name = ?
               ORDER BY confidence DESC
               LIMIT 1""",
            (table_name, column_name),
        ).fetchone()
        if row:
            return dict(row)
        return None

    return None


def classify_update(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_name: str,
    attribute: str,
    new_value: str,
    new_confidence: float,
) -> tuple[UpdateOp, dict | None]:
    """Classify how a new finding relates to existing knowledge.

    Returns:
        Tuple of (operation, existing_fact_dict_or_None).
    """
    existing = find_existing_fact(conn, entity_type, entity_name, attribute)

    if existing is None:
        return (UpdateOp.ADD, None)

    if existing["value"] == new_value:
        if abs(existing["confidence"] - new_confidence) < 0.05:
            return (UpdateOp.NOOP, existing)
        return (UpdateOp.REINFORCE, existing)

    return (UpdateOp.CONFLICT, existing)


def apply_findings(
    conn: sqlite3.Connection,
    gap: GapRecord,
    findings: AgentFindings,
    now_ts: int,
    now_iso: str,
) -> dict:
    """Apply all findings from an agent run to the knowledge store.

    Each finding is classified then written with bi-temporal versioning:
    old rows are invalidated, new rows inserted.

    Returns:
        Dict with counts: {add, reinforce, conflict, noop, escalated}.
    """
    results = {"add": 0, "reinforce": 0, "conflict": 0, "noop": 0, "escalated": 0}

    for item in findings.items:
        op, existing = classify_update(
            conn, item.entity_type, item.entity_name,
            item.attribute, item.value, item.confidence,
        )

        if op == UpdateOp.ADD:
            _write_new_fact(conn, item.entity_type, item.entity_name,
                            item.attribute, item.value, item.confidence,
                            item.source, now_ts, now_iso)
            _log_operation(
                conn, now_ts, "ADD",
                entity_type=item.entity_type, entity_id=item.entity_name,
                attribute=item.attribute, new_value=item.value,
                confidence_after=item.confidence, source=item.source or "learning_loop",
            )
            results["add"] += 1

        elif op == UpdateOp.REINFORCE:
            new_conf = reinforce_confidence(existing["confidence"])
            _invalidate_row(conn, item.attribute, existing["id"], now_ts, now_iso)
            _write_new_fact(conn, item.entity_type, item.entity_name,
                            item.attribute, item.value, new_conf,
                            item.source, now_ts, now_iso)
            _log_operation(
                conn, now_ts, "REINFORCE",
                entity_type=item.entity_type, entity_id=item.entity_name,
                attribute=item.attribute, old_value=existing["value"], new_value=item.value,
                confidence_before=existing["confidence"], confidence_after=new_conf,
                source=item.source or "learning_loop",
            )
            results["reinforce"] += 1

        elif op == UpdateOp.CONFLICT:
            strategy, rationale = resolve_conflict(
                fact_a_conf=existing["confidence"],
                fact_a_sources=1,
                fact_a_ts=existing.get("valid_from_ts", 0),
                fact_b_conf=item.confidence,
                fact_b_sources=1,
                fact_b_ts=now_ts,
            )

            if strategy == "SUPERSEDE_A":
                # Fact B (new finding) wins over Fact A (existing)
                _invalidate_row(conn, item.attribute, existing["id"], now_ts, now_iso)
                _write_new_fact(conn, item.entity_type, item.entity_name,
                                item.attribute, item.value, item.confidence,
                                item.source, now_ts, now_iso)
                _log_operation(
                    conn, now_ts, "SUPERSEDE",
                    entity_type=item.entity_type, entity_id=item.entity_name,
                    attribute=item.attribute, old_value=existing["value"], new_value=item.value,
                    confidence_before=existing["confidence"], confidence_after=item.confidence,
                    source=item.source or "learning_loop",
                    details={"strategy": strategy, "rationale": rationale},
                )
            elif strategy == "SUPERSEDE_B":
                # Fact A (existing) wins — discard new finding, no changes needed
                _log_operation(
                    conn, now_ts, "CONFLICT",
                    entity_type=item.entity_type, entity_id=item.entity_name,
                    attribute=item.attribute, old_value=existing["value"], new_value=item.value,
                    confidence_before=existing["confidence"], confidence_after=existing["confidence"],
                    source=item.source or "learning_loop",
                    details={"strategy": strategy, "rationale": rationale},
                )
            elif strategy == "KEEP":
                _write_new_fact(conn, item.entity_type, item.entity_name,
                                item.attribute, item.value, item.confidence,
                                item.source, now_ts, now_iso)
                _log_operation(
                    conn, now_ts, "CONFLICT",
                    entity_type=item.entity_type, entity_id=item.entity_name,
                    attribute=item.attribute, old_value=existing["value"], new_value=item.value,
                    confidence_before=existing["confidence"], confidence_after=item.confidence,
                    source=item.source or "learning_loop",
                    details={"strategy": strategy, "rationale": rationale},
                )
            elif strategy == "SPLIT":
                _write_new_fact(conn, item.entity_type, item.entity_name,
                                item.attribute, item.value, item.confidence,
                                item.source, now_ts, now_iso)
                _log_operation(
                    conn, now_ts, "CONFLICT",
                    entity_type=item.entity_type, entity_id=item.entity_name,
                    attribute=item.attribute, old_value=existing["value"], new_value=item.value,
                    confidence_before=existing["confidence"], confidence_after=item.confidence,
                    source=item.source or "learning_loop",
                    details={"strategy": strategy, "rationale": rationale},
                )
            elif strategy == "ESCALATE":
                # Create an escalated conflict gap for human review
                conn.execute(
                    """INSERT INTO knowledge_gaps
                       (gap_type, entity_type, entity_id, entity_name,
                        description, severity, status,
                        valid_from, valid_from_ts, recorded_at, recorded_at_ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?,
                               ?, ?, ?, ?)""",
                    ("escalated_conflict", item.entity_type, gap.entity_id,
                     item.entity_name,
                     f"Conflict: {rationale}",
                     0.8, "open",
                     now_iso, now_ts, now_iso, now_ts),
                )
                _log_operation(
                    conn, now_ts, "CONFLICT",
                    entity_type=item.entity_type, entity_id=item.entity_name,
                    attribute=item.attribute, old_value=existing["value"], new_value=item.value,
                    confidence_before=existing["confidence"], confidence_after=item.confidence,
                    source=item.source or "learning_loop",
                    details={"strategy": "ESCALATE", "rationale": rationale},
                )
                results["escalated"] += 1

            results["conflict"] += 1

        elif op == UpdateOp.NOOP:
            results["noop"] += 1

    conn.commit()
    return results


def mark_gap_resolved(
    conn: sqlite3.Connection,
    gap_id: int,
    now_ts: int,
    now_iso: str,
    resolution_notes: str = "",
) -> None:
    """Mark a knowledge gap as resolved via bi-temporal invalidation + new row."""
    row = conn.execute(
        "SELECT * FROM current_knowledge_gaps WHERE id = ?", (gap_id,)
    ).fetchone()
    if row is None:
        return

    # Invalidate current row
    conn.execute(
        """UPDATE knowledge_gaps
           SET invalidated_at = ?, invalidated_at_ts = ?
           WHERE id = ? AND invalidated_at IS NULL""",
        (now_iso, now_ts, gap_id),
    )

    # Insert resolved version
    conn.execute(
        """INSERT INTO knowledge_gaps
           (gap_type, entity_type, entity_id, entity_name,
            description, severity, priority_score, status,
            attempt_count, resolution_notes, human_confirmed,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?)""",
        (row["gap_type"], row["entity_type"], row["entity_id"],
         row["entity_name"], row["description"], row["severity"],
         row["priority_score"], "resolved",
         row["attempt_count"], resolution_notes,
         row["human_confirmed"],
         now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()


def bump_attempt_count(
    conn: sqlite3.Connection,
    gap_id: int,
    cooldown_hours: list[int],
    max_attempts_before_permanent: int,
    now_ts: int,
    now_iso: str,
) -> None:
    """Increment attempt count with exponential cooldown backoff (D-11).

    Args:
        conn: SQLite connection.
        gap_id: The gap to update.
        cooldown_hours: List of cooldown durations in hours per attempt.
        max_attempts_before_permanent: After this many attempts, mark permanent.
        now_ts: Current epoch timestamp.
        now_iso: Current ISO timestamp.
    """
    row = conn.execute(
        "SELECT * FROM current_knowledge_gaps WHERE id = ?", (gap_id,)
    ).fetchone()
    if row is None:
        return

    new_count = row["attempt_count"] + 1

    if new_count >= max_attempts_before_permanent:
        new_status = "permanent"
        cooldown_until_ts = None
        cooldown_until = None
    else:
        new_status = row["status"]
        idx = min(new_count - 1, len(cooldown_hours) - 1)
        cooldown_secs = cooldown_hours[idx] * 3600
        cooldown_until_ts = now_ts + cooldown_secs
        # Simple ISO from epoch — good enough for cooldown tracking
        from datetime import datetime, timezone
        cooldown_until = datetime.fromtimestamp(
            cooldown_until_ts, tz=timezone.utc
        ).isoformat()

    # Invalidate current row
    conn.execute(
        """UPDATE knowledge_gaps
           SET invalidated_at = ?, invalidated_at_ts = ?
           WHERE id = ? AND invalidated_at IS NULL""",
        (now_iso, now_ts, gap_id),
    )

    # Insert updated version
    conn.execute(
        """INSERT INTO knowledge_gaps
           (gap_type, entity_type, entity_id, entity_name,
            description, severity, priority_score, status,
            attempt_count, cooldown_until, cooldown_until_ts,
            last_attempt_at, last_attempt_at_ts,
            resolution_notes, human_confirmed,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?)""",
        (row["gap_type"], row["entity_type"], row["entity_id"],
         row["entity_name"], row["description"], row["severity"],
         row["priority_score"], new_status,
         new_count, cooldown_until, cooldown_until_ts,
         now_iso, now_ts,
         row["resolution_notes"], row["human_confirmed"],
         now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()


# ── Private helpers ──────────────────────────────────────────────


def _log_operation(
    conn: sqlite3.Connection,
    now_ts: int,
    operation: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    attribute: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    confidence_before: float | None = None,
    confidence_after: float | None = None,
    source: str | None = None,
    details: dict | None = None,
) -> None:
    """Append a row to the knowledge_operations audit log.

    Silently no-ops if the table does not exist (e.g. in test DBs that
    use minimal schemas without running the full DDL).
    """
    try:
        conn.execute(
            """INSERT INTO knowledge_operations
               (timestamp_ts, operation, entity_type, entity_id, attribute,
                old_value, new_value, confidence_before, confidence_after,
                source, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now_ts,
                operation,
                entity_type,
                entity_id,
                attribute,
                old_value,
                new_value,
                confidence_before,
                confidence_after,
                source,
                json.dumps(details) if details is not None else None,
            ),
        )
    except Exception:
        pass


def _table_for_attribute(attribute: str) -> str | None:
    """Map attribute type to Phase 2 table name."""
    return {
        "enum_label": "enum_values",
        "bitmask_label": "bitmask_definitions",
        "alias": "column_aliases",
    }.get(attribute)


def _invalidate_row(
    conn: sqlite3.Connection,
    attribute: str,
    row_id: int,
    now_ts: int,
    now_iso: str,
) -> None:
    """Invalidate a bi-temporal row in the appropriate table."""
    table = _table_for_attribute(attribute)
    if table is None:
        return
    # Defense-in-depth: validate table is from known set (CR-01)
    _VALID_TABLES = ("enum_values", "bitmask_definitions", "column_aliases")
    assert table in _VALID_TABLES, f"Unexpected table name: {table}"
    conn.execute(
        f"UPDATE {table} SET invalidated_at = ?, invalidated_at_ts = ? "
        f"WHERE id = ? AND invalidated_at IS NULL",
        (now_iso, now_ts, row_id),
    )


def _write_new_fact(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
    confidence: float,
    source: str | None,
    now_ts: int,
    now_iso: str,
) -> None:
    """Insert a new bi-temporal row into the appropriate Phase 2 table."""
    parts = entity_name.split(".", 1)
    table_name = parts[0]
    column_name = parts[1] if len(parts) == 2 else ""

    if attribute == "enum_label":
        conn.execute(
            """INSERT INTO enum_values
               (table_name, column_name, enum_value, enum_label,
                confidence, detection_method, source_procedure_id,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (table_name, column_name, value, value,
             confidence, "learning_loop", None,
             now_iso, now_ts, now_iso, now_ts),
        )

    elif attribute == "bitmask_label":
        conn.execute(
            """INSERT INTO bitmask_definitions
               (table_name, column_name, bit_position, bit_label,
                confidence, detection_method, source_procedure_id,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (table_name, column_name, 0, value,
             confidence, "learning_loop", None,
             now_iso, now_ts, now_iso, now_ts),
        )

    elif attribute == "alias":
        conn.execute(
            """INSERT INTO column_aliases
               (table_name, column_name, alias, confidence,
                source_procedure_id,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (table_name, column_name, value, confidence,
             None,
             now_iso, now_ts, now_iso, now_ts),
        )
