"""
Unit tests for DuckDB adapter schema change handling methods (OTS 0.2.1).
"""

import tempfile
from pathlib import Path

import pytest

from tee.adapters.duckdb.adapter import DuckDBAdapter


class TestDuckDBSchemaChangeMethods:
    """Test cases for DuckDB adapter schema change methods."""

    @pytest.fixture
    def adapter(self):
        """Create a DuckDB adapter instance."""
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
            db_path = tmp_file.name

        # Remove the file so DuckDB can create it fresh
        Path(db_path).unlink(missing_ok=True)

        config = {"type": "duckdb", "path": db_path}
        adapter = DuckDBAdapter(config)
        adapter.connect()

        yield adapter

        # Cleanup
        try:
            adapter.disconnect()
            Path(db_path).unlink(missing_ok=True)
        except Exception:
            pass

    def test_describe_query_schema(self, adapter):
        """Test describe_query_schema method."""
        # Create a test table first
        adapter.create_table(
            "test_table",
            "SELECT 1 as id, 'test' as name, 3.14 as value",
        )

        # Describe a query
        query = "SELECT id, name, value FROM test_table"
        schema = adapter.describe_query_schema(query)

        assert len(schema) == 3
        assert schema[0]["name"] == "id"
        assert schema[1]["name"] == "name"
        assert schema[2]["name"] == "value"
        # Types may vary, but should be present
        assert "type" in schema[0]
        assert "type" in schema[1]
        assert "type" in schema[2]

    def test_describe_query_schema_complex_query(self, adapter):
        """Test describe_query_schema with a complex query."""
        adapter.create_table(
            "source_table",
            "SELECT 1 as id, 'test' as name, CURRENT_TIMESTAMP as created_at",
        )

        query = "SELECT id, UPPER(name) as name_upper, created_at FROM source_table WHERE id > 0"
        schema = adapter.describe_query_schema(query)

        assert len(schema) == 3
        assert schema[0]["name"] == "id"
        assert schema[1]["name"] == "name_upper"
        assert schema[2]["name"] == "created_at"

    def test_describe_query_schema_not_connected(self):
        """Test describe_query_schema raises error when not connected."""
        config = {"type": "duckdb", "path": ":memory:"}
        adapter = DuckDBAdapter(config)
        # Don't connect

        with pytest.raises(RuntimeError) as exc_info:
            adapter.describe_query_schema("SELECT 1")

        assert "Not connected" in str(exc_info.value)

    def test_add_column(self, adapter):
        """Test add_column method."""
        # Create a table
        adapter.create_table(
            "test_table",
            "SELECT 1 as id, 'test' as name",
        )

        # Add a new column
        column = {"name": "email", "type": "VARCHAR"}
        adapter.add_column("test_table", column)

        # Verify column was added
        table_info = adapter.get_table_info("test_table")
        column_names = [col["column"] for col in table_info["schema"]]
        assert "email" in column_names

    def test_add_column_with_type(self, adapter):
        """Test add_column with specific type."""
        adapter.create_table(
            "test_table",
            "SELECT 1 as id",
        )

        # Add INTEGER column
        column = {"name": "count", "type": "INTEGER"}
        adapter.add_column("test_table", column)

        # Verify column was added with correct type
        table_info = adapter.get_table_info("test_table")
        schema = {col["column"]: col["type"] for col in table_info["schema"]}
        assert "count" in schema
        assert "INTEGER" in schema["count"].upper()

    def test_add_column_not_connected(self):
        """Test add_column raises error when not connected."""
        config = {"type": "duckdb", "path": ":memory:"}
        adapter = DuckDBAdapter(config)
        # Don't connect

        with pytest.raises(RuntimeError) as exc_info:
            adapter.add_column("test_table", {"name": "col", "type": "VARCHAR"})

        assert "Not connected" in str(exc_info.value)

    def test_add_column_table_not_exists(self, adapter):
        """Test add_column raises error when table doesn't exist."""
        with pytest.raises(Exception):  # DuckDB will raise an error
            adapter.add_column("nonexistent_table", {"name": "col", "type": "VARCHAR"})

    def test_drop_column(self, adapter):
        """Test drop_column method."""
        # Create a table with multiple columns
        adapter.create_table(
            "test_table",
            "SELECT 1 as id, 'test' as name, 'email@test.com' as email",
        )

        # Drop a column
        adapter.drop_column("test_table", "email")

        # Verify column was dropped
        table_info = adapter.get_table_info("test_table")
        column_names = [col["column"] for col in table_info["schema"]]
        assert "email" not in column_names
        assert "id" in column_names
        assert "name" in column_names

    def test_drop_column_not_connected(self):
        """Test drop_column raises error when not connected."""
        config = {"type": "duckdb", "path": ":memory:"}
        adapter = DuckDBAdapter(config)
        # Don't connect

        with pytest.raises(RuntimeError) as exc_info:
            adapter.drop_column("test_table", "col")

        assert "Not connected" in str(exc_info.value)

    def test_drop_column_table_not_exists(self, adapter):
        """Test drop_column raises error when table doesn't exist."""
        with pytest.raises(Exception):  # DuckDB will raise an error
            adapter.drop_column("nonexistent_table", "col")

    def test_drop_column_column_not_exists(self, adapter):
        """Test drop_column raises error when column doesn't exist."""
        adapter.create_table(
            "test_table",
            "SELECT 1 as id",
        )

        with pytest.raises(Exception):  # DuckDB will raise an error
            adapter.drop_column("test_table", "nonexistent_column")

    def test_schema_change_workflow(self, adapter):
        """Test complete workflow: describe, add, drop columns."""
        # Create initial table
        adapter.create_table(
            "test_table",
            "SELECT 1 as id, 'test' as name",
        )

        # Describe a query that would add a new column
        query = "SELECT id, name, 'new@email.com' as email FROM test_table"
        schema = adapter.describe_query_schema(query)

        # Find the new column
        new_column = next(col for col in schema if col["name"] == "email")

        # Add the column
        adapter.add_column("test_table", new_column)

        # Verify it was added
        table_info = adapter.get_table_info("test_table")
        column_names = [col["column"] for col in table_info["schema"]]
        assert "email" in column_names

        # Drop it again
        adapter.drop_column("test_table", "email")

        # Verify it was dropped
        table_info = adapter.get_table_info("test_table")
        column_names = [col["column"] for col in table_info["schema"]]
        assert "email" not in column_names
