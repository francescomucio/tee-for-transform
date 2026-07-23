"""
Test execution engine that integrates with model execution.

Refactored to use feature-based split with dedicated executors, parsers, and checkers.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.adapters.base import DatabaseAdapter

from .base import TestSeverity
from .checkers import UnusedTestChecker
from .executors import BatchTestExecutor, FunctionTestExecutor, ModelTestExecutor
from .test_discovery import TestDiscovery


class TestExecutor:
    """Executes tests against models and functions after they are created."""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(
        self,
        adapter: DatabaseAdapter,
        project_folder: str | None = None,
        run_id: str | None = None,
    ):
        """
        Initialize test executor.

        Args:
            adapter: Database adapter for executing test queries
            project_folder: Optional project folder path for discovering SQL tests
            run_id: Identity of the run this test execution belongs to,
                threaded into the model/function test executors so
                test_started/test_finished events carry it.
        """
        self.adapter = adapter
        self.project_folder = Path(project_folder) if project_folder else None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.run_id = run_id
        self._test_discovery: TestDiscovery | None = None

        # Initialize executors
        self.function_executor = FunctionTestExecutor(adapter, run_id=run_id)
        self.model_executor = ModelTestExecutor(adapter, parsed_models=None, run_id=run_id)

        # Discover and register SQL tests from tests/ folder
        if self.project_folder:
            self._test_discovery = TestDiscovery(self.project_folder)
            self._test_discovery.register_discovered_tests()

    def execute_tests_for_model(
        self,
        table_name: str,
        metadata: dict[str, Any] | None = None,
        severity_overrides: dict[str, TestSeverity] | None = None,
        *,
        parsed_models: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Execute all tests for a given model based on its metadata.

        Args:
            table_name: Fully qualified table name
            metadata: Model metadata containing test definitions
            severity_overrides: Optional dict to override test severities
            parsed_models: Optional parsed project models for dimension-aware default tests

        Returns:
            List of TestResult objects
        """
        if not metadata:
            return []

        return self.model_executor.execute_tests_for_model(
            table_name=table_name,
            metadata=metadata,
            severity_overrides=severity_overrides,
            parsed_models=parsed_models,
        )

    def execute_tests_for_function(
        self,
        function_name: str,
        metadata: dict[str, Any] | None = None,
        severity_overrides: dict[str, TestSeverity] | None = None,
    ) -> list[Any]:
        """
        Execute all tests for a given function based on its metadata.

        Args:
            function_name: Fully qualified function name
            metadata: Function metadata containing test definitions
            severity_overrides: Optional dict to override test severities

        Returns:
            List of TestResult objects
        """
        if not metadata:
            return []

        return self.function_executor.execute_tests_for_function(
            function_name=function_name,
            metadata=metadata,
            severity_overrides=severity_overrides,
        )

    def execute_all_tests(
        self,
        parsed_models: dict[str, Any],
        execution_order: list[str] | None = None,
        parsed_functions: dict[str, Any] | None = None,
        severity_overrides: dict[str, TestSeverity] | None = None,
    ) -> dict[str, Any]:
        """
        Execute all tests for all models and functions in execution order.

        Tests are executed after their dependent models/functions have been created.

        Args:
            parsed_models: Dictionary of parsed models with metadata
            execution_order: List of table/function names in execution order (optional, defaults to all models)
            parsed_functions: Dictionary of parsed functions with metadata (optional)
            severity_overrides: Optional dict to override test severities

        Returns:
            Dictionary with test execution results
        """
        parsed_functions = parsed_functions or {}

        # If execution_order not provided, use all models
        if execution_order is None:
            execution_order = list(parsed_models.keys())

        self.model_executor.parsed_models = parsed_models

        # Initialize batch executor
        batch_executor = BatchTestExecutor(
            adapter=self.adapter,
            function_executor=self.function_executor,
            model_executor=self.model_executor,
        )

        # Execute all tests
        results = batch_executor.execute_all_tests(
            parsed_models=parsed_models,
            parsed_functions=parsed_functions,
            execution_order=execution_order,
            severity_overrides=severity_overrides,
        )

        # Collect used test names from both executors
        used_test_names = (
            self.function_executor.get_used_test_names() | self.model_executor.get_used_test_names()
        )

        # Check for unused generic tests
        if self._test_discovery:
            unused_checker = UnusedTestChecker(self._test_discovery, self.project_folder)
            unused_warnings = unused_checker.check_unused_tests(
                parsed_models=parsed_models,
                parsed_functions=parsed_functions,
                used_test_names=used_test_names,
            )
            if unused_warnings:
                results["warnings"].extend(unused_warnings)

        return results

    def _check_unused_generic_tests(
        self, parsed_models: dict[str, Any], parsed_functions: dict[str, Any]
    ) -> list[str]:
        """
        Check for unused generic SQL tests and return warning messages.

        This method is kept for backward compatibility but delegates to UnusedTestChecker.

        Args:
            parsed_models: Dictionary of parsed models
            parsed_functions: Dictionary of parsed functions

        Returns:
            List of warning messages for unused generic tests
        """
        if not self._test_discovery:
            return []

        # Collect used test names from both executors
        used_test_names = (
            self.function_executor.get_used_test_names() | self.model_executor.get_used_test_names()
        )

        unused_checker = UnusedTestChecker(self._test_discovery, self.project_folder)
        return unused_checker.check_unused_tests(
            parsed_models=parsed_models,
            parsed_functions=parsed_functions,
            used_test_names=used_test_names,
        )

    def _extract_metadata(self, model_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract metadata from model data.

        This method is kept for backward compatibility but delegates to MetadataExtractor.

        Args:
            model_data: Model data dictionary

        Returns:
            Metadata dictionary or None if not found
        """
        from t4t.testing.utils import MetadataExtractor

        return MetadataExtractor.extract_model_metadata(model_data)

    def _extract_function_metadata(self, function_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract metadata from function data.

        This method is kept for backward compatibility but delegates to MetadataExtractor.

        Args:
            function_data: Function data dictionary

        Returns:
            Metadata dictionary or None if not found
        """
        from t4t.testing.utils import MetadataExtractor

        return MetadataExtractor.extract_function_metadata(function_data)
