"""Shared confirm/teach logic for human knowledge injection.

Used by both MCP tools and CLI commands. Implements LEARN-10:
- confirm_fact: verify an existing fact (sets confidence=1.0, detection_method='human_confirmed')
- teach_fact: add or override a fact with human authority

Human-confirmed facts get slow decay (0.5%/month per D-15) handled
automatically by confidence.decay_confidence checking the human_confirmed flag.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

from db_wiki.learning.pipeline import _invalidate_row, _log_operation, find_existing_fact


def confirm_fact(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
) -> str:
    """Confirm an existing fact as human-verified.

    Sets confidence to 1.0 and detection_method to 'human_confirmed'.
    Human-confirmed facts get slower decay rate (0.5%/month) -- the decay
    function checks detection_method, not a separate flag.

    If the value doesn't match or the fact doesn't exist, returns guidance.
    """
    existing = find_existing_fact(conn, entity_type, entity_name, attribute)

    if existing is None:
        return f"No existing fact for {entity_name}.{attribute}. Use 'teach' to add new knowledge."

    if existing["value"] != value:
        return (
            f"Value mismatch: existing is '{existing['value']}', "
            f"you confirmed '{value}'. Use 'teach' to override."
        )

    now_ts = int(time.time())
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    # Invalidate old row and insert confirmed version
    _invalidate_row(conn, attribute, existing["id"], now_ts, now_iso)
    _write_confirmed_fact(conn, entity_name, attribute, value, now_ts, now_iso)
    _log_operation(
        conn, now_ts, "CONFIRM",
        entity_type=entity_type, entity_id=entity_name,
        attribute=attribute, old_value=existing["value"], new_value=value,
        confidence_before=existing["confidence"], confidence_after=1.0,
        source="human",
    )
    conn.commit()

    return f"Confirmed: {entity_name}.{attribute} = {value} (confidence set to 1.0)"


def teach_fact(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_name: str,
    attribute: str,
    value: str,
) -> str:
    """Add or override a fact with human authority.

    Always sets confidence=1.0 and human_confirmed=True.
    Handles ADD, REINFORCE, and CONFLICT cases — human overrides all.
    """
    now_ts = int(time.time())
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    existing = find_existing_fact(conn, entity_type, entity_name, attribute)

    if existing is not None:
        # Invalidate the old row regardless of match
        _invalidate_row(conn, attribute, existing["id"], now_ts, now_iso)

    # Write new fact with human authority
    _write_confirmed_fact(conn, entity_name, attribute, value, now_ts, now_iso)
    _log_operation(
        conn, now_ts, "TEACH",
        entity_type=entity_type, entity_id=entity_name,
        attribute=attribute,
        old_value=existing["value"] if existing is not None else None,
        new_value=value,
        confidence_before=existing["confidence"] if existing is not None else None,
        confidence_after=1.0,
        source="human",
    )
    conn.commit()

    return f"Taught: {entity_name}.{attribute} = {value} (confidence 1.0, human confirmed)"


def _write_confirmed_fact(
    conn: sqlite3.Connection,
    entity_name: str,
    attribute: str,
    value: str,
    now_ts: int,
    now_iso: str,
) -> None:
    """Insert a fact row with confidence=1.0 and human_confirmed=1."""
    parts = entity_name.split(".", 1)
    table_name = parts[0]
    column_name = parts[1] if len(parts) == 2 else ""

    if attribute == "enum_label":
        conn.execute(
            """INSERT INTO enum_values
               (table_name, column_name, enum_value, enum_label,
                confidence, detection_method, source_procedure_id,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, ?, ?, 1.0, 'human_confirmed', NULL,
                       ?, ?, ?, ?)""",
            (table_name, column_name, value, value,
             now_iso, now_ts, now_iso, now_ts),
        )

    elif attribute == "bitmask_label":
        conn.execute(
            """INSERT INTO bitmask_definitions
               (table_name, column_name, bit_position, bit_label,
                confidence, detection_method, source_procedure_id,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, 0, ?, 1.0, 'human_confirmed', NULL,
                       ?, ?, ?, ?)""",
            (table_name, column_name, value,
             now_iso, now_ts, now_iso, now_ts),
        )

    elif attribute == "alias":
        conn.execute(
            """INSERT INTO column_aliases
               (table_name, column_name, alias, confidence,
                source_procedure_id,
                valid_from, valid_from_ts, recorded_at, recorded_at_ts)
               VALUES (?, ?, ?, 1.0, NULL, ?, ?, ?, ?)""",
            (table_name, column_name, value,
             now_iso, now_ts, now_iso, now_ts),
        )
