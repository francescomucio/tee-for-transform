"""
Unit tests for test decorator and create_test function.
"""

import pytest

from t4t.testing.base import TestRegistry, TestSeverity
from t4t.testing.python_test import PythonTest
from t4t.testing.test_decorator import TestDecoratorError, create_test
from t4t.testing.test_decorator import test as test_decorator  # Rename to avoid pytest collection


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
        # Create a tests/ subfolder to match the expected project structure
        import sys

        tests_folder = tmp_path / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "test_check_something.py"
        # Don't import from t4t.testing in the file content - the module
        # namespace already has 'test' injected by the discovery process
        test_file.write_text(
            """
@test(severity="error")
def check_something():
    return "SELECT 1"
"""
        )

        # Execute the file in an isolated module to trigger the decorator
        import importlib.util

        module_name = f"temp_derive_test_{hash(test_file)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        module.__file__ = str(test_file.absolute())

        # Import test decorator into the module (as 'test' so the file content works)
        from t4t.testing.test_decorator import test as test_decorator_func

        test_decorator_func.__test__ = False
        module.test = test_decorator_func

        with open(test_file) as f:
            content = f.read()
        exec(content, module.__dict__)

        # Name should be derived from file and function: {file_stem}__{function_name}
        # Since the file is in tests/ (not a subfolder), no folder prefix
        registered_test = TestRegistry.get("test_check_something__check_something")
        assert registered_test is not None
        assert registered_test.name == "test_check_something__check_something"

        if module_name in sys.modules:
            del sys.modules[module_name]

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

    def test_test_decorator_function_exception_raises_error(self):
        """Test that @test decorator properly handles exceptions from decorated functions."""

        with pytest.raises(TestDecoratorError, match="Failed to execute test function"):

            @test_decorator(name="my_test")
            def my_test():
                raise ValueError("Something went wrong in the function")


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

    def test_create_test_with_severity_enum(self):
        """Test create_test() with TestSeverity enum directly."""
        create_test(name="my_test", sql="SELECT 1", severity=TestSeverity.WARNING)

        registered_test = TestRegistry.get("my_test")
        assert registered_test.severity == TestSeverity.WARNING

    def test_create_test_with_metadata_kwargs(self):
        """Test create_test() with additional metadata kwargs."""
        create_test(
            name="my_test",
            sql="SELECT 1",
            severity="error",
            extra_param="value",
        )

        registered_test = TestRegistry.get("my_test")
        assert registered_test is not None
        assert registered_test.name == "my_test"

    def test_create_test_whitespace_only_sql_raises_error(self):
        """Test that create_test() raises error for whitespace-only SQL."""
        with pytest.raises(TestDecoratorError, match="sql parameter is required"):
            create_test(name="my_test", sql="   ")

    def test_create_test_none_name_raises_error(self):
        """Test that create_test() raises error when name is None."""
        with pytest.raises(TestDecoratorError, match="name parameter is required"):
            create_test(name=None, sql="SELECT 1")  # type: ignore[arg-type]

    def test_create_test_none_sql_raises_error(self):
        """Test that create_test() raises error when sql is None."""
        with pytest.raises(TestDecoratorError, match="sql parameter is required"):
            create_test(name="my_test", sql=None)  # type: ignore[arg-type]

    def test_create_test_with_tags_none(self):
        """Test create_test() with tags=None."""
        create_test(name="my_test", sql="SELECT 1", tags=None)

        registered_test = TestRegistry.get("my_test")
        assert registered_test.tags == []

    def test_create_test_with_description_none(self):
        """Test create_test() with description=None."""
        create_test(name="my_test", sql="SELECT 1", description=None)

        registered_test = TestRegistry.get("my_test")
        assert registered_test.description is None

    def test_test_decorator_error_exception(self):
        """Test that TestDecoratorError is a proper exception."""
        error = TestDecoratorError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"


class TestDeriveTestName:
    """Test cases for _derive_test_name function."""

    def test_derive_test_name_with_folder_and_function(self):
        """Test deriving test name with folder and function name."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name("/project/tests/my_schema/check_minimum_rows.py", "my_function")
        assert result == "my_schema__check_minimum_rows__my_function"

    def test_derive_test_name_with_folder_no_function(self):
        """Test deriving test name with folder but no function name."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name("/project/tests/my_schema/check_minimum_rows.py", None)
        assert result == "my_schema__check_minimum_rows"

    def test_derive_test_name_root_folder_with_function(self):
        """Test deriving test name from root tests/ folder with function."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name("/project/tests/check_minimum_rows.py", "my_function")
        assert result == "check_minimum_rows__my_function"

    def test_derive_test_name_root_folder_no_function(self):
        """Test deriving test name from root tests/ folder without function."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name("/project/tests/check_minimum_rows.py", None)
        assert result == "check_minimum_rows"

    def test_derive_test_name_no_file_path_with_function(self):
        """Test deriving test name with no file path but with function name."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name(None, "my_function")
        assert result == "my_function"

    def test_derive_test_name_no_file_path_no_function_raises_error(self):
        """Test that _derive_test_name raises error with no file path and no function."""
        from t4t.testing.test_decorator import _derive_test_name

        with pytest.raises(TestDecoratorError, match="Cannot derive test name"):
            _derive_test_name(None, None)

    def test_derive_test_name_deeply_nested_folder(self):
        """Test deriving test name from deeply nested folder."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name("/project/tests/schema/subfolder/check_test.py", "my_func")
        assert result == "subfolder__check_test__my_func"

    def test_derive_test_name_tests_folder_name_edge(self):
        """Test deriving test name when parent folder is 'tests'."""
        from t4t.testing.test_decorator import _derive_test_name

        result = _derive_test_name("/project/tests/check_test.py", "my_func")
        assert result == "check_test__my_func"
