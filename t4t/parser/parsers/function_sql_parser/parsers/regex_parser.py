"""
Regex-based parser for CREATE FUNCTION/MACRO statements.

This parser serves as a fallback when SQLglot parsing fails, particularly
for CREATE MACRO statements in DuckDB.

SQLglot Bug with CREATE MACRO
=============================
SQLglot cannot parse DuckDB's CREATE MACRO syntax (see sqlglot_parser.py for details).
This regex parser is necessary to handle CREATE MACRO statements until the SQLglot
bug is fixed.

Issue: https://github.com/tobymao/sqlglot/issues/6290
SQLglot Version: 27.29.0 (and earlier)

Even though CREATE MACRO and CREATE FUNCTION are aliases in DuckDB, SQLglot only
parses CREATE FUNCTION correctly. This parser handles both syntaxes using regex
patterns to extract the same metadata that SQLglot would extract for CREATE FUNCTION.
"""

import logging
import re
from typing import Any

from t4t.typing.metadata import FunctionType

from ..extractors import (
    DependencyExtractor,
    FunctionBodyExtractor,
    FunctionNameExtractor,
    ParameterExtractor,
)

logger = logging.getLogger(__name__)


class RegexParser:
    """Parses CREATE FUNCTION/MACRO statements using regex patterns."""

    @staticmethod
    def parse(content: str, file_path_str: str) -> dict[str, Any] | None:
        """
        Parse a CREATE FUNCTION/MACRO statement and extract function metadata.

        Args:
            content: SQL content
            file_path_str: File path for error messages

        Returns:
            Dict with function metadata or None if not found

        Note:
            This parser handles both CREATE FUNCTION and CREATE MACRO syntaxes,
            which is necessary due to SQLglot's inability to parse CREATE MACRO.
        """
        # Normalize whitespace
        content_normalized = re.sub(r"\s+", " ", content.strip())

        # Pattern to match CREATE [OR REPLACE] FUNCTION or CREATE [OR REPLACE] MACRO (DuckDB)
        # This is a simplified pattern - we'll handle common variations
        pattern = r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|MACRO)\s+([^\s(]+)\s*\(([^)]*)\)\s*(?:RETURNS\s+([^\s{]+)\s*)?(?:AS\s+)?(?:['\"`]?(\$\$|['\"`])?)?\s*(.*?)(?:\1|;)?$"

        # Try to match the pattern
        match = re.search(pattern, content_normalized, re.IGNORECASE | re.DOTALL)
        if not match:
            # Try a more flexible pattern (for MACRO without RETURNS)
            pattern2 = r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|MACRO)\s+([^\s(]+)\s*\(([^)]*)\)"
            match = re.search(pattern2, content_normalized, re.IGNORECASE)
            if not match:
                logger.warning(
                    f"Could not parse CREATE FUNCTION/MACRO statement in {file_path_str}"
                )
                return None

        function_name_full = match.group(1).strip()
        # Extract schema and function name
        function_name, schema = FunctionNameExtractor.extract_from_string(function_name_full)

        # Parse parameters
        params_str = match.group(2).strip() if len(match.groups()) > 1 else ""
        parameters = ParameterExtractor.extract_from_string(params_str)

        # Parse return type
        return_type = None
        if len(match.groups()) > 2 and match.group(3):
            return_type = match.group(3).strip()

        # Extract function body (everything after RETURNS ... AS or AS for MACRO)
        function_body = ""
        if len(match.groups()) > 4 and match.group(5):
            function_body = match.group(5).strip()
            # Remove delimiter markers if present
            if function_body.startswith("$$"):
                function_body = function_body[2:]
            if function_body.endswith("$$"):
                function_body = function_body[:-2]
            # For MACRO, remove parentheses if present
            if function_body.startswith("(") and function_body.endswith(")"):
                function_body = function_body[1:-1].strip()
            function_body = function_body.strip()

        # If we didn't get the body from the regex, try using the extractor
        if not function_body:
            function_body = FunctionBodyExtractor.extract(content)

        # Try to extract language
        language = "sql"
        language_match = re.search(r"LANGUAGE\s+(\w+)", content, re.IGNORECASE)
        if language_match:
            language = language_match.group(1).lower()

        # Determine function type (default to scalar)
        function_type: FunctionType = "scalar"
        if "RETURNS TABLE" in content.upper() or return_type and "TABLE" in return_type.upper():
            function_type = "table"

        # Extract dependencies
        dependencies = DependencyExtractor.extract(function_body)

        return {
            "function_name": function_name,
            "description": None,  # Will be filled from metadata file if available
            "function_type": function_type,
            "language": language,
            "parameters": parameters,
            "return_type": return_type,
            "return_table_schema": None,  # Will be filled from metadata if table function
            "schema": schema,
            "deterministic": None,  # Will be filled from metadata if available
            "tests": [],
            "tags": [],
            "object_tags": {},
            "function_body": function_body,
            # Store dependencies temporarily - will be moved to code["sql"] in the result structure
            "_dependencies": dependencies,
        }
