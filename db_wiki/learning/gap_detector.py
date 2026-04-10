"""Gap detection rules for the learning loop's Discover phase.

Each detection function queries Phase 2 current_* views to identify
knowledge gaps -- things the system does not yet know or understand.

All SQL uses parameterized queries where parameters exist.
Entity names use stable format:
  - "{table_name}.{column_name}" for column gaps
  - "{source_table}_to_{target_table}" for relationship gaps

Conservative detection (D-10): gaps are created only when there is
concrete SQL evidence from Phase 2 views. No speculative gaps.
"""

import logging
import sqlite3
import time

from db_wiki.learning.models import GapInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detection rules
# ---------------------------------------------------------------------------

def detect_unlabeled_enums(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 1: Find enum values with no human-readable label.

    Queries current_enum_values for (table_name, column_name) pairs where
    at least one row has enum_label IS NULL or ''.
    Severity 0.7 -- unlabeled enums reduce query generation quality significantly.
    """
    rows = conn.execute("""
        SELECT table_name, column_name, COUNT(*) AS cnt
        FROM current_enum_values
        WHERE enum_label IS NULL OR enum_label = ''
        GROUP BY table_name, column_name
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="unlabeled_enum",
            entity_type="column",
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"{row['cnt']} unlabeled enum value(s) in {row['table_name']}.{row['column_name']}",
            severity=0.7,
        ))
    return gaps


def detect_orphan_tables(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 2: Find tables with zero relationships.

    Queries current_db_tables for tables that do not appear as source_id
    or target_id in any current_db_relationships row.
    Severity 0.5 -- isolated tables may represent missing FK knowledge.
    """
    rows = conn.execute("""
        SELECT t.id, t.table_name
        FROM current_db_tables t
        WHERE NOT EXISTS (
            SELECT 1 FROM current_db_relationships r
            WHERE r.source_id = t.id OR r.target_id = t.id
        )
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="orphan_table",
            entity_type="table",
            entity_id=row["id"],
            entity_name=row["table_name"],
            description=f"Table '{row['table_name']}' has no relationships",
            severity=0.5,
        ))
    return gaps


def detect_missing_joins(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 3: Find joins_with relationships that lack FK evidence.

    Queries current_db_relationships for rows with relationship_type='joins_with'
    where no fk_declared or fk_inferred relationship exists for the same
    source_id/target_id pair.
    Severity 0.6 -- unvalidated joins may produce incorrect query paths.
    """
    rows = conn.execute("""
        SELECT r.id, r.source_id, r.target_id,
               ts.table_name AS source_table, tt.table_name AS target_table
        FROM current_db_relationships r
        JOIN current_db_tables ts ON ts.id = r.source_id
        JOIN current_db_tables tt ON tt.id = r.target_id
        WHERE r.relationship_type = 'joins_with'
          AND NOT EXISTS (
              SELECT 1 FROM current_db_relationships fk
              WHERE fk.source_id = r.source_id
                AND fk.target_id = r.target_id
                AND fk.relationship_type IN ('fk_declared', 'fk_inferred')
          )
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        name = f"{row['source_table']}_to_{row['target_table']}"
        gaps.append(GapInfo(
            gap_type="missing_join_fk",
            entity_type="relationship",
            entity_id=row["id"],
            entity_name=name,
            description=f"Join '{name}' has no FK evidence (fk_declared or fk_inferred)",
            severity=0.6,
        ))
    return gaps


def detect_stale_facts(
    conn: sqlite3.Connection,
    staleness_days: int = 90,
) -> list[GapInfo]:
    """Rule 4: Find low-confidence enum values recorded long ago.

    Queries current_enum_values for rows where confidence < 0.7 AND
    recorded_at_ts is older than staleness_days.
    Severity 0.4 -- stale low-confidence facts may be outdated.
    """
    threshold_ts = int(time.time()) - staleness_days * 86400
    rows = conn.execute("""
        SELECT table_name, column_name, COUNT(*) AS cnt
        FROM current_enum_values
        WHERE confidence < 0.7
          AND recorded_at_ts < ?
        GROUP BY table_name, column_name
    """, (threshold_ts,)).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="stale_fact",
            entity_type="column",
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"{row['cnt']} stale low-confidence fact(s) older than {staleness_days} days",
            severity=0.4,
        ))
    return gaps


def detect_alias_clusters(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 5: Find columns with multiple competing aliases.

    Queries current_column_aliases for (table_name, column_name) groups
    with more than one alias -- indicating naming ambiguity.
    Severity 0.3 -- alias clusters reduce query matching accuracy.
    """
    rows = conn.execute("""
        SELECT table_name, column_name, COUNT(*) AS alias_count
        FROM current_column_aliases
        GROUP BY table_name, column_name
        HAVING COUNT(*) > 1
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="alias_cluster",
            entity_type="column",
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"{row['alias_count']} competing aliases for {row['table_name']}.{row['column_name']}",
            severity=0.3,
        ))
    return gaps


def detect_incomplete_state_machines(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 6: Find state columns with fewer than 2 distinct state values.

    Queries current_state_transitions, groups by (table_name, column_name),
    and flags groups with fewer than 2 distinct values (from_value + to_value).
    Severity 0.6 -- incomplete state machines prevent workflow understanding.
    """
    rows = conn.execute("""
        SELECT table_name, column_name,
               COUNT(DISTINCT from_value) + COUNT(DISTINCT to_value) AS value_count
        FROM current_state_transitions
        GROUP BY table_name, column_name
        HAVING COUNT(DISTINCT from_value) + COUNT(DISTINCT to_value) < 2
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="incomplete_state_machine",
            entity_type="column",
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"State machine for {row['table_name']}.{row['column_name']} has fewer than 2 distinct values",
            severity=0.6,
        ))
    return gaps


def detect_unresolved_calls(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 7: Find stored procedures with unresolved call targets.

    Queries current_sp_call_chains WHERE is_resolved = 0, JOINed with
    current_db_procedures to get the caller name.
    Severity 0.5 -- unresolved calls prevent complete call graph analysis.
    """
    rows = conn.execute("""
        SELECT cc.id, p.id AS proc_id, p.procedure_name, cc.callee_name_raw
        FROM current_sp_call_chains cc
        JOIN current_db_procedures p ON p.id = cc.caller_id
        WHERE cc.is_resolved = 0
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="unresolved_call",
            entity_type="sp",
            entity_id=row["proc_id"],
            entity_name=f"{row['procedure_name']}.calls.{row['callee_name_raw']}",
            description=f"SP '{row['procedure_name']}' calls unresolved target '{row['callee_name_raw']}'",
            severity=0.5,
        ))
    return gaps


def detect_low_confidence_facts(
    conn: sqlite3.Connection,
    threshold: float = 0.4,
) -> list[GapInfo]:
    """Rule 8: Find facts with very low confidence across multiple sources.

    UNION query across current_enum_values, current_bitmask_definitions,
    current_column_aliases WHERE confidence < threshold.
    Severity 0.4 -- very low confidence facts may be wrong.
    """
    rows = conn.execute("""
        SELECT 'column' AS entity_type, table_name, column_name, 'enum_value' AS fact_type, confidence
        FROM current_enum_values
        WHERE confidence < ?
        UNION ALL
        SELECT 'column' AS entity_type, table_name, column_name, 'bitmask' AS fact_type, confidence
        FROM current_bitmask_definitions
        WHERE confidence < ?
        UNION ALL
        SELECT 'column' AS entity_type, table_name, column_name, 'alias' AS fact_type, confidence
        FROM current_column_aliases
        WHERE confidence < ?
    """, (threshold, threshold, threshold)).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="low_confidence_fact",
            entity_type="column",
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"Low confidence {row['fact_type']} fact (confidence={row['confidence']:.2f})",
            severity=0.4,
        ))
    return gaps


def detect_cross_sp_contradictions(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 9: Find enum values with conflicting labels across stored procedures.

    Self-join on current_enum_values where same (table_name, column_name,
    enum_value) has different non-NULL enum_labels.
    Severity 0.8 -- contradictions indicate data quality or logic issues.
    """
    rows = conn.execute("""
        SELECT a.table_name, a.column_name, a.enum_value
        FROM current_enum_values a
        JOIN current_enum_values b
          ON a.table_name = b.table_name
         AND a.column_name = b.column_name
         AND a.enum_value = b.enum_value
         AND a.enum_label != b.enum_label
         AND a.enum_label IS NOT NULL
         AND b.enum_label IS NOT NULL
        GROUP BY a.table_name, a.column_name, a.enum_value
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="cross_sp_contradiction",
            entity_type="column",
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"Contradictory labels for enum value '{row['enum_value']}' in {row['table_name']}.{row['column_name']}",
            severity=0.8,
        ))
    return gaps


def detect_missing_fks(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 10: Find columns named *_id or *_code with no FK relationship.

    Queries current_db_columns WHERE (column_name LIKE '%_id' OR
    column_name LIKE '%_code') AND is_primary_key = 0 AND the column's
    table has no FK relationship involving that column.
    Severity 0.6 -- likely foreign keys without declared relationships.
    """
    rows = conn.execute("""
        SELECT c.id, c.column_name, t.id AS table_id, t.table_name
        FROM current_db_columns c
        JOIN current_db_tables t ON t.id = c.table_id
        WHERE (c.column_name LIKE '%_id' OR c.column_name LIKE '%_code')
          AND c.is_primary_key = 0
          AND NOT EXISTS (
              SELECT 1 FROM current_db_relationships r
              WHERE (r.source_id = t.id OR r.target_id = t.id)
                AND r.relationship_type IN ('fk_declared', 'fk_inferred')
                AND r.source_column = c.column_name
          )
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="missing_fk",
            entity_type="column",
            entity_id=row["table_id"],
            entity_name=f"{row['table_name']}.{row['column_name']}",
            description=f"Column '{row['column_name']}' looks like a FK but has no FK relationship declared",
            severity=0.6,
        ))
    return gaps


def detect_coverage_gaps(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 11: Find tables and stored procedures with no description.

    UNION query: current_db_tables WHERE description IS NULL,
    current_db_procedures WHERE description IS NULL.
    Severity 0.3 -- missing descriptions reduce documentation quality.
    """
    rows = conn.execute("""
        SELECT id, table_name AS entity_name, 'table' AS entity_type
        FROM current_db_tables
        WHERE description IS NULL OR description = ''
        UNION ALL
        SELECT id, procedure_name AS entity_name, 'sp' AS entity_type
        FROM current_db_procedures
        WHERE description IS NULL OR description = ''
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        gaps.append(GapInfo(
            gap_type="coverage_gap",
            entity_type=row["entity_type"],
            entity_id=row["id"],
            entity_name=row["entity_name"],
            description=f"No description for {row['entity_type']} '{row['entity_name']}'",
            severity=0.3,
        ))
    return gaps


def detect_pattern_anomalies(conn: sqlite3.Connection) -> list[GapInfo]:
    """Rule 12: Find stored procedures with low parse quality or degraded status.

    Queries current_sp_reliability WHERE parse_quality < 0.8 OR is_degraded = 1,
    JOINed with current_db_procedures.
    Severity 0.4 -- degraded SPs produce unreliable analysis results.
    """
    rows = conn.execute("""
        SELECT sr.id, p.id AS proc_id, p.procedure_name,
               sr.parse_quality, sr.is_degraded
        FROM current_sp_reliability sr
        JOIN current_db_procedures p ON p.id = sr.procedure_id
        WHERE sr.parse_quality < 0.8 OR sr.is_degraded = 1
    """).fetchall()

    gaps: list[GapInfo] = []
    for row in rows:
        reason = []
        if row["parse_quality"] < 0.8:
            reason.append(f"parse_quality={row['parse_quality']:.2f}")
        if row["is_degraded"]:
            reason.append("is_degraded=1")
        gaps.append(GapInfo(
            gap_type="pattern_anomaly",
            entity_type="sp",
            entity_id=row["proc_id"],
            entity_name=row["procedure_name"],
            description=f"SP '{row['procedure_name']}' has reliability issues: {', '.join(reason)}",
            severity=0.4,
        ))
    return gaps


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def detect_all_gaps(
    conn: sqlite3.Connection,
    now_ts: int,
    now_iso: str,
) -> list[GapInfo]:
    """Run all 12 gap detection rules and concatenate results.

    Args:
        conn: SQLite connection with Phase 2 current_* views.
        now_ts: Current epoch timestamp (for staleness threshold).
        now_iso: Current ISO timestamp (reserved for future use).

    Returns:
        Combined list of GapInfo from all 12 rules. May contain duplicates
        across rules -- caller should use upsert_gaps() to deduplicate.
    """
    results: list[GapInfo] = []
    rules = [
        ("detect_unlabeled_enums", detect_unlabeled_enums),
        ("detect_orphan_tables", detect_orphan_tables),
        ("detect_missing_joins", detect_missing_joins),
        ("detect_stale_facts", detect_stale_facts),
        ("detect_alias_clusters", detect_alias_clusters),
        ("detect_incomplete_state_machines", detect_incomplete_state_machines),
        ("detect_unresolved_calls", detect_unresolved_calls),
        ("detect_low_confidence_facts", detect_low_confidence_facts),
        ("detect_cross_sp_contradictions", detect_cross_sp_contradictions),
        ("detect_missing_fks", detect_missing_fks),
        ("detect_coverage_gaps", detect_coverage_gaps),
        ("detect_pattern_anomalies", detect_pattern_anomalies),
    ]

    for rule_name, rule_fn in rules:
        try:
            rule_gaps = rule_fn(conn)
            logger.debug("Rule %s found %d gaps", rule_name, len(rule_gaps))
            results.extend(rule_gaps)
        except Exception:
            logger.exception("Error in gap detection rule %s", rule_name)

    return results


# ---------------------------------------------------------------------------
# Deduplication / upsert
# ---------------------------------------------------------------------------

def upsert_gaps(
    conn: sqlite3.Connection,
    gaps: list[GapInfo],
    now_ts: int,
    now_iso: str,
) -> list[int | None]:
    """Persist detected gaps with deduplication logic.

    For each gap, check current_knowledge_gaps for existing rows matching
    (gap_type, entity_name):
      - status='open' or 'investigating': skip, return existing id
      - status='permanent': skip entirely, return None
      - status='resolved' and cooldown_until_ts > now_ts: skip (cooling down)
      - status='resolved' and cooldown_until_ts <= now_ts or NULL: insert new row
      - No existing row: insert new row

    All inserted rows use full bi-temporal columns.

    Args:
        conn: SQLite connection with knowledge_gaps table.
        gaps: List of GapInfo to upsert.
        now_ts: Current epoch timestamp.
        now_iso: Current ISO timestamp string.

    Returns:
        List of gap IDs (int) for inserted/existing gaps, None for skipped gaps.
    """
    result_ids: list[int | None] = []

    for gap in gaps:
        existing = conn.execute(
            """
            SELECT id, status, cooldown_until_ts
            FROM current_knowledge_gaps
            WHERE gap_type = ? AND entity_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (gap.gap_type, gap.entity_name),
        ).fetchone()

        if existing is not None:
            status = existing["status"]

            # Already tracked actively -- return existing ID
            if status in ("open", "investigating"):
                result_ids.append(existing["id"])
                continue

            # Permanently closed -- skip entirely
            if status == "permanent":
                result_ids.append(None)
                continue

            # Resolved but still in cooldown
            if status == "resolved":
                cooldown_ts = existing["cooldown_until_ts"]
                if cooldown_ts is not None and cooldown_ts > now_ts:
                    result_ids.append(None)
                    continue
                # Cooldown expired or not set -- fall through to insert (re-open)

        # Insert new gap row with full bi-temporal columns
        cursor = conn.execute(
            """
            INSERT INTO knowledge_gaps (
                gap_type, entity_type, entity_id, entity_name, description,
                severity, priority_score, status, attempt_count,
                valid_from, valid_from_ts, valid_until, valid_until_ts,
                recorded_at, recorded_at_ts, invalidated_at, invalidated_at_ts
            ) VALUES (?, ?, ?, ?, ?, ?, 0.0, 'open', 0, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
            """,
            (
                gap.gap_type,
                gap.entity_type,
                gap.entity_id,
                gap.entity_name,
                gap.description,
                gap.severity,
                now_iso,
                now_ts,
                now_iso,
                now_ts,
            ),
        )
        conn.commit()
        result_ids.append(cursor.lastrowid)

    return result_ids
