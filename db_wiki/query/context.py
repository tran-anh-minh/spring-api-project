"""L0/L1/L2 tiered context assembler for the NL-to-SQL pipeline.

Builds schema context in three levels of detail:
  L2 (core tables)    — full detail: columns, constraints, enums, state machines
  L1 (related tables) — medium detail: columns with types and key relationships
  L0 (all others)     — summary: one-line table name + column count

Token budget is enforced to stay under DEFAULT_TOKEN_BUDGET (8000 tokens).
L1 entries are dropped (lowest-scored last, since related_entity_ids is sorted
by relevance score descending) when budget is tight.

Security note (T-04-05): Context reads from local SQLite knowledge store only.
Schema information is intentionally shared with LLM for SQL generation.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# Approximate character-to-token ratio for schema text
CHARS_PER_TOKEN = 3.5

# Default total token budget (question + instructions + schema context)
DEFAULT_TOKEN_BUDGET: int = 8000

# Tokens reserved for question + system instructions
_RESERVED_TOKENS: int = 3000


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length.

    Uses a fixed ratio of 3.5 chars per token, which is a good approximation
    for schema text (SQL identifiers, type names, brief descriptions).

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count (minimum 1).
    """
    return max(1, int(len(text) / CHARS_PER_TOKEN))


@dataclass
class ContextResult:
    """Result of context assembly."""

    text: str
    token_count: int
    l0_count: int  # number of tables in L0 (summary) section
    l1_count: int  # number of tables in L1 (medium detail) section
    l2_count: int  # number of tables in L2 (full detail) section


def assemble_context(
    conn: sqlite3.Connection,
    core_entity_ids: list[int],
    related_entity_ids: list[int],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> ContextResult:
    """Assemble L0/L1/L2 tiered schema context within a token budget.

    Args:
        conn: SQLite connection to the knowledge store.
        core_entity_ids: Table IDs for L2 (full detail). Usually 3-7 tables
            most directly relevant to the question.
        related_entity_ids: Table IDs for L1 (medium detail), sorted by
            relevance score descending. Lower-scored entries are dropped
            first when budget is tight.
        token_budget: Maximum tokens for the combined context output.
            Default 8000. 3000 tokens are reserved for question + instructions.

    Returns:
        ContextResult with combined text and per-level counts.
    """
    schema_budget = token_budget - _RESERVED_TOKENS
    if schema_budget <= 0:
        # Extremely small budget — return empty context
        return ContextResult(text="", token_count=1, l0_count=0, l1_count=0, l2_count=0)

    used_tokens = 0
    sections: list[str] = []

    # ---- L2: Full detail for core tables -----------------------------------
    l2_blocks: list[str] = []
    core_set = set(core_entity_ids)

    for table_id in core_entity_ids:
        block = _build_l2_block(conn, table_id)
        if not block:
            continue
        block_tokens = estimate_tokens(block)
        if used_tokens + block_tokens > schema_budget:
            break  # stop adding L2 blocks when budget exhausted
        l2_blocks.append(block)
        used_tokens += block_tokens

    if l2_blocks:
        sections.append("== L2: Core Tables (Full Detail) ==\n" + "\n\n".join(l2_blocks))

    # ---- L1: Medium detail for related tables ------------------------------
    l1_blocks: list[str] = []

    for table_id in related_entity_ids:
        if table_id in core_set:
            continue  # Already in L2
        block = _build_l1_block(conn, table_id)
        if not block:
            continue
        block_tokens = estimate_tokens(block)
        if used_tokens + block_tokens <= schema_budget:
            l1_blocks.append(block)
            used_tokens += block_tokens
        # related_entity_ids is sorted score-descending; continue trying
        # smaller entries that might still fit

    if l1_blocks:
        sections.append("== L1: Related Tables (Column Summary) ==\n" + "\n\n".join(l1_blocks))

    # ---- L0: One-line summary for all other tables -------------------------
    l0_lines: list[str] = []
    all_table_ids = _get_all_table_ids(conn)
    l1_ids = {tid for tid in related_entity_ids if tid not in core_set}
    l0_set = all_table_ids - core_set - l1_ids

    for _table_id, table_name, col_count in _get_table_summaries(conn, l0_set):
        line = f"  {table_name} ({col_count} cols)"
        line_tokens = estimate_tokens(line)
        if used_tokens + line_tokens <= schema_budget:
            l0_lines.append(line)
            used_tokens += line_tokens
        # Stop adding L0 lines when budget reached
        # (L0 is purely informational; truncation is acceptable)

    if l0_lines:
        sections.append("== L0: All Tables (Summary) ==\n" + "\n".join(l0_lines))

    text = "\n\n".join(sections)
    token_count = estimate_tokens(text) if text else 1

    return ContextResult(
        text=text,
        token_count=token_count,
        l0_count=len(l0_lines),
        l1_count=len(l1_blocks),
        l2_count=len(l2_blocks),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_l2_block(conn: sqlite3.Connection, table_id: int) -> str:
    """Build full-detail block for a core table (L2)."""
    table_row = conn.execute(
        "SELECT table_name, description FROM current_db_tables WHERE id = ?",
        (table_id,),
    ).fetchone()
    if table_row is None:
        return ""

    table_name = table_row["table_name"]
    desc = table_row["description"] or ""

    lines = [f"Table: {table_name}"]
    if desc:
        lines.append(f"  Description: {desc}")

    # Columns
    cols = conn.execute(
        """SELECT column_name, data_type, is_nullable, is_primary_key
           FROM current_db_columns
           WHERE table_id = ?
           ORDER BY ordinal_position, id""",
        (table_id,),
    ).fetchall()

    if cols:
        lines.append("  Columns:")
        for col in cols:
            pk_mark = " [PK]" if col["is_primary_key"] else ""
            null_mark = " NULL" if col["is_nullable"] else " NOT NULL"
            lines.append(f"    {col['column_name']} {col['data_type'] or 'TEXT'}{pk_mark}{null_mark}")

    # Relationships
    rels = conn.execute(
        """SELECT r.relationship_type, r.source_column, r.target_column,
                  t_src.table_name AS src_table, t_tgt.table_name AS tgt_table
           FROM current_db_relationships r
           LEFT JOIN current_db_tables t_src ON t_src.id = r.source_id
           LEFT JOIN current_db_tables t_tgt ON t_tgt.id = r.target_id
           WHERE r.source_id = ? OR r.target_id = ?
           LIMIT 20""",
        (table_id, table_id),
    ).fetchall()

    if rels:
        lines.append("  Relationships:")
        for rel in rels:
            lines.append(
                f"    {rel['src_table']}.{rel['source_column'] or '*'} "
                f"--[{rel['relationship_type']}]--> "
                f"{rel['tgt_table']}.{rel['target_column'] or '*'}"
            )

    # Enum values
    enums = conn.execute(
        """SELECT column_name, enum_value, enum_label
           FROM current_enum_values
           WHERE table_name = ?
           LIMIT 30""",
        (table_name,),
    ).fetchall()

    if enums:
        lines.append("  Enum Values:")
        from itertools import groupby
        for col_name, group in groupby(enums, key=lambda r: r["column_name"]):
            values = ", ".join(
                f"{r['enum_value']}={r['enum_label']}" if r["enum_label"] else r["enum_value"]
                for r in group
            )
            lines.append(f"    {col_name}: {values}")

    # State transitions
    transitions = conn.execute(
        """SELECT column_name, from_value, to_value
           FROM current_state_transitions
           WHERE table_name = ?
           LIMIT 20""",
        (table_name,),
    ).fetchall()

    if transitions:
        lines.append("  State Transitions:")
        for tr in transitions:
            lines.append(f"    {tr['column_name']}: {tr['from_value']} -> {tr['to_value']}")

    return "\n".join(lines)


def _build_l1_block(conn: sqlite3.Connection, table_id: int) -> str:
    """Build medium-detail block for a related table (L1)."""
    table_row = conn.execute(
        "SELECT table_name FROM current_db_tables WHERE id = ?",
        (table_id,),
    ).fetchone()
    if table_row is None:
        return ""

    table_name = table_row["table_name"]
    lines = [f"Table: {table_name}"]

    # Columns (name, data_type, is_pk only)
    cols = conn.execute(
        """SELECT column_name, data_type, is_primary_key
           FROM current_db_columns
           WHERE table_id = ?
           ORDER BY ordinal_position, id""",
        (table_id,),
    ).fetchall()

    if cols:
        col_parts = []
        for col in cols:
            pk_mark = " [PK]" if col["is_primary_key"] else ""
            col_parts.append(f"{col['column_name']} {col['data_type'] or 'TEXT'}{pk_mark}")
        lines.append("  Columns: " + ", ".join(col_parts))

    # Key relationships (FK declared only)
    rels = conn.execute(
        """SELECT r.relationship_type, r.source_column, r.target_column,
                  t_tgt.table_name AS tgt_table
           FROM current_db_relationships r
           LEFT JOIN current_db_tables t_tgt ON t_tgt.id = r.target_id
           WHERE r.source_id = ? AND r.relationship_type = 'fk_declared'
           LIMIT 5""",
        (table_id,),
    ).fetchall()

    if rels:
        for rel in rels:
            lines.append(
                f"  FK: {rel['source_column']} -> {rel['tgt_table']}.{rel['target_column'] or '*'}"
            )

    return "\n".join(lines)


def _get_all_table_ids(conn: sqlite3.Connection) -> set[int]:
    """Return set of all current table IDs."""
    rows = conn.execute("SELECT id FROM current_db_tables").fetchall()
    return {r["id"] for r in rows}


def _get_table_summaries(
    conn: sqlite3.Connection, table_ids: set[int]
) -> list[tuple[int, str, int]]:
    """Return (id, table_name, col_count) tuples for the given table IDs."""
    if not table_ids:
        return []

    placeholders = ",".join("?" * len(table_ids))
    rows = conn.execute(
        f"""SELECT t.id, t.table_name,
                   COUNT(c.id) AS col_count
            FROM current_db_tables t
            LEFT JOIN current_db_columns c ON c.table_id = t.id
            WHERE t.id IN ({placeholders})
            GROUP BY t.id, t.table_name
            ORDER BY t.table_name""",
        list(table_ids),
    ).fetchall()

    return [(r["id"], r["table_name"], r["col_count"]) for r in rows]
