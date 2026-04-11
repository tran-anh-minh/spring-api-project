"""Markdown wiki exporter (EXPORT-03).

Generates markdown files from L1/L2 wiki pages for each entity.
"""
import sqlite3
from db_wiki.query.wiki import get_wiki_page


class MarkdownExporter:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def export_all(self) -> dict[str, str]:
        """Export all entities as markdown. Returns {filename: content}."""
        results = {}
        # Tables
        tables = self._conn.execute(
            "SELECT id, table_name FROM current_db_tables"
        ).fetchall()
        for t in tables:
            name = t["table_name"]
            l1 = get_wiki_page(self._conn, "table", t["id"], "L1")
            l2 = get_wiki_page(self._conn, "table", t["id"], "L2")
            content = f"# {name}\n\n## Overview\n\n{l1}\n\n## Details\n\n{l2}\n"
            results[f"tables/{name}.md"] = content
        # Procedures
        procs = self._conn.execute(
            "SELECT id, procedure_name FROM current_db_procedures"
        ).fetchall()
        for p in procs:
            name = p["procedure_name"]
            l1 = get_wiki_page(self._conn, "procedure", p["id"], "L1")
            l2 = get_wiki_page(self._conn, "procedure", p["id"], "L2")
            content = f"# {name}\n\n## Overview\n\n{l1}\n\n## Details\n\n{l2}\n"
            results[f"procedures/{name}.md"] = content
        return results

    def export_entity(self, entity_type: str, entity_name: str) -> str | None:
        """Export a single entity by name."""
        if entity_type == "table":
            row = self._conn.execute(
                "SELECT id FROM current_db_tables WHERE table_name = ?",
                (entity_name,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT id FROM current_db_procedures WHERE procedure_name = ?",
                (entity_name,),
            ).fetchone()
        if not row:
            return None
        l1 = get_wiki_page(self._conn, entity_type, row["id"], "L1")
        l2 = get_wiki_page(self._conn, entity_type, row["id"], "L2")
        return f"# {entity_name}\n\n## Overview\n\n{l1}\n\n## Details\n\n{l2}\n"
