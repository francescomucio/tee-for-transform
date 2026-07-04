"""
SQLglot-based parser for CREATE FUNCTION statements.

NOTE: SQLglot Bug with CREATE MACRO
====================================
SQLglot cannot parse DuckDB's CREATE MACRO syntax, even though CREATE MACRO
and CREATE FUNCTION are aliases in DuckDB. When SQLglot encounters CREATE MACRO,
it falls back to parsing as a generic exp.Command object instead of a structured
exp.Create with exp.UserDefinedFunction.

This means we cannot extract structured metadata (function name, parameters,
function body, schema) from CREATE MACRO statements using SQLglot alone.

Issue: https://github.com/tobymao/sqlglot/issues/6290
SQLglot Version: 27.29.0 (and earlier)

As a workaround, we use regex parsing (see regex_parser.py) for CREATE MACRO
statements. The regex parser is used as a fallback when SQLglot parsing fails
or returns a Command object instead of a Create object.
"""

import logging
import re
from typing import Any

import sqlglot
from sqlglot import exp

from t4t.typing.metadata import FunctionType

from ..extractors import (
    DependencyExtractor,
    FunctionBodyExtractor,
    FunctionNameExtractor,
    ParameterExtractor,
    ReturnTypeExtractor,
)

logger = logging.getLogger(__name__)


class SQLglotParser:
    """Parses CREATE FUNCTION statements using SQLglot."""

    @staticmethod
    def parse(content: str, file_path_str: str, dialect: str = "postgres") -> dict[str, Any] | None:
        """
        Parse CREATE FUNCTION using SQLglot.

        Args:
            content: SQL content
            file_path_str: File path for error messages
            dialect: SQL dialect to use for parsing

        Returns:
            Dict with function metadata or None if parsing fails

        Note:
            This parser will fail for CREATE MACRO statements in DuckDB due to
            a SQLglot bug. See module docstring for details.
        """
        try:
            # Try parsing with the specified dialect
            parsed = sqlglot.parse_one(content, dialect=dialect)

            if not parsed or not isinstance(parsed, exp.Create):
                return None

            # Check if it's a UserDefinedFunction
            if not isinstance(parsed.this, exp.UserDefinedFunction):
                return None

            udf = parsed.this

            # Extract function name and schema
            name_result = FunctionNameExtractor.extract_from_udf(udf)
            if not name_result:
                return None

            function_name, schema = name_result

            # Extract parameters
            parameters = ParameterExtractor.extract_from_udf(udf)

            # Extract return type from SQL (SQLglot doesn't expose RETURNS directly)
            return_type = ReturnTypeExtractor.extract(content)

            # Extract language
            language = "sql"
            language_match = re.search(r"LANGUAGE\s+(\w+)", content, re.IGNORECASE)
            if language_match:
                language = language_match.group(1).lower()

            # Extract function body
            function_body = FunctionBodyExtractor.extract(content)

            # Determine function type
            function_type: FunctionType = "scalar"
            if "RETURNS TABLE" in content.upper() or (
                return_type and "TABLE" in return_type.upper()
            ):
                function_type = "table"

            # Extract dependencies
            dependencies = DependencyExtractor.extract(function_body)

            return {
                "function_name": function_name,
                "description": None,
                "function_type": function_type,
                "language": language,
                "parameters": parameters,
                "return_type": return_type,
                "return_table_schema": None,
                "schema": schema,
                "deterministic": None,
                "tests": [],
                "tags": [],
                "object_tags": {},
                "function_body": function_body,
                # Store dependencies temporarily - will be moved to code["sql"] in the result structure
                "_dependencies": dependencies,
            }

        except Exception as e:
            logger.debug(f"SQLglot parsing failed for {file_path_str}: {e}")
            return None
