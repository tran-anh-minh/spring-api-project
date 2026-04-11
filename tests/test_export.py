"""Phase 5 Wave 0 test stubs for export formatters (EXPORT-03).

All tests are marked xfail — they verify the contracts that the Phase 5
export implementation must satisfy.
"""
import json

import pytest


XFAIL_REASON = "Phase 5 Wave 0 stub — not yet implemented"


# ---------------------------------------------------------------------------
# EXPORT-03: Markdown exporter
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_markdown_exporter(tmp_path):
    """MarkdownExporter.export() produces output containing a '# ' heading. (EXPORT-03)"""
    from db_wiki.export.markdown import MarkdownExporter

    exporter = MarkdownExporter(store_path=tmp_path)
    output = exporter.export()
    assert "# " in output


# ---------------------------------------------------------------------------
# EXPORT-03: Mermaid exporter
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_mermaid_exporter(tmp_path):
    """MermaidExporter.export() produces output containing 'erDiagram'. (EXPORT-03)"""
    from db_wiki.export.mermaid import MermaidExporter

    exporter = MermaidExporter(store_path=tmp_path)
    output = exporter.export()
    assert "erDiagram" in output


# ---------------------------------------------------------------------------
# EXPORT-03: JSON schema exporter
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_json_schema_exporter(tmp_path):
    """JsonSchemaExporter.export() produces valid JSON with 'tables' key. (EXPORT-03)"""
    from db_wiki.export.json_schema import JsonSchemaExporter

    exporter = JsonSchemaExporter(store_path=tmp_path)
    output = exporter.export()
    data = json.loads(output)
    assert "tables" in data


# ---------------------------------------------------------------------------
# EXPORT-03: Annotated DDL exporter
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_ddl_annotated_exporter(tmp_path):
    """AnnotatedDDLExporter.export() produces DDL with CREATE TABLE and '-- ' comments. (EXPORT-03)"""
    from db_wiki.export.ddl_annotated import AnnotatedDDLExporter

    exporter = AnnotatedDDLExporter(store_path=tmp_path)
    output = exporter.export()
    assert "CREATE TABLE" in output
    assert "-- " in output
