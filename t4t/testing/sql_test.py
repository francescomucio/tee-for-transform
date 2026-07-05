"""
SQL-based custom tests.

Supports custom tests defined in SQL files in the tests/ folder, similar to dbt.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.parser.processing.variable_substitution import substitute_sql_variables

from .base import StandardTest, TestResult, TestSeverity


class SqlTest(StandardTest):
    """
    Custom test defined in a SQL file.

    SQL tests follow the dbt pattern:
    - Query returns rows when test fails
    - 0 rows returned = test passes
    - Query should use COUNT(*) for performance

    The SQL can reference:
    - Table names directly
    - Variables via {{ variable_name }} or @variable_name
    - Model references (future: {{ ref('table_name') }})
    """

    def __init__(
        self,
        name: str,
        sql_file_path: Path,
        project_folder: Path,
        severity: TestSeverity = TestSeverity.ERROR,
    ):
        """
        Initialize a SQL test.

        Args:
            name: Test name (derived from file name or specified)
            sql_file_path: Path to the SQL test file
            project_folder: Project folder path (for resolving variables)
            severity: Test severity level
        """
        super().__init__(name, severity)
        self.sql_file_path = sql_file_path
        self.project_folder = project_folder
        self.logger = logging.getLogger(self.__class__.__name__)
        self._sql_content: str | None = None

    def _load_sql_content(self) -> str:
        """Load SQL content from file."""
        if self._sql_content is None:
            try:
                with open(self.sql_file_path, encoding="utf-8") as f:
                    self._sql_content = f.read()
            except Exception as e:
                raise ValueError(f"Failed to load SQL test file {self.sql_file_path}: {e}") from e
        return self._sql_content

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        """
        Validate SQL test parameters.

        SQL tests can accept parameters that will be substituted as variables.

        Args:
            params: Optional parameters (will be available as variables in SQL)
            column_name: Column name if this is a column-level test (optional)
        """
        # SQL tests can accept any parameters (they become variables)
        # No specific validation needed - the SQL file itself defines what it needs
        pass

    def get_test_query(
        self,
        adapter,  # noqa: ARG002
        table_name: str | None = None,
        column_name: str | None = None,
        function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate SQL query by loading from file and applying variable substitution.

        Args:
            adapter: Database adapter instance
            table_name: Fully qualified table name (available as 'table_name' variable, for model tests)
            column_name: Column name if applicable (available as 'column_name' variable, for model tests)
            function_name: Fully qualified function name (available as 'function_name' variable, for function tests)
            params: Additional parameters (available as variables, including @param1, @param2, etc.)

        Returns:
            SQL query string with variables substituted
        """
        # Load SQL content
        sql = self._load_sql_content()

        # Apply special substitutions for table_name and column_name (unquoted identifiers)
        # These should be replaced directly, not as SQL values
        if table_name:
            sql = sql.replace("{{ table_name }}", table_name)
            sql = sql.replace("{{table_name}}", table_name)  # No spaces
            sql = sql.replace("@table_name", table_name)

        if column_name:
            sql = sql.replace("{{ column_name }}", column_name)
            sql = sql.replace("{{column_name}}", column_name)  # No spaces
            sql = sql.replace("@column_name", column_name)

        # Apply special substitutions for function_name (unquoted identifier)
        if function_name:
            sql = sql.replace("{{ function_name }}", function_name)
            sql = sql.replace("{{function_name}}", function_name)  # No spaces
            sql = sql.replace("@function_name", function_name)

        # Build variables dict for other parameter substitution
        variables = {}

        # Add any additional params as variables (these will be quoted as SQL values)
        if params:
            variables.update(params)
            # Also support @param1, @param2, etc. as direct replacements (unquoted, for function parameters)
            for key, value in params.items():
                if key.startswith("param") or key.startswith("@param"):
                    # Remove @ prefix if present
                    param_key = key.replace("@", "")
                    # Support both @param1 and @param_1 formats
                    sql = sql.replace(f"@param{param_key.replace('param', '')}", str(value))
                    sql = sql.replace(f"@param_{param_key.replace('param', '')}", str(value))
                    sql = sql.replace(
                        f"{{{{ param{param_key.replace('param', '')} }}}}", str(value)
                    )
                    sql = sql.replace(f"{{{{param{param_key.replace('param', '')}}}}}", str(value))

        # Apply variable substitution for other variables (these are SQL values, quoted)
        # Support both {{ variable }} and @variable syntax
        if variables:
            try:
                sql = substitute_sql_variables(sql, variables)
            except Exception as e:
                self.logger.warning(f"Variable substitution failed in {self.name}: {e}")
                # Continue with original SQL if substitution fails

        # Note: SQL tests should return COUNT(*) for performance
        # If they return SELECT *, we might want to wrap it, but for now
        # we trust the user to write efficient queries

        return sql

    def execute(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        function_name: str | None = None,
        params: dict[str, Any] | None = None,
        expected: Any | None = None,
        severity: TestSeverity | None = None,
    ) -> TestResult:
        """
        Execute the SQL test.

        For model tests: SQL tests follow dbt pattern: 0 rows = pass, 1+ rows = fail.
        For function tests: Supports two patterns:
        1. Assertion-based: Query returns boolean (TRUE/1/truthy = pass, FALSE/0/falsy = fail)
        2. Expected value: Query returns result, compare to `expected` parameter

        The query can return either:
        - Rows directly (SELECT * FROM ... WHERE violation)
        - COUNT(*) result (SELECT COUNT(*) FROM ... WHERE violation)
        - Boolean result (for function tests: SELECT function(...) = expected)
        """
        # Validate parameters
        self.validate_params(params, column_name)

        # Use provided severity or test default
        test_severity = severity or self.severity

        try:
            # Get test query (with variable substitution)
            query = self.get_test_query(adapter, table_name, column_name, function_name, params)

            # Execute query
            results = adapter.execute_query(query)

            # Determine test result based on test type
            if function_name is not None:
                # Function test: support both assertion-based and expected value patterns
                passed = self._evaluate_function_test_result(results, expected)
                if expected is not None:
                    # Expected value pattern
                    if isinstance(results, list) and len(results) > 0:
                        actual_value = results[0][0] if len(results[0]) > 0 else None
                        message = (
                            f"Test passed: {self.name} returned {actual_value} (expected {expected})"
                            if passed
                            else f"Test failed: {self.name} returned {actual_value} (expected {expected})"
                        )
                    else:
                        message = (
                            f"Test passed: {self.name}"
                            if passed
                            else f"Test failed: {self.name} returned no result"
                        )
                else:
                    # Assertion-based pattern (boolean result)
                    if isinstance(results, list) and len(results) > 0:
                        result_value = results[0][0] if len(results[0]) > 0 else None
                        message = (
                            f"Test passed: {self.name} returned {result_value}"
                            if passed
                            else f"Test failed: {self.name} returned {result_value}"
                        )
                    else:
                        message = (
                            f"Test passed: {self.name}"
                            if passed
                            else f"Test failed: {self.name} returned no result"
                        )
            else:
                # Model test: dbt pattern (0 rows = pass)
                row_count = len(results) if isinstance(results, list) else 0

                passed = row_count == 0
                message = (
                    f"Test passed: {self.name}"
                    if passed
                    else f"Test failed: {self.name} found {row_count} violation(s)"
                )

            return TestResult(
                test_name=self.name,
                table_name=table_name,
                column_name=column_name,
                function_name=function_name,
                passed=passed,
                message=message,
                severity=test_severity,
                rows_returned=len(results) if isinstance(results, list) else 0,
            )

        except Exception as e:
            error_msg = f"Error executing SQL test {self.name}: {str(e)}"
            self.logger.error(error_msg)
            return TestResult(
                test_name=self.name,
                table_name=table_name,
                column_name=column_name,
                function_name=function_name,
                passed=False,
                message=error_msg,
                severity=test_severity,
                error=str(e),
            )

    def _evaluate_function_test_result(self, results: Any, expected: Any | None = None) -> bool:
        """
        Evaluate function test result based on pattern.

        Args:
            results: Query results from adapter
            expected: Expected value (if provided, use expected value pattern)

        Returns:
            True if test passed, False otherwise
        """
        if not isinstance(results, list) or len(results) == 0:
            return False

        result_value = results[0][0] if len(results[0]) > 0 else None

        if expected is not None:
            # Expected value pattern: compare actual to expected
            # Handle type coercion for numeric comparisons
            try:
                if isinstance(expected, (int, float)) and isinstance(result_value, (int, float)):
                    return abs(float(result_value) - float(expected)) < 1e-9  # Float comparison
                return result_value == expected
            except (ValueError, TypeError):
                return str(result_value) == str(expected)
        else:
            # Assertion-based pattern: check if result is truthy
            # Handle boolean representations across databases
            if result_value is None:
                return False
            if isinstance(result_value, bool):
                return result_value
            if isinstance(result_value, (int, float)):
                return bool(result_value)  # 0 = False, non-zero = True
            if isinstance(result_value, str):
                # Handle string representations of booleans
                return result_value.upper() in ("TRUE", "1", "YES", "T", "Y")
            # For other types, use truthiness
            return bool(result_value)
