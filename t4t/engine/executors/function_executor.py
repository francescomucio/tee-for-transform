"""Function execution logic."""

import logging
from typing import Any

from t4t.adapters.base.core import DatabaseAdapter
from t4t.parser.shared.types import ParsedFunction

from ..metadata.metadata_extractor import MetadataExtractor

logger = logging.getLogger(__name__)


class FunctionExecutor:
    """Handles function execution logic."""

    def __init__(
        self,
        adapter: DatabaseAdapter,
        project_folder: str,
        metadata_extractor: MetadataExtractor,
    ) -> None:
        """
        Initialize the function executor.

        Args:
            adapter: Database adapter instance
            project_folder: Project folder path
            metadata_extractor: Metadata extractor instance
        """
        self.adapter = adapter
        self.project_folder = project_folder
        self.metadata_extractor = metadata_extractor
        # Track schemas that have been processed for tag attachment
        self._processed_schemas: dict[str, dict[str, Any]] = {}

    def execute(
        self, parsed_functions: dict[str, ParsedFunction], execution_order: list[str]
    ) -> dict[str, Any]:
        """
        Execute user-defined functions in dependency order.

        Functions are always created/overwritten (no versioning).
        Execution order should include functions before models that depend on them.

        Args:
            parsed_functions: Dictionary mapping function names to parsed function data
            execution_order: List of all objects (functions and models) in execution order

        Returns:
            Dictionary with execution results and status
        """
        results = {
            "executed_functions": [],
            "failed_functions": [],
            "execution_log": [],
            "warnings": [],
        }

        # Filter execution order to get only functions
        function_order = [name for name in execution_order if name in parsed_functions]

        if not function_order:
            logger.info("No functions to execute")
            return results

        logger.info(
            f"Starting execution of {len(function_order)} functions using {self.adapter.__class__.__name__}"
        )

        for function_name in function_order:
            # Skip test nodes
            if function_name.startswith("test:"):
                logger.debug(f"Skipping test node: {function_name}")
                continue

            try:
                logger.info(f"Executing function: {function_name}")

                if function_name not in parsed_functions:
                    logger.warning(f"Function {function_name} not found in parsed functions")
                    results["failed_functions"].append(
                        {
                            "function": function_name,
                            "error": "Function not found in parsed functions",
                        }
                    )
                    continue

                function_data = parsed_functions[function_name]

                # Extract function SQL
                function_sql = self._extract_function_sql(function_data, function_name)
                if not function_sql:
                    results["failed_functions"].append(
                        {"function": function_name, "error": "No SQL found for function"}
                    )
                    continue

                # Extract metadata
                metadata = self.metadata_extractor.extract_function_metadata(function_data)

                # Apply naming strategy to the function name (env-aware schema prefix)
                mapped_name = self.adapter.apply_naming(function_name)

                # Extract schema name and attach schema-level tags if needed
                schema_name = self._extract_schema_name(function_name)
                if schema_name:
                    self._attach_schema_tags_if_needed(schema_name)

                # Execute function creation (always CREATE OR REPLACE)
                # No need to check if function exists - CREATE OR REPLACE handles replacement
                # All supported databases (DuckDB, Snowflake, PostgreSQL, BigQuery) support CREATE OR REPLACE
                self.adapter.create_function(mapped_name, function_sql, metadata)

                results["executed_functions"].append(function_name)
                results["execution_log"].append(
                    {
                        "function": function_name,
                        "status": "success",
                    }
                )

                logger.info(
                    f"Successfully executed function: {function_name} (mapped to {mapped_name})"
                )

            except Exception as e:
                error_msg = f"Error executing function {function_name}: {str(e)}"
                logger.error(error_msg)
                results["failed_functions"].append({"function": function_name, "error": str(e)})
                results["execution_log"].append(
                    {"function": function_name, "status": "failed", "error": str(e)}
                )
                # Continue with other functions even if one fails
                # Functions are independent, so one failure shouldn't stop others

        logger.info(
            f"Function execution completed. {len(results['executed_functions'])} successful, "
            f"{len(results['failed_functions'])} failed"
        )
        return results

    def _extract_function_sql(self, function_data: dict[str, Any], function_name: str) -> str:
        """
        Extract SQL query from function data and convert to target dialect.

        Source dialect is determined in priority order:
        1. source_sql_dialect from function metadata
        2. source_sql_dialect from project.toml
        3. source_dialect from adapter config
        4. "generic" (default, most flexible)

        Args:
            function_data: Parsed function data
            function_name: Name of the function

        Returns:
            SQL query string converted to target dialect, or empty string if not found
        """
        code_data = function_data.get("code", {})
        if not code_data or "sql" not in code_data:
            logger.error(f"No code.sql found for function {function_name}")
            return ""

        sql_data = code_data["sql"]

        # Get the SQL (prefer resolved_sql if available, fallback to original_sql)
        function_sql = None
        if "resolved_sql" in sql_data:
            function_sql = sql_data["resolved_sql"]
        elif "original_sql" in sql_data:
            function_sql = sql_data["original_sql"]

            # Determine source dialect in priority order:
            # 1. source_sql_dialect from function metadata
            # 2. source_sql_dialect from project.toml
            # 3. source_dialect from adapter config
            # 4. "generic" (default, most flexible)
            source_dialect = None

            # Check function metadata first
            function_metadata = function_data.get("function_metadata", {})
            if isinstance(function_metadata, dict):
                # Check for source_sql_dialect in metadata dict
                metadata_dict = function_metadata.get("metadata", {})
                if isinstance(metadata_dict, dict):
                    source_dialect = metadata_dict.get("source_sql_dialect")
                # Also check directly in function_metadata
                if not source_dialect:
                    source_dialect = function_metadata.get("source_sql_dialect")

            # Check project.toml if not found in metadata
            if not source_dialect:
                source_dialect = self._get_source_sql_dialect_from_project()

            # Fall back to adapter config
            if not source_dialect:
                source_dialect = self.adapter.config.source_dialect

            # Default to None (auto-detect) for flexible parsing (convert_sql_dialect will use this)
            # No need to set it explicitly here since convert_sql_dialect defaults to None/auto-detect

            target_dialect = self.adapter.get_default_dialect()

            # Convert SQL to target dialect (convert_sql_dialect uses auto-detect if source_dialect is None)
            if source_dialect:
                logger.debug(
                    f"Converting function {function_name} SQL from {source_dialect} to {target_dialect}"
                )
            else:
                logger.debug(
                    f"Converting function {function_name} SQL using auto-detect to {target_dialect}"
                )

            try:
                # Convert SQL to target dialect
                logger.debug(
                    f"Converting function {function_name} SQL (source: {source_dialect or 'auto-detect'}, target: {target_dialect})"
                )
                original_sql = function_sql
                function_sql = self.adapter.convert_sql_dialect(
                    function_sql, source_dialect=source_dialect
                )

                # Persist the converted SQL back to function_data
                sql_data["resolved_sql"] = function_sql

                if function_sql != original_sql:
                    logger.debug(
                        f"Successfully converted function {function_name} SQL to {target_dialect}"
                    )
                    logger.debug(f"Converted SQL preview: {function_sql[:200]}...")
                    # Print full converted SQL only in debug mode
                    self._print_converted_function_sql(function_name, function_sql, target_dialect)
                else:
                    logger.debug(
                        f"Function {function_name} SQL unchanged after conversion (may be compatible or conversion not needed)"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to convert function {function_name} SQL to {target_dialect}: {e}. "
                    f"Using original SQL. Please review manually."
                )
                # Store original SQL as resolved_sql if conversion fails
                sql_data["resolved_sql"] = function_sql
                # Don't raise - continue with original SQL (might work if dialects are compatible)
        else:
            logger.error(f"No original_sql or resolved_sql found for function {function_name}")
            return ""

        return function_sql or ""

    def _print_converted_function_sql(
        self, function_name: str, converted_sql: str, target_dialect: str
    ) -> None:
        """
        Print the converted function SQL in a formatted, human-readable way.

        Displays the complete converted SQL that will be executed in the target database.

        Args:
            function_name: Name of the function
            converted_sql: The converted SQL string
            target_dialect: Target database dialect
        """
        output = []
        output.append("\n" + "━" * 80)
        output.append(f"  🔧 CONVERTED FUNCTION SQL: {function_name}")
        output.append(f"  🎯 Target Dialect: {target_dialect}")
        output.append("━" * 80)
        output.append("")
        output.append("  📝 Converted SQL Definition:")
        sql_lines = converted_sql.split("\n")
        for line in sql_lines:
            output.append(f"     {line}")
        output.append("")
        output.append("━" * 80)
        output.append("")

        logger.debug("\n".join(output))

    def _get_source_sql_dialect_from_project(self) -> str | None:
        """
        Get source_sql_dialect from project.toml.

        Checks root level first, then connection section for backward compatibility.

        Returns:
            source_sql_dialect from project config, or None if not found
        """
        try:
            import tomllib
            from pathlib import Path

            project_toml = Path(self.project_folder) / "project.toml"
            if not project_toml.exists():
                return None

            with open(project_toml, "rb") as f:
                project_config = tomllib.load(f)

            # Check at root level first (preferred location)
            if "source_sql_dialect" in project_config:
                return project_config.get("source_sql_dialect")

            # Also check in connection section (for backward compatibility)
            connection_config = project_config.get("connection", {})
            if isinstance(connection_config, dict):
                return connection_config.get("source_sql_dialect")

            return None

        except Exception as e:
            logger.debug(f"Could not read source_sql_dialect from project.toml: {e}")
            return None

    def _extract_schema_name(self, function_name: str) -> str:
        """
        Extract schema name from function name.

        Args:
            function_name: Full function name (e.g., "my_schema.function_name")

        Returns:
            Schema name or None if no schema in function name
        """
        if "." in function_name:
            return function_name.split(".", 1)[0]
        return None

    def _attach_schema_tags_if_needed(self, schema_name: str) -> None:
        """
        Attach tags to schema if not already processed and if schema-level tags are configured.

        Args:
            schema_name: Name of the schema
        """
        # Skip if already processed
        if schema_name in self._processed_schemas:
            return

        # Load schema-level tags from project config
        schema_metadata = self.metadata_extractor.load_schema_metadata(
            schema_name, self.project_folder
        )
        if not schema_metadata:
            # Mark as processed even if no tags to avoid repeated checks
            self._processed_schemas[schema_name] = {}
            return

        # Attach tags to schema if adapter supports it
        if hasattr(self.adapter, "attach_tags") and hasattr(
            self.adapter, "_create_schema_if_needed"
        ):
            try:
                # Use the adapter's _create_schema_if_needed with metadata to attach tags
                # This will create the schema if needed and attach tags
                self.adapter._create_schema_if_needed(f"{schema_name}.dummy", schema_metadata)
                logger.info(f"Attached tags to schema: {schema_name}")
            except Exception as e:
                logger.warning(f"Could not attach tags to schema {schema_name}: {e}")

        # Mark as processed
        self._processed_schemas[schema_name] = schema_metadata
