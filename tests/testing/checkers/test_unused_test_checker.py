"""
Unit tests for UnusedTestChecker.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from tee.testing.checkers.unused_test_checker import UnusedTestChecker
from tee.testing.sql_test import SqlTest
from tee.testing.test_discovery import TestDiscovery


class TestUnusedTestChecker:
    """Test cases for UnusedTestChecker."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_discovery(self, temp_dir):
        """Create a TestDiscovery instance."""
        return TestDiscovery(temp_dir)

    @pytest.fixture
    def checker(self, test_discovery, temp_dir):
        """Create an UnusedTestChecker instance."""
        return UnusedTestChecker(test_discovery, temp_dir)

    def test_init(self, test_discovery, temp_dir):
        """Test UnusedTestChecker initialization."""
        checker = UnusedTestChecker(test_discovery, temp_dir)

        assert checker.test_discovery == test_discovery
        assert checker.project_folder == temp_dir

    def test_check_unused_tests_no_test_discovery(self, temp_dir):
        """Test checking unused tests when test_discovery is None."""
        checker = UnusedTestChecker(None, temp_dir)

        result = checker.check_unused_tests({}, {}, set())

        assert result == []

    def test_check_unused_tests_no_unused_tests(self, checker, temp_dir):
        """Test checking when all tests are used."""
        # Create a generic test file
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "my_test.sql"
        test_file.write_text("SELECT COUNT(*) FROM @table_name WHERE id IS NULL")

        parsed_models = {"my_table": {"model_metadata": {"metadata": {"tests": ["my_test"]}}}}

        used_test_names = {"my_test"}

        result = checker.check_unused_tests(parsed_models, {}, used_test_names)

        assert result == []

    def test_check_unused_tests_unused_generic_test(self, checker, temp_dir):
        """Test checking for unused generic test."""
        # Create a generic test file
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "unused_test.sql"
        test_file.write_text("SELECT COUNT(*) FROM @table_name WHERE id IS NULL")

        parsed_models = {}
        used_test_names = set()

        result = checker.check_unused_tests(parsed_models, {}, used_test_names)

        assert len(result) == 1
        assert "unused_test" in result[0]
        assert "never used" in result[0].lower()

    def test_check_unused_tests_referenced_in_metadata(self, checker, temp_dir):
        """Test that tests referenced in metadata are not flagged."""
        # Create a generic test file
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "referenced_test.sql"
        test_file.write_text("SELECT COUNT(*) FROM @table_name WHERE id IS NULL")

        parsed_models = {
            "my_table": {"model_metadata": {"metadata": {"tests": ["referenced_test"]}}}
        }
        used_test_names = set()  # Not used yet, but referenced

        result = checker.check_unused_tests(parsed_models, {}, used_test_names)

        assert result == []  # Should not be flagged

    def test_check_unused_tests_singular_test_not_flagged(self, checker, temp_dir):
        """Test that singular (non-generic) tests are not flagged."""
        # Create a singular test file (no placeholders)
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "singular_test.sql"
        test_file.write_text("SELECT COUNT(*) FROM my_specific_table WHERE id IS NULL")

        parsed_models = {}
        used_test_names = set()

        result = checker.check_unused_tests(parsed_models, {}, used_test_names)

        assert result == []  # Singular tests are not flagged

    def test_check_unused_tests_function_tests(self, checker, temp_dir):
        """Test checking for unused function tests."""
        # Create a function test file
        functions_tests_folder = temp_dir / "tests" / "functions"
        functions_tests_folder.mkdir(parents=True)
        test_file = functions_tests_folder / "unused_function_test.sql"
        test_file.write_text("SELECT @function_name(1, 2) = 3")

        parsed_functions = {}
        used_test_names = set()

        result = checker.check_unused_tests({}, parsed_functions, used_test_names)

        assert len(result) == 1
        assert "unused_function_test" in result[0]
        assert "function" in result[0].lower()

    def test_check_unused_tests_function_tests_referenced(self, checker, temp_dir):
        """Test that function tests referenced in metadata are not flagged."""
        # Create a function test file
        functions_tests_folder = temp_dir / "tests" / "functions"
        functions_tests_folder.mkdir(parents=True)
        test_file = functions_tests_folder / "referenced_function_test.sql"
        test_file.write_text("SELECT @function_name(1, 2) = 3")

        parsed_functions = {
            "my_function": {
                "function_metadata": {"metadata": {"tests": ["referenced_function_test"]}}
            }
        }
        used_test_names = set()

        result = checker.check_unused_tests({}, parsed_functions, used_test_names)

        assert result == []

    def test_collect_referenced_tests_from_models(self, checker):
        """Test collecting referenced tests from model metadata."""
        parsed_models = {
            "table1": {
                "model_metadata": {
                    "metadata": {
                        "tests": ["test1", {"name": "test2"}],
                        "schema": [
                            {
                                "name": "id",
                                "tests": ["test3", {"name": "test4"}],
                            }
                        ],
                    }
                }
            }
        }

        result = checker._collect_referenced_tests(parsed_models, {})

        assert result == {"test1", "test2", "test3", "test4"}

    def test_collect_referenced_tests_from_functions(self, checker):
        """Test collecting referenced tests from function metadata."""
        parsed_functions = {
            "func1": {"function_metadata": {"metadata": {"tests": ["test1", {"name": "test2"}]}}}
        }

        result = checker._collect_referenced_tests({}, parsed_functions)

        assert result == {"test1", "test2"}

    def test_collect_referenced_tests_empty(self, checker):
        """Test collecting referenced tests when none exist."""
        result = checker._collect_referenced_tests({}, {})

        assert result == set()

    def test_extract_test_name_string(self, checker):
        """Test extracting test name from string."""
        result = checker._extract_test_name("my_test")

        assert result == "my_test"

    def test_extract_test_name_dict_with_name(self, checker):
        """Test extracting test name from dict with 'name' key."""
        result = checker._extract_test_name({"name": "my_test"})

        assert result == "my_test"

    def test_extract_test_name_dict_with_test_key(self, checker):
        """Test extracting test name from dict with 'test' key."""
        result = checker._extract_test_name({"test": "my_test"})

        assert result == "my_test"

    def test_extract_test_name_dict_missing_name(self, checker):
        """Test extracting test name from dict missing name."""
        result = checker._extract_test_name({"param1": 10})

        assert result is None

    def test_extract_test_name_invalid_type(self, checker):
        """Test extracting test name from invalid type."""
        result = checker._extract_test_name(123)

        assert result is None

    def test_is_generic_test_with_placeholders(self, checker, temp_dir):
        """Test identifying generic test with placeholders."""
        test_file = temp_dir / "test.sql"
        test_file.write_text("SELECT COUNT(*) FROM @table_name WHERE @column_name IS NULL")

        sql_test = SqlTest(name="test", sql_file_path=test_file, project_folder=temp_dir)

        result = checker._is_generic_test(sql_test)

        assert result is True

    def test_is_generic_test_without_placeholders(self, checker, temp_dir):
        """Test identifying singular test without placeholders."""
        test_file = temp_dir / "test.sql"
        test_file.write_text("SELECT COUNT(*) FROM my_specific_table WHERE id IS NULL")

        sql_test = SqlTest(name="test", sql_file_path=test_file, project_folder=temp_dir)

        result = checker._is_generic_test(sql_test)

        assert result is False

    def test_is_generic_test_with_function_placeholder(self, checker, temp_dir):
        """Test identifying generic test with function placeholder."""
        test_file = temp_dir / "test.sql"
        test_file.write_text("SELECT @function_name(1, 2) = 3")

        sql_test = SqlTest(name="test", sql_file_path=test_file, project_folder=temp_dir)

        result = checker._is_generic_test(sql_test)

        assert result is True

    def test_is_generic_test_with_jinja_placeholders(self, checker, temp_dir):
        """Test identifying generic test with Jinja placeholders."""
        test_file = temp_dir / "test.sql"
        test_file.write_text(
            "SELECT COUNT(*) FROM {{ table_name }} WHERE {{ column_name }} IS NULL"
        )

        sql_test = SqlTest(name="test", sql_file_path=test_file, project_folder=temp_dir)

        result = checker._is_generic_test(sql_test)

        assert result is True

    def test_is_generic_test_exception_handling(self, checker):
        """Test that exceptions during SQL loading are handled."""
        # Create a mock sql_test that raises an exception
        mock_sql_test = Mock()
        mock_sql_test._load_sql_content.side_effect = Exception("Error loading SQL")

        result = checker._is_generic_test(mock_sql_test)

        assert result is True  # Should default to True on error

    def test_check_unused_model_tests_used_test(self, checker, temp_dir):
        """Test that used tests are not flagged."""
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "used_test.sql"
        test_file.write_text("SELECT COUNT(*) FROM @table_name")

        discovered_tests = {"used_test": SqlTest("used_test", test_file, temp_dir)}
        referenced_test_names = set()
        used_test_names = {"used_test"}

        result = checker._check_unused_model_tests(
            discovered_tests, referenced_test_names, used_test_names
        )

        assert result == []

    def test_check_unused_function_tests_used_test(self, checker, temp_dir):
        """Test that used function tests are not flagged."""
        functions_tests_folder = temp_dir / "tests" / "functions"
        functions_tests_folder.mkdir(parents=True)
        test_file = functions_tests_folder / "used_test.sql"
        test_file.write_text("SELECT @function_name(1) = 2")

        discovered_tests = {"used_test": SqlTest("used_test", test_file, temp_dir)}
        referenced_test_names = set()
        used_test_names = {"used_test"}

        result = checker._check_unused_function_tests(
            discovered_tests, referenced_test_names, used_test_names
        )

        assert result == []
