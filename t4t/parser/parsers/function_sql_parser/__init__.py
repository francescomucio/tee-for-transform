"""
SQL function parsing functionality for UDFs.

This module has been refactored into a feature-based structure:
- dialect/: Dialect inference logic
- extractors/: Focused extraction modules (name, parameters, return type, body, dependencies)
- parsers/: SQLglot and regex parsing strategies
- utils/: Metadata merging utilities

The main FunctionSQLParser class orchestrates these components.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.parser.shared.exceptions import FunctionParsingError
from t4t.parser.shared.file_utils import find_metadata_file
from t4t.parser.shared.metadata_schema import parse_metadata_from_python_file
from t4t.parser.shared.types import FilePath

from ..base import BaseParser
from .dialect import DialectInferencer
from .parsers import RegexParser, SQLglotParser
from .utils import MetadataMerger

# Configure logging
logger = logging.getLogger(__name__)


class FunctionSQLParsingError(FunctionParsingError):
    """Raised when SQL function parsing fails."""

    pass


class FunctionSQLParser(BaseParser):
    """
    Handles SQL function parsing from CREATE FUNCTION statements.

    This parser uses SQLglot for structured parsing when possible, and falls back
    to regex parsing when SQLglot fails (e.g., for CREATE MACRO in DuckDB due to
    a SQLglot bug - see parsers/sqlglot_parser.py for details).
    """

    def __init__(
        self, connection: dict[str, Any] | None = None, project_config: dict[str, Any] | None = None
    ):
        """
        Initialize the SQL function parser.

        Args:
            connection: Optional connection configuration dict (for dialect inference)
            project_config: Optional project configuration dict (for dialect inference)
        """
        super().__init__()
        self.connection = connection or {}
        self.project_config = project_config or {}
        self._dialect_inferencer = DialectInferencer()

    def parse(
        self, content: str, file_path: FilePath = None, dialect: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """
        Parse SQL function content and extract function metadata.

        Args:
            content: The SQL content to parse
            file_path: Optional file path for context
            dialect: Optional SQL dialect override (if not provided, inferred from connection/project_config/filename)

        Returns:
            Dict mapping function_name to function registration data

        Raises:
            FunctionSQLParsingError: If parsing fails
        """
        if file_path is None:
            raise FunctionSQLParsingError("file_path is required for SQL function parsing")

        file_path = Path(file_path)
        file_path_str = str(file_path)

        # Check cache first
        cache_key = self._get_cache_key(content, file_path)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        try:
            logger.debug(f"Parsing SQL function file: {file_path}")

            # Try to find and parse companion metadata file first (to check for dialect override)
            metadata_file = find_metadata_file(file_path_str)
            metadata_dialect = None
            raw_metadata = None

            if metadata_file:
                try:
                    raw_metadata = parse_metadata_from_python_file(metadata_file)
                    # Check for dialect in metadata
                    if isinstance(raw_metadata, dict) and "dialect" in raw_metadata:
                        metadata_dialect = raw_metadata["dialect"]
                        logger.debug(f"Found dialect override in metadata: {metadata_dialect}")
                except Exception as e:
                    logger.warning(f"Failed to parse metadata from {metadata_file}: {str(e)}")

            # Determine dialect in priority order:
            # 1. Explicit dialect parameter
            # 2. Dialect from metadata
            # 3. Dialect from filename (database override)
            # 4. Dialect from connection/project config
            if not dialect:
                if metadata_dialect:
                    dialect = metadata_dialect
                else:
                    # Try to infer from filename (database override)
                    filename_dialect = self._dialect_inferencer.infer_from_filename(file_path)
                    if filename_dialect:
                        dialect = filename_dialect
                        logger.debug(f"Inferred dialect from filename: {dialect}")
                    else:
                        # Infer from connection/project config
                        dialect = self._dialect_inferencer.infer_from_connection(self.connection)
                        logger.debug(f"Inferred dialect from connection: {dialect}")

            # Try to parse with SQLglot first
            function_data = SQLglotParser.parse(content, file_path_str, dialect)

            # Fall back to regex parsing if SQLglot fails
            # This is necessary for CREATE MACRO in DuckDB due to SQLglot bug
            # See parsers/sqlglot_parser.py and parsers/regex_parser.py for details
            if not function_data:
                logger.debug(f"SQLglot parsing failed, falling back to regex for {file_path_str}")
                function_data = RegexParser.parse(content, file_path_str)

            if not function_data:
                raise FunctionSQLParsingError(f"No CREATE FUNCTION statement found in {file_path}")

            function_name = function_data["function_name"]

            # Merge metadata from Python file if available
            if raw_metadata and isinstance(raw_metadata, dict):
                try:
                    # Merge metadata from Python file
                    function_data = MetadataMerger.merge(function_data, raw_metadata)
                except Exception as e:
                    logger.warning(f"Failed to merge metadata from {metadata_file}: {str(e)}")

            # Extract dependencies from function_data (temporarily stored as _dependencies)
            dependencies = function_data.pop("_dependencies", {"tables": [], "functions": []})
            source_tables = dependencies.get("tables", [])
            source_functions = dependencies.get("functions", [])

            # Create standardized function structure
            result = {
                function_name: {
                    "function_metadata": function_data,
                    "needs_evaluation": False,  # SQL functions don't need evaluation
                    "code": {
                        "sql": {
                            "original_sql": content.strip(),
                            "function_body": function_data.get("function_body", ""),
                            "dialect": dialect,  # Store the dialect used for parsing
                            "source_tables": source_tables,  # Store dependencies like models
                            "source_functions": source_functions,  # Store dependencies like models
                        }
                    },
                    "file_path": file_path_str,
                }
            }

            # Cache the result
            self._set_cache(cache_key, result)
            logger.debug(
                f"Successfully parsed function {function_name} from {file_path} (dialect: {dialect})"
            )
            return result

        except Exception as e:
            if isinstance(e, FunctionSQLParsingError):
                raise
            raise FunctionSQLParsingError(
                f"Error parsing SQL function file {file_path}: {str(e)}"
            ) from e


# Export the main class for backward compatibility
__all__ = ["FunctionSQLParser", "FunctionSQLParsingError"]
