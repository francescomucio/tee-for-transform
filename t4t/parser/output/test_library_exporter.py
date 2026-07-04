"""
Test Library Exporter - Exports discovered SQL tests to OTS test library format.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from t4t.parser.shared.exceptions import OutputGenerationError
from t4t.testing.base import StandardTest
from t4t.testing.python_test import PythonTest
from t4t.testing.sql_test import SqlTest
from t4t.testing.test_discovery import TestDiscovery

logger = logging.getLogger(__name__)


class TestLibraryExporter:
    """Exports discovered SQL tests to OTS test library format."""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(self, project_folder: Path, project_name: str):
        """
        Initialize the test library exporter.

        Args:
            project_folder: Path to the project folder
            project_name: Project name (for filename generation)
        """
        self.project_folder = Path(project_folder)
        self.project_name = project_name
        self.test_discovery = TestDiscovery(self.project_folder)

    def export_test_library(self, output_folder: Path, format: str = "json") -> Path:
        """
        Export discovered SQL tests to OTS test library format.

        Args:
            output_folder: Path to output folder
            format: Output format ("json" or "yaml")

        Returns:
            Path to the exported test library file

        Raises:
            OutputGenerationError: If export fails
        """
        try:
            # Discover all SQL tests
            discovered_tests = self.test_discovery.discover_tests()

            if not discovered_tests:
                logger.info("No SQL tests found to export")
                return None

            # Separate generic and singular tests
            generic_tests = {}
            singular_tests = {}

            for test_name, sql_test in discovered_tests.items():
                test_metadata = self._extract_test_metadata(sql_test)

                if test_metadata["is_generic"]:
                    generic_tests[test_name] = test_metadata["definition"]
                else:
                    singular_tests[test_name] = test_metadata["definition"]

            # Build test library structure
            test_library = {
                "ots_version": "0.2.1",  # Test libraries are part of OTS 0.2.1
                "test_library_version": "1.0",
                "description": f"Test library for {self.project_name} project",
            }

            if generic_tests:
                test_library["generic_tests"] = generic_tests
            if singular_tests:
                test_library["singular_tests"] = singular_tests

            # Generate filename with appropriate extension
            if format == "yaml":
                filename = f"{self.project_name}_test_library.ots.yaml"
            else:
                filename = f"{self.project_name}_test_library.ots.json"
            output_file = output_folder / filename

            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Write file in the specified format
            with open(output_file, "w", encoding="utf-8") as f:
                if format == "yaml":
                    import yaml

                    yaml.dump(
                        test_library,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        allow_unicode=True,
                    )
                else:
                    json.dump(test_library, f, indent=2, ensure_ascii=False)

            logger.info(f"Exported test library to {output_file}")
            # Note: This is a temporary export that will be merged by the compiler
            # Don't print here to avoid confusion - the compiler will print the final merged version

            return output_file

        except Exception as e:
            raise OutputGenerationError(f"Failed to export test library: {e}") from e

    def _extract_test_metadata(self, test: StandardTest) -> dict[str, Any]:
        """
        Extract metadata from a test to build OTS test definition.

        Args:
            test: StandardTest instance (SqlTest or PythonTest)

        Returns:
            Dictionary with 'is_generic', 'definition', and other metadata
        """
        try:
            # Handle different test types
            if isinstance(test, SqlTest):
                # SqlTest: load SQL from file
                sql_content = test._load_sql_content()
            elif isinstance(test, PythonTest):
                # PythonTest: SQL is already in memory
                sql_content = test.sql
            else:
                # Unknown test type - log warning and use empty SQL
                logger.warning(f"Unknown test type for {test.name}: {type(test)}")
                sql_content = ""
        except Exception as e:
            logger.warning(f"Failed to load SQL content for {test.name}: {e}")
            sql_content = ""

        # Determine if generic or singular
        is_generic = self._is_generic_test(sql_content)

        # Extract description from SQL comments
        description = self._extract_description(sql_content)

        # Remove comments from SQL for the sql field (description is already extracted)
        cleaned_sql = self._remove_sql_comments(sql_content)

        # Determine test level (table or column)
        # Check if test uses @column_name or {{ column_name }}
        has_column_placeholder = bool(
            re.search(r"@column_name|{{\s*column_name\s*}}", cleaned_sql, re.IGNORECASE)
        )
        level = "column" if has_column_placeholder else "table"

        # Extract parameters from SQL (use cleaned SQL to avoid matching in comments)
        parameters = self._extract_parameters(cleaned_sql)

        # Build base definition
        definition = {
            "type": "sql",
            "level": level,
            "description": description or f"SQL test: {test.name}",
            "sql": cleaned_sql.strip(),
        }

        if is_generic:
            # Generic test: add parameters if any
            if parameters:
                definition["parameters"] = parameters
            else:
                definition["parameters"] = []
        else:
            # Singular test: extract target_transformation from SQL
            target_transformation = self._extract_target_transformation(sql_content)
            if target_transformation:
                definition["target_transformation"] = target_transformation
            else:
                logger.warning(
                    f"Singular test '{test.name}' has no identifiable target transformation. "
                    f"Please ensure the SQL contains a fully qualified table name."
                )

        return {
            "is_generic": is_generic,
            "definition": definition,
        }

    def _is_generic_test(self, sql_content: str) -> bool:
        """
        Check if a SQL test is generic (uses placeholders) vs singular (hardcoded).

        Args:
            sql_content: SQL content of the test

        Returns:
            True if generic, False if singular
        """
        placeholder_patterns = [
            r"@table_name",
            r"{{\s*table_name\s*}}",
            r"@column_name",
            r"{{\s*column_name\s*}}",
        ]
        return any(
            re.search(pattern, sql_content, re.IGNORECASE) for pattern in placeholder_patterns
        )

    def _extract_description(self, sql_content: str) -> str | None:
        """
        Extract description from SQL comments.

        Args:
            sql_content: SQL content

        Returns:
            Description string or None
        """
        lines = sql_content.split("\n")
        description_lines = []

        for line in lines:
            line = line.strip()
            # Skip empty lines and SQL code
            if (
                not line
                or line.startswith("SELECT")
                or line.startswith("FROM")
                or line.startswith("WHERE")
            ):
                break
            # Extract from comments
            if line.startswith("--"):
                comment = line[2:].strip()
                if (
                    comment
                    and not comment.startswith("Usage:")
                    and not comment.startswith("Returns")
                ):
                    description_lines.append(comment)

        if description_lines:
            return " ".join(description_lines[:3])  # Take first few comment lines

        return None

    def _remove_sql_comments(self, sql_content: str) -> str:
        """
        Remove SQL comments (-- style) from SQL content.

        Args:
            sql_content: SQL content with comments

        Returns:
            SQL content without comments
        """
        lines = sql_content.split("\n")
        cleaned_lines = []

        for line in lines:
            # Check if line is a comment
            stripped = line.strip()
            if stripped.startswith("--"):
                # Skip comment lines
                continue

            # Check for inline comments (-- at end of line)
            if "--" in line:
                # Find the first -- that's not in a string
                # Simple approach: split on -- and take first part
                # This won't handle strings with -- in them perfectly, but it's good enough
                parts = line.split("--", 1)
                if len(parts) > 1:
                    # Check if the -- is likely a comment (not in a string)
                    # Simple heuristic: if there's an odd number of quotes before --, it's in a string
                    before_comment = parts[0]
                    quote_count = before_comment.count("'") + before_comment.count('"')
                    if quote_count % 2 == 0:
                        # Even number of quotes means -- is likely a comment
                        line = parts[0].rstrip()

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def _extract_parameters(self, sql_content: str) -> dict[str, dict[str, Any]]:
        """
        Extract parameter definitions from SQL using @param:default syntax.

        Args:
            sql_content: SQL content

        Returns:
            Dictionary of parameter definitions
        """
        parameters = {}

        # Find all @param:default patterns
        # Pattern: @param_name:default_value
        # Supports:
        # - Numbers: @min_rows:10, @threshold:5.5
        # - Strings: @name:'test', @name:"test"
        # - Booleans: @enabled:true, @enabled:false
        # - No spaces, commas, semicolons, or closing parens after the colon (unless in quotes)

        # Pattern for quoted strings: @param:'value' or @param:"value"
        quoted_pattern = r'@(\w+):([\'"])([^\'"]*)\2'
        # Pattern for unquoted values (numbers, booleans, etc.): @param:value
        unquoted_pattern = r'@(\w+):([^\s\'"`,;\)]+)'

        # First match quoted strings
        for match in re.finditer(quoted_pattern, sql_content):
            param_name = match.group(1)
            match.group(2)
            default_value = match.group(3)

            # Skip table_name and column_name as they're special placeholders
            if param_name in ["table_name", "column_name"]:
                continue

            parameters[param_name] = {
                "type": "string",
                "default": default_value,
                "description": f"Parameter {param_name}",
            }

        # Then match unquoted values (but skip if already found as quoted)
        for match in re.finditer(unquoted_pattern, sql_content):
            param_name = match.group(1)
            default_value = match.group(2)

            # Skip if already found as quoted parameter
            if param_name in parameters:
                continue

            # Skip table_name and column_name as they're special placeholders
            if param_name in ["table_name", "column_name"]:
                continue

            # Try to infer type from default value
            param_type = self._infer_parameter_type(default_value)

            parameters[param_name] = {
                "type": param_type,
                "default": self._parse_default_value(default_value, param_type),
                "description": f"Parameter {param_name}",
            }

        return parameters

    def _infer_parameter_type(self, value: str) -> str:
        """
        Infer parameter type from default value.

        Args:
            value: Default value string

        Returns:
            Type string: "number", "string", "boolean", or "array"
        """
        value = value.strip()

        # Check for numbers
        try:
            float(value)
            return "number"
        except ValueError:
            pass

        # Check for booleans
        if value.lower() in ["true", "false"]:
            return "boolean"

        # Check for arrays (simple heuristic)
        if value.startswith("[") and value.endswith("]"):
            return "array"

        # Default to string
        return "string"

    def _parse_default_value(self, value: str, param_type: str) -> Any:
        """
        Parse default value according to type.

        Args:
            value: Value string
            param_type: Type string

        Returns:
            Parsed value
        """
        if param_type == "number":
            try:
                if "." in value:
                    return float(value)
                return int(value)
            except ValueError:
                return 0
        elif param_type == "boolean":
            return value.lower() == "true"
        elif param_type == "array":
            # Simple array parsing (basic)
            try:
                import ast

                return ast.literal_eval(value)
            except Exception:
                return []
        else:
            return value

    def _extract_target_transformation(self, sql_content: str) -> str | None:
        """
        Extract target transformation ID from singular test SQL.

        Looks for fully qualified table names (schema.table) in FROM clauses.

        Args:
            sql_content: SQL content

        Returns:
            Transformation ID (schema.table) or None
        """
        # Pattern to match FROM schema.table or FROM "schema"."table"
        patterns = [
            r"FROM\s+([\w]+)\.([\w]+)",  # FROM schema.table
            r'FROM\s+"([\w]+)"\."([\w]+)"',  # FROM "schema"."table"
            r"FROM\s+\'([\w]+)\'\.\'([\w]+)\'",  # FROM 'schema'.'table'
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, sql_content, re.IGNORECASE)
            for match in matches:
                schema = match.group(1)
                table = match.group(2)
                # Return first fully qualified table found
                return f"{schema}.{table}"

        # Fallback: look for any table reference that looks like schema.table
        # This is less reliable but might catch some cases
        fallback_pattern = r"([\w]+)\.([\w]+)"
        matches = re.finditer(fallback_pattern, sql_content)
        for match in matches:
            # Skip common SQL keywords
            if match.group(1).upper() not in [
                "SELECT",
                "FROM",
                "WHERE",
                "JOIN",
                "INNER",
                "LEFT",
                "RIGHT",
            ]:
                return f"{match.group(1)}.{match.group(2)}"

        return None
