"""
Unit tests for SqlTestMetadata class.
"""

import tempfile
from pathlib import Path

import pytest

from t4t.testing.base import TestRegistry, TestSeverity
from t4t.testing.python_test import PythonTest
from t4t.testing.test_builder import SqlTestMetadata, TestBuilderError


class TestSqlTestMetadata:
    """Test cases for SqlTestMetadata class."""

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
    def test_files(self, temp_dir):
        """Create test Python and SQL files."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "check_minimum_rows.py"
        sql_file = tests_folder / "check_minimum_rows.sql"

        py_file.write_text(
            """
from t4t.testing import SqlTestMetadata

metadata = {
    "name": "check_minimum_rows",
    "severity": "error",
    "description": "Check minimum rows",
    "tags": ["data-quality"]
}

test = SqlTestMetadata(**metadata)
"""
        )

        sql_file.write_text(
            """
SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < 5
"""
        )

        return py_file, sql_file

    def test_sql_test_metadata_basic(self, temp_dir, test_files):
        """Test SqlTestMetadata with basic usage."""
        py_file, sql_file = test_files

        # Execute the Python file (simulating test discovery)
        import importlib.util
        import sys

        module_name = f"temp_module_{hash(py_file)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        module.SqlTestMetadata = SqlTestMetadata
        module.__file__ = str(py_file.absolute())

        with open(py_file) as f:
            content = f.read()
        exec(content, module.__dict__)

        # Test should be registered
        registered_test = TestRegistry.get("check_minimum_rows")
        assert registered_test is not None
        assert isinstance(registered_test, PythonTest)
        assert registered_test.name == "check_minimum_rows"
        assert registered_test.severity == TestSeverity.ERROR
        assert registered_test.description == "Check minimum rows"
        assert registered_test.tags == ["data-quality"]
        assert "SELECT 1 as violation" in registered_test.sql

        # Cleanup
        if module_name in sys.modules:
            del sys.modules[module_name]

    def test_sql_test_metadata_missing_sql_file_raises_error(self, temp_dir):
        """Test that SqlTestMetadata raises error when SQL file is missing."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        py_file.write_text(
            """
from t4t.testing import SqlTestMetadata

test = SqlTestMetadata(name="test", severity="error")
"""
        )

        # Execute and expect error
        import importlib.util
        import sys

        module_name = f"temp_module_{hash(py_file)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        module.SqlTestMetadata = SqlTestMetadata
        module.__file__ = str(py_file.absolute())

        with open(py_file) as f:
            content = f.read()

        with pytest.raises(TestBuilderError, match="Companion SQL file not found"):
            exec(content, module.__dict__)

        # Cleanup
        if module_name in sys.modules:
            del sys.modules[module_name]

    def test_sql_test_metadata_empty_sql_file_raises_error(self, temp_dir):
        """Test that SqlTestMetadata raises error when SQL file is empty."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        sql_file = tests_folder / "test.sql"

        py_file.write_text(
            """
from t4t.testing import SqlTestMetadata

test = SqlTestMetadata(name="test", severity="error")
"""
        )

        sql_file.write_text("")  # Empty file

        import importlib.util
        import sys

        module_name = f"temp_module_{hash(py_file)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        module.SqlTestMetadata = SqlTestMetadata
        module.__file__ = str(py_file.absolute())

        with open(py_file) as f:
            content = f.read()

        with pytest.raises(TestBuilderError, match="SQL file.*is empty"):
            exec(content, module.__dict__)

        # Cleanup
        if module_name in sys.modules:
            del sys.modules[module_name]

    def test_sql_test_metadata_name_conflict_raises_error(self, temp_dir, test_files):
        """Test that SqlTestMetadata raises error on name conflict."""
        py_file, sql_file = test_files

        # Register a test with the same name first
        from t4t.testing.python_test import PythonTest

        existing_test = PythonTest(name="check_minimum_rows", sql="SELECT 1")
        TestRegistry.register(existing_test)

        # Now try to create SqlTestMetadata with same name
        import importlib.util
        import sys

        module_name = f"temp_module_{hash(py_file)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        module.SqlTestMetadata = SqlTestMetadata
        module.__file__ = str(py_file.absolute())

        with open(py_file) as f:
            content = f.read()

        with pytest.raises(TestBuilderError, match="Test name conflict"):
            exec(content, module.__dict__)

        # Cleanup
        if module_name in sys.modules:
            del sys.modules[module_name]

    def test_sql_test_metadata_severity_warning(self, temp_dir):
        """Test SqlTestMetadata with warning severity."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()

        py_file = tests_folder / "test.py"
        sql_file = tests_folder / "test.sql"

        py_file.write_text(
            """
from t4t.testing import SqlTestMetadata

test = SqlTestMetadata(name="test", severity="warning")
"""
        )

        sql_file.write_text("SELECT 1")

        import importlib.util
        import sys

        module_name = f"temp_module_{hash(py_file)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        module.SqlTestMetadata = SqlTestMetadata
        module.__file__ = str(py_file.absolute())

        with open(py_file) as f:
            content = f.read()
        exec(content, module.__dict__)

        registered_test = TestRegistry.get("test")
        assert registered_test.severity == TestSeverity.WARNING

        # Cleanup
        if module_name in sys.modules:
            del sys.modules[module_name]
