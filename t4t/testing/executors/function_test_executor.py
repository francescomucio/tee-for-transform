"""
Function test execution logic.

Handles execution of tests for user-defined functions.
"""

import inspect
import logging
from typing import Any

from t4t.adapters.base import DatabaseAdapter
from t4t.testing.base import TestRegistry, TestResult, TestSeverity
from t4t.testing.parsers import TestDefinitionParser
from t4t.typing.metadata import TestDefinition

logger = logging.getLogger(__name__)


class FunctionTestExecutor:
    """Executes tests for user-defined functions."""

    def __init__(self, adapter: DatabaseAdapter):
        """
        Initialize function test executor.

        Args:
            adapter: Database adapter for executing test queries
        """
        self.adapter = adapter
        self.logger = logger
        self._used_test_names: set[str] = set()

    def execute_tests_for_function(
        self,
        function_name: str,
        metadata: dict[str, Any],
        severity_overrides: dict[str, TestSeverity] | None = None,
    ) -> list[TestResult]:
        """
        Execute all tests for a given function based on its metadata.

        Args:
            function_name: Fully qualified function name
            metadata: Function metadata containing test definitions
            severity_overrides: Optional dict to override test severities

        Returns:
            List of TestResult objects
        """
        results = []

        if not metadata:
            return results

        severity_overrides = severity_overrides or {}

        # Execute function-level tests
        if "tests" in metadata and metadata["tests"]:
            for test_def in metadata["tests"]:
                result = self._execute_single_function_test(
                    function_name=function_name,
                    test_def=test_def,
                    severity_overrides=severity_overrides,
                )
                if result:
                    results.append(result)

        return results

    def _execute_single_function_test(
        self,
        function_name: str,
        test_def: TestDefinition,
        severity_overrides: dict[str, TestSeverity],
    ) -> TestResult | None:
        """
        Execute a single function test definition.

        Args:
            function_name: Fully qualified function name
            test_def: Test definition (string name or dict with name/params/severity/expected)
            severity_overrides: Dict of severity overrides

        Returns:
            TestResult or None if test not found
        """
        # Parse test definition
        context = function_name
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
                function_name=function_name,
                passed=True,
                message=warning_msg,
                severity=TestSeverity.WARNING,
                error=None,
            )

        # Track that this test was used
        self._used_test_names.add(parsed.test_name)

        # Execute test
        return self._run_function_test(
            test=test,
            function_name=function_name,
            test_name=parsed.test_name,
            params=parsed.params,
            expected=parsed.expected,
            severity_override=parsed.severity_override,
        )

    def _run_function_test(
        self,
        test: Any,
        function_name: str,
        test_name: str,
        params: dict[str, Any] | None,
        expected: Any | None,
        severity_override: TestSeverity | None,
    ) -> TestResult:
        """
        Run a function test.

        Args:
            test: Test instance from registry
            function_name: Fully qualified function name
            test_name: Test name
            params: Test parameters
            expected: Expected value (for expected value pattern)
            severity_override: Optional severity override

        Returns:
            TestResult
        """
        try:
            # For SqlTest, pass function_name and expected
            if hasattr(test, "execute"):
                # Check if test supports function_name parameter
                sig = inspect.signature(test.execute)
                if "function_name" in sig.parameters:
                    result = test.execute(
                        adapter=self.adapter,
                        function_name=function_name,
                        params=params,
                        expected=expected,
                        severity=severity_override,
                    )
                    return result
                else:
                    # Fallback for tests that don't support function_name yet
                    self.logger.warning(
                        f"Test {test_name} does not support function testing, skipping"
                    )
                    return None
            else:
                # Standard tests don't support function testing
                self.logger.warning(f"Test {test_name} does not support function testing, skipping")
                return None

        except Exception as e:
            error_msg = f"Error executing test {test_name}: {str(e)}"
            self.logger.error(error_msg)
            return TestResult(
                test_name=test_name,
                function_name=function_name,
                passed=False,
                message=error_msg,
                severity=severity_override or test.severity,
                error=str(e),
            )

    def get_used_test_names(self) -> set[str]:
        """Get set of test names that were used during execution."""
        return self._used_test_names
