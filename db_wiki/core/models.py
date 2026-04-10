"""Pydantic models for parsed DDL entities.

These are intermediate data structures that bridge sqlglot AST output to
SQLite INSERT statements. They are NOT ORM models — they represent parsed
schema information before it is written to the bi-temporal knowledge store.
"""

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    """Represents a column parsed from a CREATE TABLE statement."""

    column_name: str
    data_type: str | None = None
    is_nullable: bool = True
    is_primary_key: bool = False
    is_unique: bool = False
    default_value: str | None = None
    ordinal_position: int | None = None


class ConstraintInfo(BaseModel):
    """Represents a table-level constraint (PK, FK, UNIQUE)."""

    constraint_type: str  # "PRIMARY KEY", "FOREIGN KEY", "UNIQUE"
    columns: list[str]
    ref_table: str | None = None  # FK target table
    ref_columns: list[str] | None = None  # FK target columns


class IndexInfo(BaseModel):
    """Represents a CREATE INDEX statement."""

    index_name: str
    table_name: str
    schema_name: str | None = None
    is_unique: bool = False
    columns: list[str]


class TableInfo(BaseModel):
    """Represents a CREATE TABLE statement with its columns and constraints."""

    table_name: str
    schema_name: str | None = None
    columns: list[ColumnInfo]
    constraints: list[ConstraintInfo] = []


class RelationshipInfo(BaseModel):
    """Represents a declared FK relationship between two tables."""

    source_table: str
    target_table: str
    relationship_type: str  # "fk_declared"
    source_column: str | None = None
    target_column: str | None = None
    confidence: float = 1.0


class ParseResult(BaseModel):
    """Aggregated result from parsing a DDL file."""

    tables: list[TableInfo] = []
    indexes: list[IndexInfo] = []
    relationships: list[RelationshipInfo] = []
    warnings: list[str] = []


# ===========================================================================
# Phase 2: SP Parsing Models
# ===========================================================================


class MutationInfo(BaseModel):
    """A write operation (INSERT/UPDATE/DELETE/MERGE) found in an SP."""

    table_name: str
    mutation_type: str  # "insert", "update", "delete", "merge"
    columns: list[str] = []


class BranchInfo(BaseModel):
    """A control flow branch extracted from an SP (IF/ELSE/CASE/WHILE)."""

    branch_index: int
    condition_text: str | None = None
    branch_type: str  # "if", "else", "case_when", "while"
    tables_touched: list[str] = []
    nesting_depth: int = 0


class CallChainInfo(BaseModel):
    """An EXEC/EXECUTE reference from one SP to another."""

    callee_name: str
    callee_schema: str | None = None
    is_dynamic: bool = False


class EnumDetection(BaseModel):
    """An enum value detected from CASE or naming heuristics."""

    table_name: str
    column_name: str
    values: list[dict] = []  # [{"value": "X", "label": "Y"}, ...]
    confidence: float = 0.5
    detection_method: str  # "case_when", "sp_name_heuristic", "column_name_heuristic"


class StateTransitionInfo(BaseModel):
    """A state transition detected from UPDATE SET col=X WHERE col=Y."""

    table_name: str
    column_name: str
    from_value: str
    to_value: str
    confidence: float = 0.9


class SPInfo(BaseModel):
    """Complete parsed information from a stored procedure."""

    procedure_name: str
    schema_name: str | None = None
    body_hash: str = ""
    table_refs: list[str] = []
    mutations: list[MutationInfo] = []
    branches: list[BranchInfo] = []
    call_chains: list[CallChainInfo] = []
    enum_detections: list[EnumDetection] = []
    state_transitions: list[StateTransitionInfo] = []
    parse_quality: float = 1.0
    is_degraded: bool = False
    has_dynamic_sql: bool = False
    partial_ast: bool = False
    dynamic_sql_locations: list[dict] = []
    warnings: list[str] = []


class SPParseResult(BaseModel):
    """Aggregated result from parsing SP files."""

    procedures: list[SPInfo] = []
    relationships: list[RelationshipInfo] = []
    warnings: list[str] = []
