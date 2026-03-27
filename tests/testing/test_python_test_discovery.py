"""
Unit tests for Python test discovery functionality.
"""

import tempfile
from pathlib import Path

import pytest

from tee.testing.base import TestRegistry
from tee.testing.python_test import PythonTest
from tee.testing.sql_test import SqlTest
from tee.testing.test_discovery import TestDiscovery, TestDiscoveryError


class TestPythonTestDiscovery:
    """Test cases for Python test discovery."""

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

    def test_discover_python_test_with_decorator(self, temp_dir):
        """Test discovering Python test with @test decorator."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "check_null.py"
        py_file.write_text(
            """
from tee.testing import test

@test(name="check_null", severity="error")
def check_null():
    return "SELECT id FROM @table_name WHERE id IS NULL"
"""
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "check_null" in tests
        assert isinstance(tests["check_null"], PythonTest)
        assert "SELECT id FROM @table_name" in tests["check_null"].sql

    def test_discover_python_test_with_create_test(self, temp_dir):
        """Test discovering Python test with create_test()."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "generate_tests.py"
        py_file.write_text(
            """
from tee.testing import create_test

create_test(
    name="check_not_empty",
    sql="SELECT 1 FROM @table_name WHERE COUNT(*) = 0",
    severity="error"
)
"""
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "check_not_empty" in tests
        assert isinstance(tests["check_not_empty"], PythonTest)

    def test_discover_python_test_with_sql_test_metadata(self, temp_dir):
        """Test discovering Python test with SqlTestMetadata."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "check_minimum.py"
        sql_file = tests_folder / "check_minimum.sql"

        py_file.write_text(
            """
from tee.testing import SqlTestMetadata

metadata = {
    "name": "check_minimum",
    "severity": "error",
    "description": "Check minimum rows"
}

test = SqlTestMetadata(**metadata)
"""
        )

        sql_file.write_text("SELECT 1 FROM @table_name WHERE COUNT(*) < 5")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "check_minimum" in tests
        assert isinstance(tests["check_minimum"], PythonTest)
        assert "SELECT 1 FROM @table_name" in tests["check_minimum"].sql

    def test_discover_mixed_python_and_sql_tests(self, temp_dir):
        """Test discovering both Python and SQL tests."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        # Python test
        py_file = tests_folder / "python_test.py"
        py_file.write_text(
            """
from tee.testing import test

@test(name="python_test")
def python_test():
    return "SELECT 1"
"""
        )

        # SQL test (no companion .py)
        sql_file = tests_folder / "sql_test.sql"
        sql_file.write_text("SELECT 2 FROM @table_name")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 2
        assert "python_test" in tests
        assert "sql_test" in tests
        assert isinstance(tests["python_test"], PythonTest)
        assert isinstance(tests["sql_test"], SqlTest)

    def test_discover_python_test_with_companion_sql_skips_sql(self, temp_dir):
        """Test that when .py (with @test) and .sql exist, Python test is used and SQL is skipped."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        sql_file = tests_folder / "test.sql"

        py_file.write_text(
            """
from tee.testing import test

@test(name="test")
def test_func():
    return "SELECT 1"
"""
        )

        sql_file.write_text("SELECT 2")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Should only have one test (from Python file, SQL file is skipped)
        assert len(tests) == 1
        assert "test" in tests
        assert isinstance(tests["test"], PythonTest)
        assert "SELECT 1" in tests["test"].sql

    def test_discover_python_test_sql_test_metadata_with_companion_sql(self, temp_dir):
        """Test that SqlTestMetadata with companion .sql doesn't conflict."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        sql_file = tests_folder / "test.sql"

        py_file.write_text(
            """
from tee.testing import SqlTestMetadata

test = SqlTestMetadata(name="test", severity="error")
"""
        )

        sql_file.write_text("SELECT 1")

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Should only have one test (from SqlTestMetadata, SQL file is skipped)
        assert len(tests) == 1
        assert "test" in tests
        assert isinstance(tests["test"], PythonTest)

    def test_discover_python_test_execution_error_raises(self, temp_dir):
        """Test that Python test file execution errors raise TestDiscoveryError."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "error_test.py"
        # Create a file with actual syntax error
        py_file.write_text(
            """
from tee.testing import test

@test(name="test")
def test_func():
    return "SELECT 1"
    # Missing closing parenthesis or bracket
    if True:
        pass
    else  # Syntax error: missing colon
        pass
"""
        )

        discovery = TestDiscovery(temp_dir)

        # Should raise error (not just log and continue)
        with pytest.raises(TestDiscoveryError):
            discovery.discover_tests()

    def test_discover_python_test_multiple_tests_in_file(self, temp_dir):
        """Test discovering multiple tests from a single Python file."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "multiple_tests.py"
        py_file.write_text(
            """
from tee.testing import test, create_test

@test(name="test1")
def test1():
    return "SELECT 1"

@test(name="test2")
def test2():
    return "SELECT 2"

create_test(name="test3", sql="SELECT 3")
"""
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 3
        assert "test1" in tests
        assert "test2" in tests
        assert "test3" in tests

    def test_discover_python_test_in_subfolder(self, temp_dir):
        """Test discovering Python tests in subfolders."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        subfolder = tests_folder / "my_schema"
        subfolder.mkdir()

        py_file = subfolder / "test.py"
        py_file.write_text(
            """
from tee.testing import test

@test(name="my_schema__test__test_func")
def test_func():
    return "SELECT 1"
"""
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        assert len(tests) == 1
        assert "my_schema__test__test_func" in tests

    def test_discover_python_test_name_derivation(self, temp_dir):
        """Test that test names are derived correctly from file and function names."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "check_minimum_rows.py"
        py_file.write_text(
            """
from tee.testing import test

@test()  # No explicit name
def check_minimum_rows():
    return "SELECT 1"
"""
        )

        discovery = TestDiscovery(temp_dir)
        tests = discovery.discover_tests()

        # Name should be derived: {file_name}__{function_name}
        assert "check_minimum_rows__check_minimum_rows" in tests
