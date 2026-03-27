"""Incremental materialization strategies for DuckDB."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tee.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class IncrementalHandler:
    """Handles incremental materialization strategies for DuckDB."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the incremental handler.

        Args:
            adapter: DuckDBAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def execute_append(self, table_name: str, sql_query: str) -> None:
        """Execute incremental append into an existing table, or create if missing."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Check if table exists
        if not self.adapter.table_exists(table_name):
            # First run: create table from query
            self.logger.info(
                f"Table {table_name} does not exist. Creating it as a full load first."
            )
            self.adapter.create_table(table_name, sql_query, metadata=None)
            return

        # Convert SQL and qualify table references
        converted_query = self.adapter.utils.convert_and_qualify_sql(sql_query)

        # Insert into existing table
        insert_query = f"INSERT INTO {table_name} {converted_query}"

        try:
            self.adapter.utils.execute_query(insert_query)
            self.logger.info(f"Executed incremental append for table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error executing incremental append for {table_name}: {e}")
            raise

    def execute_merge(self, table_name: str, source_sql: str, config: dict[str, Any]) -> None:
        """Execute incremental merge operation."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Get table columns dynamically
        columns = self.adapter.get_table_columns(table_name)
        unique_key = config["unique_key"]

        # Generate DuckDB-specific merge SQL
        merge_sql = self._generate_merge_sql(table_name, source_sql, unique_key, columns)

        # Convert SQL and qualify table references
        converted_query = self.adapter.utils.convert_and_qualify_sql(merge_sql)

        # Log the generated SQL (debug level for cleaner output)
        self.logger.debug(f"Generated DuckDB merge SQL for {table_name}: {converted_query}")

        try:
            self.adapter.utils.execute_query(converted_query)
            self.logger.info("Executed incremental merge")
        except Exception as e:
            self.logger.error(f"Error executing incremental merge: {e}")
            raise

    def execute_delete_insert(self, table_name: str, delete_sql: str, insert_sql: str) -> None:
        """Execute incremental delete+insert operation."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        # Convert SQL and qualify table references
        converted_delete = self.adapter.utils.convert_and_qualify_sql(delete_sql)
        converted_insert = self.adapter.utils.convert_and_qualify_sql(insert_sql)

        # Log the generated SQL (debug level for cleaner output)
        self.logger.debug(f"Generated DuckDB delete+insert SQL for {table_name}:")
        self.logger.debug(f"DELETE: {converted_delete}")
        self.logger.debug(f"INSERT: {converted_insert}")

        try:
            # Execute delete
            self.adapter.utils.execute_query(converted_delete)
            self.logger.info(f"Executed delete for table: {table_name}")

            # Execute insert
            insert_query = f"INSERT INTO {table_name} {converted_insert}"
            self.adapter.utils.execute_query(insert_query)
            self.logger.info(f"Executed insert for table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error executing incremental delete+insert for {table_name}: {e}")
            raise

    def _generate_merge_sql(
        self, table_name: str, source_sql: str, unique_key: list[str], columns: list[str]
    ) -> str:
        """Generate DuckDB-specific MERGE SQL statement."""
        key_conditions = []
        for key in unique_key:
            key_conditions.append(f"target.{key} = source.{key}")

        key_condition = " AND ".join(key_conditions)

        # Generate UPDATE SET clause (exclude unique key columns)
        update_clauses = []
        for col in columns:
            if col not in unique_key:
                update_clauses.append(f"{col} = source.{col}")

        update_set = (
            ", ".join(update_clauses)
            if update_clauses
            else f"{unique_key[0]} = source.{unique_key[0]}"
        )

        # Generate INSERT clause
        insert_columns = ", ".join(columns)
        insert_values = ", ".join([f"source.{col}" for col in columns])

        merge_sql = f"""
        MERGE INTO {table_name} AS target
        USING ({source_sql}) AS source
        ON {key_condition}
        WHEN MATCHED THEN UPDATE SET {update_set}
        WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
        """

        return merge_sql.strip()
