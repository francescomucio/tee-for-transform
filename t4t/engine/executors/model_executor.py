"""Model execution logic."""

import logging
from typing import Any

from t4t.adapters.base.core import DatabaseAdapter

from ..materialization.materialization_handler import MaterializationHandler
from ..metadata.metadata_extractor import MetadataExtractor
from ..state.state_checker import StateChecker

logger = logging.getLogger(__name__)


class ModelExecutor:
    """Handles model execution logic."""

    def __init__(
        self,
        adapter: DatabaseAdapter,
        project_folder: str,
        variables: dict[str, Any],
        materialization_handler: MaterializationHandler,
        metadata_extractor: MetadataExtractor,
        state_checker: StateChecker,
        config: Any | None = None,
    ) -> None:
        """
        Initialize the model executor.

        Args:
            adapter: Database adapter instance
            project_folder: Project folder path
            variables: Variables dictionary for model execution
            materialization_handler: Materialization handler instance
            metadata_extractor: Metadata extractor instance
            state_checker: State checker instance
            config: Optional adapter config
        """
        self.adapter = adapter
        self.project_folder = project_folder
        self.variables = variables
        self.materialization_handler = materialization_handler
        self.metadata_extractor = metadata_extractor
        self.state_checker = state_checker
        self.config = config
        # Track schemas that have been processed for tag attachment
        self._processed_schemas: dict[str, dict[str, Any]] = {}

    def execute(self, parsed_models: dict[str, Any], execution_order: list[str]) -> dict[str, Any]:
        """
        Execute SQL models in the specified order with dialect conversion.

        Args:
            parsed_models: Dictionary mapping table names to parsed SQL arguments
            execution_order: List of table names in execution order

        Returns:
            Dictionary with execution results and status
        """
        results = {
            "executed_tables": [],
            "failed_tables": [],
            "execution_log": [],
            "table_info": {},
            "dialect_conversions": [],
            "warnings": [],
        }

        logger.info(
            f"Starting execution of {len(execution_order)} models using {self.adapter.__class__.__name__}"
        )

        # Build table mapping for resolving references
        table_mapping = {}
        for table_name in execution_order:
            # Skip test nodes
            if table_name.startswith("test:"):
                continue
            if table_name in parsed_models:
                model_data = parsed_models[table_name]
                tables = model_data.get("tables", [])
                for table in tables:
                    # Find the full table name that matches this short name
                    for full_name in execution_order:
                        if full_name.endswith(f".{table}") or full_name == table:
                            table_mapping[table] = full_name
                            break

        for table_name in execution_order:
            # Skip test nodes - they are executed separately by TestExecutor
            if table_name.startswith("test:"):
                logger.debug(f"Skipping test node: {table_name}")
                continue

            try:
                logger.debug(f"Executing model: {table_name}")

                if table_name not in parsed_models:
                    logger.warning(f"Model {table_name} not found in parsed models")
                    results["failed_tables"].append(
                        {"table": table_name, "error": "Model not found in parsed models"}
                    )
                    continue

                model_data = parsed_models[table_name]

                # Apply naming strategy to the table name (env-aware schema prefix)
                mapped_name = self.adapter.apply_naming(table_name)

                # Get SQL query (prefer resolved_sql, fallback to original_sql)
                sql_query = self._extract_sql_query(model_data, table_name)
                if not sql_query:
                    results["failed_tables"].append(
                        {"table": table_name, "error": "No SQL query found"}
                    )
                    continue

                # Remap dependency references in SQL when naming is active
                if (
                    self.config
                    and hasattr(self.config, "naming")
                    and self.config.naming
                    and self.config.naming.schema_prefix
                ):
                    sql_query = self._remap_sql_references(
                        sql_query, table_name, execution_order
                    )

                # Log dialect conversion if applicable
                if (
                    self.adapter.config.source_dialect
                    and self.adapter.config.source_dialect != self.adapter.get_default_dialect()
                ):
                    results["dialect_conversions"].append(
                        {
                            "table": table_name,
                            "from_dialect": self.adapter.config.source_dialect,
                            "to_dialect": self.adapter.get_default_dialect(),
                        }
                    )

                # Execute based on materialization type
                materialization = self._get_materialization_type(model_data)
                metadata = self.metadata_extractor.extract_model_metadata(model_data)

                # Extract schema name and attach schema-level tags if needed
                schema_name = self._extract_schema_name(table_name)
                if schema_name:
                    self._attach_schema_tags_if_needed(schema_name)

                # Check for materialization changes and database existence
                self.state_checker.check_model_state(
                    mapped_name, materialization, metadata, self.adapter
                )

                # Execute the model using the mapped name
                self.materialization_handler.materialize(
                    mapped_name, sql_query, materialization, metadata, self.config
                )

                # Save model state after successful execution
                self.state_checker.save_model_state(
                    mapped_name, materialization, sql_query, metadata
                )

                # Get table information
                table_info = self.adapter.get_table_info(mapped_name)

                results["executed_tables"].append(table_name)
                results["table_info"][table_name] = table_info
                results["execution_log"].append(
                    {
                        "table": table_name,
                        "status": "success",
                        "row_count": table_info["row_count"],
                        "materialization": materialization,
                    }
                )

                logger.debug(
                    f"Successfully executed {table_name} (mapped to {mapped_name}) with {table_info['row_count']} rows"
                )

            except Exception as e:
                error_msg = f"Error executing {table_name}: {str(e)}"
                logger.error(error_msg)
                results["failed_tables"].append({"table": table_name, "error": str(e)})
                results["execution_log"].append(
                    {"table": table_name, "status": "failed", "error": str(e)}
                )

        logger.info(
            f"Execution completed. {len(results['executed_tables'])} successful, {len(results['failed_tables'])} failed"
        )
        return results

    def _extract_sql_query(self, model_data: dict[str, Any], table_name: str) -> str:
        """
        Extract SQL query from model data.

        Args:
            model_data: Parsed model data
            table_name: Name of the table

        Returns:
            SQL query string or empty string if not found
        """
        code_data = model_data.get("code", {})
        if not code_data or "sql" not in code_data:
            logger.error(f"No code.sql found for {table_name}")
            return ""

        sql_data = code_data["sql"]
        if "resolved_sql" in sql_data:
            return sql_data["resolved_sql"]
        elif "original_sql" in sql_data:
            logger.warning(f"No resolved_sql found for {table_name}, falling back to original_sql")
            return sql_data["original_sql"]

        logger.error(f"No SQL query found for {table_name}")
        return ""

    def _get_materialization_type(self, model_data: dict[str, Any]) -> str:
        """
        Extract materialization type from model data.

        Args:
            model_data: Parsed model data containing metadata

        Returns:
            Materialization type ("table", "view", "materialized_view") or "table" as default
        """
        try:
            # Check if metadata exists and has materialization field
            if "model_metadata" in model_data and "metadata" in model_data["model_metadata"]:
                metadata = model_data["model_metadata"]["metadata"]
                if isinstance(metadata, dict) and "materialization" in metadata:
                    materialization = metadata["materialization"]
                    # Check if the adapter supports this materialization type
                    supported_types = [
                        m.value for m in self.adapter.get_supported_materializations()
                    ]
                    if materialization in supported_types:
                        return materialization
                    else:
                        logger.warning(
                            f"Materialization type '{materialization}' not supported by {self.adapter.__class__.__name__}, "
                            f"falling back to 'table'. Supported types: {supported_types}"
                        )

            # Default to table if no materialization specified or invalid type
            return "table"

        except Exception as e:
            logger.warning(f"Error extracting materialization type: {e}, defaulting to 'table'")
            return "table"

    def _extract_schema_name(self, table_name: str) -> str | None:
        """
        Extract schema name from table name.

        Args:
            table_name: Full table name (e.g., "my_schema.table_name")

        Returns:
            Schema name or None if no schema in table name
        """
        if "." in table_name:
            return table_name.split(".", 1)[0]
        return None

    def _remap_sql_references(
        self, sql_query: str, current_table: str, execution_order: list[str]
    ) -> str:
        """Remap upstream model references in SQL to their mapped names.

        When a ``schema_prefix`` is active, models are materialised under
        the prefixed schema (e.g. ``dev_my_schema.my_table``).  This method
        rewrites references to upstream models in *sql_query* so they point
        to the correct prefixed location.

        Uses longest-first string replacement on fully-qualified names.
        """
        dep_mapping: dict[str, str] = {}
        for dep_name in execution_order:
            if dep_name == current_table:
                break
            if dep_name.startswith("test:"):
                continue
            dep_mapped = self.adapter.apply_naming(dep_name)
            if dep_mapped != dep_name:
                dep_mapping[dep_name] = dep_mapped

        if not dep_mapping:
            return sql_query

        # Sort by length (longest first) to avoid partial replacements
        for logical_name in sorted(dep_mapping, key=len, reverse=True):
            sql_query = sql_query.replace(logical_name, dep_mapping[logical_name])
        return sql_query

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
