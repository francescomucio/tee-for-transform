"""Incremental materialization strategies for Snowflake."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tee.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class IncrementalHandler:
    """Handles incremental materialization strategies for Snowflake."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the incremental handler.

        Args:
            adapter: SnowflakeAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    def execute_append(self, table_name: str, sql_query: str) -> None:
        """Execute incremental append into an existing table, or create if missing."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        cursor = self.adapter.connection.cursor()
        try:
            qualified_table = self.adapter.utils.qualify_object_name(table_name)
            if not self.adapter.table_exists(table_name):
                # First run: create table from filtered select
                create_sql = f"CREATE OR REPLACE TABLE {qualified_table} AS {sql_query}"
                cursor.execute(create_sql)
                self.logger.info(f"Created table (append first run): {table_name}")
                return
            # Subsequent runs: insert aligned columns
            columns = self.adapter.get_table_columns(table_name)
            if columns:
                column_list = ", ".join(columns)
                insert_sql = f"INSERT INTO {qualified_table} ({column_list}) SELECT {column_list} FROM ({sql_query})"
            else:
                # Fallback without explicit columns
                insert_sql = f"INSERT INTO {qualified_table} {sql_query}"
            cursor.execute(insert_sql)
            self.logger.info(f"Executed incremental append for table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error executing incremental append for {table_name}: {e}")
            raise
        finally:
            cursor.close()

    def execute_merge(self, table_name: str, source_sql: str, config: dict[str, Any]) -> None:
        """Execute incremental merge (upsert) with dedup and tuple ON for composite keys."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")
        unique_key = config.get("unique_key")
        if not unique_key:
            raise ValueError("unique_key is required for incremental merge")
        if isinstance(unique_key, str):
            unique_key = [unique_key]
        filter_column = config.get("filter_column")
        columns = self.adapter.get_table_columns(table_name)
        if not columns:
            # As a fallback, attempt executing using select * mapping
            self.logger.warning(
                "Could not resolve table columns; proceeding with '*' mapping may fail if order mismatches"
            )
            # We still build merge but it may not be correct; raise to be explicit
            raise ValueError("Cannot resolve table columns for merge")
        merge_sql = self._generate_merge_sql(
            table_name, source_sql, unique_key, columns, filter_column
        )
        cursor = self.adapter.connection.cursor()
        try:
            cursor.execute(merge_sql)
            self.logger.info("Executed incremental merge")
        except Exception as e:
            self.logger.error(f"Error executing incremental merge for {table_name}: {e}")
            raise
        finally:
            cursor.close()

    def execute_delete_insert(self, table_name: str, delete_sql: str, insert_sql: str) -> None:
        """Execute incremental delete+insert operation."""
        if not self.adapter.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        qualified_table = self.adapter._qualify_object_name(table_name)
        cursor = self.adapter.connection.cursor()
        try:
            # Execute delete
            cursor.execute(delete_sql)
            self.logger.info(f"Executed delete for table: {table_name}")

            # Execute insert
            insert_query = f"INSERT INTO {qualified_table} {insert_sql}"
            cursor.execute(insert_query)
            self.logger.info(f"Executed insert for table: {table_name}")
        except Exception as e:
            self.logger.error(f"Error executing incremental delete+insert for {table_name}: {e}")
            raise
        finally:
            cursor.close()

    def _generate_merge_sql(
        self,
        table_name: str,
        source_sql: str,
        unique_key: list[str],
        all_columns: list[str],
        filter_column: str | None,
    ) -> str:
        """Generate Snowflake MERGE SQL with tuple ON and optional dedup by latest filter_column."""
        qualified_table = self.adapter.utils.qualify_object_name(table_name)

        # Check if source_sql already contains CTEs (e.g., from auto_incremental wrapper)
        # The auto_incremental wrapper returns queries like: "WITH ... SELECT DISTINCT ..."
        # When we have existing CTEs, we need to handle them differently to avoid nested CTE syntax errors
        source_sql_upper = source_sql.strip().upper()
        has_existing_ctes = source_sql_upper.startswith("WITH ")

        if has_existing_ctes:
            # Source SQL already has CTEs from auto_incremental wrapper
            # In Snowflake, we can't nest CTEs like: WITH new AS (WITH old AS ... SELECT ...)
            # Instead, we'll use the wrapped query directly in the MERGE USING clause as a subquery
            # The auto_incremental wrapper already handles exclusion of existing records
            # So we can skip the CTE-based deduplication and use the query directly
            # Use the wrapped query as a subquery in the MERGE USING clause
            source_for_using = f"({source_sql})"
            using_alias = "src"
            # Don't create a CTE - use the subquery directly in MERGE
            dedup_cte = ""  # No CTE needed - use subquery directly
        else:
            # Source SQL is a simple SELECT - use normal CTE-based deduplication
            source_for_cte = source_sql

            # Deduplicate by unique key picking latest by filter_column if provided
            if filter_column:
                partition_keys = ", ".join(unique_key)
                dedup_cte = (
                    "WITH src AS (" + source_for_cte + "), dedup AS ("
                    f"SELECT * FROM src QUALIFY ROW_NUMBER() OVER (PARTITION BY ({partition_keys}) ORDER BY {filter_column} DESC) = 1)"
                )
                using_alias = "dedup"
            else:
                dedup_cte = "WITH dedup AS (" + source_for_cte + ")"
                using_alias = "dedup"
        tuple_left = ", ".join([f"t.{k}" for k in unique_key])
        tuple_right = ", ".join([f"s.{k}" for k in unique_key])
        # Update set excludes keys
        update_cols = [c for c in all_columns if c not in unique_key]
        update_set = (
            ", ".join([f"{c} = s.{c}" for c in update_cols])
            if update_cols
            else f"{unique_key[0]} = s.{unique_key[0]}"
        )
        insert_cols = ", ".join(all_columns)
        insert_vals = ", ".join([f"s.{c}" for c in all_columns])

        # Build MERGE statement
        if has_existing_ctes:
            # For queries with existing CTEs, use subquery directly in USING clause
            merge_sql = (
                f"MERGE INTO {qualified_table} t USING {source_for_using} s ON ({tuple_left}) = ({tuple_right}) \n"
                f"WHEN MATCHED THEN UPDATE SET {update_set} \n"
                f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
            )
        else:
            # For simple queries, use CTE-based approach
            merge_sql = (
                f"{dedup_cte} \n"
                f"MERGE INTO {qualified_table} t USING {using_alias} s ON ({tuple_left}) = ({tuple_right}) \n"
                f"WHEN MATCHED THEN UPDATE SET {update_set} \n"
                f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
            )
        return merge_sql
