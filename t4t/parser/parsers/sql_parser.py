"""
Unified SQL parsing functionality using sqlglot.
"""

import logging

import sqlglot
from sqlglot import exp

from t4t.parser.analysis.sql_qualifier import generate_resolved_sql
from t4t.parser.shared.constants import SQL_BUILT_IN_FUNCTIONS
from t4t.parser.shared.exceptions import SQLParsingError
from t4t.parser.shared.file_utils import find_metadata_file
from t4t.parser.shared.metadata_schema import (
    parse_metadata_from_python_file,
    validate_metadata_dict,
)
from t4t.parser.shared.model_utils import compute_sqlglot_hash, create_model_metadata
from t4t.parser.shared.types import FilePath, ParsedModel
from t4t.typing.metadata import ModelMetadata

from .base import BaseParser

# Configure logging
logger = logging.getLogger(__name__)


class SQLParser(BaseParser):
    """Handles SQL parsing using sqlglot."""

    def _parse_metadata(self, sql_file_path: str) -> ModelMetadata | None:
        """
        Parse metadata from companion Python file or SQL comments.

        Args:
            sql_file_path: Path to the SQL file

        Returns:
            Parsed metadata dictionary or None if not found
        """
        # First try companion Python file
        metadata_file = find_metadata_file(sql_file_path)
        if metadata_file:
            try:
                raw_metadata = parse_metadata_from_python_file(metadata_file)
                if raw_metadata:
                    # Validate the metadata
                    validated_metadata = validate_metadata_dict(raw_metadata)
                    return ModelMetadata(
                        description=validated_metadata.description,
                        schema=[
                            {
                                "name": col.name,
                                "datatype": col.datatype,
                                "description": col.description,
                                "tests": col.tests,
                                "fk_to": col.fk_to,
                                "dimension": col.dimension,
                            }
                            for col in validated_metadata.schema
                        ]
                        if validated_metadata.schema
                        else None,
                        partitions=validated_metadata.partitions or [],
                        materialization=validated_metadata.materialization,
                        tests=validated_metadata.tests or [],
                        incremental=validated_metadata.incremental,
                        table_type=validated_metadata.table_type,
                        data_model=validated_metadata.data_model,
                        hierarchy=validated_metadata.hierarchy,
                        conformed_dimension=validated_metadata.conformed_dimension,
                        disable_default_tests=validated_metadata.disable_default_tests,
                    )
            except Exception as e:
                logger.warning(f"Failed to parse metadata from {metadata_file}: {str(e)}")

        # If no Python file, try to extract metadata from SQL comments
        try:
            logger.debug(f"Trying to extract metadata from SQL comments in {sql_file_path}")
            with open(sql_file_path, encoding="utf-8") as f:
                content = f.read()

            # Look for metadata comment: -- metadata: {...}
            import json
            import re

            metadata_match = re.search(r"--\s*metadata:\s*(\{.*\})", content, re.DOTALL)
            if metadata_match:
                metadata_json = metadata_match.group(1)
                logger.debug(f"Found metadata JSON in SQL comments: {metadata_json}")
                raw_metadata = json.loads(metadata_json)
                if raw_metadata:
                    logger.debug(f"Parsed metadata from SQL comments: {raw_metadata}")
                    # Validate the metadata
                    validated_metadata = validate_metadata_dict(raw_metadata)
                    return ModelMetadata(
                        description=validated_metadata.description,
                        schema=[
                            {
                                "name": col.name,
                                "datatype": col.datatype,
                                "description": col.description,
                                "tests": col.tests,
                                "fk_to": col.fk_to,
                                "dimension": col.dimension,
                            }
                            for col in validated_metadata.schema
                        ]
                        if validated_metadata.schema
                        else None,
                        partitions=validated_metadata.partitions or [],
                        materialization=validated_metadata.materialization,
                        tests=validated_metadata.tests or [],
                        incremental=validated_metadata.incremental,
                        table_type=validated_metadata.table_type,
                        data_model=validated_metadata.data_model,
                        hierarchy=validated_metadata.hierarchy,
                        conformed_dimension=validated_metadata.conformed_dimension,
                        disable_default_tests=validated_metadata.disable_default_tests,
                    )
            else:
                logger.debug(f"No metadata found in SQL comments for {sql_file_path}")
        except Exception as e:
            logger.warning(
                f"Failed to parse metadata from SQL comments in {sql_file_path}: {str(e)}"
            )

        return None

    def parse(
        self, content: str, file_path: FilePath = None, table_name: str = None
    ) -> ParsedModel:
        """
        Parse SQL content with sqlglot and extract relevant arguments.

        Args:
            content: The SQL content to parse
            file_path: Optional file path for context
            table_name: Name of the table for qualified SQL generation

        Returns:
            Dict containing parsed SQL arguments

        Raises:
            SQLParsingError: If SQL parsing fails
        """
        try:
            # Check cache first
            cache_key = self._get_cache_key(content, file_path)
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

            # Parse the SQL
            parsed = sqlglot.parse_one(content)

            if parsed is None:
                raise SQLParsingError("Failed to parse SQL")

            # Extract SQLGlot data
            result = self._parse_sqlglot_expression(
                parsed, table_name, str(file_path) if file_path else None
            )

            # Cache the result
            self._set_cache(cache_key, result)

            return result

        except Exception as e:
            if isinstance(e, SQLParsingError):
                raise
            raise SQLParsingError(f"SQL parsing error: {str(e)}") from e

    def _parse_sqlglot_expression(
        self, expr, table_name: str = None, file_path: str = None
    ) -> ParsedModel:
        """
        Parse a SQLGlot expression and extract relevant information.

        Args:
            expr: SQLGlot expression (either parsed AST or Expression object)
            table_name: Name of the table for qualified SQL generation

        Returns:
            Dict containing parsed SQL arguments
        """
        try:
            # Convert expression to SQL string
            sql_content = str(expr)

            # Extract table references
            source_tables = []
            for table in expr.find_all(exp.Table):
                source_tables.append(table.name)

            # Extract function calls (user-defined functions only)
            source_functions = []
            for func_node in expr.find_all(exp.Func):
                # Get function name - SQLglot Function nodes have a 'name' attribute
                func_name = func_node.name if hasattr(func_node, "name") else None

                # For qualified names (schema.func), check the 'this' attribute
                if not func_name and hasattr(func_node, "this"):
                    # Try to extract from 'this' (could be Identifier, Column, etc.)
                    this_node = func_node.this
                    if hasattr(this_node, "name"):
                        func_name = this_node.name
                    elif hasattr(this_node, "this") and hasattr(this_node.this, "name"):
                        # Handle nested structures (e.g., schema.func)
                        func_name = this_node.this.name
                    else:
                        func_name = str(this_node) if this_node else None

                # Fallback to string representation
                if not func_name:
                    func_name = str(func_node)

                # Filter out built-in functions and add to list
                if func_name and func_name.lower() not in SQL_BUILT_IN_FUNCTIONS:
                    source_functions.append(func_name)

            # Remove duplicates while preserving order
            source_functions = list(dict.fromkeys(source_functions))

            # Generate resolved SQL with table reference resolution if table_name provided
            if table_name:
                resolved_sql = generate_resolved_sql(str(expr), source_tables, table_name)
            else:
                # No table name provided, use original SQL as resolved SQL
                resolved_sql = sql_content.strip()

            # Build code structure with new field names
            code_data = {
                "sql": {
                    "original_sql": sql_content.strip(),
                    "resolved_sql": resolved_sql,
                    "operation_type": expr.key if hasattr(expr, "key") else "unknown",
                    "source_tables": source_tables,
                    "source_functions": source_functions,
                }
            }

            # Parse additional metadata from companion Python file
            additional_metadata = None
            if file_path:
                additional_metadata = self._parse_metadata(str(file_path))

            # Create model metadata
            model_metadata = create_model_metadata(
                table_name=table_name or "unknown_table",
                file_path=str(file_path) if file_path else None,
                description=f"SQL model for {table_name or 'unknown_table'}",
                metadata=additional_metadata,
            )

            # Compute hash of the resolved SQL for change detection
            sqlglot_hash = compute_sqlglot_hash({"resolved_sql": resolved_sql})

            # Return standardized structure with code and model_metadata
            return {
                "code": code_data,
                "model_metadata": model_metadata,
                "sqlglot_hash": sqlglot_hash,
            }

        except Exception as e:
            raise SQLParsingError(f"SQLGlot expression parsing error: {str(e)}") from e
