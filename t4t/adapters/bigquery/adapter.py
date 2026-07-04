"""
BigQuery adapter implementation.

This module provides BigQuery-specific functionality including:
- SQL dialect conversion
- BigQuery-specific optimizations
- Connection management with service account authentication
- Materialization support including external tables
"""

import importlib.util
from typing import Any

from t4t.adapters.base import AdapterConfig, DatabaseAdapter, MaterializationType
from t4t.adapters.registry import register_adapter


class BigQueryAdapter(DatabaseAdapter):
    """BigQuery database adapter with SQLglot integration."""

    def __init__(self, config: AdapterConfig) -> None:
        if importlib.util.find_spec("google.cloud.bigquery") is None:
            raise ImportError(
                "google-cloud-bigquery is not installed. Install it with: uv add google-cloud-bigquery"
            ) from None

        super().__init__(config)

    def get_default_dialect(self) -> str:
        """Get the default SQL dialect for BigQuery."""
        return "bigquery"

    def get_supported_materializations(self) -> list[MaterializationType]:
        """Get list of supported materialization types for BigQuery."""
        return [
            MaterializationType.TABLE,
            MaterializationType.VIEW,
            MaterializationType.MATERIALIZED_VIEW,
            MaterializationType.EXTERNAL_TABLE,
        ]

    def connect(self) -> None:
        """Establish connection to BigQuery."""
        if not all([self.config.project, self.config.database]):
            raise ValueError("BigQuery connection requires project and database")

        try:
            from google.cloud import bigquery

            # Initialize BigQuery client
            if self.config.extra and "service_account_path" in self.config.extra:
                # Use service account file
                self.client = bigquery.Client.from_service_account_json(
                    self.config.extra["service_account_path"], project=self.config.project
                )
            else:
                # Use default credentials
                self.client = bigquery.Client(project=self.config.project)

            self.connection = self.client  # For compatibility
            self.logger.info(f"Connected to BigQuery: {self.config.project}/{self.config.database}")
        except Exception as e:
            self.logger.error(f"Failed to connect to BigQuery: {e}")
            raise

    def disconnect(self) -> None:
        """Close the BigQuery connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.connection = None
            self.logger.info("Disconnected from BigQuery")

    def execute_query(self, query: str) -> Any:
        """Execute a SQL query and return results."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Convert SQL if needed
            converted_query = self.convert_sql_dialect(query)

            # Qualify table references if dataset is specified
            if self.config.database:
                converted_query = self.qualify_table_references(
                    converted_query, self.config.database
                )

            # Execute query
            query_job = self.client.query(converted_query)
            result = query_job.result()

            # Convert to list of tuples for compatibility
            rows = []
            for row in result:
                rows.append(tuple(row.values()))

            self.logger.debug(f"Executed query: {converted_query[:100]}...")
            return rows
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            raise

    def create_table(
        self,
        table_name: str,
        query: str,
        metadata: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> None:
        """Create a table from a qualified SQL query."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if dataset is specified
        if self.config.database:
            converted_query = self.qualify_table_references(converted_query, self.config.database)

        # Create fully qualified table name
        if "." not in table_name and self.config.database:
            full_table_name = f"{self.config.project}.{self.config.database}.{table_name}"
        else:
            full_table_name = table_name

        # Wrap the query in a CREATE TABLE statement
        create_query = f"CREATE OR REPLACE TABLE `{full_table_name}` AS {converted_query}"

        try:
            query_job = self.client.query(create_query)
            query_job.result()  # Wait for completion
            self.logger.info(f"Created table: {full_table_name}")
        except Exception as e:
            self.logger.error(f"Failed to create table {full_table_name}: {e}")
            raise

    def create_view(
        self, view_name: str, query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Create a view from a qualified SQL query."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if dataset is specified
        if self.config.database:
            converted_query = self.qualify_table_references(converted_query, self.config.database)

        # Create fully qualified view name
        if "." not in view_name and self.config.database:
            full_view_name = f"{self.config.project}.{self.config.database}.{view_name}"
        else:
            full_view_name = view_name

        # Wrap the query in a CREATE VIEW statement
        create_query = f"CREATE OR REPLACE VIEW `{full_view_name}` AS {converted_query}"

        try:
            query_job = self.client.query(create_query)
            query_job.result()  # Wait for completion
            self.logger.info(f"Created view: {full_view_name}")

            # Add view and column comments if metadata is provided
            if metadata:
                # Add view description
                if "description" in metadata and metadata["description"]:
                    self._add_table_comment(full_view_name, metadata["description"])

                # Add column comments
                if "schema" in metadata and metadata["schema"]:
                    column_descriptions = self._validate_column_metadata(metadata)
                    if column_descriptions:
                        self._add_column_comments(full_view_name, column_descriptions)

        except Exception as e:
            self.logger.error(f"Failed to create view {full_view_name}: {e}")
            raise

    def create_materialized_view(self, view_name: str, query: str) -> None:
        """Create a materialized view from a qualified SQL query."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if dataset is specified
        if self.config.database:
            converted_query = self.qualify_table_references(converted_query, self.config.database)

        # Create fully qualified view name
        if "." not in view_name and self.config.database:
            full_view_name = f"{self.config.project}.{self.config.database}.{view_name}"
        else:
            full_view_name = view_name

        # BigQuery materialized view syntax
        create_query = f"CREATE MATERIALIZED VIEW `{full_view_name}` AS {converted_query}"

        try:
            query_job = self.client.query(create_query)
            query_job.result()  # Wait for completion
            self.logger.info(f"Created materialized view: {full_view_name}")
        except Exception as e:
            self.logger.error(f"Failed to create materialized view {full_view_name}: {e}")
            raise

    def create_external_table(self, table_name: str, query: str, external_location: str) -> None:
        """Create an external table from a qualified SQL query."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL if needed
        converted_query = self.convert_sql_dialect(query)

        # Qualify table references if dataset is specified
        if self.config.database:
            converted_query = self.qualify_table_references(converted_query, self.config.database)

        # Create fully qualified table name
        if "." not in table_name and self.config.database:
            full_table_name = f"{self.config.project}.{self.config.database}.{table_name}"
        else:
            full_table_name = table_name

        # BigQuery external table syntax (simplified - would need proper column definitions)
        create_query = f"""
        CREATE OR REPLACE EXTERNAL TABLE `{full_table_name}`
        OPTIONS (
            format = 'PARQUET',
            uris = ['{external_location}']
        )
        """

        try:
            query_job = self.client.query(create_query)
            query_job.result()  # Wait for completion
            self.logger.info(f"Created external table: {full_table_name}")
        except Exception as e:
            self.logger.error(f"Failed to create external table {full_table_name}: {e}")
            raise

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Create fully qualified table name
            if "." not in table_name and self.config.database:
                full_table_name = f"{self.config.project}.{self.config.database}.{table_name}"
            else:
                full_table_name = table_name

            table_ref = self.client.get_table(full_table_name)
            return table_ref is not None
        except Exception:
            return False

    def drop_table(self, table_name: str) -> None:
        """Drop a table from the database."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Create fully qualified table name
            if "." not in table_name and self.config.database:
                full_table_name = f"{self.config.project}.{self.config.database}.{table_name}"
            else:
                full_table_name = table_name

            self.client.delete_table(full_table_name)
            self.logger.info(f"Dropped table: {full_table_name}")
        except Exception as e:
            self.logger.error(f"Error dropping table {table_name}: {e}")
            raise

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Create fully qualified table name
            if "." not in table_name and self.config.database:
                full_table_name = f"{self.config.project}.{self.config.database}.{table_name}"
            else:
                full_table_name = table_name

            table = self.client.get_table(full_table_name)

            # Get schema information
            schema = []
            for field in table.schema:
                schema.append({"column": field.name, "type": field.field_type})

            # Get row count
            count_query = f"SELECT COUNT(*) FROM `{full_table_name}`"
            query_job = self.client.query(count_query)
            result = query_job.result()
            row_count = next(result)[0]

            return {"schema": schema, "row_count": row_count}
        except Exception as e:
            self.logger.error(f"Error getting table info for {table_name}: {e}")
            raise

    def describe_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """Infer schema from SQL query output using BigQuery dry run."""
        # TODO: Implement BigQuery-specific schema inference
        raise NotImplementedError("describe_query_schema not yet implemented for BigQuery")

    def add_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Add a column to an existing table."""
        # TODO: Implement BigQuery-specific column addition
        raise NotImplementedError("add_column not yet implemented for BigQuery")

    def drop_column(self, table_name: str, column_name: str) -> None:
        """Drop a column from an existing table."""
        # TODO: Implement BigQuery-specific column dropping
        raise NotImplementedError("drop_column not yet implemented for BigQuery")

    def create_function(
        self,
        function_name: str,
        function_sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create or replace a user-defined function in the database."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Create fully qualified function name
        if "." not in function_name and self.config.database:
            # If not fully qualified, add project.dataset prefix
            full_function_name = f"{self.config.project}.{self.config.database}.{function_name}"
        else:
            full_function_name = function_name

        # Function SQL is already a complete CREATE OR REPLACE FUNCTION statement
        # Execute it as-is (should already be in BigQuery dialect)
        try:
            # Convert SQL dialect if needed (though function_sql should already be BigQuery)
            converted_sql = self.convert_sql_dialect(function_sql)

            # Execute the CREATE OR REPLACE FUNCTION statement
            query_job = self.client.query(converted_sql)
            query_job.result()  # Wait for completion
            self.logger.info(f"Created function: {full_function_name}")

            # Attach tags if provided (BigQuery doesn't natively support tags, but log debug)
            if metadata:
                tags = metadata.get("tags", [])
                object_tags = metadata.get("object_tags", {})
                if tags:
                    self.attach_tags("FUNCTION", full_function_name, tags)
                if object_tags:
                    self.attach_object_tags("FUNCTION", full_function_name, object_tags)

        except Exception as e:
            self.logger.error(f"Failed to create function {full_function_name}: {e}")
            from t4t.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(
                f"Failed to create function {full_function_name}: {e}"
            ) from e

    def function_exists(
        self,
        function_name: str,
        signature: str | None = None,  # noqa: ARG002
    ) -> bool:
        """Check if a function exists in the database."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Extract dataset and function name
            if "." in function_name:
                parts = function_name.split(".")
                if len(parts) == 3:
                    # project.dataset.function
                    dataset_name = parts[1]
                    func_name = parts[2]
                elif len(parts) == 2:
                    # dataset.function (use current project)
                    dataset_name = parts[0]
                    func_name = parts[1]
                else:
                    dataset_name = self.config.database
                    func_name = function_name
            else:
                dataset_name = self.config.database
                func_name = function_name

            # Query INFORMATION_SCHEMA.ROUTINES for functions
            query = f"""
                SELECT COUNT(*)
                FROM `{self.config.project}.{dataset_name}.INFORMATION_SCHEMA.ROUTINES`
                WHERE routine_name = '{func_name}' AND routine_type = 'FUNCTION'
            """
            query_job = self.client.query(query)
            result = query_job.result()
            row_count = next(result)[0]
            return row_count > 0
        except Exception as e:
            self.logger.warning(f"Error checking if function {function_name} exists: {e}")
            return False

    def drop_function(self, function_name: str) -> None:
        """Drop a function from the database."""
        if not self.client:
            raise RuntimeError("Not connected to database. Call connect() first.")

        try:
            # Create fully qualified function name
            if "." not in function_name and self.config.database:
                full_function_name = f"{self.config.project}.{self.config.database}.{function_name}"
            else:
                full_function_name = function_name

            # BigQuery requires the full signature for DROP FUNCTION
            # For now, we'll use DROP FUNCTION IF EXISTS with just the qualified name
            # This may fail if there are multiple overloads - that's expected behavior
            drop_query = f"DROP FUNCTION IF EXISTS `{full_function_name}`"
            query_job = self.client.query(drop_query)
            query_job.result()  # Wait for completion
            self.logger.info(f"Dropped function: {full_function_name}")
        except Exception as e:
            self.logger.error(f"Error dropping function {function_name}: {e}")
            from t4t.parser.shared.exceptions import FunctionExecutionError

            raise FunctionExecutionError(f"Failed to drop function {function_name}: {e}") from e


# Register the adapter
register_adapter("bigquery", BigQueryAdapter)
