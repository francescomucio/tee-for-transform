"""
OTS to ParsedModel Converter - Converts OTS modules to t4t's internal ParsedModel format.

This module handles the transformation from OTS (Open Transformation Specification) format
to t4t's internal ParsedModel format for execution.
"""

import logging
from pathlib import Path
from typing import Any

from tee.parser.shared.function_utils import create_function_metadata
from tee.parser.shared.model_utils import create_model_metadata
from tee.parser.shared.types import ParsedFunction, ParsedModel
from tee.typing.metadata import OTSFunction, OTSModule, OTSTransformation

logger = logging.getLogger(__name__)


class OTSConverterError(Exception):
    """Exception raised when converting OTS modules fails."""

    pass


class OTSConverter:
    """Converts OTS modules to ParsedModel format."""

    def __init__(self, module_path: Path | None = None) -> None:
        """
        Initialize the OTS converter.

        Args:
            module_path: Optional path to the OTS module file (for resolving relative paths)
        """
        self.module_path = module_path

    def convert_module(
        self, module: OTSModule
    ) -> tuple[dict[str, ParsedModel], dict[str, ParsedFunction]]:
        """
        Convert an OTS module to dictionaries of ParsedModels and ParsedFunctions.

        Args:
            module: OTS module dictionary

        Returns:
            Tuple of (parsed_models, parsed_functions) dictionaries

        Raises:
            OTSConverterError: If conversion fails
        """
        try:
            transformations = module.get("transformations", [])
            parsed_models = {}

            for transformation in transformations:
                transformation_id = transformation.get("transformation_id")
                if not transformation_id:
                    logger.warning("Skipping transformation without transformation_id")
                    continue

                try:
                    parsed_model = self._convert_transformation(transformation, module)
                    parsed_models[transformation_id] = parsed_model
                except Exception as e:
                    logger.error(f"Failed to convert transformation {transformation_id}: {e}")
                    raise OTSConverterError(
                        f"Failed to convert transformation {transformation_id}: {e}"
                    ) from e

            # Convert functions (OTS 0.2.0+)
            parsed_functions = {}
            ots_version = module.get("ots_version", "0.1.0")
            # Check if version is 0.2.0 or higher (includes 0.2.1)
            # For simple versions like "0.1.0", "0.2.0", and "0.2.1", string comparison works
            if ots_version >= "0.2.0":
                functions = module.get("functions", [])
                for function in functions:
                    function_id = function.get("function_id")
                    if not function_id:
                        logger.warning("Skipping function without function_id")
                        continue

                    try:
                        parsed_function = self._convert_function(function, module)
                        parsed_functions[function_id] = parsed_function
                    except Exception as e:
                        logger.error(f"Failed to convert function {function_id}: {e}")
                        raise OTSConverterError(
                            f"Failed to convert function {function_id}: {e}"
                        ) from e

            logger.info(
                f"Converted {len(parsed_models)} transformations and {len(parsed_functions)} functions from OTS module"
            )
            return parsed_models, parsed_functions

        except Exception as e:
            raise OTSConverterError(f"Failed to convert OTS module: {e}") from e

    def _convert_transformation(
        self, transformation: OTSTransformation, module: OTSModule
    ) -> ParsedModel:
        """
        Convert a single OTS transformation to ParsedModel format.

        Args:
            transformation: OTS transformation dictionary
            module: Parent OTS module (for module-level metadata)

        Returns:
            ParsedModel dictionary
        """
        transformation.get("transformation_id", "")
        transformation_type = transformation.get("transformation_type", "sql")

        # Extract code structure
        code_data = self._convert_code(transformation.get("code", {}), transformation_type)

        # Extract and merge metadata
        model_metadata = self._convert_metadata(transformation, module)

        # Build ParsedModel structure
        parsed_model: ParsedModel = {
            "code": code_data,
            "model_metadata": model_metadata,
            "sqlglot_hash": "",  # Will be computed if needed
        }

        return parsed_model

    def _convert_code(self, code: dict[str, Any], transformation_type: str) -> dict[str, Any]:
        """
        Convert OTS code structure to ParsedModel code structure.

        Args:
            code: OTS code dictionary
            transformation_type: Type of transformation (e.g., "sql")

        Returns:
            ParsedModel code dictionary
        """
        if transformation_type == "sql":
            sql_code = code.get("sql", {})
            if not sql_code:
                raise OTSConverterError("SQL transformation missing 'code.sql' field")

            # OTS format matches ParsedModel format closely
            # Use resolved_sql if available, fallback to original_sql
            resolved_sql = sql_code.get("resolved_sql") or sql_code.get("original_sql", "")
            original_sql = sql_code.get("original_sql", resolved_sql)
            source_tables = sql_code.get("source_tables", [])

            return {
                "sql": {
                    "original_sql": original_sql,
                    "resolved_sql": resolved_sql,
                    "operation_type": "select",  # Default, could be inferred from SQL
                    "source_tables": source_tables,
                }
            }
        else:
            # For non-SQL transformations, preserve as-is for now
            logger.warning(
                f"Non-SQL transformation type '{transformation_type}' not fully supported yet"
            )
            return code

    def _convert_metadata(
        self, transformation: OTSTransformation, module: OTSModule
    ) -> dict[str, Any]:
        """
        Convert OTS metadata to ParsedModel metadata structure.

        Args:
            transformation: OTS transformation dictionary
            module: Parent OTS module (for module-level metadata)

        Returns:
            ParsedModel model_metadata dictionary
        """
        transformation_id = transformation.get("transformation_id", "")

        # Extract schema.table from transformation_id
        if "." in transformation_id:
            table_name = transformation_id
            transformation_id.split(".")[0]
        else:
            table_name = transformation_id
            module.get("target", {}).get("schema", "default")

        # Extract description
        description = transformation.get("description")

        # Extract file_path from metadata
        metadata = transformation.get("metadata", {})
        file_path = metadata.get("file_path", "")

        # Convert schema first (needed for attaching column tests)
        schema_data = self._convert_schema(transformation.get("schema"))

        # Convert tests (attaches column tests to schema_data)
        tests_data = self._convert_tests(transformation.get("tests"), schema_data)

        # Convert materialization
        materialization_data = self._convert_materialization(transformation.get("materialization"))

        # Merge module-level and transformation-level tags
        module_tags = module.get("tags", [])
        transformation_tags = metadata.get("tags", [])
        all_tags = list(set(module_tags + transformation_tags))  # Deduplicate

        # Build nested metadata structure
        nested_metadata: dict[str, Any] = {}

        if schema_data:
            nested_metadata["schema"] = schema_data
            # Add partitions if present
            if "partitioning" in transformation.get("schema", {}):
                nested_metadata["partitions"] = transformation["schema"]["partitioning"]
            # Add indexes if present
            if "indexes" in transformation.get("schema", {}):
                nested_metadata["indexes"] = transformation["schema"]["indexes"]

        if materialization_data:
            nested_metadata["materialization"] = materialization_data.get("type", "table")
            if materialization_data.get("type") == "incremental":
                nested_metadata["incremental"] = self._convert_incremental_details(
                    materialization_data.get("incremental_details", {})
                )
            elif materialization_data.get("type") == "scd2":
                nested_metadata["scd2_details"] = materialization_data.get("scd2_details", {})

        if tests_data:
            # Add table tests
            if "table" in tests_data:
                nested_metadata["tests"] = tests_data["table"]
            # Column tests are already in schema_data

        if all_tags:
            nested_metadata["tags"] = all_tags

        # Add object_tags if present
        object_tags = metadata.get("object_tags")
        if object_tags:
            nested_metadata["object_tags"] = object_tags

        # Create model_metadata structure
        model_metadata = create_model_metadata(
            table_name=table_name,
            file_path=file_path,
            description=description,
            metadata=nested_metadata,
        )

        return model_metadata

    def _convert_schema(self, schema: dict[str, Any] | None) -> list[dict[str, Any]] | None:
        """
        Convert OTS schema to ParsedModel schema format.

        Args:
            schema: OTS schema dictionary

        Returns:
            List of column definitions (ParsedModel format)
        """
        if not schema:
            return None

        columns = schema.get("columns", [])
        if not columns:
            return None

        # Convert columns - OTS format is already compatible
        # But we need to handle tests separately
        column_definitions = []
        for col in columns:
            col_def = {
                "name": col.get("name"),
                "datatype": col.get("datatype", "string"),
                "description": col.get("description"),
            }
            # Add auto_incremental if present (OTS 0.2.2+)
            if col.get("auto_incremental"):
                col_def["auto_incremental"] = True
            # Tests will be added separately in _convert_tests
            column_definitions.append(col_def)

        return column_definitions

    def _convert_materialization(self, materialization: dict[str, Any] | None) -> dict[str, Any]:
        """
        Convert OTS materialization to ParsedModel format.

        Args:
            materialization: OTS materialization dictionary

        Returns:
            ParsedModel materialization dictionary
        """
        if not materialization:
            return {"type": "table"}

        mat_type = materialization.get("type", "table")
        result = {"type": mat_type}

        if mat_type == "incremental":
            # Store incremental_details for later conversion
            result["incremental_details"] = materialization.get("incremental_details", {})
        elif mat_type == "scd2":
            result["scd2_details"] = materialization.get("scd2_details", {})

        return result

    def _convert_incremental_details(self, incremental_details: dict[str, Any]) -> dict[str, Any]:
        """
        Convert OTS incremental_details to ParsedModel incremental config.

        Args:
            incremental_details: OTS incremental_details dictionary

        Returns:
            ParsedModel incremental config dictionary
        """
        if not incremental_details:
            return {}

        strategy = incremental_details.get("strategy", "append")

        result: dict[str, Any] = {"strategy": strategy}

        if strategy == "delete_insert":
            delete_condition = incremental_details.get("delete_condition", "")
            # Use filter_column, start_value, and destination_filter_column if present (OTS 0.2.2+)
            # Fallback to start_date for backward compatibility (OTS < 0.2.2)
            filter_column = incremental_details.get("filter_column", "")
            start_value = incremental_details.get("start_value") or incremental_details.get(
                "start_date", "auto"
            )
            destination_filter_column = incremental_details.get("destination_filter_column")
            result["delete_insert"] = {
                "where_condition": delete_condition,
                "filter_column": filter_column,
                "start_value": start_value,
            }
            if destination_filter_column:
                result["delete_insert"]["destination_filter_column"] = destination_filter_column
            lookback = incremental_details.get("lookback")
            if lookback:
                result["delete_insert"]["lookback"] = lookback
        elif strategy == "append":
            # Use filter_column, start_value, and destination_filter_column if present (OTS 0.2.2+)
            # Fallback to start_date for backward compatibility (OTS < 0.2.2)
            filter_column = incremental_details.get("filter_column", "")
            start_value = incremental_details.get("start_value") or incremental_details.get(
                "start_date", "auto"
            )
            destination_filter_column = incremental_details.get("destination_filter_column")
            if not filter_column:
                # Fallback: Try to extract from filter_condition (for older OTS versions)
                filter_condition = incremental_details.get("filter_condition", "")
                # Simple heuristic: extract column name from "column >= value" or "column > value"
                import re

                match = re.match(r"(\w+)\s*[><=]+\s*", filter_condition)
                if match:
                    filter_column = match.group(1)
            result["append"] = {
                "filter_column": filter_column,
                "start_value": start_value,
            }
            if destination_filter_column:
                result["append"]["destination_filter_column"] = destination_filter_column
            lookback = incremental_details.get("lookback")
            if lookback:
                result["append"]["lookback"] = lookback
        elif strategy == "merge":
            merge_key = incremental_details.get("merge_key", [])
            # Use filter_column, start_value, and destination_filter_column if present (OTS 0.2.2+)
            # Fallback to start_date for backward compatibility (OTS < 0.2.2)
            filter_column = incremental_details.get("filter_column", "")
            start_value = incremental_details.get("start_value") or incremental_details.get(
                "start_date", "auto"
            )
            destination_filter_column = incremental_details.get("destination_filter_column")
            result["merge"] = {
                "unique_key": merge_key,
                "filter_column": filter_column,
                "start_value": start_value,
            }
            if destination_filter_column:
                result["merge"]["destination_filter_column"] = destination_filter_column
            lookback = incremental_details.get("lookback")
            if lookback:
                result["merge"]["lookback"] = lookback
            update_columns = incremental_details.get("update_columns")
            if update_columns:
                result["merge"]["update_columns"] = update_columns

        return result

    def _convert_tests(
        self, tests: dict[str, Any] | None, schema_data: list[dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        """
        Convert OTS tests to ParsedModel format.

        Args:
            tests: OTS tests dictionary
            schema_data: Schema data (to attach column tests)

        Returns:
            Tests dictionary with table and column tests
        """
        if not tests:
            return None

        result: dict[str, Any] = {}

        # Convert table tests
        table_tests = tests.get("table", [])
        if table_tests:
            result["table"] = table_tests

        # Convert column tests - attach to schema columns
        column_tests = tests.get("columns", {})
        if column_tests and schema_data:
            # Create a mapping of column name to tests
            col_test_map = {}
            for col_name, col_test_list in column_tests.items():
                col_test_map[col_name] = col_test_list

            # Attach tests to columns in schema
            for col_def in schema_data:
                col_name = col_def.get("name")
                if col_name in col_test_map:
                    col_def["tests"] = col_test_map[col_name]

        return result if result else None

    def _convert_function(self, function: OTSFunction, module: OTSModule) -> ParsedFunction:
        """
        Convert a single OTS function to ParsedFunction format.

        Args:
            function: OTS function dictionary
            module: Parent OTS module (for module-level metadata)

        Returns:
            ParsedFunction dictionary
        """
        function_id = function.get("function_id", "")

        # Extract schema.function_name from function_id
        if "." in function_id:
            parts = function_id.split(".", 1)
            schema = parts[0]
            function_name = parts[1]
        else:
            schema = module.get("target", {}).get("schema", "default")
            function_name = function_id

        # Extract function properties
        description = function.get("description")
        function_type = function.get("function_type", "scalar")
        language = function.get("language", "sql")
        parameters = function.get("parameters", [])
        return_type = function.get("return_type")
        return_table_schema = function.get("return_table_schema")
        dependencies = function.get("dependencies", {})

        # Extract code structure
        code_data = self._convert_function_code(function.get("code", {}), language, dependencies)

        # Extract and merge metadata
        metadata = function.get("metadata", {})
        file_path = metadata.get("file_path", "")

        # Merge module-level and function-level tags
        module_tags = module.get("tags", [])
        function_tags = metadata.get("tags", [])
        all_tags = list(set(module_tags + function_tags))  # Deduplicate

        # Extract object_tags
        object_tags = metadata.get("object_tags", {})

        # Build nested metadata structure
        nested_metadata: dict[str, Any] = {
            "tags": all_tags if all_tags else [],
            "object_tags": object_tags if object_tags else {},
            "tests": [],  # Functions can have tests, but we'll handle that separately if needed
        }

        # Create function_metadata structure
        function_metadata = create_function_metadata(
            function_name=function_name,
            schema=schema,
            file_path=file_path,
            description=description,
            function_type=function_type,
            language=language,
            parameters=parameters,
            return_type=return_type,
            metadata={
                **nested_metadata,
                "return_table_schema": return_table_schema,
            },
        )

        # Build ParsedFunction structure
        parsed_function: ParsedFunction = {
            "function_metadata": function_metadata,
            "code": code_data,
            "function_hash": "",  # Will be computed if needed
        }

        return parsed_function

    def _convert_function_code(
        self, code: dict[str, Any], language: str, dependencies: dict[str, list[str]]
    ) -> dict[str, Any]:
        """
        Convert OTS function code structure to ParsedFunction code structure.

        Args:
            code: OTS code dictionary
            language: Function language (e.g., "sql", "python")
            dependencies: Dependencies dict with 'tables' and 'functions' keys

        Returns:
            ParsedFunction code dictionary
        """
        if language == "sql":
            # OTS format: {"generic_sql": "...", "database_specific": {"duckdb": "...", ...}}
            generic_sql = code.get("generic_sql", "")
            code.get("database_specific", {})

            # For now, use generic_sql as original_sql
            # In the future, we might want to select database-specific SQL based on target
            original_sql = generic_sql

            # Extract dependencies (consistent with models)
            source_tables = dependencies.get("tables", [])
            source_functions = dependencies.get("functions", [])

            return {
                "sql": {
                    "original_sql": original_sql,
                    # Note: resolved_sql would be generated during parsing
                    "source_tables": source_tables,  # Store dependencies like models
                    "source_functions": source_functions,  # Store dependencies like models
                }
            }
        else:
            # For non-SQL functions (Python, JavaScript, etc.), preserve as-is
            logger.warning(f"Non-SQL function language '{language}' not fully supported yet")
            return code
