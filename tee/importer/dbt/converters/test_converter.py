"""
Test converter from dbt format to t4t format.

Converts dbt test files to t4t SQL test format.
"""

import logging
import re
from pathlib import Path
from typing import Any

from tee.importer.common.path_utils import ensure_directory_exists
from tee.importer.dbt.constants import MAX_MODELS_IN_ERROR_MESSAGE

logger = logging.getLogger(__name__)


class TestConverter:
    """Converts dbt tests to t4t format."""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(
        self,
        target_path: Path,
        model_name_map: dict[str, str],
        verbose: bool = False,
    ) -> None:
        """
        Initialize test converter.

        Args:
            target_path: Path where t4t project will be created
            model_name_map: Dictionary mapping dbt model names to final t4t table names
            verbose: Enable verbose logging
        """
        self.target_path = Path(target_path).resolve()
        self.model_name_map = model_name_map
        self.verbose = verbose
        self.conversion_log: list[dict[str, Any]] = []

    def convert_test_file(
        self, test_file: Path, rel_path: str, is_freshness_test: bool = False
    ) -> dict[str, Any]:
        """
        Convert a single dbt test file to t4t format.

        Args:
            test_file: Path to the dbt test file
            rel_path: Relative path from dbt project root
            is_freshness_test: Whether this is a source freshness test

        Returns:
            Dictionary with conversion result
        """
        result: dict[str, Any] = {
            "test_file": str(test_file),
            "rel_path": rel_path,
            "converted": False,
            "skipped": False,
            "warnings": [],
            "errors": [],
        }

        if is_freshness_test:
            result["skipped"] = True
            result["warnings"].append(
                "Source freshness tests are not supported in t4t yet. "
                "See issue #01-freshness-tests for details."
            )
            logger.warning(
                f"Skipping source freshness test: {rel_path}. "
                "Freshness tests are not yet supported in t4t."
            )
            return result

        try:
            # Read test SQL content
            sql_content = test_file.read_text(encoding="utf-8")

            # Convert dbt syntax to t4t syntax
            converted_sql = self._convert_test_sql(sql_content, rel_path)

            # Determine target path
            target_test_file = self._get_target_test_path(rel_path)

            # Write converted test
            ensure_directory_exists(target_test_file)
            target_test_file.write_text(converted_sql, encoding="utf-8")

            result["converted"] = True
            result["target_file"] = str(target_test_file)

            if self.verbose:
                logger.info(f"Converted test: {rel_path} -> {target_test_file}")

        except Exception as e:
            result["errors"].append(f"Error converting test: {e}")
            logger.error(f"Failed to convert test {rel_path}: {e}", exc_info=True)

        return result

    def _convert_test_sql(self, sql_content: str, test_path: str) -> str:
        """
        Convert dbt test SQL syntax to t4t format.

        Args:
            sql_content: Original dbt test SQL
            test_path: Path to test file (for context)

        Returns:
            Converted SQL in t4t format
        """
        converted = sql_content

        # Convert {{ ref('model_name') }} to @table_name
        # In tests, ref() typically refers to the model being tested
        # We need to detect which model this test is for
        converted = self._convert_refs(converted, test_path)

        # Convert {{ this }} to @table_name
        # {{ this }} in dbt tests refers to the model being tested
        converted = self._convert_this(converted, test_path)

        # Convert {{ source('schema', 'table') }} to schema.table
        converted = self._convert_sources(converted)

        # Convert {{ var('name') }} to @name or @name:default
        converted = self._convert_vars(converted)

        # Note: Other Jinja (loops, conditionals) should be minimal in tests
        # If present, they'll need to be handled manually or converted to Python

        return converted

    def _convert_refs(self, sql_content: str, test_path: str) -> str:
        """
        Convert {{ ref('model_name') }} to actual table name for singular tests.

        For singular tests (tests with specific ref() calls), we use the actual
        table name from model_name_map. This makes the test specific to that table.

        Note: Generic tests (tests that can be applied to multiple tables) use
        @table_name placeholder, but those are defined in schema.yml, not as
        SQL files in tests/ directory.

        Args:
            sql_content: SQL content
            test_path: Path to test file

        Returns:
            SQL with ref() calls converted to actual table names
        """
        # Pattern: {{ ref('model_name') }} or {{ ref("model_name") }}
        ref_pattern = r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"

        def replace_ref(match: re.Match[str]) -> str:
            model_name = match.group(1)
            # Try to find the table name in model_name_map
            if model_name in self.model_name_map:
                table_name = self.model_name_map[model_name]
                # Use actual table name for singular tests
                return table_name
            else:
                # Model not found in map - this is an error
                # The model_name_map should be generated before converting tests
                available_models = list(self.model_name_map.keys())[:MAX_MODELS_IN_ERROR_MESSAGE]
                error_msg = (
                    f"Model '{model_name}' referenced in test {test_path} not found in model_name_map. "
                    f"This test cannot be properly converted. "
                    f"Available models: {available_models}..."
                )
                logger.error(error_msg)
                # Return model name as-is (will likely cause issues, but preserves the reference)
                return model_name

        converted = re.sub(ref_pattern, replace_ref, sql_content, flags=re.IGNORECASE)
        return converted

    def _convert_this(self, sql_content: str, _test_path: str) -> str:
        """
        Convert {{ this }} to @table_name.

        {{ this }} in dbt tests refers to the model being tested.
        We use @table_name as a placeholder that will be substituted at runtime.

        Args:
            sql_content: SQL content
            _test_path: Path to test file (reserved)

        Returns:
            SQL with {{ this }} converted to @table_name
        """
        # Pattern: {{ this }} or {{ this.column }}
        this_pattern = r"\{\{\s*this(?:\.[\w]+)?\s*\}\}"

        def replace_this(match: re.Match[str]) -> str:
            # Handle {{ this.column }} syntax
            matched = match.group(0)
            if ".column" in matched.lower() or re.search(r"\.\w+", matched):
                # Extract column name if present
                column_match = re.search(r"\.(\w+)", matched)
                if column_match:
                    column = column_match.group(1)
                    return f"@table_name.{column}"

            # Use @table_name placeholder
            return "@table_name"

        converted = re.sub(this_pattern, replace_this, sql_content, flags=re.IGNORECASE)
        return converted

    def _convert_sources(self, sql_content: str) -> str:
        """
        Convert {{ source('schema', 'table') }} to schema.table.

        Args:
            sql_content: SQL content

        Returns:
            SQL with source() calls converted
        """
        # Pattern: {{ source('schema', 'table') }}
        source_pattern = (
            r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
        )

        def replace_source(match: re.Match[str]) -> str:
            schema = match.group(1)
            table = match.group(2)
            return f"{schema}.{table}"

        converted = re.sub(source_pattern, replace_source, sql_content, flags=re.IGNORECASE)
        return converted

    def _convert_vars(self, sql_content: str) -> str:
        """
        Convert {{ var('name') }} to @name and {{ var('name', 'default') }} to @name:default.

        Args:
            sql_content: SQL content

        Returns:
            SQL with var() calls converted
        """
        # Pattern: {{ var('name', 'default') }} or {{ var('name') }}
        var_pattern = (
            r"\{\{\s*var\s*\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?\s*\)\s*\}\}"
        )

        def replace_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2) if match.group(2) else None
            if default:
                return f"@{var_name}:{default}"
            else:
                return f"@{var_name}"

        converted = re.sub(var_pattern, replace_var, sql_content, flags=re.IGNORECASE)
        return converted

    def _get_target_test_path(self, rel_path: str) -> Path:
        """
        Get target path for converted test file.

        Args:
            rel_path: Relative path from dbt project root (e.g., "tests/my_test.sql")

        Returns:
            Target Path object
        """
        # Keep the same structure under tests/ directory
        # e.g., tests/my_test.sql -> target_path/tests/my_test.sql
        # e.g., tests/schema/test_model.sql -> target_path/tests/schema/test_model.sql
        return self.target_path / rel_path

    def convert_all_tests(
        self, test_files: dict[str, Path], freshness_tests: set[str]
    ) -> dict[str, Any]:
        """
        Convert all test files.

        Args:
            test_files: Dictionary mapping relative paths to test file Paths
            freshness_tests: Set of relative paths that are freshness tests

        Returns:
            Dictionary with conversion summary
        """
        results = {
            "converted": 0,
            "skipped": 0,
            "errors": 0,
            "total": len(test_files),
            "conversion_log": [],
        }

        for rel_path, test_file in test_files.items():
            is_freshness = rel_path in freshness_tests
            result = self.convert_test_file(test_file, rel_path, is_freshness)
            results["conversion_log"].append(result)

            if result["converted"]:
                results["converted"] += 1
            elif result["skipped"]:
                results["skipped"] += 1
            elif result["errors"]:
                results["errors"] += 1

        if self.verbose:
            logger.info(
                f"Test conversion summary: {results['converted']} converted, "
                f"{results['skipped']} skipped, {results['errors']} errors"
            )

        return results
