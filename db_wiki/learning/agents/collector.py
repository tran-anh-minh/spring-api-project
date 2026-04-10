"""Collector Agent — samples live database for evidence.

Executes read-only queries against SQL Server via pyodbc with safety limits:
timeout, max_rows, and query_budget per D-04 / AGENT-04.

Falls back to no-op when pyodbc is not installed or no connection configured.
"""

from __future__ import annotations

import logging
import re
import sqlite3

from db_wiki.learning.models import AgentFindings, FindingItem, GapRecord

logger = logging.getLogger(__name__)

# Validate table/column names: alphanumeric + underscore only (T-03-09)
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_]+$")


def _safe_name(name: str) -> str | None:
    """Return name if it matches safe identifier pattern, else None."""
    return name if _SAFE_IDENTIFIER.match(name) else None


def _build_sampling_query(gap_type: str, entity_name: str) -> str | None:
    """Generate a read-only sampling query for the given gap type.

    Returns None if no sampling strategy exists for this gap type.
    """
    parts = entity_name.split(".", 1)
    table = _safe_name(parts[0]) if parts else None
    column = _safe_name(parts[1]) if len(parts) > 1 else None

    if table is None:
        return None

    if gap_type in ("unlabeled_enum", "stale_fact", "low_confidence_fact"):
        if column is None:
            return None
        return f"SELECT DISTINCT [{column}] FROM [{table}] ORDER BY [{column}]"

    if gap_type == "missing_fk":
        if column is None:
            return None
        return (
            f"SELECT DISTINCT [{column}], COUNT(*) AS cnt "
            f"FROM [{table}] GROUP BY [{column}] ORDER BY cnt DESC"
        )

    return None


def _execute_sample(
    connection_string: str,
    query: str,
    timeout: int,
    max_rows: int,
) -> list[dict] | None:
    """Execute a single sampling query with safety limits."""
    try:
        import pyodbc
    except ImportError:
        logger.debug("pyodbc not installed — skipping live DB sampling")
        return None

    if not connection_string:
        return None

    conn = None
    try:
        conn = pyodbc.connect(connection_string, timeout=timeout, readonly=True)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchmany(max_rows)
        return [dict(zip(columns, row)) for row in rows]
    except Exception:
        logger.warning("Collector sampling failed", exc_info=True)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def collect_evidence(
    conn: sqlite3.Connection,
    gap: GapRecord,
    config,
) -> AgentFindings:
    """Collect evidence for a knowledge gap from the live database.

    Args:
        conn: SQLite knowledge store connection (for future context lookups).
        gap: The knowledge gap to investigate.
        config: DBWikiConfig with database and learning settings.

    Returns:
        AgentFindings with sampled data items, or empty findings if no DB.
    """
    if config.database.connection_string is None:
        return AgentFindings(
            summary="No live DB connection; skipping data collection",
            evidence_quality=0.0,
        )

    query = _build_sampling_query(gap.gap_type, gap.entity_name)
    if query is None:
        return AgentFindings(
            summary=f"No sampling strategy for gap type {gap.gap_type}",
            evidence_quality=0.0,
        )

    result = _execute_sample(
        config.database.connection_string,
        query,
        config.learning.collector_timeout_seconds,
        config.learning.collector_max_rows,
    )

    if result is None:
        return AgentFindings(
            summary="Sampling query failed or pyodbc not available",
            evidence_quality=0.0,
        )

    # Convert sampled rows to FindingItems
    parts = gap.entity_name.split(".", 1)
    column_name = parts[1] if len(parts) > 1 else ""
    items: list[FindingItem] = []

    for row in result:
        value = str(row.get(column_name, next(iter(row.values()), "")))
        if value:
            items.append(
                FindingItem(
                    entity_type=gap.entity_type,
                    entity_name=gap.entity_name,
                    attribute="enum_label" if gap.gap_type == "unlabeled_enum" else "sampled_value",
                    value=value,
                    confidence=0.5,
                    source="collector_sampling",
                )
            )

    return AgentFindings(
        items=items,
        summary=f"Collected {len(items)} samples from live DB",
        evidence_quality=0.5 if items else 0.0,
    )
