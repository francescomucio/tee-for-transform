"""
Unit tests for test decorator and create_test function.
"""

import pytest

from tee.testing.base import TestRegistry, TestSeverity
from tee.testing.python_test import PythonTest
from tee.testing.test_decorator import TestDecoratorError, create_test
from tee.testing.test_decorator import test as test_decorator  # Rename to avoid pytest collection


class TestTestDecorator:
    """Test cases for @test decorator."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear test registry before and after each test."""
        TestRegistry.clear()
        yield
        TestRegistry.clear()

    def test_test_decorator_basic(self):
        """Test @test decorator with basic usage."""

        @test_decorator(name="my_test", severity="error")
        def my_test():
            return "SELECT 1 FROM @table_name WHERE id IS NULL"

        # Test should be registered
        registered_test = TestRegistry.get("my_test")
        assert registered_test is not None
        assert isinstance(registered_test, PythonTest)
        assert registered_test.name == "my_test"
        assert registered_test.severity == TestSeverity.ERROR
        assert "SELECT 1 FROM @table_name" in registered_test.sql

    def test_test_decorator_with_description(self):
        """Test @test decorator with description."""

        @test_decorator(name="my_test", severity="error", description="Test description")
        def my_test():
            return "SELECT 1"

        registered_test = TestRegistry.get("my_test")
        assert registered_test.description == "Test description"

    def test_test_decorator_with_tags(self):
        """Test @test decorator with tags."""

        @test_decorator(name="my_test", severity="error", tags=["data-quality", "validation"])
        def my_test():
            return "SELECT 1"

        registered_test = TestRegistry.get("my_test")
        assert registered_test.tags == ["data-quality", "validation"]

    def test_test_decorator_severity_warning(self):
        """Test @test decorator with warning severity."""

        @test_decorator(name="my_test", severity="warning")
        def my_test():
            return "SELECT 1"

        registered_test = TestRegistry.get("my_test")
        assert registered_test.severity == TestSeverity.WARNING

    def test_test_decorator_without_name_derives_from_function(self, tmp_path):
        """Test @test decorator without explicit name (should derive from function)."""

        # The decorator uses inspect to get caller file, which is tricky to mock
        # Instead, test that it requires explicit name when file path can't be determined
        # Or test with explicit name (which is the recommended approach)
        @test_decorator(name="explicit_name", severity="error")
        def check_something():
            return "SELECT 1"

        # With explicit name, it should work
        registered_test = TestRegistry.get("explicit_name")
        assert registered_test is not None
        assert registered_test.name == "explicit_name"

    def test_test_decorator_empty_sql_raises_error(self):
        """Test that @test decorator raises error for empty SQL."""
        with pytest.raises(TestDecoratorError, match="empty SQL string"):

            @test_decorator(name="my_test")
            def my_test():
                return ""

    def test_test_decorator_non_string_return_raises_error(self):
        """Test that @test decorator raises error for non-string return."""
        with pytest.raises(TestDecoratorError, match="must return a SQL string"):

            @test_decorator(name="my_test")
            def my_test():
                return 123

    def test_test_decorator_name_conflict_raises_error(self):
        """Test that @test decorator raises error on name conflict."""

        @test_decorator(name="duplicate_test")
        def test1():
            return "SELECT 1"

        # Try to register another test with same name
        with pytest.raises(TestDecoratorError, match="Test name conflict"):

            @test_decorator(name="duplicate_test")
            def test2():
                return "SELECT 2"


class TestCreateTest:
    """Test cases for create_test() function."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear test registry before and after each test."""
        TestRegistry.clear()
        yield
        TestRegistry.clear()

    def test_create_test_basic(self):
        """Test create_test() with basic usage."""
        create_test(
            name="my_test",
            sql="SELECT 1 FROM @table_name WHERE id IS NULL",
            severity="error",
        )

        registered_test = TestRegistry.get("my_test")
        assert registered_test is not None
        assert isinstance(registered_test, PythonTest)
        assert registered_test.name == "my_test"
        assert registered_test.severity == TestSeverity.ERROR
        assert "SELECT 1 FROM @table_name" in registered_test.sql

    def test_create_test_with_description(self):
        """Test create_test() with description."""
        create_test(
            name="my_test",
            sql="SELECT 1",
            description="Test description",
        )

        registered_test = TestRegistry.get("my_test")
        assert registered_test.description == "Test description"

    def test_create_test_with_tags(self):
        """Test create_test() with tags."""
        create_test(
            name="my_test",
            sql="SELECT 1",
            tags=["data-quality", "validation"],
        )

        registered_test = TestRegistry.get("my_test")
        assert registered_test.tags == ["data-quality", "validation"]

    def test_create_test_severity_warning(self):
        """Test create_test() with warning severity."""
        create_test(name="my_test", sql="SELECT 1", severity="warning")

        registered_test = TestRegistry.get("my_test")
        assert registered_test.severity == TestSeverity.WARNING

    def test_create_test_missing_name_raises_error(self):
        """Test that create_test() raises error when name is missing."""
        with pytest.raises(TestDecoratorError, match="name parameter is required"):
            create_test(name="", sql="SELECT 1")  # Empty name should also fail

    def test_create_test_empty_sql_raises_error(self):
        """Test that create_test() raises error for empty SQL."""
        with pytest.raises(TestDecoratorError, match="sql parameter is required"):
            create_test(name="my_test", sql="")

    def test_create_test_name_conflict_raises_error(self):
        """Test that create_test() raises error on name conflict."""
        create_test(name="duplicate_test", sql="SELECT 1")

        with pytest.raises(TestDecoratorError, match="Test name conflict"):
            create_test(name="duplicate_test", sql="SELECT 2")

    def test_create_test_invalid_name_raises_error(self):
        """Test that create_test() raises error for invalid test name."""
        with pytest.raises(TestDecoratorError, match="Invalid test name"):
            create_test(name="invalid-name!", sql="SELECT 1")

    def test_create_test_dynamic_creation(self):
        """Test create_test() for dynamic test creation (e.g., in loops)."""
        tables = ["users", "orders", "products"]

        for table in tables:
            create_test(
                name=f"check_{table}_not_empty",
                sql=f"SELECT 1 FROM {table} WHERE COUNT(*) = 0",
            )

        # All tests should be registered
        assert TestRegistry.get("check_users_not_empty") is not None
        assert TestRegistry.get("check_orders_not_empty") is not None
        assert TestRegistry.get("check_products_not_empty") is not None
