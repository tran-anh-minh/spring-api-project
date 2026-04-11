"""JSON schema exporter (EXPORT-03).

Exports knowledge store as structured JSON with tables, columns, relationships.
"""
import json
import sqlite3


class JsonSchemaExporter:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def export_all(self) -> str:
        """Generate JSON schema representation."""
        tables = self._conn.execute(
            "SELECT id, table_name, description FROM current_db_tables"
        ).fetchall()
        result: dict = {"tables": [], "relationships": []}
        for t in tables:
            cols = self._conn.execute(
                "SELECT column_name, data_type, is_nullable, is_primary_key "
                "FROM current_db_columns WHERE table_id = ? "
                "ORDER BY ordinal_position, id",
                (t["id"],),
            ).fetchall()
            result["tables"].append({
                "name": t["table_name"],
                "description": t["description"] or "",
                "columns": [
                    {
                        "name": c["column_name"],
                        "type": c["data_type"] or "TEXT",
                        "nullable": bool(c["is_nullable"]),
                        "primary_key": bool(c["is_primary_key"]),
                    }
                    for c in cols
                ],
            })
        rels = self._conn.execute(
            "SELECT source_id, target_id, relationship_type, confidence "
            "FROM current_db_relationships"
        ).fetchall()
        # Build ID-to-name map
        name_map = {t["id"]: t["table_name"] for t in tables}
        for r in rels:
            result["relationships"].append({
                "source": name_map.get(r["source_id"], str(r["source_id"])),
                "target": name_map.get(r["target_id"], str(r["target_id"])),
                "type": r["relationship_type"],
                "confidence": r["confidence"] or 1.0,
            })
        return json.dumps(result, indent=2) + "\n"
