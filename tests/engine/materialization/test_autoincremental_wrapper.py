"""
Test cases for AutoIncrementalWrapper.
"""

from unittest.mock import Mock

import pytest
import sqlglot
from sqlglot import expressions as exp

from t4t.engine.materialization.auto_incremental_wrapper import AutoIncrementalWrapper


class TestAutoIncrementalWrapper:
    """Test cases for AutoIncrementalWrapper."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter."""
        adapter = Mock()
        adapter.utils = Mock()
        adapter.utils.qualify_object_name = Mock(return_value="my_schema.dim_brand")
        return adapter

    @pytest.fixture
    def wrapper(self, mock_adapter):
        """Create an AutoIncrementalWrapper instance."""
        return AutoIncrementalWrapper(mock_adapter)

    @pytest.fixture
    def metadata_with_auto_incremental(self):
        """Sample metadata with auto_incremental column."""
        return {
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ]
        }

    @pytest.fixture
    def metadata_without_auto_incremental(self):
        """Sample metadata without auto_incremental column."""
        return {
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ]
        }

    def test_should_wrap_with_auto_incremental(self, wrapper, metadata_with_auto_incremental):
        """Test should_wrap returns True when auto_incremental column exists."""
        assert wrapper.should_wrap(metadata_with_auto_incremental) is True

    def test_should_wrap_without_auto_incremental(self, wrapper, metadata_without_auto_incremental):
        """Test should_wrap returns False when no auto_incremental column."""
        assert wrapper.should_wrap(metadata_without_auto_incremental) is False

    def test_should_wrap_with_none_metadata(self, wrapper):
        """Test should_wrap returns False when metadata is None."""
        assert wrapper.should_wrap(None) is False

    def test_should_wrap_with_empty_schema(self, wrapper):
        """Test should_wrap returns False when schema is empty."""
        assert wrapper.should_wrap({"schema": []}) is False

    def test_should_wrap_multiple_auto_incremental_raises_error(self, wrapper):
        """Test should_wrap raises error when multiple auto_incremental columns exist."""
        metadata = {
            "schema": [
                {"name": "id1", "datatype": "integer", "auto_incremental": True},
                {"name": "id2", "datatype": "integer", "auto_incremental": True},
            ]
        }
        with pytest.raises(ValueError, match="Multiple auto_incremental columns"):
            wrapper.should_wrap(metadata)

    def test_wrap_query_for_merge_basic(self, wrapper, metadata_with_auto_incremental):
        """Test wrap_query_for_merge with basic query."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        result = wrapper.wrap_query_for_merge(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
        )

        assert "WITH source_data AS" in result
        assert "existing_data AS" in result
        assert "max_id AS" in result
        assert "SELECT" in result
        assert "brand_id" in result
        assert "brand_name" in result
        assert "COALESCE(MAX(brand_id), 0)" in result
        assert "ROW_NUMBER() OVER" in result
        assert "LEFT JOIN existing_data" in result
        assert "WHERE e.brand_name IS NULL" in result

    def test_wrap_query_for_merge_with_time_filter(self, wrapper, metadata_with_auto_incremental):
        """Test wrap_query_for_merge with time filter."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        time_filter = "created_date > '2024-01-01'"
        result = wrapper.wrap_query_for_merge(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
            time_filter=time_filter,
        )

        assert "AND created_date > '2024-01-01'" in result

    def test_wrap_query_for_merge_no_unique_key_raises_error(
        self, wrapper, metadata_with_auto_incremental
    ):
        """Test wrap_query_for_merge raises error when unique_key is missing."""
        sql = "SELECT DISTINCT brand FROM source_table"
        with pytest.raises(ValueError, match="unique_key is required"):
            wrapper.wrap_query_for_merge(
                sql_query=sql,
                table_name="dim_brand",
                metadata=metadata_with_auto_incremental,
                unique_key=[],
            )

    def test_wrap_query_for_merge_no_auto_incremental_returns_original(
        self, wrapper, metadata_without_auto_incremental
    ):
        """Test wrap_query_for_merge returns original query when no auto_incremental."""
        sql = "SELECT DISTINCT brand FROM source_table"
        result = wrapper.wrap_query_for_merge(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_without_auto_incremental,
            unique_key=["brand_name"],
        )
        assert result == sql

    def test_wrap_query_for_append_basic(self, wrapper, metadata_with_auto_incremental):
        """Test wrap_query_for_append with basic query."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        result = wrapper.wrap_query_for_append(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
        )

        assert "WITH source_data AS" in result
        assert "max_id AS" in result
        assert "SELECT" in result
        assert "brand_id" in result
        assert "brand_name" in result
        assert "COALESCE(MAX(brand_id), 0)" in result
        assert "ROW_NUMBER() OVER" in result
        assert "CROSS JOIN max_id" in result
        # Append should NOT have LEFT JOIN exclusion
        assert "LEFT JOIN existing_data" not in result
        assert "WHERE e.brand_name IS NULL" not in result

    def test_wrap_query_for_append_with_time_filter(self, wrapper, metadata_with_auto_incremental):
        """Test wrap_query_for_append with time filter."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        time_filter = "created_date > '2024-01-01'"
        result = wrapper.wrap_query_for_append(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            time_filter=time_filter,
        )

        assert "AND created_date > '2024-01-01'" in result

    def test_wrap_query_for_append_no_auto_incremental_returns_original(
        self, wrapper, metadata_without_auto_incremental
    ):
        """Test wrap_query_for_append returns original query when no auto_incremental."""
        sql = "SELECT DISTINCT brand FROM source_table"
        result = wrapper.wrap_query_for_append(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_without_auto_incremental,
        )
        assert result == sql

    def test_wrap_query_for_delete_insert_basic(self, wrapper, metadata_with_auto_incremental):
        """Test wrap_query_for_delete_insert with basic query."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        result = wrapper.wrap_query_for_delete_insert(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
        )

        assert "WITH source_data AS" in result
        assert "existing_data AS" in result
        assert "max_id AS" in result
        assert "SELECT" in result
        assert "brand_id" in result
        assert "brand_name" in result
        assert "COALESCE(MAX(brand_id), 0)" in result
        assert "ROW_NUMBER() OVER" in result
        assert "LEFT JOIN existing_data" in result
        assert "WHERE e.brand_name IS NULL" in result

    def test_wrap_query_for_delete_insert_without_unique_key(
        self, wrapper, metadata_with_auto_incremental
    ):
        """Test wrap_query_for_delete_insert without unique_key (no exclusion)."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        result = wrapper.wrap_query_for_delete_insert(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=None,
        )

        assert "WITH source_data AS" in result
        assert "max_id AS" in result
        # Should NOT have existing_data CTE or LEFT JOIN when unique_key is None
        assert "existing_data AS" not in result
        assert "LEFT JOIN existing_data" not in result
        assert "WHERE e.brand_name IS NULL" not in result

    def test_wrap_query_for_delete_insert_with_time_filter(
        self, wrapper, metadata_with_auto_incremental
    ):
        """Test wrap_query_for_delete_insert with time filter."""
        sql = "SELECT DISTINCT brand FROM source_table WHERE brand IS NOT NULL"
        time_filter = "created_date > '2024-01-01'"
        result = wrapper.wrap_query_for_delete_insert(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
            time_filter=time_filter,
        )

        assert "AND created_date > '2024-01-01'" in result

    def test_wrap_query_for_delete_insert_no_auto_incremental_returns_original(
        self, wrapper, metadata_without_auto_incremental
    ):
        """Test wrap_query_for_delete_insert returns original query when no auto_incremental."""
        sql = "SELECT DISTINCT brand FROM source_table"
        result = wrapper.wrap_query_for_delete_insert(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_without_auto_incremental,
            unique_key=["brand_name"],
        )
        assert result == sql

    def test_wrap_query_uses_qualified_table_name(self, wrapper, metadata_with_auto_incremental):
        """Test that wrap_query uses qualified table name when adapter supports it."""
        sql = "SELECT DISTINCT brand FROM source_table"
        result = wrapper.wrap_query_for_merge(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
        )

        assert "my_schema.dim_brand" in result
        wrapper.adapter.utils.qualify_object_name.assert_called_with("dim_brand")

    def test_wrap_query_fallback_to_unqualified_name(self, metadata_with_auto_incremental):
        """Test that wrap_query falls back to unqualified name when adapter doesn't support qualification."""
        adapter = Mock()
        adapter.utils = Mock()
        # Simulate adapter without qualify_object_name
        del adapter.utils.qualify_object_name

        wrapper = AutoIncrementalWrapper(adapter)
        sql = "SELECT DISTINCT brand FROM source_table"
        result = wrapper.wrap_query_for_merge(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
        )

        assert "dim_brand" in result

    def test_wrap_query_handles_exception_in_qualification(self, metadata_with_auto_incremental):
        """Test that wrap_query handles exceptions during table name qualification."""
        adapter = Mock()
        adapter.utils = Mock()
        adapter.utils.qualify_object_name = Mock(side_effect=Exception("Qualification failed"))

        wrapper = AutoIncrementalWrapper(adapter)
        sql = "SELECT DISTINCT brand FROM source_table"
        result = wrapper.wrap_query_for_merge(
            sql_query=sql,
            table_name="dim_brand",
            metadata=metadata_with_auto_incremental,
            unique_key=["brand_name"],
        )

        # Should fallback to unqualified name
        assert "dim_brand" in result

    # ========================================================================
    # Tests for _extract_query_columns and helper methods
    # ========================================================================

    def test_extract_query_columns_with_sqlglot(self, wrapper):
        """Test _extract_query_columns with sqlglot parsing."""
        sql = "SELECT brand AS brand_name, category FROM source_table"
        columns = wrapper._extract_query_columns(sql)
        assert "brand_name" in columns
        assert "category" in columns

    def test_extract_query_columns_with_regex_fallback(self, wrapper):
        """Test _extract_query_columns falls back to regex when sqlglot fails."""
        # Use invalid SQL that sqlglot can't parse
        sql = "SELECT brand AS brand_name, category FROM"
        columns = wrapper._extract_query_columns(sql)
        # Should return empty list or handle gracefully
        assert isinstance(columns, list)

    def test_extract_query_columns_with_qualified_names(self, wrapper):
        """Test _extract_query_columns with qualified column names."""
        sql = "SELECT table.brand AS brand_name, table.category FROM source_table"
        columns = wrapper._extract_query_columns(sql)
        assert "brand_name" in columns
        assert "category" in columns

    def test_extract_query_columns_with_row_number(self, wrapper):
        """Test _extract_query_columns with ROW_NUMBER() expression."""
        sql = "SELECT ROW_NUMBER() OVER (ORDER BY brand) AS brand_id, brand FROM source_table"
        columns = wrapper._extract_query_columns(sql)
        assert "brand_id" in columns
        assert "brand" in columns

    def test_get_column_name_from_alias(self, wrapper):
        """Test _get_column_name_from_expression with Alias expression."""
        sql = "SELECT brand AS brand_name FROM source_table"
        parsed = sqlglot.parse_one(sql)
        expr = parsed.expressions[0]  # Should be an Alias
        assert isinstance(expr, exp.Alias)

        column_name = wrapper._get_column_name_from_expression(expr)
        assert column_name == "brand_name"

    def test_get_column_name_from_column(self, wrapper):
        """Test _get_column_name_from_expression with Column expression."""
        sql = "SELECT brand FROM source_table"
        parsed = sqlglot.parse_one(sql)
        expr = parsed.expressions[0]  # Should be a Column
        assert isinstance(expr, exp.Column)

        column_name = wrapper._get_column_name_from_expression(expr)
        assert column_name == "brand"

    def test_get_column_name_from_nested_expression(self, wrapper):
        """Test _get_column_name_from_expression with nested expression."""
        sql = "SELECT ROW_NUMBER() OVER (ORDER BY brand) AS brand_id FROM source_table"
        parsed = sqlglot.parse_one(sql)
        expr = parsed.expressions[0]  # Should be an Alias with nested expression

        column_name = wrapper._get_column_name_from_expression(expr)
        assert column_name == "brand_id"

    def test_extract_columns_with_regex_simple(self, wrapper):
        """Test _extract_columns_with_regex with simple SELECT."""
        sql = "SELECT brand, category FROM source_table"
        columns = wrapper._extract_columns_with_regex(sql)
        assert "brand" in columns
        assert "category" in columns

    def test_extract_columns_with_regex_with_aliases(self, wrapper):
        """Test _extract_columns_with_regex with aliases."""
        sql = "SELECT brand AS brand_name, category AS cat_name FROM source_table"
        columns = wrapper._extract_columns_with_regex(sql)
        assert "BRAND_NAME" in columns  # Regex converts to uppercase
        assert "CAT_NAME" in columns

    def test_extract_columns_with_regex_no_match(self, wrapper):
        """Test _extract_columns_with_regex when no SELECT...FROM pattern found."""
        sql = "INSERT INTO table VALUES (1, 2, 3)"
        columns = wrapper._extract_columns_with_regex(sql)
        assert columns == []

    def test_parse_column_string_with_alias(self, wrapper):
        """Test _parse_column_string with AS alias."""
        col = "brand AS brand_name"
        result = wrapper._parse_column_string(col)
        assert result == "BRAND_NAME"  # Uppercase from regex logic

    def test_parse_column_string_without_alias(self, wrapper):
        """Test _parse_column_string without alias."""
        col = "brand"
        result = wrapper._parse_column_string(col)
        assert result == "brand"

    def test_parse_column_string_qualified_name(self, wrapper):
        """Test _parse_column_string with qualified name."""
        col = "table.brand"
        result = wrapper._parse_column_string(col)
        assert result == "brand"

    def test_parse_column_string_qualified_with_alias(self, wrapper):
        """Test _parse_column_string with qualified name and alias."""
        col = "table.brand AS brand_name"
        result = wrapper._parse_column_string(col)
        assert result == "BRAND_NAME"

    def test_extract_query_columns_complex_query(self, wrapper):
        """Test _extract_query_columns with complex query."""
        sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name,
            category,
            COUNT(*) AS total
        FROM source_table
        GROUP BY brand, category
        """
        columns = wrapper._extract_query_columns(sql)
        assert "brand_id" in columns
        assert "brand_name" in columns
        assert "category" in columns
        assert "total" in columns
