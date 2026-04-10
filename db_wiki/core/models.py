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
