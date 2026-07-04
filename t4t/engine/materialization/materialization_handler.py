"""Materialization handler for different materialization types."""

import logging
from typing import Any

from t4t.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class MaterializationHandler:
    """Handles different materialization types (table, view, incremental, etc.)."""

    def __init__(
        self, adapter: DatabaseAdapter, state_manager: Any, variables: dict[str, Any]
    ) -> None:
        """
        Initialize the materialization handler.

        Args:
            adapter: Database adapter instance
            state_manager: State manager instance
            variables: Variables dictionary for model execution
        """
        self.adapter = adapter
        self.state_manager = state_manager
        self.variables = variables

    def materialize(
        self,
        table_name: str,
        sql_query: str,
        materialization: str,
        metadata: dict[str, Any] | None = None,
        config: Any | None = None,
    ) -> None:
        """
        Execute the appropriate materialization based on type.

        Args:
            table_name: Name of the table/view
            sql_query: SQL query to execute
            materialization: Materialization type
            metadata: Optional metadata dictionary
            config: Optional adapter config
        """
        if materialization == "view":
            self.adapter.create_view(table_name, sql_query, metadata)
        elif materialization == "materialized_view":
            if hasattr(self.adapter, "create_materialized_view"):
                self.adapter.create_materialized_view(table_name, sql_query)
            else:
                logger.warning(
                    f"Materialized views not supported by {self.adapter.__class__.__name__}, creating table instead"
                )
                self.adapter.create_table(table_name, sql_query, metadata)
        elif materialization == "external_table":
            if hasattr(self.adapter, "create_external_table"):
                # External tables need additional configuration
                external_location = (
                    config.extra.get("external_location") if config and config.extra else None
                )
                if external_location:
                    self.adapter.create_external_table(table_name, sql_query, external_location)
                else:
                    logger.warning("External table location not configured, creating table instead")
                    self.adapter.create_table(table_name, sql_query, metadata)
            else:
                logger.warning(
                    f"External tables not supported by {self.adapter.__class__.__name__}, creating table instead"
                )
                self.adapter.create_table(table_name, sql_query, metadata)
        elif materialization == "incremental":
            self._execute_incremental_materialization(table_name, sql_query, metadata)
        else:  # Default to table for "table" or any other type
            self.adapter.create_table(table_name, sql_query, metadata)

    def _execute_incremental_materialization(
        self, table_name: str, sql_query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Execute incremental materialization using the universal state manager."""
        from datetime import UTC, datetime

        from .incremental_executor import IncrementalExecutor

        # Use the universal state manager
        executor = IncrementalExecutor(self.state_manager)

        try:
            # Extract incremental configuration
            incremental_config = metadata.get("incremental") if metadata else None

            # If incremental config is not found, check if the metadata itself contains incremental info
            if (
                not incremental_config
                and metadata
                and metadata.get("materialization") == "incremental"
            ):
                # This is a flat metadata structure from SQL files, need to restructure it
                strategy = metadata.get("strategy", "append")  # Default to append if not specified
                incremental_config = {
                    "strategy": strategy,
                    strategy: {
                        "filter_column": metadata.get("filter_column"),
                        # start_value is the new generic name; keep backward compatibility with start_date
                        "start_value": metadata.get("start_value", metadata.get("start_date")),
                        "lookback": metadata.get("lookback"),
                        "unique_key": metadata.get("unique_key"),
                        "where_condition": metadata.get("where_condition"),
                    },
                }
                # Remove None values
                incremental_config[strategy] = {
                    k: v for k, v in incremental_config[strategy].items() if v is not None
                }

            if not incremental_config:
                logger.error("Incremental materialization requires incremental configuration")
                # Fallback to table
                self.adapter.create_table(table_name, sql_query, metadata)
                return

            strategy = incremental_config.get("strategy")
            if not strategy:
                logger.error("Incremental strategy is required")
                # Fallback to table
                self.adapter.create_table(table_name, sql_query, metadata)
                return

            # Extract on_schema_change from incremental config (default: "fail")
            on_schema_change = incremental_config.get("on_schema_change", "fail")

            # Extract full_incremental_refresh config from metadata (transformation level, OTS 0.2.1)
            full_incremental_refresh_config = (
                metadata.get("full_incremental_refresh") if metadata else None
            )

            # Store original query for hash computation (before wrapping)
            # The SQL hash should be computed from the original query, not the wrapped one
            original_sql_query = sql_query

            # Wrap query with auto_incremental logic if needed (before schema change detection)
            # This ensures the wrapped query is used for schema comparison and execution
            from .auto_incremental_wrapper import AutoIncrementalWrapper

            wrapper = AutoIncrementalWrapper(self.adapter)
            table_exists = self.adapter.table_exists(table_name)
            if metadata and wrapper.should_wrap(metadata):
                strategy_type = incremental_config.get("strategy")
                if strategy_type == "merge":
                    merge_config = incremental_config.get("merge")
                    if merge_config:
                        sql_query = wrapper.wrap_query_for_merge(
                            sql_query=sql_query,
                            table_name=table_name,
                            metadata=metadata,
                            unique_key=merge_config.get("unique_key", []),
                            time_filter=None,  # No time filter yet - will be added later if needed
                            table_exists=table_exists,
                        )
                elif strategy_type == "append":
                    append_config = incremental_config.get("append")
                    if append_config:
                        sql_query = wrapper.wrap_query_for_append(
                            sql_query=sql_query,
                            table_name=table_name,
                            metadata=metadata,
                            time_filter=None,  # No time filter yet - will be added later if needed
                            table_exists=table_exists,
                        )
                elif strategy_type == "delete_insert":
                    delete_insert_config = incremental_config.get("delete_insert")
                    if delete_insert_config:
                        sql_query = wrapper.wrap_query_for_delete_insert(
                            sql_query=sql_query,
                            table_name=table_name,
                            metadata=metadata,
                            unique_key=delete_insert_config.get("unique_key"),
                            time_filter=None,  # No time filter yet - will be added later if needed
                            table_exists=table_exists,
                        )

            # Check for schema changes BEFORE deciding whether to run incrementally
            # If schema changes require full refresh, handle that first
            schema_change_requires_full_refresh = False
            if self.adapter.table_exists(table_name):
                from .schema_change_handler import SchemaChangeHandler
                from .schema_comparator import SchemaComparator

                handler = SchemaChangeHandler(self.adapter)
                comparator = SchemaComparator(self.adapter)

                query_schema = comparator.infer_query_schema(sql_query)
                table_schema = comparator.get_table_schema(table_name)
                differences = comparator.compare_schemas(query_schema, table_schema)

                if differences["has_changes"]:
                    # Check if on_schema_change requires full refresh
                    if on_schema_change in [
                        "full_refresh",
                        "full_incremental_refresh",
                        "recreate_empty",
                    ]:
                        schema_change_requires_full_refresh = True
                        logger.info(
                            f"Schema changes detected for {table_name} with on_schema_change='{on_schema_change}'. "
                            f"Handling schema change before incremental run."
                        )
                        handler.handle_schema_changes(
                            table_name,
                            query_schema,
                            table_schema,
                            on_schema_change,
                            sql_query=sql_query,
                            full_incremental_refresh_config=full_incremental_refresh_config,
                            incremental_config={
                                "strategy": strategy,
                                strategy: incremental_config.get(strategy),
                            },
                            metadata=metadata,
                        )
                    elif on_schema_change in ["append_new_columns", "sync_all_columns"]:
                        # These don't require full refresh, handle them later in strategy execution
                        pass
                    elif on_schema_change == "fail":
                        # Will be handled in strategy execution
                        pass
                    # ignore: no action needed

            # Check if we should run incrementally
            # Use ORIGINAL query for hash computation, not wrapped query
            # If schema change required full refresh, we should run as full load
            # Also, for merge/delete_insert strategies, table must exist to run incrementally
            strategy = incremental_config.get("strategy") if incremental_config else None
            table_exists_for_incremental = self.adapter.table_exists(table_name)

            # For merge and delete_insert, table must exist to run incrementally
            if strategy in ["merge", "delete_insert"] and not table_exists_for_incremental:
                logger.info(
                    f"Table {table_name} does not exist. Cannot run incremental {strategy}. "
                    "Running full load instead."
                )
                should_run_incremental = False
            else:
                should_run_incremental = (
                    not schema_change_requires_full_refresh
                    and executor.should_run_incremental(
                        table_name, original_sql_query, incremental_config
                    )
                )

            if not should_run_incremental:
                # Run as full load (create/replace table)
                self.adapter.create_table(table_name, sql_query, metadata)

                # Save state after full load to enable incremental runs
                # Compute hashes from the original query (not wrapped)
                sql_hash = self.state_manager.compute_sql_hash(original_sql_query)
                config_hash = self.state_manager.compute_config_hash(incremental_config)
                current_time = datetime.now(UTC).isoformat()
                strategy = incremental_config.get("strategy") if incremental_config else None

                # Save state with proper hashes so next run can detect if model changed
                self.state_manager.save_model_state(
                    model_name=table_name,
                    materialization="incremental",
                    sql_hash=sql_hash,
                    config_hash=config_hash,
                    last_processed_value=current_time,
                    strategy=strategy,
                )
            else:
                # Run incremental strategy
                # Note: strategy was already determined above
                if strategy == "append":
                    append_config = incremental_config.get("append")
                    if not append_config:
                        logger.error("Append strategy requires append configuration")
                        return
                    executor.execute_append_strategy(
                        table_name,
                        sql_query,
                        append_config,
                        self.adapter,
                        table_name,
                        self.variables,
                        on_schema_change=on_schema_change,
                        full_incremental_refresh_config=full_incremental_refresh_config,
                        metadata=metadata,
                    )

                elif strategy == "merge":
                    merge_config = incremental_config.get("merge")
                    if not merge_config:
                        logger.error("Merge strategy requires merge configuration")
                        return
                    executor.execute_merge_strategy(
                        table_name,
                        sql_query,
                        merge_config,
                        self.adapter,
                        table_name,
                        self.variables,
                        on_schema_change=on_schema_change,
                        full_incremental_refresh_config=full_incremental_refresh_config,
                        metadata=metadata,
                    )

                elif strategy == "delete_insert":
                    delete_insert_config = incremental_config.get("delete_insert")
                    if not delete_insert_config:
                        logger.error("Delete+insert strategy requires delete_insert configuration")
                        return
                    executor.execute_delete_insert_strategy(
                        table_name,
                        sql_query,
                        delete_insert_config,
                        self.adapter,
                        table_name,
                        self.variables,
                        on_schema_change=on_schema_change,
                        full_incremental_refresh_config=full_incremental_refresh_config,
                        metadata=metadata,
                    )

                else:
                    logger.error(f"Unknown incremental strategy: {strategy}")
                    return

            # State is already saved by individual strategy methods

        except Exception as e:
            logger.error(f"Error executing incremental materialization: {e}")
            # Fallback to table creation
            self.adapter.create_table(table_name, sql_query, metadata)
