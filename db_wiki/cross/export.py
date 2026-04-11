"""Export patterns from knowledge.db to cross.db (CROSS-01, D-07, D-08).

Extracts naming conventions, enum values, schema shapes, and state machine
templates. Only called when user explicitly runs `db-wiki export --to-cross`.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from db_wiki.cross.store import open_cross_store, init_cross_schema


def push_patterns_to_cross(
    knowledge_conn: sqlite3.Connection,
    db_name: str,
    cross_db_path: Path | None = None,
) -> dict:
    """Extract patterns from knowledge.db and push to cross.db.

    Returns dict with counts: {"naming": N, "enum": N, "schema_shape": N, "state_machine": N}
    """
    cross_conn = open_cross_store(cross_db_path)
    init_cross_schema(cross_conn)
    now = datetime.now(timezone.utc).isoformat()
    counts = {"naming": 0, "enum": 0, "schema_shape": 0, "state_machine": 0}

    # 1. Naming patterns: extract column naming conventions
    #    (e.g., columns ending in _id, _at, _flag, is_, has_)
    cols = knowledge_conn.execute(
        "SELECT column_name, data_type FROM current_db_columns"
    ).fetchall()
    naming_patterns = _extract_naming_patterns(cols)
    for key, value in naming_patterns.items():
        _upsert_pattern(cross_conn, "naming", key, json.dumps(value), db_name, now)
        counts["naming"] += 1

    # 2. Enum values: extract known enum value sets
    try:
        enums = knowledge_conn.execute(
            "SELECT table_name, column_name, enum_value FROM current_enum_values"
        ).fetchall()
        enum_groups: dict = {}
        for row in enums:
            k = f"{row['table_name']}.{row['column_name']}"
            enum_groups.setdefault(k, []).append(row["enum_value"])
        for key, values in enum_groups.items():
            _upsert_pattern(cross_conn, "enum", key, json.dumps(values), db_name, now)
            counts["enum"] += 1
    except Exception:
        pass  # enum table may not exist if no enums detected

    # 3. Schema shapes: detect common patterns (audit cols, soft delete, etc.)
    shapes = _detect_schema_shapes(knowledge_conn)
    for key, value in shapes.items():
        _upsert_pattern(cross_conn, "schema_shape", key, json.dumps(value), db_name, now)
        counts["schema_shape"] += 1

    # 4. State machines: extract state transition templates
    try:
        transitions = knowledge_conn.execute(
            "SELECT table_name, column_name, from_value, to_value "
            "FROM current_state_transitions"
        ).fetchall()
        sm_groups: dict = {}
        for row in transitions:
            k = f"{row['table_name']}.{row['column_name']}"
            sm_groups.setdefault(k, []).append(
                {"from": row["from_value"], "to": row["to_value"]}
            )
        for key, value in sm_groups.items():
            _upsert_pattern(cross_conn, "state_machine", key, json.dumps(value), db_name, now)
            counts["state_machine"] += 1
    except Exception:
        pass  # state_transitions may not exist

    # 5. Store DB profile for similarity calculation
    table_names = [r["table_name"] for r in knowledge_conn.execute(
        "SELECT table_name FROM current_db_tables"
    ).fetchall()]
    col_names = [r["column_name"] for r in cols]
    cross_conn.execute(
        "INSERT OR REPLACE INTO cross_db_profiles "
        "(db_name, table_names, column_names, table_count, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (db_name, json.dumps(table_names), json.dumps(col_names), len(table_names), now),
    )

    cross_conn.commit()
    cross_conn.close()
    return counts


def _extract_naming_patterns(cols: list) -> dict[str, list[str]]:
    """Group columns by naming convention suffix/prefix patterns.

    Returns dict mapping pattern name to list of example column names.
    Patterns detected: _id, _at, _flag, is_, has_, _count, _name, _code,
    _status, _type.
    """
    patterns: dict[str, list[str]] = {}
    suffixes = ["_id", "_at", "_flag", "_count", "_name", "_code", "_status", "_type"]
    prefixes = ["is_", "has_"]

    for row in cols:
        col = row["column_name"].lower() if hasattr(row, "keys") else row[0].lower()
        for suffix in suffixes:
            if col.endswith(suffix):
                patterns.setdefault(f"suffix:{suffix}", []).append(col)
                break
        for prefix in prefixes:
            if col.startswith(prefix):
                patterns.setdefault(f"prefix:{prefix}", []).append(col)
                break

    return patterns


def _detect_schema_shapes(conn: sqlite3.Connection) -> dict[str, dict]:
    """Detect common schema patterns: audit columns, soft delete, polymorphic.

    Returns dict mapping shape name to metadata dict.
    """
    shapes: dict[str, dict] = {}

    try:
        col_names = {
            row["column_name"].lower()
            for row in conn.execute(
                "SELECT column_name FROM current_db_columns"
            ).fetchall()
        }

        # Audit columns pattern: both created_at and updated_at present
        if "created_at" in col_names and "updated_at" in col_names:
            shapes["audit_columns"] = {
                "has_created_at": True,
                "has_updated_at": True,
            }

        # Soft delete pattern: is_deleted or deleted_at column present
        if "is_deleted" in col_names or "deleted_at" in col_names:
            shapes["soft_delete"] = {
                "has_is_deleted": "is_deleted" in col_names,
                "has_deleted_at": "deleted_at" in col_names,
            }

        # Polymorphic association pattern: entity_type + entity_id columns present
        if "entity_type" in col_names and "entity_id" in col_names:
            shapes["polymorphic"] = {
                "has_entity_type": True,
                "has_entity_id": True,
            }
    except Exception:
        pass

    return shapes


def _upsert_pattern(
    conn: sqlite3.Connection,
    pattern_type: str,
    pattern_key: str,
    pattern_value: str,
    source_db: str,
    created_at: str,
) -> None:
    """INSERT OR REPLACE a pattern into cross_patterns."""
    conn.execute(
        "INSERT OR REPLACE INTO cross_patterns "
        "(pattern_type, pattern_key, pattern_value, source_db, confidence, created_at) "
        "VALUES (?, ?, ?, ?, 0.5, ?)",
        (pattern_type, pattern_key, pattern_value, source_db, created_at),
    )
