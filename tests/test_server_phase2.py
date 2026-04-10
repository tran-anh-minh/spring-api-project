"""Tests for Phase 2 MCP server tools and shared entity lookup (02-05).

Tests cover:
- db_wiki.core.queries lookup_entity_name and find_entity_by_name
- MCP tool registration for search, lineage, sp_info
- Tool parameter signatures
- Extended status tool with procedure/relationship counts
"""
import sqlite3

import pytest


# ---- Fixtures ----

@pytest.fixture
def db_with_entities(initialized_db: sqlite3.Connection) -> sqlite3.Connection:
    """Insert sample table and procedure entities for lookup tests."""
    conn = initialized_db
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_ts = int(now.timestamp())

    # Insert a table entity
    conn.execute(
        "INSERT INTO db_tables (table_name, schema_name, description, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Orders", "dbo", "Order table", now_iso, now_ts, now_iso, now_ts),
    )
    # Insert a procedure entity
    conn.execute(
        "INSERT INTO db_procedures (procedure_name, schema_name, description, "
        "valid_from, valid_from_ts, recorded_at, recorded_at_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("GetOrders", "dbo", "Get orders proc", now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()
    return conn


# ---- Tests for db_wiki.core.queries ----

class TestLookupEntityName:
    def test_returns_table_name(self, db_with_entities: sqlite3.Connection):
        from db_wiki.core.queries import lookup_entity_name

        conn = db_with_entities
        table_id = conn.execute(
            "SELECT id FROM current_db_tables WHERE table_name='Orders'"
        ).fetchone()[0]
        assert lookup_entity_name(conn, table_id) == "Orders"

    def test_returns_procedure_name(self, db_with_entities: sqlite3.Connection):
        from db_wiki.core.queries import lookup_entity_name

        conn = db_with_entities
        proc_id = conn.execute(
            "SELECT id FROM current_db_procedures WHERE procedure_name='GetOrders'"
        ).fetchone()[0]
        assert lookup_entity_name(conn, proc_id) == "GetOrders"

    def test_returns_fallback_for_unknown(self, db_with_entities: sqlite3.Connection):
        from db_wiki.core.queries import lookup_entity_name

        assert lookup_entity_name(db_with_entities, 99999) == "entity#99999"


class TestFindEntityByName:
    def test_finds_table(self, db_with_entities: sqlite3.Connection):
        from db_wiki.core.queries import find_entity_by_name

        conn = db_with_entities
        entity_id, entity_type = find_entity_by_name(conn, "Orders")
        assert entity_id is not None
        assert entity_type == "table"

    def test_finds_procedure(self, db_with_entities: sqlite3.Connection):
        from db_wiki.core.queries import find_entity_by_name

        conn = db_with_entities
        entity_id, entity_type = find_entity_by_name(conn, "GetOrders")
        assert entity_id is not None
        assert entity_type == "procedure"

    def test_returns_none_for_unknown(self, db_with_entities: sqlite3.Connection):
        from db_wiki.core.queries import find_entity_by_name

        entity_id, entity_type = find_entity_by_name(db_with_entities, "NonExistent")
        assert entity_id is None
        assert entity_type is None


# ---- Tests for MCP tool registration ----

class TestMCPToolRegistration:
    def test_search_tool_registered(self):
        from db_wiki.server.app import mcp

        tools = mcp._tool_manager.list_tools()
        tool_names = [t.name for t in tools]
        assert "search" in tool_names

    def test_lineage_tool_registered(self):
        from db_wiki.server.app import mcp

        tools = mcp._tool_manager.list_tools()
        tool_names = [t.name for t in tools]
        assert "lineage" in tool_names

    def test_sp_info_tool_registered(self):
        from db_wiki.server.app import mcp

        tools = mcp._tool_manager.list_tools()
        tool_names = [t.name for t in tools]
        assert "sp_info" in tool_names


# ---- Tests for tool parameter signatures ----

class TestToolSignatures:
    def _get_tool_schema(self, tool_name: str) -> dict:
        from db_wiki.server.app import mcp

        tools = mcp._tool_manager.list_tools()
        for t in tools:
            if t.name == tool_name:
                return t.inputSchema
        raise ValueError(f"Tool {tool_name} not found")

    def test_search_accepts_query(self):
        schema = self._get_tool_schema("search")
        assert "query" in schema.get("properties", {})

    def test_search_accepts_limit(self):
        schema = self._get_tool_schema("search")
        assert "limit" in schema.get("properties", {})

    def test_search_accepts_fts_weight(self):
        schema = self._get_tool_schema("search")
        assert "fts_weight" in schema.get("properties", {})

    def test_lineage_accepts_entity_name(self):
        schema = self._get_tool_schema("lineage")
        assert "entity_name" in schema.get("properties", {})

    def test_lineage_accepts_max_depth(self):
        schema = self._get_tool_schema("lineage")
        assert "max_depth" in schema.get("properties", {})

    def test_lineage_accepts_edge_types(self):
        schema = self._get_tool_schema("lineage")
        assert "edge_types" in schema.get("properties", {})

    def test_sp_info_accepts_procedure_name(self):
        schema = self._get_tool_schema("sp_info")
        assert "procedure_name" in schema.get("properties", {})


# ---- Tests for extended status tool ----

class TestStatusExtended:
    def test_status_tool_registered(self):
        """status tool still registered (no regression)."""
        from db_wiki.server.app import mcp

        tools = mcp._tool_manager.list_tools()
        tool_names = [t.name for t in tools]
        assert "status" in tool_names
