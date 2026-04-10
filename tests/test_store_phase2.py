"""Tests for Phase 2 SP Pydantic models and store sqlite-vec integration."""
import sqlite3
from pathlib import Path

import pytest

from db_wiki.core.store import open_store, init_schema


# ---------------------------------------------------------------------------
# Test 1: SPInfo model fields
# ---------------------------------------------------------------------------

class TestSPInfoModel:
    def test_spinfo_fields(self) -> None:
        from db_wiki.core.models import SPInfo

        sp = SPInfo(procedure_name="usp_CreateOrder")
        assert sp.procedure_name == "usp_CreateOrder"
        assert sp.schema_name is None
        assert sp.body_hash == ""
        assert sp.table_refs == []
        assert sp.mutations == []
        assert sp.branches == []
        assert sp.call_chains == []
        assert sp.enum_detections == []
        assert sp.state_transitions == []
        assert sp.parse_quality == 1.0
        assert sp.is_degraded is False
        assert sp.has_dynamic_sql is False
        assert sp.partial_ast is False
        assert sp.dynamic_sql_locations == []
        assert sp.warnings == []


# ---------------------------------------------------------------------------
# Test 2: MutationInfo model
# ---------------------------------------------------------------------------

class TestMutationInfoModel:
    def test_mutation_info_fields(self) -> None:
        from db_wiki.core.models import MutationInfo

        m = MutationInfo(table_name="Orders", mutation_type="insert")
        assert m.table_name == "Orders"
        assert m.mutation_type == "insert"
        assert m.columns == []

        m2 = MutationInfo(
            table_name="Orders", mutation_type="update", columns=["Status", "ModifiedDate"]
        )
        assert m2.columns == ["Status", "ModifiedDate"]


# ---------------------------------------------------------------------------
# Test 3: BranchInfo model
# ---------------------------------------------------------------------------

class TestBranchInfoModel:
    def test_branch_info_fields(self) -> None:
        from db_wiki.core.models import BranchInfo

        b = BranchInfo(branch_index=0, branch_type="if")
        assert b.branch_index == 0
        assert b.condition_text is None
        assert b.branch_type == "if"
        assert b.tables_touched == []
        assert b.nesting_depth == 0

        b2 = BranchInfo(
            branch_index=1,
            condition_text="@Status = 'Active'",
            branch_type="case_when",
            tables_touched=["Orders"],
            nesting_depth=2,
        )
        assert b2.condition_text == "@Status = 'Active'"
        assert b2.tables_touched == ["Orders"]
        assert b2.nesting_depth == 2


# ---------------------------------------------------------------------------
# Test 4: CallChainInfo model
# ---------------------------------------------------------------------------

class TestCallChainInfoModel:
    def test_call_chain_info_fields(self) -> None:
        from db_wiki.core.models import CallChainInfo

        c = CallChainInfo(callee_name="usp_SendEmail")
        assert c.callee_name == "usp_SendEmail"
        assert c.callee_schema is None
        assert c.is_dynamic is False

        c2 = CallChainInfo(
            callee_name="usp_AuditLog", callee_schema="audit", is_dynamic=True
        )
        assert c2.callee_schema == "audit"
        assert c2.is_dynamic is True


# ---------------------------------------------------------------------------
# Test 5: EnumDetection model
# ---------------------------------------------------------------------------

class TestEnumDetectionModel:
    def test_enum_detection_fields(self) -> None:
        from db_wiki.core.models import EnumDetection

        e = EnumDetection(
            table_name="Orders",
            column_name="Status",
            detection_method="case_when",
        )
        assert e.table_name == "Orders"
        assert e.column_name == "Status"
        assert e.values == []
        assert e.confidence == 0.5
        assert e.detection_method == "case_when"

        e2 = EnumDetection(
            table_name="Orders",
            column_name="Status",
            values=[{"value": "A", "label": "Active"}, {"value": "I", "label": "Inactive"}],
            confidence=0.8,
            detection_method="case_when",
        )
        assert len(e2.values) == 2
        assert e2.confidence == 0.8


# ---------------------------------------------------------------------------
# Test 6: StateTransitionInfo model
# ---------------------------------------------------------------------------

class TestStateTransitionInfoModel:
    def test_state_transition_info_fields(self) -> None:
        from db_wiki.core.models import StateTransitionInfo

        st = StateTransitionInfo(
            table_name="Orders",
            column_name="Status",
            from_value="Pending",
            to_value="Shipped",
        )
        assert st.table_name == "Orders"
        assert st.column_name == "Status"
        assert st.from_value == "Pending"
        assert st.to_value == "Shipped"
        assert st.confidence == 0.9


# ---------------------------------------------------------------------------
# Test 7: SPParseResult model
# ---------------------------------------------------------------------------

class TestSPParseResultModel:
    def test_sp_parse_result_fields(self) -> None:
        from db_wiki.core.models import SPParseResult, SPInfo, RelationshipInfo

        r = SPParseResult()
        assert r.procedures == []
        assert r.relationships == []
        assert r.warnings == []

        r2 = SPParseResult(
            procedures=[SPInfo(procedure_name="usp_Test")],
            relationships=[
                RelationshipInfo(
                    source_table="A",
                    target_table="B",
                    relationship_type="reads_from",
                )
            ],
            warnings=["Dynamic SQL found"],
        )
        assert len(r2.procedures) == 1
        assert len(r2.relationships) == 1
        assert r2.warnings == ["Dynamic SQL found"]


# ---------------------------------------------------------------------------
# Test 8: open_store loads sqlite-vec
# ---------------------------------------------------------------------------

class TestStoreVecExtension:
    def test_open_store_loads_sqlite_vec(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".db-wiki" / "knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = open_store(db_path)
        row = conn.execute("SELECT vec_version()").fetchone()
        assert row is not None
        assert row[0].startswith("v")
        conn.close()


# ---------------------------------------------------------------------------
# Test 9: init_vec_table with 384 dimensions
# ---------------------------------------------------------------------------

class TestInitVecTable:
    def test_init_vec_table_384(self, tmp_path: Path) -> None:
        from db_wiki.core.store import init_vec_table

        db_path = tmp_path / ".db-wiki" / "knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = open_store(db_path)
        init_schema(conn)
        init_vec_table(conn, 384)

        # Verify table exists
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vec_embeddings_384'"
        ).fetchone()
        assert row[0] == 1
        conn.close()

    # ---------------------------------------------------------------------------
    # Test 10: init_vec_table with 1536 dimensions
    # ---------------------------------------------------------------------------

    def test_init_vec_table_1536(self, tmp_path: Path) -> None:
        from db_wiki.core.store import init_vec_table

        db_path = tmp_path / ".db-wiki" / "knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = open_store(db_path)
        init_schema(conn)
        init_vec_table(conn, 1536)

        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vec_embeddings_1536'"
        ).fetchone()
        assert row[0] == 1
        conn.close()

    def test_init_vec_table_idempotent(self, tmp_path: Path) -> None:
        """Calling init_vec_table twice should not error."""
        from db_wiki.core.store import init_vec_table

        db_path = tmp_path / ".db-wiki" / "knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = open_store(db_path)
        init_schema(conn)
        init_vec_table(conn, 384)
        init_vec_table(conn, 384)  # Should not raise
        conn.close()
