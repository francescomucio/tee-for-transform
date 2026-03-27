"""
Unit tests for schema change handling functionality.
"""

from unittest import mock
from unittest.mock import Mock

import pytest

from tee.engine.materialization.schema_change_handler import SchemaChangeHandler
from tee.engine.materialization.schema_comparator import SchemaComparator


class TestSchemaChangeHandler:
    """Test cases for SchemaChangeHandler."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock database adapter."""
        adapter = Mock()
        adapter.get_table_info.return_value = {
            "schema": [
                {"column": "id", "type": "INTEGER"},
                {"column": "name", "type": "VARCHAR"},
            ],
            "row_count": 100,
        }
        adapter.execute_query = Mock()
        adapter.drop_table = Mock()
        adapter.create_table = Mock()
        return adapter

    @pytest.fixture
    def handler(self, mock_adapter):
        """Create a SchemaChangeHandler instance."""
        return SchemaChangeHandler(mock_adapter)

    @pytest.fixture
    def query_schema(self):
        """Sample query schema."""
        return [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
            {"name": "email", "type": "VARCHAR"},  # New column
        ]

    @pytest.fixture
    def table_schema(self):
        """Sample table schema."""
        return [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
        ]

    def test_handle_schema_changes_no_changes(self, handler, query_schema):
        """Test handling when there are no schema changes."""
        # Use same schema for both
        handler.handle_schema_changes(
            "test_table",
            query_schema,
            query_schema,  # Same schema
            "fail",
        )

        # Should not raise or call any adapter methods
        handler.adapter.drop_table.assert_not_called()
        handler.adapter.create_table.assert_not_called()

    def test_handle_schema_changes_fail(self, handler, query_schema, table_schema):
        """Test fail behavior raises error."""
        with pytest.raises(ValueError) as exc_info:
            handler.handle_schema_changes(
                "test_table",
                query_schema,
                table_schema,
                "fail",
            )

        assert "Schema changes detected" in str(exc_info.value)
        assert "New columns" in str(exc_info.value)

    def test_handle_schema_changes_ignore(self, handler, query_schema, table_schema):
        """Test ignore behavior logs and continues."""
        handler.handle_schema_changes(
            "test_table",
            query_schema,
            table_schema,
            "ignore",
        )

        # Should not raise or modify table
        handler.adapter.drop_table.assert_not_called()
        handler.adapter.create_table.assert_not_called()

    def test_handle_schema_changes_append_new_columns(self, handler, query_schema, table_schema):
        """Test append_new_columns adds new columns."""
        # Mock add_column method
        handler.adapter.add_column = Mock()

        handler.handle_schema_changes(
            "test_table",
            query_schema,
            table_schema,
            "append_new_columns",
        )

        # Should add the new column
        handler.adapter.add_column.assert_called_once()
        call_args = handler.adapter.add_column.call_args
        assert call_args[0][0] == "test_table"
        assert call_args[0][1]["name"] == "email"

    def test_handle_schema_changes_append_new_columns_fallback_ddl(
        self, handler, query_schema, table_schema
    ):
        """Test append_new_columns falls back to DDL when adapter method not available."""
        # Don't set add_column method
        handler.adapter.add_column = None

        handler.handle_schema_changes(
            "test_table",
            query_schema,
            table_schema,
            "append_new_columns",
        )

        # Should have executed ALTER TABLE ADD COLUMN DDL
        handler.adapter.execute_query.assert_called()
        ddl_call = handler.adapter.execute_query.call_args[0][0]
        assert "ALTER TABLE" in ddl_call
        assert "ADD COLUMN" in ddl_call
        assert "email" in ddl_call

    def test_handle_schema_changes_sync_all_columns(self, handler, query_schema, table_schema):
        """Test sync_all_columns adds new and removes missing columns."""
        handler.adapter.add_column = Mock()
        handler.adapter.drop_column = Mock()

        # Add a missing column scenario
        table_schema_with_extra = table_schema + [{"name": "old_col", "type": "VARCHAR"}]
        query_schema_no_old = query_schema  # Doesn't have old_col

        handler.handle_schema_changes(
            "test_table",
            query_schema_no_old,
            table_schema_with_extra,
            "sync_all_columns",
        )

        # Should add new column
        handler.adapter.add_column.assert_called_once()
        # Should remove missing column
        handler.adapter.drop_column.assert_called_once_with("test_table", "old_col")

    def test_handle_schema_changes_full_refresh(self, handler, query_schema, table_schema):
        """Test full_refresh drops and recreates table."""
        sql_query = "SELECT id, name, email FROM source"

        handler.handle_schema_changes(
            "test_table",
            query_schema,
            table_schema,
            "full_refresh",
            sql_query=sql_query,
        )

        # Should drop table
        handler.adapter.drop_table.assert_called_once_with("test_table")
        # Should recreate with full query
        handler.adapter.create_table.assert_called_once_with("test_table", sql_query)

    def test_handle_schema_changes_full_refresh_requires_query(
        self, handler, query_schema, table_schema
    ):
        """Test full_refresh raises error if sql_query not provided."""
        with pytest.raises(ValueError) as exc_info:
            handler.handle_schema_changes(
                "test_table",
                query_schema,
                table_schema,
                "full_refresh",
                sql_query=None,
            )

        assert "full_refresh requires sql_query" in str(exc_info.value)

    def test_handle_schema_changes_full_incremental_refresh(
        self, handler, query_schema, table_schema, mock_adapter
    ):
        """Test full_incremental_refresh drops, recreates, and prepares for chunking."""
        sql_query = "SELECT id, name, email FROM source"
        full_incremental_config = {
            "parameters": [
                {
                    "name": "event_date",
                    "start_value": "2024-01-01",
                    "end_value": "2025-12-31",
                    "step": "INTERVAL 1 DAY",
                }
            ]
        }
        incremental_config = {"strategy": "append", "append": {"filter_column": "event_date"}}

        # Mock schema inference via adapter
        mock_adapter.execute_query.return_value = Mock()
        # Mock the LIMIT 0 query result to return schema info
        # The handler will use SchemaComparator which will call infer_query_schema
        # For this test, we just verify the table is dropped and DDL is executed
        with mock.patch.object(SchemaComparator, "infer_query_schema", return_value=query_schema):
            handler.handle_schema_changes(
                "test_table",
                query_schema,
                table_schema,
                "full_incremental_refresh",
                sql_query=sql_query,
                full_incremental_refresh_config=full_incremental_config,
                incremental_config=incremental_config,
            )

        # Should drop table
        handler.adapter.drop_table.assert_called_once_with("test_table")
        # Should create empty table (via DDL)
        handler.adapter.execute_query.assert_called()

    def test_handle_schema_changes_full_incremental_refresh_requires_config(
        self, handler, query_schema, table_schema
    ):
        """Test full_incremental_refresh raises error if configs not provided."""
        with pytest.raises(ValueError) as exc_info:
            handler.handle_schema_changes(
                "test_table",
                query_schema,
                table_schema,
                "full_incremental_refresh",
                sql_query="SELECT * FROM source",
                full_incremental_refresh_config=None,
            )

        assert "full_incremental_refresh requires full_incremental_refresh_config" in str(
            exc_info.value
        )

    def test_handle_schema_changes_recreate_empty(self, handler, query_schema, table_schema):
        """Test recreate_empty drops and recreates empty table."""
        handler.handle_schema_changes(
            "test_table",
            query_schema,
            table_schema,
            "recreate_empty",
        )

        # Should drop table
        handler.adapter.drop_table.assert_called_once_with("test_table")
        # Should create empty table with schema
        handler.adapter.execute_query.assert_called()
        create_ddl = handler.adapter.execute_query.call_args[0][0]
        assert "CREATE TABLE" in create_ddl
        assert "id" in create_ddl
        assert "name" in create_ddl
        assert "email" in create_ddl

    def test_handle_schema_changes_unknown_action(self, handler, query_schema, table_schema):
        """Test that unknown on_schema_change value raises error."""
        with pytest.raises(ValueError) as exc_info:
            handler.handle_schema_changes(
                "test_table",
                query_schema,
                table_schema,
                "unknown_action",  # type: ignore
            )

        assert "Unknown on_schema_change value" in str(exc_info.value)

    def test_handle_schema_changes_type_mismatch_in_error(self, handler):
        """Test that type mismatches are included in fail error message."""
        query_schema = [{"name": "id", "type": "VARCHAR"}]
        table_schema = [{"name": "id", "type": "INTEGER"}]

        with pytest.raises(ValueError) as exc_info:
            handler.handle_schema_changes(
                "test_table",
                query_schema,
                table_schema,
                "fail",
            )

        error_msg = str(exc_info.value)
        assert "Type mismatches" in error_msg
        assert "id" in error_msg

    def test_add_column_uses_adapter_method(self, handler):
        """Test that _add_column uses adapter method when available."""
        handler.adapter.add_column = Mock()
        column = {"name": "email", "type": "VARCHAR"}

        handler._add_column("test_table", column)

        handler.adapter.add_column.assert_called_once_with("test_table", column)

    def test_add_column_fallback_ddl(self, handler):
        """Test that _add_column falls back to DDL when adapter method not available."""
        handler.adapter.add_column = None
        column = {"name": "email", "type": "VARCHAR"}

        handler._add_column("test_table", column)

        handler.adapter.execute_query.assert_called_once()
        ddl = handler.adapter.execute_query.call_args[0][0]
        assert "ALTER TABLE" in ddl
        assert "ADD COLUMN" in ddl
        assert "email" in ddl
        assert "VARCHAR" in ddl

    def test_drop_column_uses_adapter_method(self, handler):
        """Test that _drop_column uses adapter method when available."""
        handler.adapter.drop_column = Mock()

        handler._drop_column("test_table", "old_col")

        handler.adapter.drop_column.assert_called_once_with("test_table", "old_col")

    def test_drop_column_fallback_ddl(self, handler):
        """Test that _drop_column falls back to DDL when adapter method not available."""
        handler.adapter.drop_column = None

        handler._drop_column("test_table", "old_col")

        handler.adapter.execute_query.assert_called_once()
        ddl = handler.adapter.execute_query.call_args[0][0]
        assert "ALTER TABLE" in ddl
        assert "DROP COLUMN" in ddl
        assert "old_col" in ddl

    def test_create_empty_table_from_schema(self, handler):
        """Test creating empty table from schema."""
        schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
        ]

        handler._create_empty_table_from_schema("test_table", schema)

        handler.adapter.execute_query.assert_called_once()
        create_ddl = handler.adapter.execute_query.call_args[0][0]
        assert "CREATE TABLE" in create_ddl
        assert "id INTEGER" in create_ddl
        assert "name VARCHAR" in create_ddl

    def test_create_empty_table_from_schema_empty_schema(self, handler):
        """Test that creating table with empty schema raises error."""
        with pytest.raises(ValueError) as exc_info:
            handler._create_empty_table_from_schema("test_table", [])

        assert "schema is empty" in str(exc_info.value)
