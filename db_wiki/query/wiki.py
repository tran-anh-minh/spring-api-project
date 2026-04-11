"""On-demand wiki page generator for knowledge store entities (EXPORT-02).

Generates L0 (one-line summary), L1 (column/relationship list), and L2 (full
detail) wiki pages for tables and stored procedures. Pages are cached in
wiki_pages with schema_version-based invalidation.

Cache strategy:
  - Cache hit: schema_version matches → return stored content
  - Cache miss / stale: generate fresh → invalidate old → store new
"""
import sqlite3
from datetime import datetime, timezone

from db_wiki.query.resolver import get_schema_version


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _get_table_row(conn: sqlite3.Connection, entity_id: int):
    return conn.execute(
        "SELECT id, table_name, description FROM current_db_tables WHERE id = ?",
        (entity_id,),
    ).fetchone()


def _get_procedure_row(conn: sqlite3.Connection, entity_id: int):
    return conn.execute(
        "SELECT id, procedure_name, description FROM current_db_procedures WHERE id = ?",
        (entity_id,),
    ).fetchone()


def _get_columns(conn: sqlite3.Connection, table_id: int):
    return conn.execute(
        "SELECT column_name, data_type, is_nullable, is_primary_key "
        "FROM current_db_columns WHERE table_id = ? ORDER BY ordinal_position, id",
        (table_id,),
    ).fetchall()


def _get_relationships(conn: sqlite3.Connection, source_id: int):
    """Get relationships where source_id is the source entity."""
    return conn.execute(
        "SELECT relationship_type, target_id, source_column, target_column "
        "FROM current_db_relationships WHERE source_id = ?",
        (source_id,),
    ).fetchall()


def _get_sp_table_refs(conn: sqlite3.Connection, procedure_id: int):
    """Get tables referenced by a procedure (reads_from relationships)."""
    return conn.execute(
        "SELECT r.target_id, t.table_name "
        "FROM current_db_relationships r "
        "LEFT JOIN current_db_tables t ON t.id = r.target_id "
        "WHERE r.source_id = ? AND r.relationship_type = 'reads_from'",
        (procedure_id,),
    ).fetchall()


def _get_sp_branches(conn: sqlite3.Connection, procedure_id: int):
    return conn.execute(
        "SELECT branch_index, branch_type, condition_text, tables_touched_json, nesting_depth "
        "FROM current_sp_branches WHERE procedure_id = ? ORDER BY branch_index",
        (procedure_id,),
    ).fetchall()


def _get_sp_reliability(conn: sqlite3.Connection, procedure_id: int):
    return conn.execute(
        "SELECT parse_quality, is_degraded, has_dynamic_sql "
        "FROM current_sp_reliability WHERE procedure_id = ?",
        (procedure_id,),
    ).fetchone()


def _get_sp_call_chains(conn: sqlite3.Connection, procedure_id: int):
    return conn.execute(
        "SELECT callee_name_raw, is_resolved FROM current_sp_call_chains WHERE caller_id = ?",
        (procedure_id,),
    ).fetchall()


def _get_enum_values(conn: sqlite3.Connection, table_name: str):
    return conn.execute(
        "SELECT column_name, enum_value, enum_label, confidence "
        "FROM current_enum_values WHERE table_name = ? "
        "ORDER BY column_name, enum_value",
        (table_name,),
    ).fetchall()


def _get_state_transitions(conn: sqlite3.Connection, table_name: str):
    return conn.execute(
        "SELECT column_name, from_value, to_value, confidence "
        "FROM current_state_transitions WHERE table_name = ? "
        "ORDER BY column_name",
        (table_name,),
    ).fetchall()


def _lookup_table_name(conn: sqlite3.Connection, table_id: int) -> str:
    row = conn.execute(
        "SELECT table_name FROM current_db_tables WHERE id = ?", (table_id,)
    ).fetchone()
    return row[0] if row else f"table#{table_id}"


# ---------------------------------------------------------------------------
# L0: One-line summary
# ---------------------------------------------------------------------------


def generate_wiki_l0(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> str:
    """Generate a one-line L0 summary for a table or procedure.

    Table: "{name} - {col_count} columns, {rel_count} relationships"
    Procedure: "{name} - touches {table_count} tables"

    Returns empty string if entity not found.
    """
    if entity_type == "table":
        row = _get_table_row(conn, entity_id)
        if not row:
            return f"table#{entity_id} - not found"
        name = row["table_name"]
        col_count = conn.execute(
            "SELECT COUNT(*) FROM current_db_columns WHERE table_id = ?",
            (entity_id,),
        ).fetchone()[0]
        rel_count = conn.execute(
            "SELECT COUNT(*) FROM current_db_relationships WHERE source_id = ?",
            (entity_id,),
        ).fetchone()[0]
        return f"{name} - {col_count} columns, {rel_count} relationships"

    elif entity_type == "procedure":
        row = _get_procedure_row(conn, entity_id)
        if not row:
            return f"procedure#{entity_id} - not found"
        name = row["procedure_name"]
        table_count = conn.execute(
            "SELECT COUNT(*) FROM current_db_relationships "
            "WHERE source_id = ? AND relationship_type = 'reads_from'",
            (entity_id,),
        ).fetchone()[0]
        return f"{name} - touches {table_count} tables"

    return ""


# ---------------------------------------------------------------------------
# L1: Column/relationship list
# ---------------------------------------------------------------------------


def generate_wiki_l1(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> str:
    """Generate L1 content (L0 summary + structured list) for a table or procedure.

    Table: L0 line + column list with types/constraints + relationship summary
    Procedure: L0 line + table refs + branch count + reliability score
    """
    l0 = generate_wiki_l0(conn, entity_type, entity_id)
    lines = [l0, ""]

    if entity_type == "table":
        columns = _get_columns(conn, entity_id)
        if columns:
            lines.append("Columns:")
            for col in columns:
                pk_marker = " [PK]" if col["is_primary_key"] else ""
                nullable = "" if col["is_nullable"] else " NOT NULL"
                lines.append(
                    f"  - {col['column_name']}: {col['data_type'] or 'unknown'}{nullable}{pk_marker}"
                )
        else:
            lines.append("Columns: (none)")

        rels = _get_relationships(conn, entity_id)
        if rels:
            lines.append("")
            lines.append("Relationships:")
            for rel in rels:
                target_name = _lookup_table_name(conn, rel["target_id"]) if rel["target_id"] else "unknown"
                lines.append(f"  - {rel['relationship_type']} -> {target_name}")

    elif entity_type == "procedure":
        table_refs = _get_sp_table_refs(conn, entity_id)
        if table_refs:
            lines.append("Tables touched:")
            for ref in table_refs:
                tname = ref["table_name"] or f"table#{ref['target_id']}"
                lines.append(f"  - {tname}")
        else:
            lines.append("Tables touched: (none)")

        branches = _get_sp_branches(conn, entity_id)
        lines.append(f"Branch count: {len(branches)}")

        reliability = _get_sp_reliability(conn, entity_id)
        if reliability:
            lines.append(f"Parse quality: {reliability['parse_quality']:.2f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# L2: Full detail
# ---------------------------------------------------------------------------


def generate_wiki_l2(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> str:
    """Generate L2 full detail content for a table or procedure.

    Table: L1 content + enum values + state transitions + SP references
    Procedure: L1 content + branch details + call chain + description
    """
    l1 = generate_wiki_l1(conn, entity_type, entity_id)
    lines = [l1]

    if entity_type == "table":
        row = _get_table_row(conn, entity_id)
        table_name = row["table_name"] if row else f"table#{entity_id}"

        enum_vals = _get_enum_values(conn, table_name)
        if enum_vals:
            lines.append("")
            lines.append("Enum Values:")
            current_col = None
            for ev in enum_vals:
                if ev["column_name"] != current_col:
                    current_col = ev["column_name"]
                    lines.append(f"  {current_col}:")
                label = f" ({ev['enum_label']})" if ev["enum_label"] else ""
                lines.append(f"    - {ev['enum_value']}{label}")

        transitions = _get_state_transitions(conn, table_name)
        if transitions:
            lines.append("")
            lines.append("State Transitions:")
            for tr in transitions:
                lines.append(
                    f"  - {tr['column_name']}: {tr['from_value']} -> {tr['to_value']}"
                )

    elif entity_type == "procedure":
        row = _get_procedure_row(conn, entity_id)
        if row and row["description"]:
            lines.append("")
            lines.append(f"Description: {row['description']}")

        branches = _get_sp_branches(conn, entity_id)
        if branches:
            lines.append("")
            lines.append("Branches:")
            for b in branches:
                cond = b["condition_text"] or "(no condition)"
                lines.append(f"  [{b['branch_type']}] {cond}")

        call_chain = _get_sp_call_chains(conn, entity_id)
        if call_chain:
            lines.append("")
            lines.append("Calls:")
            for cc in call_chain:
                resolved = " (resolved)" if cc["is_resolved"] else " (unresolved)"
                lines.append(f"  - {cc['callee_name_raw']}{resolved}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Caching layer
# ---------------------------------------------------------------------------


def _get_cached_page(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    tier: str,
    schema_version: int,
):
    """Return cached page content if it matches the current schema_version, else None."""
    row = conn.execute(
        "SELECT id, content, schema_version FROM current_wiki_pages "
        "WHERE entity_type = ? AND entity_id = ? AND tier = ?",
        (entity_type, entity_id, tier),
    ).fetchone()

    if row is None:
        return None

    if row["schema_version"] == schema_version:
        return row["content"]

    # Stale cache — invalidate it
    _invalidate_by_id(conn, row["id"])
    return None


def _invalidate_by_id(conn: sqlite3.Connection, page_id: int) -> None:
    now_iso = _now_iso()
    now_ts = _now_ts()
    conn.execute(
        "UPDATE wiki_pages SET invalidated_at = ?, invalidated_at_ts = ? "
        "WHERE id = ?",
        (now_iso, now_ts, page_id),
    )
    conn.commit()


def _store_page(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    tier: str,
    content: str,
    schema_version: int,
) -> None:
    now_iso = _now_iso()
    now_ts = _now_ts()
    conn.execute(
        "INSERT INTO wiki_pages "
        "(entity_type, entity_id, tier, content, schema_version, "
        " valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, tier, content, schema_version,
         now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()


def get_wiki_page(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    tier: str,
) -> str:
    """Return wiki page content for an entity at the given tier.

    Checks current_wiki_pages for a cached version matching the current
    schema_version. If found, returns it. Otherwise generates fresh content,
    invalidates any stale cache, and stores the new version.

    Args:
        conn: SQLite connection with initialized schema.
        entity_type: "table" or "procedure".
        entity_id: Entity row ID.
        tier: "L0", "L1", or "L2".

    Returns:
        Wiki page content string.
    """
    schema_version = get_schema_version(conn)
    cached = _get_cached_page(conn, entity_type, entity_id, tier, schema_version)
    if cached is not None:
        return cached

    # Generate fresh content
    generator = {
        "L0": generate_wiki_l0,
        "L1": generate_wiki_l1,
        "L2": generate_wiki_l2,
    }.get(tier)

    if generator is None:
        raise ValueError(f"Unknown wiki tier: {tier!r}. Expected 'L0', 'L1', or 'L2'.")

    content = generator(conn, entity_type, entity_id)
    _store_page(conn, entity_type, entity_id, tier, content, schema_version)
    return content


def invalidate_wiki_cache(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
) -> int:
    """Invalidate all current wiki pages for an entity.

    Sets invalidated_at/invalidated_at_ts on all non-invalidated rows
    matching (entity_type, entity_id).

    Args:
        conn: SQLite connection.
        entity_type: "table" or "procedure".
        entity_id: Entity row ID.

    Returns:
        Count of rows invalidated.
    """
    now_iso = _now_iso()
    now_ts = _now_ts()
    cur = conn.execute(
        "UPDATE wiki_pages SET invalidated_at = ?, invalidated_at_ts = ? "
        "WHERE entity_type = ? AND entity_id = ? AND invalidated_at IS NULL",
        (now_iso, now_ts, entity_type, entity_id),
    )
    conn.commit()
    return cur.rowcount


def generate_wiki_markdown(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
) -> str:
    """Generate a complete markdown wiki document for an entity (EXPORT-02).

    Combines L0, L1, and L2 content into a structured markdown document.

    Format:
        # {entity name}
        {L0 summary line}

        ## Summary
        {L1 content (excluding L0 line already shown)}

        ## Details
        {L2 additional content}

    Args:
        conn: SQLite connection.
        entity_type: "table" or "procedure".
        entity_id: Entity row ID.

    Returns:
        Full markdown document as a string.
    """
    l0 = generate_wiki_l0(conn, entity_type, entity_id)
    l1 = generate_wiki_l1(conn, entity_type, entity_id)
    l2 = generate_wiki_l2(conn, entity_type, entity_id)

    # Extract entity name from L0 (everything before " - ")
    name = l0.split(" - ")[0] if " - " in l0 else l0

    # Build markdown document
    sections = [
        f"# {name}",
        "",
        l0,
        "",
        "## Summary",
        "",
        l1,
        "",
        "## Details",
        "",
        l2,
    ]
    return "\n".join(sections)
