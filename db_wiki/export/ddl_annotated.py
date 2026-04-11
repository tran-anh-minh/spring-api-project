"""Annotated DDL exporter (EXPORT-03).

Generates CREATE TABLE DDL with inline comments from wiki descriptions.
"""
import sqlite3


class AnnotatedDDLExporter:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def export_all(self) -> str:
        """Generate annotated DDL for all tables."""
        tables = self._conn.execute(
            "SELECT id, table_name, description FROM current_db_tables"
        ).fetchall()
        parts = []
        for t in tables:
            desc = t["description"] or ""
            header = f"-- {desc}" if desc else f"-- Table: {t['table_name']}"
            cols = self._conn.execute(
                "SELECT column_name, data_type, is_nullable, is_primary_key "
                "FROM current_db_columns WHERE table_id = ? "
                "ORDER BY ordinal_position, id",
                (t["id"],),
            ).fetchall()
            col_lines = []
            for c in cols:
                dtype = c["data_type"] or "TEXT"
                nullable = "" if c["is_nullable"] else " NOT NULL"
                pk = " PRIMARY KEY" if c["is_primary_key"] else ""
                col_lines.append(f"  {c['column_name']} {dtype}{nullable}{pk}")
            create = (
                f"{header}\n"
                f"CREATE TABLE {t['table_name']} (\n"
                + ",\n".join(col_lines)
                + "\n);\n"
            )
            parts.append(create)
        return "\n".join(parts)
