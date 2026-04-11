"""Read cross-project patterns with similarity-scaled confidence penalty (CROSS-02, D-09).

Similarity metric: Jaccard similarity on table name sets between source and target.
Close naming match = lower penalty (~20% discount).
Very different schemas = higher penalty (~70% discount).
"""
import json
import sqlite3
from pathlib import Path

from db_wiki.cross.store import open_cross_store, init_cross_schema


def get_cross_patterns(
    target_conn: sqlite3.Connection,
    pattern_type: str | None = None,
    cross_db_path: Path | None = None,
) -> list[dict]:
    """Return cross-project patterns with adjusted confidence.

    Each result dict: {"pattern_type", "pattern_key", "pattern_value",
                       "source_db", "original_confidence", "adjusted_confidence"}

    Adjusted confidence = original * (1.0 - penalty) where penalty is
    based on schema similarity per D-09.
    """
    cross_conn = open_cross_store(cross_db_path)
    init_cross_schema(cross_conn)

    # Get target DB table names for similarity
    target_tables = set(
        r["table_name"] for r in target_conn.execute(
            "SELECT table_name FROM current_db_tables"
        ).fetchall()
    )

    # Query patterns
    query = "SELECT * FROM cross_patterns"
    params: list = []
    if pattern_type:
        query += " WHERE pattern_type = ?"
        params.append(pattern_type)

    rows = cross_conn.execute(query, params).fetchall()
    results = []
    # Cache similarity per source_db
    similarity_cache: dict[str, float] = {}

    for row in rows:
        source_db = row["source_db"]
        if source_db not in similarity_cache:
            similarity_cache[source_db] = _compute_similarity(
                cross_conn, source_db, target_tables
            )

        similarity = similarity_cache[source_db]
        # D-09: penalty inversely proportional to similarity
        # similarity 1.0 = identical schemas = 20% penalty
        # similarity 0.0 = completely different = 70% penalty
        penalty = 0.7 - (0.5 * similarity)  # range: 0.2 to 0.7
        adjusted = row["confidence"] * (1.0 - penalty)

        results.append({
            "pattern_type": row["pattern_type"],
            "pattern_key": row["pattern_key"],
            "pattern_value": json.loads(row["pattern_value"]),
            "source_db": source_db,
            "original_confidence": row["confidence"],
            "adjusted_confidence": round(adjusted, 4),
            "similarity": round(similarity, 4),
        })

    cross_conn.close()
    return results


def _compute_similarity(
    cross_conn: sqlite3.Connection,
    source_db: str,
    target_tables: set[str],
) -> float:
    """Jaccard similarity on table name sets between source and target."""
    row = cross_conn.execute(
        "SELECT table_names FROM cross_db_profiles WHERE db_name = ?",
        (source_db,),
    ).fetchone()
    if not row:
        return 0.0
    source_tables = set(json.loads(row["table_names"]))
    if not source_tables and not target_tables:
        return 0.0
    intersection = source_tables & target_tables
    union = source_tables | target_tables
    return len(intersection) / len(union) if union else 0.0
