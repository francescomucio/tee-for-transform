"""
Unused test checker.

Checks for generic SQL tests that are never used in model or function metadata.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.testing.sql_test import SqlTest
from t4t.testing.test_discovery import TestDiscovery
from t4t.testing.utils import MetadataExtractor

logger = logging.getLogger(__name__)


class UnusedTestChecker:
    """Checks for unused generic SQL tests."""

    def __init__(self, test_discovery: TestDiscovery, project_folder: Path):
        """
        Initialize unused test checker.

        Args:
            test_discovery: TestDiscovery instance
            project_folder: Project folder path
        """
        self.test_discovery = test_discovery
        self.project_folder = project_folder
        self.logger = logger

    def check_unused_tests(
        self,
        parsed_models: dict[str, Any],
        parsed_functions: dict[str, Any],
        used_test_names: set[str],
    ) -> list[str]:
        """
        Check for unused generic SQL tests and return warning messages.

        Generic tests are SQL tests that use placeholders like @table_name, @function_name, etc.
        These tests must be referenced in model/function metadata to be used.

        Args:
            parsed_models: Dictionary of parsed models
            parsed_functions: Dictionary of parsed functions
            used_test_names: Set of test names that were used during execution

        Returns:
            List of warning messages for unused generic tests
        """
        if not self.test_discovery:
            return []

        warnings = []
        discovered_tests = self.test_discovery.discover_tests()
        discovered_function_tests = self.test_discovery.discover_function_tests()

        # Get all test names referenced in metadata
        referenced_test_names = self._collect_referenced_tests(parsed_models, parsed_functions)

        # Check unused model tests
        warnings.extend(
            self._check_unused_model_tests(discovered_tests, referenced_test_names, used_test_names)
        )

        # Check unused function tests
        warnings.extend(
            self._check_unused_function_tests(
                discovered_function_tests, referenced_test_names, used_test_names
            )
        )

        return warnings

    def _collect_referenced_tests(
        self, parsed_models: dict[str, Any], parsed_functions: dict[str, Any]
    ) -> set[str]:
        """
        Collect all test names referenced in model and function metadata.

        Args:
            parsed_models: Dictionary of parsed models
            parsed_functions: Dictionary of parsed functions

        Returns:
            Set of referenced test names
        """
        referenced_test_names = set()

        # Collect from model metadata
        for model_data in parsed_models.values():
            metadata = MetadataExtractor.extract_model_metadata(model_data)
            if not metadata:
                continue

            # Check model-level tests
            if "tests" in metadata and metadata["tests"]:
                for test_def in metadata["tests"]:
                    test_name = self._extract_test_name(test_def)
                    if test_name:
                        referenced_test_names.add(test_name)

            # Check column-level tests
            if "schema" in metadata and metadata["schema"]:
                for column_def in metadata["schema"]:
                    if "tests" in column_def and column_def["tests"]:
                        for test_def in column_def["tests"]:
                            test_name = self._extract_test_name(test_def)
                            if test_name:
                                referenced_test_names.add(test_name)

        # Collect from function metadata
        for function_data in parsed_functions.values():
            metadata = MetadataExtractor.extract_function_metadata(function_data)
            if not metadata:
                continue

            # Check function-level tests
            if "tests" in metadata and metadata["tests"]:
                for test_def in metadata["tests"]:
                    test_name = self._extract_test_name(test_def)
                    if test_name:
                        referenced_test_names.add(test_name)

        return referenced_test_names

    def _extract_test_name(self, test_def: Any) -> str | None:
        """
        Extract test name from test definition.

        Args:
            test_def: Test definition (string or dict)

        Returns:
            Test name or None
        """
        if isinstance(test_def, str):
            return test_def
        elif isinstance(test_def, dict):
            return test_def.get("name") or test_def.get("test")
        return None

    def _check_unused_model_tests(
        self,
        discovered_tests: dict[str, Any],
        referenced_test_names: set[str],
        used_test_names: set[str],
    ) -> list[str]:
        """
        Check for unused model SQL tests.

        Args:
            discovered_tests: Dictionary of discovered model tests
            referenced_test_names: Set of test names referenced in metadata
            used_test_names: Set of test names used during execution

        Returns:
            List of warning messages
        """
        warnings = []

        for test_name, sql_test in discovered_tests.items():
            # Skip if test was used during execution
            if test_name in used_test_names:
                continue

            # Skip if test is referenced in metadata (might be used in future runs)
            if test_name in referenced_test_names:
                continue

            # Check if this is a generic test (has placeholders)
            if self._is_generic_test(sql_test):
                file_info = self._get_test_file_info(sql_test, test_name)
                warnings.append(
                    f"Generic SQL test '{test_name}' is never used. "
                    f"Add it to model metadata to apply it to tables. "
                    f"{file_info}"
                )

        return warnings

    def _check_unused_function_tests(
        self,
        discovered_function_tests: dict[str, Any],
        referenced_test_names: set[str],
        used_test_names: set[str],
    ) -> list[str]:
        """
        Check for unused function SQL tests.

        Args:
            discovered_function_tests: Dictionary of discovered function tests
            referenced_test_names: Set of test names referenced in metadata
            used_test_names: Set of test names used during execution

        Returns:
            List of warning messages
        """
        warnings = []

        for test_name, sql_test in discovered_function_tests.items():
            # Skip if test was used during execution
            if test_name in used_test_names:
                continue

            # Skip if test is referenced in metadata (might be used in future runs)
            if test_name in referenced_test_names:
                continue

            # Check if this is a generic test (has placeholders)
            if self._is_generic_test(sql_test):
                file_info = self._get_test_file_info(sql_test, test_name)
                warnings.append(
                    f"Generic function SQL test '{test_name}' is never used. "
                    f"Add it to function metadata to apply it to functions. "
                    f"{file_info}"
                )

        return warnings

    def _get_test_file_info(self, test: Any, test_name: str) -> str:
        """
        Get file information for a test (SqlTest or PythonTest).

        Args:
            test: Test instance (SqlTest or PythonTest)
            test_name: Name of the test

        Returns:
            File information string
        """
        if isinstance(test, SqlTest):
            file_path = (
                test.sql_file_path.relative_to(self.project_folder)
                if self.project_folder
                else test.sql_file_path
            )
            return f"File: {file_path}"
        else:
            # PythonTest - use test name to indicate it's from a Python file
            return f"Test defined in Python file (name: {test_name})"

    def _is_generic_test(self, sql_test: Any) -> bool:
        """
        Check if a SQL test is generic (uses placeholders) vs singular (hardcoded table name).

        Generic tests use @table_name, {{ table_name }}, or similar placeholders.
        Singular tests have hardcoded table names.

        Args:
            sql_test: SqlTest instance

        Returns:
            True if generic, False otherwise
        """
        try:
            sql_content = sql_test._load_sql_content()
            # Check for common placeholder patterns
            placeholder_patterns = [
                "@table_name",
                "{{ table_name }}",
                "{{table_name}}",
                "@column_name",
                "{{ column_name }}",
                "{{column_name}}",
                "@function_name",
                "{{ function_name }}",
                "{{function_name}}",
            ]
            return any(pattern in sql_content for pattern in placeholder_patterns)
        except Exception:
            # If we can't load the SQL, assume it's generic to be safe
            return True
