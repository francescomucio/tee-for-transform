"""
Test cases for function adapter interface.

These tests verify that adapters correctly implement the function
management interface and can be reused across different adapters.
"""

from unittest.mock import Mock

import pytest

from tee.adapters.base import DatabaseAdapter


class TestFunctionAdapterInterface:
    """Test cases for function adapter interface compliance."""

    def test_adapter_has_create_function_abstract_method(self):
        """Test that DatabaseAdapter defines create_function as abstract."""
        assert hasattr(DatabaseAdapter, "create_function")

        # Check if it's abstract by trying to instantiate a class without implementing it
        class IncompleteAdapter(DatabaseAdapter):
            def get_default_dialect(self):
                return "duckdb"

            def get_supported_materializations(self):
                return []

            def connect(self):
                pass

            def disconnect(self):
                pass

            def execute_query(self, query: str):
                pass

            def create_table(self, table_name: str, query: str, metadata=None):
                pass

            def create_view(self, view_name: str, query: str, metadata=None):
                pass

            def table_exists(self, table_name: str):
                return False

            def drop_table(self, table_name: str):
                pass

            def get_table_info(self, table_name: str):
                return {}

            def describe_query_schema(self, sql_query: str):
                return []

            def add_column(self, table_name: str, column: dict):
                pass

            def drop_column(self, table_name: str, column_name: str):
                pass

        # Should raise TypeError because abstract methods aren't implemented
        with pytest.raises(TypeError):
            IncompleteAdapter({"type": "test"})

    def test_adapter_has_function_exists_abstract_method(self):
        """Test that DatabaseAdapter defines function_exists as abstract."""
        assert hasattr(DatabaseAdapter, "function_exists")

    def test_adapter_has_drop_function_abstract_method(self):
        """Test that DatabaseAdapter defines drop_function as abstract."""
        assert hasattr(DatabaseAdapter, "drop_function")

    def test_adapter_has_get_function_info_method(self):
        """Test that DatabaseAdapter defines get_function_info (non-abstract)."""
        assert hasattr(DatabaseAdapter, "get_function_info")
        # This should be a concrete method, not abstract

    def test_mock_adapter_implements_function_interface(self):
        """Test that a mock adapter can implement the function interface."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.create_function = Mock()
        adapter.function_exists = Mock(return_value=False)
        adapter.drop_function = Mock()
        adapter.get_function_info = Mock(
            return_value={"function_name": "test.func", "exists": False}
        )

        # Test create_function
        function_name = "my_schema.calculate_percentage"
        function_sql = "CREATE OR REPLACE FUNCTION calculate_percentage(numerator DOUBLE, denominator DOUBLE) RETURNS DOUBLE AS $$ SELECT (numerator / denominator) * 100.0 $$;"
        metadata = {"description": "Calculate percentage", "tags": ["math"]}

        adapter.create_function(function_name, function_sql, metadata)
        adapter.create_function.assert_called_once_with(function_name, function_sql, metadata)

        # Test function_exists
        result = adapter.function_exists(function_name)
        assert result is False
        adapter.function_exists.assert_called_once_with(function_name)

        # Test drop_function
        adapter.drop_function(function_name)
        adapter.drop_function.assert_called_once_with(function_name)

        # Test get_function_info
        info = adapter.get_function_info(function_name)
        assert info == {"function_name": "test.func", "exists": False}
        adapter.get_function_info.assert_called_once_with(function_name)


class TestFunctionAdapterBehavior:
    """Test cases for function adapter behavior patterns."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter with realistic behavior."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.create_function = Mock()
        adapter.function_exists = Mock(return_value=False)
        adapter.drop_function = Mock()
        adapter.get_function_info = Mock(
            return_value={"function_name": "my_schema.calculate_percentage", "exists": False}
        )
        return adapter

    def test_create_function_behavior(self, mock_adapter):
        """Test expected behavior for create_function."""
        function_name = "my_schema.calculate_percentage"
        function_sql = "CREATE OR REPLACE FUNCTION calculate_percentage(numerator DOUBLE, denominator DOUBLE) RETURNS DOUBLE AS $$ SELECT (numerator / denominator) * 100.0 $$;"
        metadata = {"description": "Calculate percentage", "tags": ["math", "utility"]}

        # Execute create_function
        mock_adapter.create_function(function_name, function_sql, metadata)

        # Verify the call
        mock_adapter.create_function.assert_called_once_with(function_name, function_sql, metadata)

    def test_function_exists_behavior(self, mock_adapter):
        """Test expected behavior for function_exists."""
        function_name = "my_schema.calculate_percentage"

        # Test when function doesn't exist
        mock_adapter.function_exists.return_value = False
        result = mock_adapter.function_exists(function_name)
        assert result is False

        # Test when function exists
        mock_adapter.function_exists.return_value = True
        result = mock_adapter.function_exists(function_name)
        assert result is True

        # Verify it was called
        assert mock_adapter.function_exists.call_count == 2

    def test_drop_function_behavior(self, mock_adapter):
        """Test expected behavior for drop_function."""
        function_name = "my_schema.calculate_percentage"

        # Execute drop_function
        mock_adapter.drop_function(function_name)

        # Verify the call
        mock_adapter.drop_function.assert_called_once_with(function_name)

    def test_get_function_info_behavior(self, mock_adapter):
        """Test expected behavior for get_function_info."""
        function_name = "my_schema.calculate_percentage"

        # Get function info
        info = mock_adapter.get_function_info(function_name)

        # Verify result structure
        assert "function_name" in info
        assert "exists" in info
        assert info["function_name"] == "my_schema.calculate_percentage"
        assert info["exists"] is False

        # Verify it was called
        mock_adapter.get_function_info.assert_called_once_with(function_name)


class TestFunctionAdapterErrorHandling:
    """Test cases for function adapter error handling."""

    @pytest.fixture
    def mock_adapter_with_errors(self):
        """Create a mock adapter that raises errors."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.create_function = Mock(side_effect=Exception("Function creation failed"))
        adapter.function_exists = Mock(side_effect=Exception("Function exists check failed"))
        adapter.drop_function = Mock(side_effect=Exception("Function drop failed"))
        adapter.get_function_info = Mock(side_effect=Exception("Get function info failed"))
        return adapter

    def test_create_function_error_handling(self, mock_adapter_with_errors):
        """Test error handling for create_function."""
        function_name = "my_schema.calculate_percentage"
        function_sql = "CREATE OR REPLACE FUNCTION ..."

        with pytest.raises(Exception, match="Function creation failed"):
            mock_adapter_with_errors.create_function(function_name, function_sql)

    def test_function_exists_error_handling(self, mock_adapter_with_errors):
        """Test error handling for function_exists."""
        function_name = "my_schema.calculate_percentage"

        with pytest.raises(Exception, match="Function exists check failed"):
            mock_adapter_with_errors.function_exists(function_name)

    def test_drop_function_error_handling(self, mock_adapter_with_errors):
        """Test error handling for drop_function."""
        function_name = "my_schema.calculate_percentage"

        with pytest.raises(Exception, match="Function drop failed"):
            mock_adapter_with_errors.drop_function(function_name)

    def test_get_function_info_error_handling(self, mock_adapter_with_errors):
        """Test error handling for get_function_info."""
        function_name = "my_schema.calculate_percentage"

        with pytest.raises(Exception, match="Get function info failed"):
            mock_adapter_with_errors.get_function_info(function_name)


class TestFunctionAdapterDefaultImplementation:
    """Test cases for default function adapter implementations."""

    def test_get_function_info_default_implementation(self):
        """Test that get_function_info has a default implementation."""

        # Create a minimal adapter that implements all abstract methods
        class MinimalAdapter(DatabaseAdapter):
            def get_default_dialect(self):
                return "duckdb"

            def get_supported_materializations(self):
                return []

            def connect(self):
                pass

            def disconnect(self):
                pass

            def execute_query(self, query: str):
                pass

            def create_table(self, table_name: str, query: str, metadata=None):
                pass

            def create_view(self, view_name: str, query: str, metadata=None):
                pass

            def table_exists(self, table_name: str):
                return False

            def drop_table(self, table_name: str):
                pass

            def get_table_info(self, table_name: str):
                return {}

            def describe_query_schema(self, sql_query: str):
                return []

            def add_column(self, table_name: str, column: dict):
                pass

            def drop_column(self, table_name: str, column_name: str):
                pass

            def create_function(self, function_name: str, function_sql: str, metadata=None):
                pass

            def function_exists(self, function_name: str):
                return False

            def drop_function(self, function_name: str):
                pass

        adapter = MinimalAdapter({"type": "test"})

        # Test that get_function_info works with default implementation
        function_name = "my_schema.calculate_percentage"
        info = adapter.get_function_info(function_name)

        # Verify default implementation structure
        assert "function_name" in info
        assert "exists" in info
        assert info["function_name"] == function_name
        assert info["exists"] is False  # Because function_exists returns False


class TestFunctionAdapterMetadata:
    """Test cases for function adapter metadata handling."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter for metadata testing."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.create_function = Mock()
        adapter.attach_tags = Mock()
        adapter.attach_object_tags = Mock()
        return adapter

    def test_create_function_with_metadata(self, mock_adapter):
        """Test that create_function accepts metadata parameter."""
        function_name = "my_schema.calculate_percentage"
        function_sql = "CREATE OR REPLACE FUNCTION ..."
        metadata = {
            "description": "Calculate percentage",
            "tags": ["math", "utility"],
            "object_tags": {"category": "calculation", "complexity": "simple"},
        }

        # Execute create_function with metadata
        mock_adapter.create_function(function_name, function_sql, metadata)

        # Verify the call included metadata
        mock_adapter.create_function.assert_called_once_with(function_name, function_sql, metadata)

    def test_create_function_without_metadata(self, mock_adapter):
        """Test that create_function works without metadata."""
        function_name = "my_schema.calculate_percentage"
        function_sql = "CREATE OR REPLACE FUNCTION ..."

        # Execute create_function without metadata
        mock_adapter.create_function(function_name, function_sql)

        # Verify the call (metadata should be None or omitted)
        mock_adapter.create_function.assert_called_once()
        call_args = mock_adapter.create_function.call_args
        assert call_args[0][0] == function_name
        assert call_args[0][1] == function_sql
        # Metadata should be None or not provided
        assert len(call_args[0]) == 2 or call_args[0][2] is None


class TestFunctionAdapterQualifiedNames:
    """Test cases for function adapter qualified name handling."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter for qualified name testing."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.create_function = Mock()
        adapter.function_exists = Mock(return_value=False)
        adapter.drop_function = Mock()
        adapter.get_function_info = Mock(return_value={"function_name": "", "exists": False})
        return adapter

    def test_qualified_function_names(self, mock_adapter):
        """Test that functions can be created with qualified names."""
        qualified_names = [
            "my_schema.calculate_percentage",
            "public.math_utils",
            "analytics.functions.complex_calculation",
        ]

        for function_name in qualified_names:
            function_sql = (
                f"CREATE OR REPLACE FUNCTION {function_name}() RETURNS DOUBLE AS $$ SELECT 1.0 $$;"
            )
            mock_adapter.create_function(function_name, function_sql)

        # Verify all qualified names were used
        assert mock_adapter.create_function.call_count == len(qualified_names)

    def test_unqualified_function_names(self, mock_adapter):
        """Test that functions can be created with unqualified names."""
        unqualified_names = ["calculate_percentage", "math_utils", "complex_calculation"]

        for function_name in unqualified_names:
            function_sql = (
                f"CREATE OR REPLACE FUNCTION {function_name}() RETURNS DOUBLE AS $$ SELECT 1.0 $$;"
            )
            mock_adapter.create_function(function_name, function_sql)

        # Verify all unqualified names were used
        assert mock_adapter.create_function.call_count == len(unqualified_names)
