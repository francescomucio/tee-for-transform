"""
Model test execution logic.

Handles execution of tests for models (tables/views).
"""

import logging
from typing import Any

from tee.adapters.base import DatabaseAdapter
from tee.testing.base import TestRegistry, TestResult, TestSeverity
from tee.testing.default_tests import inject_default_tests
from tee.testing.parsers import TestDefinitionParser
from tee.typing.metadata import TestDefinition

logger = logging.getLogger(__name__)


class ModelTestExecutor:
    """Executes tests for models (tables/views)."""

    def __init__(
        self,
        adapter: DatabaseAdapter,
        parsed_models: dict[str, Any] | None = None,
    ):
        """
        Initialize model test executor.

        Args:
            adapter: Database adapter for executing test queries
            parsed_models: Optional full parsed-models map so default-test injection can use
                the same auto-built dimension registry as the parser/docs.
        """
        self.adapter = adapter
        self.parsed_models = parsed_models
        self.logger = logger
        self._used_test_names: set[str] = set()

    def execute_tests_for_model(
        self,
        table_name: str,
        metadata: dict[str, Any],
        severity_overrides: dict[str, TestSeverity] | None = None,
        *,
        parsed_models: dict[str, Any] | None = None,
    ) -> list[TestResult]:
        """
        Execute all tests for a given model based on its metadata.

        Args:
            table_name: Fully qualified table name
            metadata: Model metadata containing test definitions
            severity_overrides: Optional dict to override test severities
            parsed_models: When set, used for dimension registry during default test injection;
                falls back to the executor's constructor value.

        Returns:
            List of TestResult objects
        """
        results: list[TestResult] = []

        if not metadata:
            return results

        severity_overrides = severity_overrides or {}

        models_for_injection = parsed_models if parsed_models is not None else self.parsed_models

        # Inject default semantic tests (if enabled) and return WARNING results for any injection warnings.
        metadata_copy, warnings = inject_default_tests(
            table_name,
            metadata,
            parsed_models=models_for_injection,
        )
        for w in warnings:
            results.append(
                TestResult(
                    test_name="default_tests_warning",
                    table_name=table_name,
                    column_name=None,
                    passed=True,
                    message=w,
                    severity=TestSeverity.WARNING,
                    error=None,
                )
            )

        metadata = metadata_copy

        # Execute column-level tests
        if "schema" in metadata and metadata["schema"]:
            results.extend(
                self._execute_column_tests(table_name, metadata["schema"], severity_overrides)
            )

        # Execute model-level tests
        if "tests" in metadata and metadata["tests"]:
            results.extend(
                self._execute_model_level_tests(table_name, metadata["tests"], severity_overrides)
            )

        return results

    def _execute_column_tests(
        self,
        table_name: str,
        schema: list[dict[str, Any]],
        severity_overrides: dict[str, TestSeverity],
    ) -> list[TestResult]:
        """
        Execute column-level tests.

        Args:
            table_name: Fully qualified table name
            schema: List of column definitions with tests
            severity_overrides: Dict of severity overrides

        Returns:
            List of TestResult objects
        """
        results = []

        for column_def in schema:
            if "tests" not in column_def or not column_def["tests"]:
                continue

            column_name = column_def.get("name")
            if not column_name:
                self.logger.warning(f"Skipping tests for column without name in {table_name}")
                continue

            for test_def in column_def["tests"]:
                result = self._execute_single_test(
                    table_name=table_name,
                    column_name=column_name,
                    test_def=test_def,
                    severity_overrides=severity_overrides,
                )
                if result:
                    results.append(result)

        return results

    def _execute_model_level_tests(
        self,
        table_name: str,
        tests: list[TestDefinition],
        severity_overrides: dict[str, TestSeverity],
    ) -> list[TestResult]:
        """
        Execute model-level tests.

        Args:
            table_name: Fully qualified table name
            tests: List of test definitions
            severity_overrides: Dict of severity overrides

        Returns:
            List of TestResult objects
        """
        results = []

        for test_def in tests:
            result = self._execute_single_test(
                table_name=table_name,
                column_name=None,
                test_def=test_def,
                severity_overrides=severity_overrides,
            )
            if result:
                results.append(result)

        return results

    def _execute_single_test(
        self,
        table_name: str,
        column_name: str | None,
        test_def: TestDefinition,
        severity_overrides: dict[str, TestSeverity],
    ) -> TestResult | None:
        """
        Execute a single test definition.

        Args:
            table_name: Fully qualified table name
            column_name: Column name (None for model-level tests)
            test_def: Test definition (string name or dict with name/params/severity)
            severity_overrides: Dict of severity overrides

        Returns:
            TestResult or None if test not found
        """
        # Parse test definition
        context = f"{table_name}.{column_name}" if column_name else table_name
        parsed = TestDefinitionParser.parse(test_def, severity_overrides, context)
        if not parsed:
            return None

        # Get test from registry
        test = TestRegistry.get(parsed.test_name)
        if not test:
            warning_msg = (
                f"Test '{parsed.test_name}' not implemented yet. "
                f"Available tests: {TestRegistry.list_all()}"
            )
            self.logger.warning(warning_msg)
            return TestResult(
                test_name=parsed.test_name,
                table_name=table_name,
                column_name=column_name,
                passed=True,
                message=warning_msg,
                severity=TestSeverity.WARNING,
                error=None,
            )

        # Track that this test was used
        self._used_test_names.add(parsed.test_name)

        # Execute test
        return self._run_test(
            test=test,
            table_name=table_name,
            column_name=column_name,
            test_name=parsed.test_name,
            params=parsed.params,
            severity_override=parsed.severity_override,
        )

    def _run_test(
        self,
        test: Any,
        table_name: str,
        column_name: str | None,
        test_name: str,
        params: dict[str, Any] | None,
        severity_override: TestSeverity | None,
    ) -> TestResult:
        """
        Run a model test.

        Args:
            test: Test instance from registry
            table_name: Fully qualified table name
            column_name: Column name (None for model-level tests)
            test_name: Test name
            params: Test parameters
            severity_override: Optional severity override

        Returns:
            TestResult
        """
        try:
            result = test.execute(
                adapter=self.adapter,
                table_name=table_name,
                column_name=column_name,
                params=params,
                severity=severity_override,
            )
            return result
        except Exception as e:
            error_msg = f"Error executing test {test_name}: {str(e)}"
            self.logger.error(error_msg)
            return TestResult(
                test_name=test_name,
                table_name=table_name,
                column_name=column_name,
                passed=False,
                message=error_msg,
                severity=severity_override or test.severity,
                error=str(e),
            )

    def get_used_test_names(self) -> set[str]:
        """Get set of test names that were used during execution."""
        return self._used_test_names
