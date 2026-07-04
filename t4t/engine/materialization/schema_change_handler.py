"""
Handles schema changes based on on_schema_change configuration (OTS 0.2.1).

This module implements all 7 on_schema_change behaviors:
- fail: Fail on schema changes
- ignore: Ignore schema differences
- append_new_columns: Add new columns only
- sync_all_columns: Sync all columns (add/remove)
- full_refresh: Drop and recreate with full query
- full_incremental_refresh: Drop, recreate, then run incremental in chunks
- recreate_empty: Drop and recreate as empty table
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

import sqlglot
from sqlglot import expressions as exp

from t4t.adapters.base.core import DatabaseAdapter
from t4t.typing.metadata import OnSchemaChange

from .schema_comparator import SchemaComparator

logger = logging.getLogger(__name__)


class SchemaChangeHandler:
    """Handles schema changes for incremental materialization."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the schema change handler.

        Args:
            adapter: Database adapter instance
        """
        self.adapter = adapter

    def handle_schema_changes(
        self,
        table_name: str,
        query_schema: list[dict[str, Any]],
        table_schema: list[dict[str, Any]],
        on_schema_change: OnSchemaChange,
        sql_query: str | None = None,
        full_incremental_refresh_config: dict[str, Any] | None = None,
        incremental_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Handle schema changes based on on_schema_change setting.

        Args:
            table_name: Target table name
            query_schema: Schema from transformation output
            table_schema: Schema from existing table
            on_schema_change: Behavior setting
            sql_query: Original SQL query (needed for full_refresh and full_incremental_refresh)
            full_incremental_refresh_config: Configuration for full_incremental_refresh behavior
            incremental_config: Incremental configuration (needed for full_incremental_refresh)
        """
        comparator = SchemaComparator(self.adapter)
        differences = comparator.compare_schemas(query_schema, table_schema)

        if not differences["has_changes"]:
            logger.debug(f"No schema changes detected for {table_name}")
            return

        # Enrich new_columns with auto_incremental flag from metadata if available
        if metadata and "schema" in metadata:
            metadata_schema = metadata["schema"]
            metadata_col_map = {
                col["name"]: col for col in metadata_schema if isinstance(col, dict)
            }

            # Add auto_incremental flag to new columns if present in metadata
            for new_col in differences["new_columns"]:
                col_name = new_col.get("name")
                if col_name and col_name in metadata_col_map:
                    if metadata_col_map[col_name].get("auto_incremental"):
                        new_col["auto_incremental"] = True

        # Log detected changes
        logger.info(
            f"Schema changes detected for {table_name}: "
            f"new_columns={len(differences['new_columns'])}, "
            f"missing_columns={len(differences['missing_columns'])}, "
            f"type_mismatches={len(differences['type_mismatches'])}"
        )

        # Handle based on on_schema_change setting
        if on_schema_change == "fail":
            self._handle_fail(table_name, differences)
        elif on_schema_change == "ignore":
            self._handle_ignore(table_name)
        elif on_schema_change == "append_new_columns":
            self._handle_append_new_columns(table_name, differences["new_columns"], metadata)
        elif on_schema_change == "sync_all_columns":
            self._handle_sync_all_columns(
                table_name, differences["new_columns"], differences["missing_columns"], metadata
            )
        elif on_schema_change == "full_refresh":
            if not sql_query:
                raise ValueError("full_refresh requires sql_query but it was not provided")
            self._handle_full_refresh(table_name, sql_query)
        elif on_schema_change == "full_incremental_refresh":
            if not sql_query:
                raise ValueError(
                    "full_incremental_refresh requires sql_query but it was not provided"
                )
            if not full_incremental_refresh_config:
                raise ValueError(
                    "full_incremental_refresh requires full_incremental_refresh_config but it was not provided"
                )
            if not incremental_config:
                raise ValueError(
                    "full_incremental_refresh requires incremental_config but it was not provided"
                )
            self._handle_full_incremental_refresh(
                table_name, sql_query, full_incremental_refresh_config, incremental_config
            )
        elif on_schema_change == "recreate_empty":
            self._handle_recreate_empty(table_name, query_schema)
        else:
            raise ValueError(f"Unknown on_schema_change value: {on_schema_change}")

    def _handle_fail(self, table_name: str, differences: dict[str, Any]) -> None:
        """Fail the transformation with detailed error message."""
        error_parts = [f"Schema changes detected for {table_name} but on_schema_change='fail'."]

        if differences["new_columns"]:
            new_col_names = [col["name"] for col in differences["new_columns"]]
            error_parts.append(f"New columns: {new_col_names}")

        if differences["missing_columns"]:
            missing_col_names = [col["name"] for col in differences["missing_columns"]]
            error_parts.append(f"Missing columns: {missing_col_names}")

        if differences["type_mismatches"]:
            type_mismatch_info = [
                f"{m['name']}: {m['table_type']} -> {m['query_type']}"
                for m in differences["type_mismatches"]
            ]
            error_parts.append(f"Type mismatches: {type_mismatch_info}")

        raise ValueError(" ".join(error_parts))

    def _handle_ignore(self, table_name: str) -> None:
        """Ignore schema differences and proceed."""
        logger.info(f"Ignoring schema changes for {table_name}")

    def _handle_append_new_columns(
        self,
        table_name: str,
        new_columns: list[dict[str, Any]],
        _metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add new columns to existing table.

        Note: If any new column is marked as auto_incremental, this will fail
        because auto_incremental columns require a full refresh to assign IDs correctly.
        """
        if not new_columns:
            return

        # Check if any new column is auto_incremental
        auto_incremental_cols = [col for col in new_columns if col.get("auto_incremental", False)]
        if auto_incremental_cols:
            col_names = [col["name"] for col in auto_incremental_cols]
            raise ValueError(
                f"Cannot add auto_incremental columns {col_names} to existing table {table_name} "
                f"using 'append_new_columns'. AutoIncremental columns require a full refresh "
                f"(on_schema_change='full_refresh' or 'full_incremental_refresh') to assign IDs correctly."
            )

        logger.info(f"Adding {len(new_columns)} new columns to {table_name}")
        for column in new_columns:
            self._add_column(table_name, column)

    def _handle_sync_all_columns(
        self,
        table_name: str,
        new_columns: list[dict[str, Any]],
        missing_columns: list[dict[str, Any]],
        _metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Sync all columns: add new, remove missing.

        Note: If any new column is marked as auto_incremental, this will fail
        because auto_incremental columns require a full refresh to assign IDs correctly.
        """
        # Check if any new column is auto_incremental
        auto_incremental_cols = [col for col in new_columns if col.get("auto_incremental", False)]
        if auto_incremental_cols:
            col_names = [col["name"] for col in auto_incremental_cols]
            raise ValueError(
                f"Cannot add auto_incremental columns {col_names} to existing table {table_name} "
                f"using 'sync_all_columns'. AutoIncremental columns require a full refresh "
                f"(on_schema_change='full_refresh' or 'full_incremental_refresh') to assign IDs correctly."
            )

        # Add new columns
        if new_columns:
            logger.info(f"Adding {len(new_columns)} new columns to {table_name}")
            for column in new_columns:
                self._add_column(table_name, column)

        # Remove missing columns (with warning)
        if missing_columns:
            missing_col_names = [col["name"] for col in missing_columns]
            logger.warning(
                f"sync_all_columns will remove {len(missing_columns)} columns from {table_name}: {missing_col_names}"
            )
            for column in missing_columns:
                self._drop_column(table_name, column["name"])

    def _handle_full_refresh(self, table_name: str, sql_query: str) -> None:
        """Drop table and recreate with full query (no incremental filtering)."""
        logger.info(
            f"Schema change detected for {table_name} with on_schema_change='full_refresh'. "
            f"Dropping and recreating table with new schema."
        )

        # Drop existing table
        self.adapter.drop_table(table_name)
        logger.info(f"Dropped table {table_name} due to schema change")

        # Recreate with full query (no filtering)
        self.adapter.create_table(table_name, sql_query)
        logger.info(f"Recreated table {table_name} with new schema")

    def _handle_full_incremental_refresh(
        self,
        table_name: str,
        sql_query: str,
        full_incremental_refresh_config: dict[str, Any],
        incremental_config: dict[str, Any],
    ) -> None:
        """
        Drop table, recreate it, then run incremental strategy in chunks.

        Args:
            table_name: Target table name
            sql_query: Original SQL query
            full_incremental_refresh_config: Configuration with parameters array
            incremental_config: Incremental configuration for strategy execution
        """
        logger.info(
            f"Performing full incremental refresh for {table_name}: "
            "dropping, recreating, then running incremental in chunks"
        )

        # Drop existing table
        self.adapter.drop_table(table_name)

        # Recreate table (empty or with initial data)
        # For now, create empty table with correct schema
        # We'll populate it with incremental chunks
        query_schema = SchemaComparator(self.adapter).infer_query_schema(sql_query)
        self._create_empty_table_from_schema(table_name, query_schema)

        # Run incremental strategy in chunks
        parameters = full_incremental_refresh_config.get("parameters", [])
        if not parameters:
            raise ValueError(
                "full_incremental_refresh requires at least one parameter in parameters array"
            )

        # Extract source tables from SQL query
        source_tables = self._extract_source_tables(sql_query)
        if not source_tables:
            logger.warning(
                "Could not extract source tables from query for end_value evaluation. "
                "Proceeding with hardcoded end_values only."
            )

        # Evaluate end_values (expressions or hardcoded values)
        evaluated_end_values = {}
        for param in parameters:
            param_name = param["name"]
            end_value = param["end_value"]

            # Check if end_value is an expression (contains function calls or column references)
            if self._is_expression(end_value):
                # Evaluate expression against source tables
                evaluated = self._evaluate_end_value_expression(
                    end_value, source_tables, param_name
                )
                evaluated_end_values[param_name] = evaluated
            else:
                # Hardcoded value
                evaluated_end_values[param_name] = end_value

        # Execute incremental strategy in chunks
        strategy = incremental_config.get("strategy")
        if not strategy:
            raise ValueError("incremental_config must specify a strategy")

        # Import IncrementalExecutor here to avoid circular dependency
        from .incremental_executor import IncrementalExecutor

        # Create a temporary state manager for chunk execution
        # Note: We don't want to update state during chunking, so we'll use a dummy state manager
        class DummyStateManager:
            def get_model_state(self, model_name: str):  # noqa: ARG002
                return None

            def update_processed_value(self, model_name: str, value: str, strategy: str):  # noqa: ARG002
                pass  # Don't update state during chunking

        executor = IncrementalExecutor(DummyStateManager())

        # Execute chunks
        self._execute_incremental_chunks(
            table_name,
            sql_query,
            parameters,
            evaluated_end_values,
            incremental_config,
            strategy,
            executor,
        )

    def _handle_recreate_empty(self, table_name: str, query_schema: list[dict[str, Any]]) -> None:
        """Drop table and recreate as empty table."""
        logger.info(f"Recreating {table_name} as empty table")

        # Drop existing table
        self.adapter.drop_table(table_name)

        # Create empty table with correct schema
        self._create_empty_table_from_schema(table_name, query_schema)

    def _add_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Add a column to a table (database-specific)."""
        column_name = column["name"]
        column_type = column.get("type", "VARCHAR")

        # Use adapter method if available
        if hasattr(self.adapter, "add_column") and callable(self.adapter.add_column):
            self.adapter.add_column(table_name, column)
        else:
            # Fallback: generate and execute ALTER TABLE ADD COLUMN DDL
            self._generate_and_execute_add_column_ddl(table_name, column_name, column_type)

    def _drop_column(self, table_name: str, column_name: str) -> None:
        """Drop a column from a table (database-specific)."""
        # Use adapter method if available
        if hasattr(self.adapter, "drop_column") and callable(self.adapter.drop_column):
            self.adapter.drop_column(table_name, column_name)
        else:
            # Fallback: generate and execute ALTER TABLE DROP COLUMN DDL
            self._generate_and_execute_drop_column_ddl(table_name, column_name)

    def _generate_and_execute_add_column_ddl(
        self, table_name: str, column_name: str, column_type: str
    ) -> None:
        """Generate and execute ALTER TABLE ADD COLUMN DDL."""
        # Get qualified table name
        if hasattr(self.adapter, "utils") and hasattr(self.adapter.utils, "qualify_object_name"):
            qualified_table = self.adapter.utils.qualify_object_name(table_name)
        else:
            qualified_table = table_name

        # Generate DDL (database-specific syntax handled by adapter's SQL processing)
        ddl = f"ALTER TABLE {qualified_table} ADD COLUMN {column_name} {column_type}"

        try:
            self.adapter.execute_query(ddl)
            logger.info(f"Added column {column_name} to {table_name}")
        except Exception as e:
            logger.error(f"Failed to add column {column_name} to {table_name}: {e}")
            raise

    def _generate_and_execute_drop_column_ddl(self, table_name: str, column_name: str) -> None:
        """Generate and execute ALTER TABLE DROP COLUMN DDL."""
        # Get qualified table name
        if hasattr(self.adapter, "utils") and hasattr(self.adapter.utils, "qualify_object_name"):
            qualified_table = self.adapter.utils.qualify_object_name(table_name)
        else:
            qualified_table = table_name

        # Generate DDL (database-specific syntax handled by adapter's SQL processing)
        ddl = f"ALTER TABLE {qualified_table} DROP COLUMN {column_name}"

        try:
            self.adapter.execute_query(ddl)
            logger.info(f"Dropped column {column_name} from {table_name}")
        except Exception as e:
            logger.error(f"Failed to drop column {column_name} from {table_name}: {e}")
            raise

    def _create_empty_table_from_schema(
        self, table_name: str, schema: list[dict[str, Any]]
    ) -> None:
        """
        Create an empty table with the specified schema.

        Args:
            table_name: Name of the table to create
            schema: List of column definitions with "name" and "type"
        """
        if not schema:
            raise ValueError(f"Cannot create empty table {table_name}: schema is empty")

        # Build CREATE TABLE DDL
        column_defs = []
        for col in schema:
            col_name = col["name"]
            col_type = col.get("type", "VARCHAR")
            column_defs.append(f"{col_name} {col_type}")

        # Get qualified table name
        if hasattr(self.adapter, "utils") and hasattr(self.adapter.utils, "qualify_object_name"):
            qualified_table = self.adapter.utils.qualify_object_name(table_name)
        else:
            qualified_table = table_name

        create_ddl = f"CREATE TABLE {qualified_table} ({', '.join(column_defs)})"

        try:
            self.adapter.execute_query(create_ddl)
            logger.info(f"Created empty table {table_name} with schema")
        except Exception as e:
            logger.error(f"Failed to create empty table {table_name}: {e}")
            raise

    def _extract_source_tables(self, sql_query: str) -> list[str]:
        """
        Extract source table names from SQL query.

        Args:
            sql_query: SQL query string

        Returns:
            List of table names (may be qualified like "schema.table")
        """
        try:
            parsed = sqlglot.parse_one(sql_query)
            source_tables = []

            # Find all table references in FROM and JOIN clauses
            for table in parsed.find_all(exp.Table):
                # Get fully qualified name if available
                if table.db and table.this:
                    table_name = f"{table.db}.{table.this}"
                elif table.this:
                    table_name = str(table.this)
                else:
                    continue

                if table_name not in source_tables:
                    source_tables.append(table_name)

            return source_tables
        except Exception as e:
            logger.warning(f"Failed to extract source tables from query: {e}")
            return []

    def _is_expression(self, value: str) -> bool:
        """
        Check if end_value is an expression (not a hardcoded value).

        Expressions typically contain:
        - Function calls (max, min, etc.)
        - Column references
        - SQL operators

        Args:
            value: end_value string

        Returns:
            True if it looks like an expression, False if hardcoded value
        """
        if not value or not isinstance(value, str):
            return False

        # Check for function calls (e.g., "max(event_date)")
        if re.search(r"\w+\s*\(", value):
            return True

        # Check for column references (simple identifiers)
        # If it's just a date string or number, it's not an expression
        if re.match(r"^[\d\-\s:]+$", value):  # Date/number pattern
            return False

        # Check for SQL keywords or operators
        sql_keywords = ["max", "min", "count", "sum", "avg", "to_date", "date"]
        value_lower = value.lower()
        return any(keyword in value_lower for keyword in sql_keywords)

    def _evaluate_end_value_expression(
        self, expression: str, source_tables: list[str], param_name: str
    ) -> str:
        """
        Evaluate end_value expression against source tables.

        Args:
            expression: Expression to evaluate (e.g., "max(event_date)")
            source_tables: List of source table names
            param_name: Parameter name for context

        Returns:
            Evaluated value as string
        """
        if not source_tables:
            raise ValueError(
                f"Cannot evaluate expression '{expression}' for {param_name}: "
                "no source tables found in query"
            )

        # Build evaluation query
        # For expressions like "max(event_date)", we need to extract the column
        # and function, then evaluate against source tables
        try:
            # Parse the expression to extract function and column
            # Simple pattern: function(column) or just column
            match = re.match(r"(\w+)\s*\(\s*(\w+)\s*\)", expression)
            if match:
                func_name = match.group(1).lower()
                column_name = match.group(2)

                # Build query: SELECT max(column) FROM source_table
                # Use first source table (in real scenarios, might need to handle multiple)
                source_table = source_tables[0]

                eval_query = f"SELECT {func_name}({column_name}) as end_value FROM {source_table}"

                result = self.adapter.execute_query(eval_query)

                # Extract result
                if hasattr(result, "fetchone"):
                    row = result.fetchone()
                    end_value = str(row[0]) if row else None
                elif isinstance(result, (list, tuple)):
                    end_value = str(result[0][0]) if result and result[0] else None
                else:
                    end_value = str(result)

                if end_value:
                    logger.info(f"Evaluated {expression} for {param_name}: {end_value}")
                    return end_value
                else:
                    raise ValueError(f"Expression '{expression}' returned no value")
            else:
                # Not a function call - might be a column reference
                # Try: SELECT column FROM source_table LIMIT 1
                source_table = source_tables[0]
                eval_query = f"SELECT {expression} as end_value FROM {source_table} LIMIT 1"

                result = self.adapter.execute_query(eval_query)

                if hasattr(result, "fetchone"):
                    row = result.fetchone()
                    end_value = str(row[0]) if row else None
                elif isinstance(result, (list, tuple)):
                    end_value = str(result[0][0]) if result and result[0] else None
                else:
                    end_value = str(result)

                if end_value:
                    return end_value
                else:
                    raise ValueError(f"Expression '{expression}' returned no value")

        except Exception as e:
            logger.error(f"Failed to evaluate expression '{expression}': {e}")
            raise ValueError(
                f"Cannot evaluate end_value expression '{expression}' for {param_name}: {e}"
            ) from e

    def _execute_incremental_chunks(
        self,
        table_name: str,
        sql_query: str,
        parameters: list[dict[str, Any]],
        evaluated_end_values: dict[str, str],
        incremental_config: dict[str, Any],
        strategy: str,
        executor: Any,  # IncrementalExecutor
    ) -> None:
        """
        Execute incremental strategy in chunks.

        Args:
            table_name: Target table name
            sql_query: Original SQL query
            parameters: Parameter configurations
            evaluated_end_values: Evaluated end values for each parameter
            incremental_config: Incremental configuration
            strategy: Strategy name (append, merge, delete_insert)
            executor: IncrementalExecutor instance
        """
        # Initialize current values with start_values
        current_values = {param["name"]: param["start_value"] for param in parameters}

        # Get step (should be the same for all parameters, or handle per-parameter)
        # For now, assume single step for all (as per OTS spec)
        step = parameters[0]["step"] if parameters else "INTERVAL 1 DAY"

        chunk_count = 0
        max_chunks = 10000  # Safety limit to prevent infinite loops

        while chunk_count < max_chunks:
            # Check if we've reached end conditions for all parameters
            all_done = True
            for param in parameters:
                param_name = param["name"]
                current = current_values[param_name]
                end_value = evaluated_end_values.get(param_name)

                if not end_value:
                    logger.warning(f"No end_value for {param_name}, skipping chunk check")
                    continue

                # Compare current with end_value
                if not self._has_reached_end(current, end_value, step):
                    all_done = False
                    break

            if all_done:
                logger.info(
                    f"Completed incremental chunks for {table_name} after {chunk_count} chunks"
                )
                break

            # Replace parameter placeholders in SQL query with current values
            chunk_query = self._replace_parameters_in_query(sql_query, current_values)

            # Execute incremental strategy for this chunk
            logger.info(
                f"Executing chunk {chunk_count + 1} for {table_name} with parameters: {current_values}"
            )

            try:
                if strategy == "append":
                    append_config = incremental_config.get("append", {})
                    executor.execute_append_strategy(
                        table_name,
                        chunk_query,
                        append_config,
                        self.adapter,
                        table_name,
                        variables=current_values,
                        on_schema_change="ignore",  # Don't check schema changes during chunking
                    )
                elif strategy == "merge":
                    merge_config = incremental_config.get("merge", {})
                    executor.execute_merge_strategy(
                        table_name,
                        chunk_query,
                        merge_config,
                        self.adapter,
                        table_name,
                        variables=current_values,
                        on_schema_change="ignore",
                    )
                elif strategy == "delete_insert":
                    delete_insert_config = incremental_config.get("delete_insert", {})
                    executor.execute_delete_insert_strategy(
                        table_name,
                        chunk_query,
                        delete_insert_config,
                        self.adapter,
                        table_name,
                        variables=current_values,
                        on_schema_change="ignore",
                    )
                else:
                    raise ValueError(f"Unknown strategy: {strategy}")

                chunk_count += 1

                # Increment parameters for next chunk
                current_values = self._increment_parameters(current_values, parameters, step)

            except Exception as e:
                logger.error(f"Error executing chunk {chunk_count + 1}: {e}")
                raise

        if chunk_count >= max_chunks:
            logger.warning(
                f"Reached maximum chunk limit ({max_chunks}) for {table_name}. "
                "Stopping chunk execution."
            )

    def _has_reached_end(self, current: str, end_value: str, step: str) -> bool:  # noqa: ARG002
        """
        Check if current value has reached or exceeded end_value.

        Args:
            current: Current parameter value
            end_value: End condition value
            step: Step increment (for determining direction)

        Returns:
            True if end condition reached
        """
        # Try to parse as dates first
        try:
            current_date = datetime.fromisoformat(current.replace(" ", "T"))
            end_date = datetime.fromisoformat(end_value.replace(" ", "T"))
            return current_date >= end_date
        except (ValueError, AttributeError):
            pass

        # Try numeric comparison
        try:
            current_num = float(current)
            end_num = float(end_value)
            return current_num >= end_num
        except (ValueError, TypeError):
            pass

        # String comparison (fallback)
        return current >= end_value

    def _replace_parameters_in_query(self, sql_query: str, parameter_values: dict[str, str]) -> str:
        """
        Replace parameter placeholders in SQL query with actual values.

        Args:
            sql_query: SQL query with parameter placeholders (e.g., "@start_date")
            parameter_values: Dictionary of parameter names to values

        Returns:
            SQL query with parameters replaced
        """
        result_query = sql_query

        for param_name, param_value in parameter_values.items():
            # Replace @param_name
            result_query = re.sub(rf"@{re.escape(param_name)}\b", param_value, result_query)
            # Replace {{ param_name }}
            result_query = re.sub(
                rf"{{\{{\s*{re.escape(param_name)}\s*\}}\}}", param_value, result_query
            )

        return result_query

    def _increment_parameters(
        self,
        current_values: dict[str, str],
        parameters: list[dict[str, Any]],
        step: str,
    ) -> dict[str, str]:
        """
        Increment parameter values by step.

        Args:
            current_values: Current parameter values
            parameters: Parameter configurations
            step: Step increment (SQL interval or numeric)

        Returns:
            Updated parameter values
        """
        incremented = current_values.copy()

        for param in parameters:
            param_name = param["name"]
            current = current_values[param_name]

            # Try to increment as date
            try:
                current_date = datetime.fromisoformat(current.replace(" ", "T"))

                # Parse step as interval
                if "INTERVAL" in step.upper():
                    # Extract number and unit from "INTERVAL 1 DAY"
                    match = re.match(r"INTERVAL\s+(\d+)\s+(\w+)", step, re.IGNORECASE)
                    if match:
                        amount = int(match.group(1))
                        unit = match.group(2).lower()

                        # Map unit to timedelta
                        unit_map = {
                            "day": "days",
                            "days": "days",
                            "month": "days",  # Approximate: 30 days
                            "months": "days",
                            "year": "days",  # Approximate: 365 days
                            "years": "days",
                            "hour": "hours",
                            "hours": "hours",
                        }

                        if unit in unit_map:
                            if unit in ["month", "months"]:
                                delta = timedelta(days=amount * 30)
                            elif unit in ["year", "years"]:
                                delta = timedelta(days=amount * 365)
                            else:
                                delta = timedelta(**{unit_map[unit]: amount})

                            new_date = current_date + delta
                            incremented[param_name] = new_date.isoformat()
                            continue

                # If not an INTERVAL, try numeric step
                try:
                    step_num = float(step)
                    # For dates, add as days
                    new_date = current_date + timedelta(days=int(step_num))
                    incremented[param_name] = new_date.isoformat()
                    continue
                except (ValueError, TypeError):
                    pass

            except (ValueError, AttributeError):
                pass

            # Try numeric increment
            try:
                current_num = float(current)
                step_num = float(step)
                incremented[param_name] = str(current_num + step_num)
                continue
            except (ValueError, TypeError):
                pass

            # If we can't increment, log warning and keep current value
            logger.warning(
                f"Could not increment parameter {param_name} with step {step}. "
                f"Keeping current value: {current}"
            )

        return incremented
