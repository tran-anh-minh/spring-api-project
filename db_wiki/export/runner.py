"""Export runner -- orchestrates format-specific exporters (EXPORT-03, D-11).

Supports:
- All formats at once: run_export(conn, output_dir)
- Per-format: run_export(conn, output_dir, formats=["markdown", "mermaid"])
- Per-entity: run_export(conn, output_dir, entity_name="orders", entity_type="table")
"""
import sqlite3
from pathlib import Path

from db_wiki.export.markdown import MarkdownExporter
from db_wiki.export.mermaid import MermaidExporter
from db_wiki.export.json_schema import JsonSchemaExporter
from db_wiki.export.ddl_annotated import AnnotatedDDLExporter

ALL_FORMATS = ["markdown", "mermaid", "json", "ddl"]


def run_export(
    conn: sqlite3.Connection,
    output_dir: Path,
    formats: list[str] | None = None,
    entity_name: str | None = None,
    entity_type: str = "table",
) -> dict[str, str]:
    """Run export for selected formats.

    Args:
        conn: Knowledge store connection.
        output_dir: Directory to write export files (e.g. .db-wiki/export/).
            Resolved to absolute path to prevent path traversal (T-05-10).
        formats: List of format names. None = all formats.
        entity_name: If set, export only this entity. None = all entities.
        entity_type: "table" or "procedure" (used with entity_name).

    Returns:
        Dict mapping output file paths (relative to output_dir) to status.
    """
    # T-05-10: Resolve to absolute path so all writes stay within output_dir
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = formats or ALL_FORMATS
    results = {}

    if "markdown" in selected:
        exporter = MarkdownExporter(conn)
        if entity_name:
            content = exporter.export_entity(entity_type, entity_name)
            if content:
                path = output_dir / f"{entity_name}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                results[str(path)] = "written"
        else:
            files = exporter.export_all()
            for filename, content in files.items():
                path = output_dir / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                results[str(path)] = "written"

    if "mermaid" in selected:
        exporter = MermaidExporter(conn)
        content = exporter.export_all()
        path = output_dir / "er-diagram.mmd"
        path.write_text(content, encoding="utf-8")
        results[str(path)] = "written"

    if "json" in selected:
        exporter = JsonSchemaExporter(conn)
        content = exporter.export_all()
        path = output_dir / "schema.json"
        path.write_text(content, encoding="utf-8")
        results[str(path)] = "written"

    if "ddl" in selected:
        exporter = AnnotatedDDLExporter(conn)
        content = exporter.export_all()
        path = output_dir / "schema-annotated.sql"
        path.write_text(content, encoding="utf-8")
        results[str(path)] = "written"

    return results
