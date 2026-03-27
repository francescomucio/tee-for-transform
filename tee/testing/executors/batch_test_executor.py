"""
Batch test execution logic.

Handles execution of tests for multiple models and functions in batch.
"""

import logging
from typing import Any

from tee.adapters.base import DatabaseAdapter
from tee.testing.base import TestResult, TestSeverity
from tee.testing.executors.function_test_executor import FunctionTestExecutor
from tee.testing.executors.model_test_executor import ModelTestExecutor
from tee.testing.utils import MetadataExtractor, ResultCategorizer

logger = logging.getLogger(__name__)


class BatchTestExecutor:
    """Executes tests for multiple models and functions in batch."""

    def __init__(
        self,
        adapter: DatabaseAdapter,
        function_executor: FunctionTestExecutor,
        model_executor: ModelTestExecutor,
    ):
        """
        Initialize batch test executor.

        Args:
            adapter: Database adapter for executing test queries
            function_executor: Function test executor instance
            model_executor: Model test executor instance
        """
        self.adapter = adapter
        self.function_executor = function_executor
        self.model_executor = model_executor
        self.logger = logger

    def execute_all_tests(
        self,
        parsed_models: dict[str, Any],
        parsed_functions: dict[str, Any],
        execution_order: list[str],
        severity_overrides: dict[str, TestSeverity] | None = None,
    ) -> dict[str, Any]:
        """
        Execute all tests for all models and functions in execution order.

        Tests are executed after their dependent models/functions have been created.

        Args:
            parsed_models: Dictionary of parsed models with metadata
            parsed_functions: Dictionary of parsed functions with metadata
            execution_order: List of table/function names in execution order
            severity_overrides: Optional dict to override test severities

        Returns:
            Dictionary with test execution results
        """
        all_results: list[TestResult] = []
        severity_overrides = severity_overrides or {}
        parsed_functions = parsed_functions or {}

        # Separate functions and models from execution order
        function_names, model_names = self._separate_models_and_functions(
            execution_order, parsed_models, parsed_functions
        )

        self.logger.info(
            f"Executing tests for {len(model_names)} models and {len(function_names)} functions"
        )

        # Execute function tests first (functions are created before models)
        function_results = self._execute_function_tests_batch(
            function_names, parsed_functions, severity_overrides
        )
        all_results.extend(function_results)

        # Execute model tests
        model_results = self._execute_model_tests_batch(
            model_names, parsed_models, severity_overrides
        )
        all_results.extend(model_results)

        # Categorize results
        categorized = ResultCategorizer.categorize_results(all_results)

        # Count only actual failures (exclude warnings)
        actual_failures = [
            r for r in all_results if not r.passed and r.severity == TestSeverity.ERROR
        ]

        return {
            "test_results": all_results,
            "passed": len([r for r in all_results if r.passed]),
            "failed": len(actual_failures),
            "errors": categorized["errors"],
            "warnings": categorized["warnings"],
            "total": len(all_results),
        }

    def _separate_models_and_functions(
        self,
        execution_order: list[str],
        parsed_models: dict[str, Any],
        parsed_functions: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        """
        Separate function names and model names from execution order.

        Args:
            execution_order: List of names in execution order
            parsed_models: Dictionary of parsed models
            parsed_functions: Dictionary of parsed functions

        Returns:
            Tuple of (function_names, model_names) lists
        """
        function_names = [name for name in execution_order if name in parsed_functions]
        model_names = [name for name in execution_order if name in parsed_models]
        return function_names, model_names

    def _execute_function_tests_batch(
        self,
        function_names: list[str],
        parsed_functions: dict[str, Any],
        severity_overrides: dict[str, TestSeverity],
    ) -> list[TestResult]:
        """
        Execute tests for a batch of functions.

        Args:
            function_names: List of function names
            parsed_functions: Dictionary of parsed functions
            severity_overrides: Dict of severity overrides

        Returns:
            List of TestResult objects
        """
        all_results: list[TestResult] = []

        for function_name in function_names:
            if function_name not in parsed_functions:
                continue

            function_data = parsed_functions[function_name]
            metadata = MetadataExtractor.extract_function_metadata(function_data)

            if not metadata:
                continue

            # Execute tests for this function
            results = self.function_executor.execute_tests_for_function(
                function_name=function_name,
                metadata=metadata,
                severity_overrides=severity_overrides,
            )

            all_results.extend(results)

        return all_results

    def _execute_model_tests_batch(
        self,
        model_names: list[str],
        parsed_models: dict[str, Any],
        severity_overrides: dict[str, TestSeverity],
    ) -> list[TestResult]:
        """
        Execute tests for a batch of models.

        Args:
            model_names: List of model names
            parsed_models: Dictionary of parsed models
            severity_overrides: Dict of severity overrides

        Returns:
            List of TestResult objects
        """
        all_results: list[TestResult] = []

        for table_name in model_names:
            if table_name not in parsed_models:
                continue

            model_data = parsed_models[table_name]
            metadata = MetadataExtractor.extract_model_metadata(model_data)

            if not metadata:
                continue

            # Execute tests for this model
            results = self.model_executor.execute_tests_for_model(
                table_name=table_name,
                metadata=metadata,
                severity_overrides=severity_overrides,
                parsed_models=parsed_models,
            )

            all_results.extend(results)

        return all_results
