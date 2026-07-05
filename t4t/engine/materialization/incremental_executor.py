"""
Incremental execution logic for different strategies.

This module handles the execution of incremental materializations including:
- Append-only strategy
- Merge strategy
- Delete+insert strategy
- Time-based filtering
- State management integration
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from t4t.adapters.base.core import DatabaseAdapter

import sqlglot
from sqlglot import expressions as exp

from t4t.typing.metadata import (
    IncrementalAppendConfig,
    IncrementalConfig,
    IncrementalDeleteInsertConfig,
    IncrementalMergeConfig,
    OnSchemaChange,
)

from ..model_state import ModelStateManager
from .auto_incremental_wrapper import AutoIncrementalWrapper

logger = logging.getLogger(__name__)


class IncrementalExecutor:
    """Handles execution of incremental materializations."""

    def __init__(self, state_manager: ModelStateManager) -> None:
        """Initialize the incremental executor."""
        self.state_manager = state_manager
        self._auto_incremental_wrapper: AutoIncrementalWrapper | None = None

    def _get_auto_incremental_wrapper(self, adapter: DatabaseAdapter) -> AutoIncrementalWrapper:
        """Get or create auto_incremental wrapper for the adapter."""
        if self._auto_incremental_wrapper is None:
            self._auto_incremental_wrapper = AutoIncrementalWrapper(adapter)
        return self._auto_incremental_wrapper

    def should_run_incremental(
        self, model_name: str, sql_query: str, config: IncrementalConfig
    ) -> bool:
        """Determine if a model should run incrementally or as a full load."""
        state = self.state_manager.get_model_state(model_name)

        if state is None:
            logger.info(f"No state exists for {model_name}, running full load")
            return False

        # Check if model definition changed
        current_sql_hash = self.state_manager.compute_sql_hash(sql_query)
        current_config_hash = self.state_manager.compute_config_hash(config)

        # Check if hashes match (debug logging removed for cleaner output)

        # Check if we have unknown hashes (from rebuilt state)
        if state.sql_hash == "unknown" or state.config_hash == "unknown":
            logger.info(f"Model state has unknown hashes for {model_name}, running full load")
            return False

        if state.sql_hash != current_sql_hash or state.config_hash != current_config_hash:
            logger.info(f"Model definition changed for {model_name}, running full load")
            return False

        # For append strategy, we don't need last_processed_value - we use time-based filtering
        strategy = config.get("strategy", "append")
        if strategy == "append":
            logger.info(f"Running incremental append for {model_name} with time-based filtering")
            return True

        # For merge and delete_insert strategies, check if we have a last processed value
        # unless start_value is "auto" or a variable reference (which uses external values)
        strategy_config = config.get(strategy, {})
        start_value = strategy_config.get("start_value")

        if start_value == "auto" or (
            start_value
            and (
                start_value.startswith("@")
                or (start_value.startswith("{{") and start_value.endswith("}}"))
            )
        ):
            logger.info(
                f"Running incremental {strategy} for {model_name} with {start_value} start_value"
            )
            return True

        if not state.last_processed_value:
            logger.info(f"No last processed value for {model_name}, running full load")
            return False

        logger.info(f"Running incremental load for {model_name}")
        return True

    def get_time_filter_condition(
        self,
        config: IncrementalAppendConfig | IncrementalMergeConfig | IncrementalDeleteInsertConfig,
        last_processed_value: str | None = None,
        variables: dict[str, Any] | None = None,
        table_name: str | None = None,
        table_exists: bool = True,
        adapter: DatabaseAdapter | None = None,
    ) -> str | None:
        """Generate time-based filter condition for incremental loading."""
        filter_column = config["filter_column"]
        start_value = config.get("start_value")
        destination_filter_column = config.get("destination_filter_column")

        # Determine which column to use for MAX() subquery in target table
        # Use destination_filter_column if provided, otherwise use filter_column
        target_column_for_max = (
            destination_filter_column if destination_filter_column else filter_column
        )

        # If we have a last processed value, use it (subsequent runs)
        # But first check if filter_column exists in target table (for dimension tables)
        if last_processed_value:
            if table_name and table_exists and adapter:
                try:
                    table_schema = adapter.get_table_columns(table_name)
                    if filter_column not in table_schema:
                        # Time column doesn't exist in target table (dimension table)
                        # Skip time filtering - dimension tables don't track time
                        logger.debug(
                            f"Time column {filter_column} not found in target table {table_name}. "
                            "Skipping time filter for dimension table."
                        )
                        return None
                except Exception:
                    # If we can't check, assume it exists and proceed
                    pass
            return f"{filter_column} > '{last_processed_value}'"

        # Handle different start_value values for first run
        if start_value == "auto":
            if table_name and table_exists and adapter:
                # Validate that target_column_for_max exists in target table
                try:
                    table_schema = adapter.get_table_columns(table_name)
                    if target_column_for_max not in table_schema:
                        # Raise error if destination_filter_column doesn't exist
                        if destination_filter_column:
                            raise ValueError(
                                f"destination_filter_column '{destination_filter_column}' not found in target table {table_name}. "
                                f"Available columns: {list(table_schema.keys())}"
                            )
                        # If using filter_column and it doesn't exist, skip time filtering (dimension table)
                        logger.debug(
                            f"Time column {filter_column} not found in target table {table_name}. "
                            "Skipping time filter (likely a dimension table)."
                        )
                        return None
                except ValueError:
                    # Re-raise validation errors
                    raise
                except Exception as e:
                    # If we can't check the schema, skip time filtering to be safe
                    logger.debug(
                        f"Could not check if time column {target_column_for_max} exists in {table_name}: {e}. "
                        "Skipping time filter."
                    )
                    return None

                # Column exists in target table, proceed with auto start_value
                # For 'auto', no COALESCE - just MAX()
                lookback = config.get("lookback")
                if lookback:
                    lookback_interval = self._parse_lookback(lookback)
                    if lookback_interval:
                        return f"{filter_column} > (SELECT MAX({target_column_for_max}) - INTERVAL {lookback_interval} FROM {table_name})"
                return f"{filter_column} > (SELECT MAX({target_column_for_max}) FROM {table_name})"
            else:
                # Table doesn't exist or table_name not provided
                # If start_value is 'auto' or missing, do full load (no filter)
                # Return None to indicate no time filter should be applied
                return None
        elif start_value == "CURRENT_DATE":
            return f"{filter_column} >= CURRENT_DATE"
        elif start_value:
            # start_value is a literal value (not 'auto')
            # Check if it's a variable reference
            if start_value.startswith("@") or (
                start_value.startswith("{{") and start_value.endswith("}}")
            ):
                # Resolve variable
                resolved_start_value = self._resolve_variable(start_value, variables)
                if resolved_start_value:
                    logger.info(f"Resolved variable {start_value} to {resolved_start_value}")
                    # On first run (table doesn't exist), use resolved value directly
                    if not table_exists:
                        return f"{filter_column} >= '{resolved_start_value}'"
                    # If table exists, use COALESCE with MAX() and resolved value as fallback
                    if table_name and adapter:
                        try:
                            table_schema = adapter.get_table_columns(table_name)
                            if target_column_for_max not in table_schema:
                                if destination_filter_column:
                                    raise ValueError(
                                        f"destination_filter_column '{destination_filter_column}' not found in target table {table_name}. "
                                        f"Available columns: {list(table_schema.keys())}"
                                    )
                                # If using filter_column and it doesn't exist, use resolved value directly
                                return f"{filter_column} >= '{resolved_start_value}'"
                        except ValueError:
                            raise
                        except Exception:
                            # If we can't check, use resolved value directly
                            return f"{filter_column} >= '{resolved_start_value}'"
                        # Use COALESCE with MAX() and resolved value as fallback
                        lookback = config.get("lookback")
                        if lookback:
                            lookback_interval = self._parse_lookback(lookback)
                            if lookback_interval:
                                return f"{filter_column} > (SELECT COALESCE(MAX({target_column_for_max}) - INTERVAL {lookback_interval}, '{resolved_start_value}') FROM {table_name})"
                        return f"{filter_column} > (SELECT COALESCE(MAX({target_column_for_max}), '{resolved_start_value}') FROM {table_name})"
                    return f"{filter_column} >= '{resolved_start_value}'"
                else:
                    # Fallback to default if variable not found
                    logger.warning(
                        f"Variable {start_value} not found, using default 7-day lookback"
                    )
                    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                    return f"{filter_column} >= '{seven_days_ago}'"
            else:
                # start_value is a literal value (e.g., '2024-01-01')
                # On first run (table doesn't exist), use it directly
                if not table_exists:
                    return f"{filter_column} >= '{start_value}'"
                # If table exists, use COALESCE with MAX() and start_value as fallback
                if table_name and adapter:
                    try:
                        table_schema = adapter.get_table_columns(table_name)
                        if target_column_for_max not in table_schema:
                            if destination_filter_column:
                                raise ValueError(
                                    f"destination_filter_column '{destination_filter_column}' not found in target table {table_name}. "
                                    f"Available columns: {list(table_schema.keys())}"
                                )
                            # If using filter_column and it doesn't exist, use start_value directly
                            return f"{filter_column} >= '{start_value}'"
                    except ValueError:
                        raise
                    except Exception:
                        # If we can't check, use start_value directly
                        return f"{filter_column} >= '{start_value}'"
                    # Use COALESCE with MAX() and start_value as fallback
                    lookback = config.get("lookback")
                    if lookback:
                        lookback_interval = self._parse_lookback(lookback)
                        if lookback_interval:
                            return f"{filter_column} > (SELECT COALESCE(MAX({target_column_for_max}) - INTERVAL {lookback_interval}, '{start_value}') FROM {table_name})"
                    return f"{filter_column} > (SELECT COALESCE(MAX({target_column_for_max}), '{start_value}') FROM {table_name})"
                return f"{filter_column} >= '{start_value}'"
        else:
            # No start_value specified
            # On first run (table doesn't exist), do full load (no filter)
            if not table_exists:
                return None
            # Default to last 7 days if no start_value specified and table exists
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            return f"{filter_column} >= '{seven_days_ago}'"

    def _apply_lookback_to_time_filter(
        self,
        time_filter: str,
        config: IncrementalAppendConfig | IncrementalMergeConfig | IncrementalDeleteInsertConfig,
    ) -> str:
        """Apply lookback to the time filter to handle late-arriving data."""
        lookback = config.get("lookback")
        if not lookback:
            return time_filter

        filter_column = config["filter_column"]
        lookback_interval = self._parse_lookback(lookback)
        if lookback_interval is None:
            logger.warning(f"Could not parse lookback: {lookback}")
            return time_filter

        # Extract the date from the time filter
        import re

        match = re.match(rf"{re.escape(filter_column)}\s*([><=]+)\s*'([^']+)'", time_filter)
        if not match:
            logger.warning(f"Could not parse time filter for lookback: {time_filter}")
            return time_filter

        operator = match.group(1)
        start_date = match.group(2)

        # Apply lookback to the start value.
        #
        # Note: lookback is intended for date/timestamp-like filters; we cast to TIMESTAMP here
        # to better match common warehouse semantics. If the literal cannot be cast by the
        # target dialect, the database will raise a query error.
        return f"{filter_column} {operator} (CAST('{start_date}' AS TIMESTAMP) - INTERVAL {lookback_interval})"

    def _parse_lookback(self, lookback: str) -> str | None:
        """Parse lookback string to SQL interval format."""
        lookback = lookback.lower().strip()

        # Define time unit mappings
        time_units = {
            "minute": ("minutes", 1),
            "hour": ("hours", 1),
            "day": ("days", 1),
            "week": ("days", 7),  # Convert weeks to days
            "month": ("days", 30),  # Approximate months as 30 days
        }

        # Find matching time unit and extract value
        for unit, (sql_unit, multiplier) in time_units.items():
            if unit in lookback:
                try:
                    value = int(lookback.split()[0])
                    converted_value = value * multiplier
                    return f"'{converted_value} {sql_unit}'"
                except (ValueError, IndexError):
                    continue

        return None

    def _resolve_variable(
        self, variable_ref: str, variables: dict[str, Any] | None = None
    ) -> str | None:
        """Resolve a variable reference to its value."""
        if not variables:
            return None

        # Handle @variable_name syntax
        if variable_ref.startswith("@"):
            var_name = variable_ref[1:]
            return variables.get(var_name)

        # Handle {{ variable_name }} syntax
        if variable_ref.startswith("{{") and variable_ref.endswith("}}"):
            var_name = variable_ref[2:-2].strip()
            return variables.get(var_name)

        return None

    def _resolve_variables_in_string(self, text: str, variables: dict[str, Any]) -> str:
        """Resolve all variable references in a string."""
        import re

        # Handle @variable syntax
        def replace_at_vars(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return str(variables.get(var_name, f"@{var_name}"))

        text = re.sub(r"@(\w+)", replace_at_vars, text)

        # Handle {{ variable }} syntax
        def replace_brace_vars(match: re.Match[str]) -> str:
            var_name = match.group(1).strip()
            return str(variables.get(var_name, f"{{{{ {var_name} }}}}"))

        text = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_brace_vars, text)

        return text

    def _add_date_casting(self, where_condition: str) -> str:
        """Add proper date casting for date comparisons in WHERE conditions."""
        import re

        # Pattern to match date comparisons like "column >= 2024-01-01" or "column >= '2024-01-01'"
        # This will match: column_name >= YYYY-MM-DD or column_name >= 'YYYY-MM-DD' etc.
        pattern = r"(\w+)\s*([><=]+)\s*(\'?)(\d{4}-\d{2}-\d{2})\3"

        def replace_date_comparison(match: re.Match[str]) -> str:
            column = match.group(1)
            operator = match.group(2)
            match.group(3)
            date_value = match.group(4)
            return f"{column} {operator} CAST('{date_value}' AS DATE)"

        return re.sub(pattern, replace_date_comparison, where_condition)

    def execute_append_strategy(
        self,
        model_name: str,
        sql_query: str,
        config: IncrementalAppendConfig,
        adapter: DatabaseAdapter,
        table_name: str,
        variables: dict[str, Any] | None = None,
        on_schema_change: OnSchemaChange | None = None,
        full_incremental_refresh_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Execute append-only incremental strategy."""
        # Default to "fail" if not specified
        if on_schema_change is None:
            on_schema_change = "fail"

        # Schema change handling will be done AFTER wrapping, so it can see the auto_incremental column

        # Get current state
        state = self.state_manager.get_model_state(model_name)
        last_processed_value = state.last_processed_value if state else None

        # Check if table exists
        table_exists = adapter.table_exists(table_name)

        # Get time filter condition
        time_filter = self.get_time_filter_condition(
            config, last_processed_value, variables, table_name, table_exists, adapter
        )

        # Apply lookback to the time filter if needed
        time_filter_with_lookback = self._apply_lookback_to_time_filter(time_filter, config)

        # Wrap query with auto_incremental logic if needed
        # But only if not already wrapped (may be wrapped by materialization_handler)
        wrapper = self._get_auto_incremental_wrapper(adapter)
        if metadata and wrapper.should_wrap(metadata) and not wrapper.is_already_wrapped(sql_query):
            # Wrap BEFORE applying time filter (wrapper handles time filter internally)
            sql_query = wrapper.wrap_query_for_append(
                sql_query=sql_query,
                table_name=table_name,
                metadata=metadata,
                time_filter=time_filter_with_lookback,
                table_exists=table_exists,
            )
            # Clear time_filter since it's now in wrapped query
            time_filter_with_lookback = None

        # Add the combined time filter to the query if not already wrapped
        if time_filter_with_lookback:
            filtered_sql = self._add_where_clause(sql_query, time_filter_with_lookback)
        else:
            filtered_sql = sql_query

        # Handle schema changes if table exists (OTS 0.2.1)
        # This runs AFTER wrapping so it can see the auto_incremental column
        if table_exists:
            from .schema_change_handler import SchemaChangeHandler
            from .schema_comparator import SchemaComparator

            handler = SchemaChangeHandler(adapter)
            comparator = SchemaComparator(adapter)

            query_schema = comparator.infer_query_schema(filtered_sql)
            table_schema = comparator.get_table_schema(table_name)

            handler.handle_schema_changes(
                table_name,
                query_schema,
                table_schema,
                on_schema_change,
                sql_query=filtered_sql,
                full_incremental_refresh_config=full_incremental_refresh_config,
                incremental_config={"strategy": "append", "append": config},
                metadata=metadata,
            )

        # If table doesn't exist, create it as a full load first (with wrapped query if auto_incremental)
        if not table_exists:
            logger.info(f"Table {table_name} doesn't exist yet, creating it as a full load")
            adapter.create_table(table_name, filtered_sql, metadata=None)
            # Update state after full load to enable incremental runs
            current_time = datetime.now(UTC).isoformat()
            self.state_manager.update_processed_value(model_name, current_time, strategy="append")
            return

        # Execute the filtered query and insert into target table
        if hasattr(adapter, "execute_incremental_append") and callable(
            adapter.execute_incremental_append
        ):
            adapter.execute_incremental_append(table_name, filtered_sql)
        else:
            # Fallback to regular table creation
            adapter.create_table(table_name, filtered_sql)

        # Update state with current max time value
        current_time = datetime.now(UTC).isoformat()
        self.state_manager.update_processed_value(model_name, current_time, strategy="append")

    def execute_merge_strategy(
        self,
        model_name: str,
        sql_query: str,
        config: IncrementalMergeConfig,
        adapter: DatabaseAdapter,
        table_name: str,
        variables: dict[str, Any] | None = None,
        on_schema_change: OnSchemaChange | None = None,
        full_incremental_refresh_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Execute merge incremental strategy."""
        # Default to "fail" if not specified
        if on_schema_change is None:
            on_schema_change = "fail"

        # Get current state
        state = self.state_manager.get_model_state(model_name)
        last_processed_value = state.last_processed_value if state else None

        # Check if table exists (required for merge)
        table_exists = adapter.table_exists(table_name)

        # Apply time filter
        # For dimension tables, filter_column might be in source, not target
        # So we need to check if filter_column exists in target before using it
        time_filter = self.get_time_filter_condition(
            config, last_processed_value, variables, table_name, table_exists, adapter
        )

        # Wrap query with auto_incremental logic if needed (BEFORE creating table or schema change detection)
        # This ensures the table is created with the auto_incremental column, and schema change handler sees the full schema
        # But only if not already wrapped (may be wrapped by materialization_handler)
        wrapper = self._get_auto_incremental_wrapper(adapter)
        if metadata and wrapper.should_wrap(metadata) and not wrapper.is_already_wrapped(sql_query):
            # Wrap BEFORE applying time filter (wrapper handles time filter internally)
            sql_query = wrapper.wrap_query_for_merge(
                sql_query=sql_query,
                table_name=table_name,
                metadata=metadata,
                unique_key=config["unique_key"],
                time_filter=time_filter,
                table_exists=table_exists,
            )
            # Clear time_filter since it's now in wrapped query
            time_filter = None

        if not table_exists:
            # For first run, create table as full load (with wrapped query if auto_incremental)
            logger.info(f"Table {table_name} does not exist. Creating it as a full load first.")
            adapter.create_table(table_name, sql_query, metadata)
            # Update state after full load to enable incremental runs
            current_time = datetime.now(UTC).isoformat()
            self.state_manager.update_processed_value(model_name, current_time, strategy="merge")
            return

        # Handle schema changes if table exists (OTS 0.2.1)
        # This runs AFTER wrapping so it can see the auto_incremental column
        if table_exists:
            from .schema_change_handler import SchemaChangeHandler
            from .schema_comparator import SchemaComparator

            handler = SchemaChangeHandler(adapter)
            comparator = SchemaComparator(adapter)

            query_schema = comparator.infer_query_schema(sql_query)
            table_schema = comparator.get_table_schema(table_name)

            handler.handle_schema_changes(
                table_name,
                query_schema,
                table_schema,
                on_schema_change,
                sql_query=sql_query,
                full_incremental_refresh_config=full_incremental_refresh_config,
                incremental_config={"strategy": "merge", "merge": config},
                metadata=metadata,
            )

        # Apply time filter if not already wrapped
        filtered_sql = self._add_where_clause(sql_query, time_filter) if time_filter else sql_query

        # Delegate to adapter for database-specific merge logic
        if hasattr(adapter, "execute_incremental_merge") and callable(
            adapter.execute_incremental_merge
        ):
            adapter.execute_incremental_merge(table_name, filtered_sql, config)
        else:
            # Fallback to regular execution
            logger.warning(
                f"Adapter {type(adapter).__name__} does not support incremental merge, falling back to regular execution"
            )
            adapter.execute_query(filtered_sql)

        # Update state
        current_time = datetime.now(UTC).isoformat()
        self.state_manager.update_processed_value(model_name, current_time, strategy="merge")

    def execute_delete_insert_strategy(
        self,
        model_name: str,
        sql_query: str,
        config: IncrementalDeleteInsertConfig,
        adapter: DatabaseAdapter,
        table_name: str,
        variables: dict[str, Any] | None = None,
        on_schema_change: OnSchemaChange | None = None,
        full_incremental_refresh_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Execute delete+insert incremental strategy."""
        # Default to "fail" if not specified
        if on_schema_change is None:
            on_schema_change = "fail"

        # Schema change handling will be done AFTER wrapping, so it can see the auto_incremental column

        # Get current state
        state = self.state_manager.get_model_state(model_name)
        last_processed_value = state.last_processed_value if state else None

        # Check if table exists
        table_exists = adapter.table_exists(table_name)

        # Apply time filter
        time_filter = self.get_time_filter_condition(
            config, last_processed_value, variables, table_name, table_exists, adapter
        )

        # Wrap query with auto_incremental logic if needed (BEFORE creating table or schema change detection)
        # This ensures the table is created with the auto_incremental column, and schema change handler sees the full schema
        # But only if not already wrapped (may be wrapped by materialization_handler)
        wrapper = self._get_auto_incremental_wrapper(adapter)
        unique_key = None
        if metadata and wrapper.should_wrap(metadata) and not wrapper.is_already_wrapped(sql_query):
            # For delete_insert, unique_key is optional (may not be in config)
            # Try to extract from metadata or config if available
            incremental_config = metadata.get("incremental", {})
            delete_insert_config = incremental_config.get("delete_insert", {})
            unique_key = delete_insert_config.get("unique_key")

            # Wrap BEFORE applying time filter (wrapper handles time filter internally)
            sql_query = wrapper.wrap_query_for_delete_insert(
                sql_query=sql_query,
                table_name=table_name,
                metadata=metadata,
                unique_key=unique_key,
                time_filter=time_filter,
                table_exists=table_exists,
            )
            # Clear time_filter since it's now in wrapped query
            time_filter = None

        # Apply time filter if not already wrapped
        filtered_sql = self._add_where_clause(sql_query, time_filter) if time_filter else sql_query

        # Handle schema changes if table exists (OTS 0.2.1)
        # This runs AFTER wrapping so it can see the auto_incremental column
        if table_exists:
            from .schema_change_handler import SchemaChangeHandler
            from .schema_comparator import SchemaComparator

            handler = SchemaChangeHandler(adapter)
            comparator = SchemaComparator(adapter)

            query_schema = comparator.infer_query_schema(filtered_sql)
            table_schema = comparator.get_table_schema(table_name)

            handler.handle_schema_changes(
                table_name,
                query_schema,
                table_schema,
                on_schema_change,
                sql_query=filtered_sql,
                full_incremental_refresh_config=full_incremental_refresh_config,
                incremental_config={"strategy": "delete_insert", "delete_insert": config},
                metadata=metadata,
            )

        # If table doesn't exist, create it as a full load first (with wrapped query if auto_incremental)
        if not table_exists:
            logger.info(f"Table {table_name} doesn't exist yet, creating it as a full load")
            adapter.create_table(table_name, filtered_sql, metadata=None)
            # Update state after full load to enable incremental runs
            current_time = datetime.now(UTC).isoformat()
            self.state_manager.update_processed_value(
                model_name, current_time, strategy="delete_insert"
            )
            return

        # Generate DELETE + INSERT statements
        where_condition = config["where_condition"]
        # Resolve variables in where_condition
        if variables:
            where_condition = self._resolve_variables_in_string(where_condition, variables)

        # Add proper date casting for date comparisons
        where_condition = self._add_date_casting(where_condition)

        # Use adapter's qualification method if available, otherwise construct manually
        if hasattr(adapter, "_qualify_object_name"):
            qualified_table_name = adapter._qualify_object_name(table_name)
        else:
            qualified_table_name = table_name

        delete_sql = f"DELETE FROM {qualified_table_name} WHERE {where_condition}"

        # Execute delete and insert
        if hasattr(adapter, "execute_incremental_delete_insert") and callable(
            adapter.execute_incremental_delete_insert
        ):
            adapter.execute_incremental_delete_insert(table_name, delete_sql, filtered_sql)
        else:
            # Fallback to regular execution
            adapter.execute_query(delete_sql)
            adapter.execute_query(filtered_sql)

        # Update state
        current_time = datetime.now(UTC).isoformat()
        self.state_manager.update_processed_value(
            model_name, current_time, strategy="delete_insert"
        )

    def _add_where_clause(self, sql_query: str, where_condition: str) -> str:
        """Add WHERE clause to SQL query."""
        try:
            parsed = sqlglot.parse_one(sql_query)

            # Find existing WHERE clause
            where_clause = None
            for node in parsed.walk():
                if isinstance(node, exp.Where):
                    where_clause = node
                    break

            # Parse the where condition as a proper SQL expression
            where_expr = sqlglot.parse_one(where_condition)

            if where_clause:
                # Add to existing WHERE clause
                existing_condition = where_clause.this
                new_condition = exp.and_(existing_condition, where_expr)
                where_clause.set("this", new_condition)
            else:
                # Add new WHERE clause
                where_clause = exp.Where(this=where_expr)
                # Find the main SELECT and add WHERE
                for node in parsed.walk():
                    if isinstance(node, exp.Select):
                        node.set("where", where_clause)
                        break

            return str(parsed)
        except Exception as e:
            logger.warning(f"Could not add WHERE clause: {e}")
            # Fallback: simple string concatenation
            return f"{sql_query} WHERE {where_condition}"
