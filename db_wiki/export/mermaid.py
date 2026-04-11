"""Mermaid ER diagram exporter (EXPORT-03).

Generates erDiagram syntax from knowledge store tables and FK relationships.
No external library needed — Mermaid is a text format.
"""
import sqlite3


class MermaidExporter:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def export_all(self) -> str:
        """Generate Mermaid erDiagram for all tables."""
        lines = ["erDiagram"]
        tables = self._conn.execute(
            "SELECT id, table_name FROM current_db_tables"
        ).fetchall()
        table_name_map = {t["id"]: t["table_name"] for t in tables}

        for t in tables:
            cols = self._conn.execute(
                "SELECT column_name, data_type, is_primary_key "
                "FROM current_db_columns WHERE table_id = ? "
                "ORDER BY ordinal_position, id",
                (t["id"],),
            ).fetchall()
            lines.append(f'  {t["table_name"]} {{')
            for c in cols:
                dtype = (c["data_type"] or "TEXT").replace(" ", "_")
                pk = " PK" if c["is_primary_key"] else ""
                lines.append(f'    {dtype} {c["column_name"]}{pk}')
            lines.append("  }")

        # FK relationships
        rels = self._conn.execute(
            "SELECT source_id, target_id, relationship_type "
            "FROM current_db_relationships "
            "WHERE relationship_type IN ('fk_declared', 'fk_inferred')"
        ).fetchall()
        for r in rels:
            src = table_name_map.get(r["source_id"], "?")
            tgt = table_name_map.get(r["target_id"], "?")
            if src != "?" and tgt != "?":
                rel_label = "FK" if r["relationship_type"] == "fk_declared" else "inferred"
                lines.append(f'  {src} ||--o{{ {tgt} : "{rel_label}"')

        return "\n".join(lines) + "\n"
