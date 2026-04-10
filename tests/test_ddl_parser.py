"""Tests for the DDL parser and ingest pipeline.

TDD RED phase: these tests define the expected behavior before the
implementation exists. All tests should fail until db_wiki/ingest/ddl_parser.py
is implemented.
"""

import sqlite3

import pytest

# ---------------------------------------------------------------------------
# Test fixture SQL — realistic T-SQL DDL with multiple statement types
# ---------------------------------------------------------------------------

MULTI_STATEMENT_DDL = """
CREATE TABLE dbo.Customers (
    CustomerID INT PRIMARY KEY NOT NULL,
    Name NVARCHAR(100) NOT NULL,
    Email NVARCHAR(255) UNIQUE,
    CreatedAt DATETIME2 DEFAULT GETDATE()
);

CREATE TABLE dbo.Orders (
    OrderID INT PRIMARY KEY NOT NULL,
    CustomerID INT NOT NULL,
    OrderDate DATETIME2 NOT NULL,
    Total DECIMAL(18,2) NOT NULL
);

CREATE INDEX IX_Orders_CustomerID ON dbo.Orders (CustomerID);

CREATE UNIQUE INDEX IX_Customers_Email ON dbo.Customers (Email);

ALTER TABLE dbo.Orders ADD CONSTRAINT FK_Orders_Customers
    FOREIGN KEY (CustomerID) REFERENCES dbo.Customers(CustomerID);
"""

INVALID_WITH_VALID_DDL = """
CREATE TABLE dbo.Valid (id INT PRIMARY KEY);

THIS IS NOT VALID SQL AT ALL !! @@##;

CREATE TABLE dbo.AlsoValid (name NVARCHAR(50) NOT NULL);
"""

SINGLE_TABLE_DDL = "CREATE TABLE dbo.Orders (id INT PRIMARY KEY NOT NULL, name NVARCHAR(100) NOT NULL)"

TABLE_WITH_TABLE_LEVEL_PK = """
CREATE TABLE dbo.OrderItems (
    OrderID INT NOT NULL,
    ItemID INT NOT NULL,
    Qty INT NOT NULL DEFAULT 1,
    CONSTRAINT PK_OrderItems PRIMARY KEY (OrderID, ItemID)
);
"""

TABLE_WITH_FK = """
CREATE TABLE dbo.OrderItems (
    OrderID INT NOT NULL,
    ItemID INT NOT NULL,
    CONSTRAINT FK_Items_Orders FOREIGN KEY (OrderID) REFERENCES dbo.Orders(OrderID)
);
"""


# ---------------------------------------------------------------------------
# Tests for parse_ddl_file
# ---------------------------------------------------------------------------


def test_parse_ddl_file_returns_single_create_table():
    """parse_ddl_file returns a list with one Create statement for a single CREATE TABLE."""
    from sqlglot import exp

    from db_wiki.ingest.ddl_parser import parse_ddl_file

    statements, warnings = parse_ddl_file(SINGLE_TABLE_DDL)
    assert len(statements) == 1
    assert isinstance(statements[0], exp.Create)


def test_parse_ddl_file_returns_multiple_statements():
    """parse_ddl_file returns all valid statements from a multi-statement file."""
    from db_wiki.ingest.ddl_parser import parse_ddl_file

    statements, warnings = parse_ddl_file(MULTI_STATEMENT_DDL)
    # 2 CREATE TABLE + 2 CREATE INDEX + 1 ALTER TABLE = 5 statements
    assert len(statements) == 5


def test_parse_ddl_file_skips_invalid_and_returns_warnings():
    """parse_ddl_file skips unparseable statements, logs warnings, and returns valid ones."""
    from db_wiki.ingest.ddl_parser import parse_ddl_file

    statements, warnings = parse_ddl_file(INVALID_WITH_VALID_DDL)
    # Should get the 2 valid CREATE TABLE statements
    assert len(statements) == 2
    # Should have at least one warning about the invalid statement
    assert len(warnings) >= 1
    assert any("skip" in w.lower() or "unparse" in w.lower() or "command" in w.lower() for w in warnings)


def test_parse_ddl_file_returns_tuple():
    """parse_ddl_file returns a tuple of (statements, warnings)."""
    from db_wiki.ingest.ddl_parser import parse_ddl_file

    result = parse_ddl_file(SINGLE_TABLE_DDL)
    assert isinstance(result, tuple)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests for extract_create_table
# ---------------------------------------------------------------------------


def test_extract_create_table_basic_names():
    """extract_create_table extracts table_name and schema_name."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    stmt = sqlglot.parse(SINGLE_TABLE_DDL, dialect="tsql")[0]
    assert isinstance(stmt, exp.Create)
    info = extract_create_table(stmt)

    assert info.table_name == "Orders"
    assert info.schema_name == "dbo"


def test_extract_create_table_column_names_and_types():
    """extract_create_table extracts column names and data types."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    stmt = sqlglot.parse(SINGLE_TABLE_DDL, dialect="tsql")[0]
    info = extract_create_table(stmt)

    col_names = [c.column_name for c in info.columns]
    assert "id" in col_names
    assert "name" in col_names


def test_extract_create_table_inline_pk():
    """extract_create_table extracts inline PRIMARY KEY column constraint."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    stmt = sqlglot.parse(SINGLE_TABLE_DDL, dialect="tsql")[0]
    info = extract_create_table(stmt)

    id_col = next(c for c in info.columns if c.column_name == "id")
    assert id_col.is_primary_key is True


def test_extract_create_table_inline_not_null():
    """extract_create_table extracts inline NOT NULL constraint (is_nullable=False)."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    stmt = sqlglot.parse(SINGLE_TABLE_DDL, dialect="tsql")[0]
    info = extract_create_table(stmt)

    name_col = next(c for c in info.columns if c.column_name == "name")
    assert name_col.is_nullable is False


def test_extract_create_table_inline_unique():
    """extract_create_table extracts inline UNIQUE constraint."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    ddl = "CREATE TABLE dbo.Customers (CustomerID INT PRIMARY KEY NOT NULL, Email NVARCHAR(255) UNIQUE)"
    stmt = sqlglot.parse(ddl, dialect="tsql")[0]
    info = extract_create_table(stmt)

    email_col = next(c for c in info.columns if c.column_name == "Email")
    assert email_col.is_unique is True


def test_extract_create_table_inline_default():
    """extract_create_table extracts inline DEFAULT constraint."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    ddl = "CREATE TABLE dbo.Customers (CustomerID INT PRIMARY KEY, CreatedAt DATETIME2 DEFAULT GETDATE())"
    stmt = sqlglot.parse(ddl, dialect="tsql")[0]
    info = extract_create_table(stmt)

    created_col = next(c for c in info.columns if c.column_name == "CreatedAt")
    assert created_col.default_value is not None
    assert len(created_col.default_value) > 0


def test_extract_create_table_table_level_pk():
    """extract_create_table extracts table-level PRIMARY KEY constraint."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    stmt = sqlglot.parse(TABLE_WITH_TABLE_LEVEL_PK, dialect="tsql")[0]
    info = extract_create_table(stmt)

    pk_constraints = [c for c in info.constraints if c.constraint_type == "PRIMARY KEY"]
    assert len(pk_constraints) >= 1
    pk = pk_constraints[0]
    assert "OrderID" in pk.columns
    assert "ItemID" in pk.columns


def test_extract_create_table_table_level_fk():
    """extract_create_table extracts table-level FOREIGN KEY constraint."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_table

    stmt = sqlglot.parse(TABLE_WITH_FK, dialect="tsql")[0]
    info = extract_create_table(stmt)

    fk_constraints = [c for c in info.constraints if c.constraint_type == "FOREIGN KEY"]
    assert len(fk_constraints) >= 1
    fk = fk_constraints[0]
    assert "OrderID" in fk.columns
    assert fk.ref_table is not None
    assert "Orders" in fk.ref_table


# ---------------------------------------------------------------------------
# Tests for extract_create_index
# ---------------------------------------------------------------------------


def test_extract_create_index_basic():
    """extract_create_index extracts index_name, table_name, is_unique, columns."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_index

    ddl = "CREATE INDEX IX_Orders_CustomerID ON dbo.Orders (CustomerID)"
    stmt = sqlglot.parse(ddl, dialect="tsql")[0]
    assert isinstance(stmt, exp.Create)

    info = extract_create_index(stmt)
    assert info is not None
    assert info.index_name == "IX_Orders_CustomerID"
    assert info.table_name == "Orders"
    assert info.is_unique is False
    assert "CustomerID" in info.columns


def test_extract_create_index_unique():
    """extract_create_index extracts is_unique=True for UNIQUE indexes."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_index

    ddl = "CREATE UNIQUE INDEX IX_Customers_Email ON dbo.Customers (Email)"
    stmt = sqlglot.parse(ddl, dialect="tsql")[0]

    info = extract_create_index(stmt)
    assert info is not None
    assert info.is_unique is True
    assert info.table_name == "Customers"
    assert "Email" in info.columns


def test_extract_create_index_returns_none_for_non_index():
    """extract_create_index returns None when given a non-index CREATE statement."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_create_index

    ddl = "CREATE TABLE dbo.Test (id INT PRIMARY KEY)"
    stmt = sqlglot.parse(ddl, dialect="tsql")[0]

    result = extract_create_index(stmt)
    assert result is None


# ---------------------------------------------------------------------------
# Tests for extract_alter_table_constraint
# ---------------------------------------------------------------------------


def test_extract_alter_table_constraint_fk():
    """extract_alter_table_constraint extracts FK from ALTER TABLE ADD CONSTRAINT."""
    from sqlglot import exp
    import sqlglot

    from db_wiki.ingest.ddl_parser import extract_alter_table_constraint

    ddl = """ALTER TABLE dbo.Orders ADD CONSTRAINT FK_Orders_Customers
        FOREIGN KEY (CustomerID) REFERENCES dbo.Customers(CustomerID)"""
    stmt = sqlglot.parse(ddl, dialect="tsql")[0]
    assert isinstance(stmt, exp.Alter)

    relationships = extract_alter_table_constraint(stmt)
    assert len(relationships) >= 1
    rel = relationships[0]
    assert rel.source_table == "Orders"
    assert "Customers" in rel.target_table
    assert rel.relationship_type == "fk_declared"


# ---------------------------------------------------------------------------
# Tests for parse_ddl (full pipeline)
# ---------------------------------------------------------------------------


def test_parse_ddl_full_result():
    """parse_ddl returns ParseResult with tables, indexes, and relationships."""
    from db_wiki.ingest.ddl_parser import parse_ddl

    result = parse_ddl(MULTI_STATEMENT_DDL)

    assert len(result.tables) == 2
    assert len(result.indexes) == 2
    assert len(result.relationships) >= 1
    assert len(result.warnings) == 0


def test_parse_ddl_table_names():
    """parse_ddl ParseResult contains correct table names."""
    from db_wiki.ingest.ddl_parser import parse_ddl

    result = parse_ddl(MULTI_STATEMENT_DDL)
    table_names = {t.table_name for t in result.tables}
    assert "Customers" in table_names
    assert "Orders" in table_names


def test_parse_ddl_fk_relationship_in_result():
    """parse_ddl includes FK relationship from ALTER TABLE in ParseResult."""
    from db_wiki.ingest.ddl_parser import parse_ddl

    result = parse_ddl(MULTI_STATEMENT_DDL)
    fk_rels = [r for r in result.relationships if r.relationship_type == "fk_declared"]
    assert len(fk_rels) >= 1


# ---------------------------------------------------------------------------
# Tests for file size check (T-02-01 mitigation)
# ---------------------------------------------------------------------------


def test_parse_ddl_file_size_limit():
    """ingest_ddl_from_file rejects files over max_file_size_mb with clear error."""
    from db_wiki.ingest.ddl_parser import check_file_size_limit

    # Simulate a "file" larger than the limit (50MB)
    oversized_content = "x" * (51 * 1024 * 1024)
    with pytest.raises(ValueError, match="[Ff]ile.*size|[Ss]ize.*limit|too large"):
        check_file_size_limit(oversized_content, max_mb=50)


def test_parse_ddl_file_size_limit_accepts_normal_file():
    """check_file_size_limit passes for files within the limit."""
    from db_wiki.ingest.ddl_parser import check_file_size_limit

    normal_content = "CREATE TABLE dbo.Test (id INT PRIMARY KEY)"
    # Should not raise
    check_file_size_limit(normal_content, max_mb=50)


# ---------------------------------------------------------------------------
# Tests for ingest_ddl (write to SQLite)
# ---------------------------------------------------------------------------


def test_ingest_ddl_tables_and_columns(initialized_db: sqlite3.Connection):
    """ingest_ddl stores tables and columns that appear in current_db_tables/current_db_columns views."""
    from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl

    result = parse_ddl(MULTI_STATEMENT_DDL)
    counts = ingest_ddl(initialized_db, result)

    assert counts["tables"] == 2
    assert counts["columns"] > 0

    rows = initialized_db.execute("SELECT * FROM current_db_tables").fetchall()
    table_names = {r["table_name"] for r in rows}
    assert "Customers" in table_names
    assert "Orders" in table_names

    col_rows = initialized_db.execute("SELECT * FROM current_db_columns").fetchall()
    assert len(col_rows) > 0


def test_ingest_ddl_relationships(initialized_db: sqlite3.Connection):
    """ingest_ddl stores FK relationships in db_relationships with type='fk_declared'."""
    from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl

    result = parse_ddl(MULTI_STATEMENT_DDL)
    counts = ingest_ddl(initialized_db, result)

    assert counts["relationships"] >= 1

    rel_rows = initialized_db.execute(
        "SELECT * FROM current_db_relationships WHERE relationship_type = 'fk_declared'"
    ).fetchall()
    assert len(rel_rows) >= 1


def test_ingest_ddl_indexes(initialized_db: sqlite3.Connection):
    """ingest_ddl stores indexes in db_indexes."""
    from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl

    result = parse_ddl(MULTI_STATEMENT_DDL)
    counts = ingest_ddl(initialized_db, result)

    assert counts["indexes"] == 2

    idx_rows = initialized_db.execute("SELECT * FROM current_db_indexes").fetchall()
    assert len(idx_rows) == 2


def test_ingest_ddl_uses_parameterized_queries(initialized_db: sqlite3.Connection):
    """ingest_ddl handles table names with SQL-like characters safely (T-02-02)."""
    from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl

    # A table named with special characters that would break string interpolation
    tricky_ddl = "CREATE TABLE dbo.Test (id INT PRIMARY KEY, val NVARCHAR(50))"
    result = parse_ddl(tricky_ddl)
    # Should not raise; parameterized queries handle this safely
    counts = ingest_ddl(initialized_db, result)
    assert counts["tables"] == 1


def test_ingest_ddl_bi_temporal_timestamps(initialized_db: sqlite3.Connection):
    """ingest_ddl writes valid_from, valid_from_ts, recorded_at, recorded_at_ts to db_tables."""
    from db_wiki.ingest.ddl_parser import ingest_ddl, parse_ddl

    result = parse_ddl(SINGLE_TABLE_DDL)
    ingest_ddl(initialized_db, result)

    row = initialized_db.execute("SELECT * FROM db_tables").fetchone()
    assert row["valid_from"] is not None
    assert row["valid_from_ts"] is not None
    assert row["recorded_at"] is not None
    assert row["recorded_at_ts"] is not None
    # valid_until and invalidated_at should be NULL for fresh inserts
    assert row["valid_until"] is None
    assert row["invalidated_at"] is None
