"""
Unit tests for TestDiscovery class.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from t4t.testing.base import TestRegistry
from t4t.testing.sql_test import SqlTest
from t4t.testing.test_discovery import TestDiscovery, TestDiscoveryError


class TestTestDiscovery:
    """Test cases for TestDiscovery class."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear test registry before and after each test."""
        TestRegistry.clear()
        yield
        TestRegistry.clear()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def discovery(self, temp_dir):
        """Create a TestDiscovery instance."""
        return TestDiscovery(temp_dir)

    def test_init(self, temp_dir):
        """Test TestDiscovery initialization."""
        discovery = TestDiscovery(temp_dir)

        assert discovery.project_folder == Path(temp_dir)
        assert discovery.tests_folder == Path(temp_dir) / "tests"
        assert discovery._discovered_tests == {}

    def test_discover_tests_no_tests_folder(self, temp_dir):
        """Test discovery when tests/ folder doesn't exist."""
        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert tests == {}

    def test_discover_tests_empty_folder(self, temp_dir):
        """Test discovery when tests/ folder is empty."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert tests == {}

    def test_discover_tests_single_file(self, temp_dir):
        """Test discovering a single SQL test file."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        sql_file = tests_folder / "my_test.sql"
        sql_file.write_text("SELECT 1 FROM {{ table_name }}")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "my_test" in tests
        assert isinstance(tests["my_test"], SqlTest)
        assert tests["my_test"].name == "my_test"
        assert tests["my_test"].sql_file_path == sql_file

    def test_discover_tests_multiple_files(self, temp_dir):
        """Test discovering multiple SQL test files."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create multiple test files
        (tests_folder / "test1.sql").write_text("SELECT 1 FROM {{ table_name }}")
        (tests_folder / "test2.sql").write_text("SELECT 2 FROM {{ table_name }}")
        (tests_folder / "test3.sql").write_text("SELECT 3 FROM {{ table_name }}")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 3
        assert "test1" in tests
        assert "test2" in tests
        assert "test3" in tests
        assert all(isinstance(t, SqlTest) for t in tests.values())

    def test_discover_tests_subdirectories(self, temp_dir):
        """Test discovering SQL files in subdirectories."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        subfolder = tests_folder / "subfolder"
        subfolder.mkdir()

        (tests_folder / "test1.sql").write_text("SELECT 1")
        (subfolder / "test2.sql").write_text("SELECT 2")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Should find both files (rglob searches recursively)
        assert len(tests) == 2
        assert "test1" in tests
        assert "test2" in tests

    def test_discover_tests_duplicate_names(self, temp_dir, caplog):
        """Test handling duplicate test names in subdirectories."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        subfolder = tests_folder / "subfolder"
        subfolder.mkdir()

        (tests_folder / "my_test.sql").write_text("SELECT 1")
        (subfolder / "my_test.sql").write_text("SELECT 2")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Should warn about duplicate and use one of them
        assert len(tests) == 1
        assert "my_test" in tests
        assert "Duplicate test name" in caplog.text

    def test_discover_tests_ignores_non_sql_files(self, temp_dir):
        """Test that non-SQL files are ignored (except .py files which are now discovered)."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        (tests_folder / "test.sql").write_text("SELECT 1")
        (tests_folder / "test.txt").write_text("Not a SQL file")
        # Python files are now discovered, but this one has no test definitions, so it won't register anything
        (tests_folder / "test.py").write_text("print('not sql')")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Should discover the SQL file (Python file has no test definitions, so nothing registered)
        assert len(tests) == 1
        assert "test" in tests
        # The test should be a SqlTest (from the .sql file)
        from t4t.testing.sql_test import SqlTest

        assert isinstance(tests["test"], SqlTest)
        assert tests["test"].sql_file_path.suffix == ".sql"

    def test_discover_tests_caching(self, temp_dir):
        """Test that discovered tests are cached."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        (tests_folder / "test.sql").write_text("SELECT 1")

        discovery = TestDiscovery(temp_dir)
        tests1 = discovery.discover_tests()

        # Add another file
        (tests_folder / "test2.sql").write_text("SELECT 2")

        # Should return cached results
        tests2 = discovery.discover_tests()

        assert len(tests2) == 1  # Still only 1, not 2
        assert tests1 is tests2  # Same object

    def test_discover_tests_invalid_sql_file(self, temp_dir, caplog):
        """Test handling of invalid SQL files (should skip gracefully)."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create a valid file
        (tests_folder / "valid.sql").write_text("SELECT 1 FROM {{ table_name }}")

        # Create a file that will cause an error when loading
        # (e.g., permission denied or corrupted)
        invalid_file = tests_folder / "invalid.sql"
        invalid_file.write_text("SELECT 1")

        # Mock SqlTest to raise an error for invalid file
        with patch("t4t.testing.test_discovery.SqlTest") as mock_sql_test:
            mock_sql_test.side_effect = Exception("Failed to load")

            discovery = TestDiscovery(temp_dir)
            discovery.discover_tests()

            # Should skip invalid file but continue
            assert "Failed to load SQL test from" in caplog.text

    def test_register_discovered_tests(self, temp_dir):
        """Test registering discovered tests with TestRegistry."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        (tests_folder / "test1.sql").write_text("SELECT 1 FROM {{ table_name }}")
        (tests_folder / "test2.sql").write_text("SELECT 2 FROM {{ table_name }}")

        discovery = TestDiscovery(temp_dir)
        discovery.register_discovered_tests()

        # Verify tests are registered
        assert TestRegistry.get("test1") is not None
        assert TestRegistry.get("test2") is not None
        assert isinstance(TestRegistry.get("test1"), SqlTest)
        assert isinstance(TestRegistry.get("test2"), SqlTest)

    def test_register_discovered_tests_no_tests(self, temp_dir):
        """Test registering when no tests are found."""
        discovery = TestDiscovery(temp_dir)
        discovery.register_discovered_tests()

        # Should not raise any errors
        assert TestRegistry.get("nonexistent") is None

    def test_register_discovered_tests_duplicate_registration(self, temp_dir):
        """Test registering tests that already exist in registry."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        (tests_folder / "test1.sql").write_text("SELECT 1 FROM {{ table_name }}")

        # Register a standard test with same name first
        from t4t.testing.standard_tests import NotNullTest

        standard_test = NotNullTest()
        TestRegistry.register(standard_test)

        # Now try to register SQL test with same name
        discovery = TestDiscovery(temp_dir)
        discovery.register_discovered_tests()

        # Should still register (TestRegistry will handle conflict)
        # The SQL test should be registered
        registered_test = TestRegistry.get("test1")
        assert registered_test is not None

    def test_discover_tests_file_encoding(self, temp_dir):
        """Test that SQL files with UTF-8 encoding are handled correctly."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        sql_file = tests_folder / "test.sql"
        sql_file.write_text(
            "-- Test with émojis 🎉\nSELECT 1 FROM {{ table_name }}", encoding="utf-8"
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "test" in tests
        # Verify SQL content includes the emoji
        content = tests["test"]._load_sql_content()
        assert "🎉" in content or "émojis" in content

    def test_discover_function_tests_no_folder(self, temp_dir):
        """Test discover_function_tests when tests/functions/ folder doesn't exist."""
        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_function_tests()

        assert tests == {}

    def test_discover_function_tests_empty_folder(self, temp_dir):
        """Test discover_function_tests when tests/functions/ folder is empty."""
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir(parents=True)

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_function_tests()

        assert tests == {}

    def test_discover_function_tests_single_file(self, temp_dir):
        """Test discovering a single function SQL test file."""
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir(parents=True)

        sql_file = functions_folder / "calculate_percentage_test.sql"
        sql_file.write_text("SELECT 1")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_function_tests()

        assert len(tests) == 1
        assert "calculate_percentage_test" in tests
        assert isinstance(tests["calculate_percentage_test"], SqlTest)
        assert tests["calculate_percentage_test"].sql_file_path == sql_file

    def test_discover_function_tests_multiple_files(self, temp_dir):
        """Test discovering multiple function SQL test files."""
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir(parents=True)

        (functions_folder / "test1.sql").write_text("SELECT 1")
        (functions_folder / "test2.sql").write_text("SELECT 2")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_function_tests()

        assert len(tests) == 2
        assert "test1" in tests
        assert "test2" in tests

    def test_discover_function_tests_duplicate_names(self, temp_dir, caplog):
        """Test handling duplicate function test names."""
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir(parents=True)

        subfolder = functions_folder / "subfolder"
        subfolder.mkdir()

        (functions_folder / "my_test.sql").write_text("SELECT 1")
        (subfolder / "my_test.sql").write_text("SELECT 2")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_function_tests()

        assert len(tests) == 1
        assert "my_test" in tests
        assert "Duplicate function test name" in caplog.text

    def test_discover_function_tests_caching(self, temp_dir):
        """Test that discovered function tests are cached."""
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir(parents=True)
        (functions_folder / "test.sql").write_text("SELECT 1")

        discovery = TestDiscovery(temp_dir)
        tests1 = discovery.discover_function_tests()

        # Add another file
        (functions_folder / "test2.sql").write_text("SELECT 2")

        # Should return cached results
        tests2 = discovery.discover_function_tests()

        assert len(tests2) == 1  # Still only 1, not 2
        assert tests1 is tests2  # Same object

    def test_discover_function_tests_invalid_file(self, temp_dir, caplog):
        """Test handling of invalid function SQL files (should skip gracefully)."""
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir(parents=True)

        (functions_folder / "valid.sql").write_text("SELECT 1")

        with patch("t4t.testing.test_discovery.SqlTest") as mock_sql_test:
            mock_sql_test.side_effect = Exception("Failed to load")

            discovery = TestDiscovery(temp_dir)
            discovery.discover_function_tests()

            assert "Failed to load function SQL test from" in caplog.text

    def test_discover_python_test_files(self, temp_dir):
        """Test discovering Python test files."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        (tests_folder / "test1.py").write_text("print('hello')")
        (tests_folder / "test2.py").write_text("print('world')")

        discovery = TestDiscovery(temp_dir)
        python_files = discovery._discover_python_test_files()

        assert len(python_files) == 2
        assert any(f.name == "test1.py" for f in python_files)
        assert any(f.name == "test2.py" for f in python_files)

    def test_discover_python_test_files_no_folder(self, temp_dir):
        """Test discovering Python test files when tests/ folder doesn't exist."""
        discovery = TestDiscovery(temp_dir)
        python_files = discovery._discover_python_test_files()

        assert python_files == []

    def test_discover_python_test_files_excludes_functions(self, temp_dir):
        """Test that Python files in tests/functions/ are excluded."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        functions_folder = temp_dir / "tests" / "functions"
        functions_folder.mkdir()

        (tests_folder / "test1.py").write_text("print('hello')")
        (functions_folder / "func_test.py").write_text("print('function')")

        discovery = TestDiscovery(temp_dir)
        python_files = discovery._discover_python_test_files()

        assert len(python_files) == 1
        assert python_files[0].name == "test1.py"

    def test_execute_python_test_file(self, temp_dir):
        """Test executing a Python test file."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        py_file.write_text(
            """
from t4t.testing import create_test
create_test(name="my_test", sql="SELECT 1")
"""
        )

        discovery = TestDiscovery(temp_dir)
        discovery._execute_python_test_file(py_file)

        registered_test = TestRegistry.get("my_test")
        assert registered_test is not None
        assert registered_test.name == "my_test"

    def test_execute_python_test_file_with_test_decorator(self, temp_dir):
        """Test executing a Python test file with @test decorator."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        py_file.write_text(
            """
from t4t.testing import test

@test(name="my_test", severity="error")
def my_test():
    return "SELECT 1"
"""
        )

        discovery = TestDiscovery(temp_dir)
        discovery._execute_python_test_file(py_file)

        registered_test = TestRegistry.get("my_test")
        assert registered_test is not None
        assert registered_test.name == "my_test"

    def test_execute_python_test_file_error_raises_discovery_error(self, temp_dir):
        """Test that executing a broken Python file raises TestDiscoveryError."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        py_file.write_text("raise ValueError('broken')")

        discovery = TestDiscovery(temp_dir)

        with pytest.raises(TestDiscoveryError, match="Failed to execute Python test file"):
            discovery._execute_python_test_file(py_file)

    def test_discover_tests_with_python_file(self, temp_dir):
        """Test discovering tests with a Python file that registers tests."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "my_test.py"
        py_file.write_text(
            """
from t4t.testing import create_test
create_test(name="my_test", sql="SELECT 1 FROM {{ table_name }}")
"""
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "my_test" in tests
        from t4t.testing.python_test import PythonTest
        assert isinstance(tests["my_test"], PythonTest)

    def test_discover_tests_with_python_and_sql_companion(self, temp_dir):
        """Test discovering tests with companion .py and .sql files (SqlTestMetadata pattern)."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Create companion .py and .sql files
        py_file = tests_folder / "my_test.py"
        py_file.write_text(
            """
from t4t.testing import create_test
create_test(name="my_test", sql="SELECT 1 FROM {{ table_name }}")
"""
        )

        sql_file = tests_folder / "my_test.sql"
        sql_file.write_text("SELECT 1 FROM {{ table_name }}")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Should only have the Python test (SQL companion is skipped)
        assert len(tests) == 1
        assert "my_test" in tests
        from t4t.testing.python_test import PythonTest
        assert isinstance(tests["my_test"], PythonTest)

    def test_discover_tests_python_file_error_handling(self, temp_dir, caplog):
        """Test that errors in Python files are handled during discovery."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "broken.py"
        py_file.write_text("raise ValueError('broken')")

        discovery = TestDiscovery(temp_dir)

        with pytest.raises(TestDiscoveryError, match="Failed to execute Python test file"):
            discovery.discover_tests()

    def test_discovery_error_exception(self):
        """Test that TestDiscoveryError is a proper exception."""
        error = TestDiscoveryError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"
