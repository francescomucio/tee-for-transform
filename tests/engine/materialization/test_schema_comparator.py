"""
Unit tests for schema comparison functionality.
"""

from unittest.mock import MagicMock, Mock

import pytest

from t4t.engine.materialization.schema_comparator import SchemaComparator


class TestSchemaComparator:
    """Test cases for SchemaComparator."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock database adapter."""
        adapter = Mock()
        adapter.get_table_info.return_value = {
            "schema": [
                {"column": "id", "type": "INTEGER"},
                {"column": "name", "type": "VARCHAR"},
                {"column": "created_at", "type": "TIMESTAMP"},
            ],
            "row_count": 100,
        }
        return adapter

    @pytest.fixture
    def comparator(self, mock_adapter):
        """Create a SchemaComparator instance."""
        return SchemaComparator(mock_adapter)

    def test_get_table_schema(self, comparator, mock_adapter):
        """Test getting schema from existing table."""
        schema = comparator.get_table_schema("test_table")

        assert len(schema) == 3
        assert schema[0]["name"] == "id"
        assert schema[0]["type"] == "INTEGER"
        assert schema[1]["name"] == "name"
        assert schema[1]["type"] == "VARCHAR"
        assert schema[2]["name"] == "created_at"
        assert schema[2]["type"] == "TIMESTAMP"

        mock_adapter.get_table_info.assert_called_once_with("test_table")

    def test_get_table_schema_normalizes_column_key(self, comparator, mock_adapter):
        """Test that get_table_schema normalizes 'column' key to 'name'."""
        mock_adapter.get_table_info.return_value = {
            "schema": [
                {"name": "id", "type": "INTEGER"},  # Already has 'name'
                {"column": "name", "type": "VARCHAR"},  # Has 'column'
            ],
            "row_count": 0,
        }

        schema = comparator.get_table_schema("test_table")

        assert schema[0]["name"] == "id"
        assert schema[1]["name"] == "name"

    def test_compare_schemas_no_changes(self, comparator):
        """Test comparing identical schemas."""
        query_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
        ]
        table_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
        ]

        result = comparator.compare_schemas(query_schema, table_schema)

        assert result["has_changes"] is False
        assert len(result["new_columns"]) == 0
        assert len(result["missing_columns"]) == 0
        assert len(result["type_mismatches"]) == 0

    def test_compare_schemas_new_columns(self, comparator):
        """Test detecting new columns."""
        query_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
            {"name": "email", "type": "VARCHAR"},  # New column
        ]
        table_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
        ]

        result = comparator.compare_schemas(query_schema, table_schema)

        assert result["has_changes"] is True
        assert len(result["new_columns"]) == 1
        assert result["new_columns"][0]["name"] == "email"
        assert len(result["missing_columns"]) == 0
        assert len(result["type_mismatches"]) == 0

    def test_compare_schemas_missing_columns(self, comparator):
        """Test detecting missing columns."""
        query_schema = [
            {"name": "id", "type": "INTEGER"},
        ]
        table_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},  # Missing in query
        ]

        result = comparator.compare_schemas(query_schema, table_schema)

        assert result["has_changes"] is True
        assert len(result["new_columns"]) == 0
        assert len(result["missing_columns"]) == 1
        assert result["missing_columns"][0]["name"] == "name"
        assert len(result["type_mismatches"]) == 0

    def test_compare_schemas_type_mismatch(self, comparator):
        """Test detecting type mismatches."""
        query_schema = [
            {"name": "id", "type": "VARCHAR"},  # Type changed
            {"name": "name", "type": "VARCHAR"},
        ]
        table_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "name", "type": "VARCHAR"},
        ]

        result = comparator.compare_schemas(query_schema, table_schema)

        assert result["has_changes"] is True
        assert len(result["new_columns"]) == 0
        assert len(result["missing_columns"]) == 0
        assert len(result["type_mismatches"]) == 1
        assert result["type_mismatches"][0]["name"] == "id"
        assert result["type_mismatches"][0]["query_type"] == "VARCHAR"
        assert result["type_mismatches"][0]["table_type"] == "INTEGER"

    def test_compare_schemas_case_insensitive(self, comparator):
        """Test that column name comparison is case-insensitive."""
        query_schema = [
            {"name": "ID", "type": "INTEGER"},  # Uppercase
            {"name": "Name", "type": "VARCHAR"},  # Mixed case
        ]
        table_schema = [
            {"name": "id", "type": "INTEGER"},  # Lowercase
            {"name": "name", "type": "VARCHAR"},  # Lowercase
        ]

        result = comparator.compare_schemas(query_schema, table_schema)

        assert result["has_changes"] is False

    def test_compare_schemas_multiple_changes(self, comparator):
        """Test detecting multiple types of changes."""
        query_schema = [
            {"name": "id", "type": "INTEGER"},
            {"name": "email", "type": "VARCHAR"},  # New
            {"name": "age", "type": "INTEGER"},  # New
        ]
        table_schema = [
            {"name": "id", "type": "VARCHAR"},  # Type mismatch
            {"name": "name", "type": "VARCHAR"},  # Missing
        ]

        result = comparator.compare_schemas(query_schema, table_schema)

        assert result["has_changes"] is True
        assert len(result["new_columns"]) == 2
        assert len(result["missing_columns"]) == 1
        assert len(result["type_mismatches"]) == 1

    def test_normalize_type_removes_length(self, comparator):
        """Test that type normalization removes length specifications."""
        assert comparator._normalize_type("VARCHAR(255)") == "VARCHAR"
        assert comparator._normalize_type("DECIMAL(10,2)") == "DECIMAL"
        assert comparator._normalize_type("CHAR(50)") == "VARCHAR"  # Also maps CHAR -> VARCHAR

    def test_normalize_type_maps_aliases(self, comparator):
        """Test that type normalization maps common aliases."""
        assert comparator._normalize_type("INT") == "INTEGER"
        assert comparator._normalize_type("INT4") == "INTEGER"
        assert comparator._normalize_type("INT8") == "BIGINT"
        assert comparator._normalize_type("FLOAT") == "DOUBLE"
        assert comparator._normalize_type("TEXT") == "VARCHAR"
        assert comparator._normalize_type("STRING") == "VARCHAR"
        assert comparator._normalize_type("BOOL") == "BOOLEAN"

    def test_normalize_type_handles_timestamps(self, comparator):
        """Test that type normalization handles timestamp variations."""
        assert comparator._normalize_type("TIMESTAMP_NTZ") == "TIMESTAMP"
        assert comparator._normalize_type("TIMESTAMP_LTZ") == "TIMESTAMP"
        assert comparator._normalize_type("TIMESTAMP_TZ") == "TIMESTAMP"

    def test_normalize_type_preserves_unknown_types(self, comparator):
        """Test that unknown types are preserved."""
        assert comparator._normalize_type("CUSTOM_TYPE") == "CUSTOM_TYPE"
        assert comparator._normalize_type("") == ""

    def test_infer_query_schema_uses_adapter_method(self, comparator, mock_adapter):
        """Test that infer_query_schema uses adapter.describe_query_schema if available."""
        mock_adapter.describe_query_schema = Mock(
            return_value=[
                {"name": "id", "type": "INTEGER"},
                {"name": "name", "type": "VARCHAR"},
            ]
        )

        schema = comparator.infer_query_schema("SELECT id, name FROM test")

        assert len(schema) == 2
        assert schema[0]["name"] == "id"
        mock_adapter.describe_query_schema.assert_called_once_with("SELECT id, name FROM test")

    def test_infer_query_schema_fallback_on_error(self, comparator, mock_adapter):
        """Test that infer_query_schema falls back to LIMIT 0 on adapter method error."""
        mock_adapter.describe_query_schema = Mock(side_effect=Exception("Not implemented"))

        # Mock the fallback LIMIT 0 approach
        mock_cursor = MagicMock()
        mock_cursor.description = [
            ("id", "INTEGER", None, None, None, None, None),
            ("name", "VARCHAR", None, None, None, None, None),
        ]
        mock_adapter.connection = mock_cursor
        mock_adapter.execute_query = Mock(return_value=mock_cursor)

        comparator.infer_query_schema("SELECT id, name FROM test")

        # Should have attempted describe_query_schema first
        mock_adapter.describe_query_schema.assert_called_once()
        # Then should have tried LIMIT 0 fallback
        mock_adapter.execute_query.assert_called()

    def test_infer_query_schema_no_adapter_method(self, comparator, mock_adapter):
        """Test that infer_query_schema falls back when adapter method doesn't exist."""
        # Don't set describe_query_schema (it shouldn't exist)
        if hasattr(mock_adapter, "describe_query_schema"):
            delattr(mock_adapter, "describe_query_schema")

        # Mock the result of execute_query to have description attribute
        mock_result = MagicMock()
        mock_result.description = [
            ("id", "INTEGER", None, None, None, None, None),
        ]
        mock_adapter.execute_query = Mock(return_value=mock_result)

        comparator.infer_query_schema("SELECT id FROM test")

        # Should have tried LIMIT 0 approach
        mock_adapter.execute_query.assert_called()
        # Verify it was called with LIMIT 0 query
        call_args = mock_adapter.execute_query.call_args[0][0]
        assert "LIMIT 0" in call_args
