"""
Unit tests for Snowflake adapter schema change handling methods (OTS 0.2.1).

These tests require a Snowflake connection. They can be run with:
- Real Snowflake credentials (via environment variables or config)
- Or mocked Snowflake connection for CI/CD
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from tee.adapters.snowflake.adapter import SnowflakeAdapter


@pytest.fixture
def snowflake_config():
    """Get Snowflake config from environment or use defaults for testing."""
    return {
        "type": "snowflake",
        "user": os.getenv("SNOWFLAKE_USER", "test_user"),
        "password": os.getenv("SNOWFLAKE_PASSWORD", "test_password"),
        "account": os.getenv("SNOWFLAKE_ACCOUNT", "test_account"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "TEST_DB"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "TEST_WH"),
    }


@pytest.fixture
def mock_snowflake_adapter(snowflake_config):
    """Create a mocked Snowflake adapter for unit testing."""
    with patch("tee.adapters.snowflake.adapter.snowflake") as mock_snowflake:
        # Mock the connector
        mock_connector = MagicMock()
        mock_snowflake.connector = mock_connector

        # Create adapter
        adapter = SnowflakeAdapter(snowflake_config)

        # Mock connection
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        adapter.connection = mock_connection

        # Mock utils methods
        adapter._qualify_object_name = lambda name: f"TEST_DB.{name}"

        yield adapter, mock_connection, mock_cursor


class TestSnowflakeSchemaChangeMethods:
    """Test cases for Snowflake adapter schema change methods."""

    def test_describe_query_schema(self, mock_snowflake_adapter):
        """Test describe_query_schema method."""
        adapter, mock_connection, mock_cursor = mock_snowflake_adapter

        # Mock DESCRIBE result
        mock_cursor.fetchall.return_value = [
            ("id", "NUMBER", "COLUMN", "Y", None, "N", "N", None, None, None),
            ("name", "VARCHAR", "COLUMN", "Y", None, "N", "N", None, None, None),
            ("value", "FLOAT", "COLUMN", "Y", None, "N", "N", None, None, None),
        ]

        query = "SELECT 1 as id, 'test' as name, 3.14 as value"
        schema = adapter.describe_query_schema(query)

        # Verify schema
        assert len(schema) == 3
        assert schema[0]["name"] == "id"
        assert schema[1]["name"] == "name"
        assert schema[2]["name"] == "value"
        assert schema[0]["type"] == "NUMBER"
        assert schema[1]["type"] == "VARCHAR"
        assert schema[2]["type"] == "FLOAT"

        # Verify cursor was used correctly
        assert mock_cursor.execute.call_count >= 2  # CREATE VIEW and DESCRIBE
        assert "DROP VIEW" in str(mock_cursor.execute.call_args_list[-1])

    def test_describe_query_schema_complex_query(self, mock_snowflake_adapter):
        """Test describe_query_schema with a complex query."""
        adapter, mock_connection, mock_cursor = mock_snowflake_adapter

        mock_cursor.fetchall.return_value = [
            ("id", "NUMBER", "COLUMN", "Y", None, "N", "N", None, None, None),
            ("name_upper", "VARCHAR", "COLUMN", "Y", None, "N", "N", None, None, None),
            ("created_at", "TIMESTAMP_NTZ", "COLUMN", "Y", None, "N", "N", None, None, None),
        ]

        query = "SELECT id, UPPER(name) as name_upper, created_at FROM source_table WHERE id > 0"
        schema = adapter.describe_query_schema(query)

        assert len(schema) == 3
        assert schema[0]["name"] == "id"
        assert schema[1]["name"] == "name_upper"
        assert schema[2]["name"] == "created_at"

    def test_describe_query_schema_not_connected(self, snowflake_config):
        """Test describe_query_schema raises error when not connected."""
        with patch("tee.adapters.snowflake.adapter.snowflake"):
            adapter = SnowflakeAdapter(snowflake_config)
            # Don't connect

            with pytest.raises(RuntimeError, match="Not connected"):
                adapter.describe_query_schema("SELECT 1")

    def test_add_column(self, mock_snowflake_adapter):
        """Test add_column method."""
        adapter, mock_connection, mock_cursor = mock_snowflake_adapter

        column = {"name": "email", "type": "VARCHAR"}
        adapter.add_column("test_table", column)

        # Verify ALTER TABLE was called
        execute_calls = [str(call) for call in mock_cursor.execute.call_args_list]
        alter_call = next((call for call in execute_calls if "ALTER TABLE" in call), None)
        assert alter_call is not None
        assert "ADD COLUMN" in alter_call
        assert "email" in alter_call
        assert "VARCHAR" in alter_call

    def test_add_column_with_type(self, mock_snowflake_adapter):
        """Test add_column with specific type."""
        adapter, mock_connection, mock_cursor = mock_snowflake_adapter

        column = {"name": "count", "type": "INTEGER"}
        adapter.add_column("test_table", column)

        # Verify correct type was used
        execute_calls = [str(call) for call in mock_cursor.execute.call_args_list]
        alter_call = next((call for call in execute_calls if "ALTER TABLE" in call), None)
        assert alter_call is not None
        assert "INTEGER" in alter_call

    def test_add_column_not_connected(self, snowflake_config):
        """Test add_column raises error when not connected."""
        with patch("tee.adapters.snowflake.adapter.snowflake"):
            adapter = SnowflakeAdapter(snowflake_config)
            # Don't connect

            with pytest.raises(RuntimeError, match="Not connected"):
                adapter.add_column("test_table", {"name": "col", "type": "VARCHAR"})

    def test_drop_column(self, mock_snowflake_adapter):
        """Test drop_column method."""
        adapter, mock_connection, mock_cursor = mock_snowflake_adapter

        adapter.drop_column("test_table", "email")

        # Verify ALTER TABLE DROP COLUMN was called
        execute_calls = [str(call) for call in mock_cursor.execute.call_args_list]
        alter_call = next((call for call in execute_calls if "ALTER TABLE" in call), None)
        assert alter_call is not None
        assert "DROP COLUMN" in alter_call
        assert "email" in alter_call

    def test_drop_column_not_connected(self, snowflake_config):
        """Test drop_column raises error when not connected."""
        with patch("tee.adapters.snowflake.adapter.snowflake"):
            adapter = SnowflakeAdapter(snowflake_config)
            # Don't connect

            with pytest.raises(RuntimeError, match="Not connected"):
                adapter.drop_column("test_table", "col")

    def test_schema_change_workflow(self, mock_snowflake_adapter):
        """Test complete workflow: describe, add, drop columns."""
        adapter, mock_connection, mock_cursor = mock_snowflake_adapter

        # Mock describe result
        mock_cursor.fetchall.return_value = [
            ("id", "NUMBER", "COLUMN", "Y", None, "N", "N", None, None, None),
            ("name", "VARCHAR", "COLUMN", "Y", None, "N", "N", None, None, None),
            ("email", "VARCHAR", "COLUMN", "Y", None, "N", "N", None, None, None),
        ]

        # Describe a query that would add a new column
        query = "SELECT id, name, 'new@email.com' as email FROM test_table"
        schema = adapter.describe_query_schema(query)

        # Find the new column
        new_column = next(col for col in schema if col["name"] == "email")

        # Add the column
        adapter.add_column("test_table", new_column)

        # Drop it again
        adapter.drop_column("test_table", "email")

        # Verify all operations were called
        assert (
            mock_cursor.execute.call_count >= 4
        )  # DESCRIBE (CREATE VIEW + DESCRIBE + DROP VIEW) + ADD + DROP
