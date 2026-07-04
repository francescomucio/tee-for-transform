"""Function transformation to OTS format."""

import logging
from typing import Any

from t4t.parser.shared.types import ParsedFunction
from t4t.typing.metadata import OTSFunction

from .base import BaseTransformer

logger = logging.getLogger(__name__)


class FunctionTransformer(BaseTransformer):
    """Transforms parsed functions to OTS functions."""

    def transform(
        self, function_id: str, function_data: ParsedFunction, _schema: str
    ) -> OTSFunction:
        """
        Transform a single parsed function to OTS function format.

        Args:
            function_id: Function identifier (e.g., "my_schema.function_name")
            function_data: Parsed function data
            _schema: Schema name (reserved)

        Returns:
            Transformed function as OTSFunction
        """
        function_metadata = function_data.get("function_metadata", {})
        code_data = function_data.get("code", {})

        # Extract function properties
        description = function_metadata.get("description")
        function_type = function_metadata.get("function_type", "scalar")
        language = function_metadata.get("language", "sql")
        parameters = function_metadata.get("parameters", [])
        return_type = function_metadata.get("return_type")
        return_table_schema = function_metadata.get("return_table_schema")

        # Extract dependencies from code["sql"] (consistent with models)
        dependencies = {"tables": [], "functions": []}
        if code_data and "sql" in code_data:
            sql_code = code_data["sql"]
            # Read dependencies from code["sql"] (like models)
            source_tables = sql_code.get("source_tables", [])
            source_functions = sql_code.get("source_functions", [])
            dependencies = {
                "tables": source_tables,
                "functions": source_functions,
            }

        # Build code structure for OTS
        # OTS expects: {"generic_sql": "...", "database_specific": {"duckdb": "...", "snowflake": "..."}}
        ots_code: dict[str, Any] = {}

        if code_data and "sql" in code_data:
            sql_code = code_data["sql"]
            # Use original_sql as generic_sql
            if "original_sql" in sql_code:
                ots_code["generic_sql"] = sql_code["original_sql"]

            # Database-specific code would go in database_specific dict
            # For now, we'll use generic_sql for all databases
            # Future: extract database-specific overrides if present
            ots_code["database_specific"] = {}
        else:
            # No SQL code (e.g., Python function that generates SQL)
            ots_code["generic_sql"] = ""
            ots_code["database_specific"] = {}

        # Build OTS function
        ots_function: OTSFunction = {
            "function_id": function_id,
            "description": description,
            "function_type": function_type,
            "language": language,
            "code": ots_code,
            "metadata": {"file_path": function_metadata.get("file_path", "")},
        }

        # Add optional fields
        if parameters:
            ots_function["parameters"] = parameters
        if return_type:
            ots_function["return_type"] = return_type
        if return_table_schema:
            ots_function["return_table_schema"] = return_table_schema
        # Add deterministic flag if present
        deterministic = function_metadata.get("deterministic")
        if deterministic is not None:
            ots_function["deterministic"] = deterministic
        if dependencies:
            ots_function["dependencies"] = dependencies

        # Add tags (dbt-style, list of strings) if present
        function_tags = function_metadata.get("tags", [])
        tags = self.tag_manager.merge_tags(function_tags)
        if tags:
            ots_function["metadata"]["tags"] = tags

        # Add object_tags (database-style, key-value pairs) if present
        object_tags = self.tag_manager.extract_object_tags(function_metadata)
        if object_tags:
            ots_function["metadata"]["object_tags"] = object_tags

        return ots_function
