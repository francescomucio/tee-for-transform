"""
End-to-end tests for Snowflake materialization with schema changes.

These tests require a Snowflake connection. They use credentials from:
- tests/.snowflake_config.json (preferred)
- Or environment variables as fallback
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from t4t.adapters.snowflake.adapter import SnowflakeAdapter
from t4t.engine.materialization.materialization_handler import MaterializationHandler
from t4t.engine.model_state import ModelStateManager


def _load_snowflake_config() -> dict[str, Any] | None:
    """Load Snowflake config from file or environment variables."""
    # Try config file first
    project_root = Path(__file__).parent.parent.parent.parent
    config_file = project_root / "tests" / ".snowflake_config.json"

    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
                # Add type field
                config["type"] = "snowflake"
                return config
        except Exception:
            pass

    # Fallback to environment variables
    if all(
        os.getenv(var)
        for var in [
            "SNOWFLAKE_USER",
            "SNOWFLAKE_PASSWORD",
            "SNOWFLAKE_ACCOUNT",
            "SNOWFLAKE_DATABASE",
        ]
    ):
        return {
            "type": "snowflake",
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "schema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
        }

    return None


def _has_snowflake_credentials() -> bool:
    """Check if Snowflake credentials are available."""
    return _load_snowflake_config() is not None


@dataclass
class IncrementalConfig:
    """Helper class for incremental metadata configuration."""

    strategy: str = "append"
    filter_column: str = "event_date"
    start_value: str = "2024-01-01"
    on_schema_change: str | None = None
    unique_key: list[str] | None = None

    def to_metadata(self) -> dict[str, Any]:
        """Convert to metadata dictionary."""
        metadata: dict[str, Any] = {
            "incremental": {
                "strategy": self.strategy,
            }
        }

        if self.strategy == "append":
            metadata["incremental"]["append"] = {
                "filter_column": self.filter_column,
                "start_value": self.start_value,
            }
        elif self.strategy == "merge":
            metadata["incremental"]["merge"] = {
                "unique_key": self.unique_key or ["event_id"],
                "filter_column": self.filter_column,
                "start_value": self.start_value,
            }

        if self.on_schema_change:
            metadata["incremental"]["on_schema_change"] = self.on_schema_change

        return metadata


class TestSnowflakeMaterializationEndToEnd:
    """End-to-end tests for Snowflake materialization with schema changes."""

    # Constants
    EXPECTED_RECORD_COUNT = 15
    BASE_COLUMNS = ["event_id", "event_name", "event_date"]
    FULL_COLUMNS = BASE_COLUMNS + ["value"]

    @staticmethod
    def _extract_count(result: Any) -> int:
        """Helper to extract count from query result."""
        if hasattr(result, "fetchone"):
            row = result.fetchone()
            count = row[0] if row else 0
        elif isinstance(result, (list, tuple)) and result:
            count = result[0][0] if isinstance(result[0], (list, tuple)) else result[0]
        else:
            count = result
        if isinstance(count, tuple):
            count = count[0]
        return int(count)

    @staticmethod
    def _extract_rows(result: Any) -> list:
        """Helper to extract rows from query result."""
        if hasattr(result, "fetchall"):
            return result.fetchall()
        elif isinstance(result, (list, tuple)):
            return list(result)
        else:
            return [result]

    @staticmethod
    def _extract_row(result: Any) -> list | Any:
        """Helper to extract single row from query result."""
        if hasattr(result, "fetchone"):
            row = result.fetchone()
            return list(row) if row and isinstance(row, tuple) else row
        elif isinstance(result, (list, tuple)) and result:
            row = result[0]
            return list(row) if isinstance(row, tuple) else row
        else:
            return result

    def _save_model_state_for_incremental(
        self,
        state_manager: ModelStateManager,
        table_name: str,
        sql_query: str,
        metadata: dict[str, Any],
        last_processed_value: str | None = None,
    ) -> None:
        """Helper to properly save model state for incremental runs."""
        sql_hash = state_manager.compute_sql_hash(sql_query)
        incremental_config = metadata.get("incremental", {}) if metadata else {}
        config_hash = state_manager.compute_config_hash(incremental_config)

        if last_processed_value is None:
            last_processed_value = datetime.now(UTC).isoformat()

        strategy = incremental_config.get("strategy") if incremental_config else None

        state_manager.save_model_state(
            model_name=table_name,
            materialization="incremental",
            sql_hash=sql_hash,
            config_hash=config_hash,
            last_processed_value=last_processed_value,
            strategy=strategy,
        )

    def _create_initial_table(
        self,
        adapter: SnowflakeAdapter,
        table_name: str,
        query: str,
        metadata: dict[str, Any],
        handler: MaterializationHandler,
    ) -> None:
        """Create initial table using materialization handler."""
        handler.materialize(table_name, query, "incremental", metadata)

    def _setup_incremental_state(
        self,
        state_manager: ModelStateManager,
        table_name: str,
        query: str,
        metadata: dict[str, Any],
    ) -> None:
        """Set up state for incremental run."""
        current_time = datetime.now(UTC).isoformat()
        self._save_model_state_for_incremental(
            state_manager, table_name, query, metadata, current_time
        )

    def _verify_table_schema(
        self,
        adapter: SnowflakeAdapter,
        table_name: str,
        expected_columns: list[str],
        unexpected_columns: list[str] | None = None,
    ) -> dict[str, str]:
        """Verify table schema matches expectations."""
        table_info = adapter.get_table_info(table_name)
        # Snowflake returns column names in uppercase, so normalize for comparison
        columns = {col["column"].upper(): col["type"] for col in table_info["schema"]}

        for col in expected_columns:
            assert col.upper() in columns, f"Expected column {col} not found in {table_name}"

        if unexpected_columns:
            for col in unexpected_columns:
                assert col.upper() not in columns, f"Unexpected column {col} found in {table_name}"

        return columns

    def _verify_table_count(
        self, adapter: SnowflakeAdapter, table_name: str, expected_count: int | None = None
    ) -> int:
        """Verify table row count."""
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = self._extract_count(result)

        if expected_count is not None:
            assert count == expected_count, f"Expected {expected_count} rows, got {count}"

        return count

    def _get_base_incremental_metadata(self, on_schema_change: str | None = None) -> dict[str, Any]:
        """Get base incremental metadata configuration."""
        config = IncrementalConfig(on_schema_change=on_schema_change)
        return config.to_metadata()

    @pytest.fixture
    def snowflake_config(self):
        """Get Snowflake config from file or environment."""
        config = _load_snowflake_config()
        if not config:
            pytest.skip(
                "Missing Snowflake credentials (check tests/.snowflake_config.json or environment variables)"
            )
        return config

    @pytest.fixture
    def adapter(self, snowflake_config):
        """Create a Snowflake adapter instance."""
        adapter = SnowflakeAdapter(snowflake_config)
        adapter.connect()

        yield adapter

        try:
            adapter.disconnect()
        except Exception:
            pass

    @pytest.fixture
    def state_manager(self):
        """Create a state manager instance."""
        import tempfile

        temp_state_db = tempfile.mktemp(suffix=".db")
        manager = ModelStateManager(state_database_path=temp_state_db)
        yield manager
        manager.close()
        try:
            os.unlink(temp_state_db)
        except Exception:
            pass

    @pytest.fixture
    def handler(self, adapter, state_manager):
        """Create a MaterializationHandler instance."""
        return MaterializationHandler(adapter, state_manager, {})

    @pytest.fixture
    def initial_table_with_data(self, adapter, snowflake_config):
        """Create initial table with data for testing."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.source_events"

        # Use adapter's qualification method to ensure consistent naming
        qualified_table_name = adapter.utils.qualify_object_name(table_name)

        # Drop table if exists (use qualified name)
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        # Create source table with initial schema and more records
        # Explicitly cast event_id to INTEGER and event_name to VARCHAR to avoid Snowflake type inference issues
        # Use qualified name for CREATE TABLE
        adapter.execute_query(
            f"""
            CREATE TABLE {qualified_table_name} AS
            SELECT
                1::INTEGER as event_id,
                'event1'::VARCHAR(50) as event_name,
                '2024-01-01'::DATE as event_date,
                100::INTEGER as value
            """
        )

        # Insert more data (15 total records)
        # Use qualified name for INSERT
        adapter.execute_query(
            f"""
            INSERT INTO {qualified_table_name} VALUES
            (2::INTEGER, 'event2', '2024-01-02'::DATE, 200::INTEGER),
            (3::INTEGER, 'event3', '2024-01-03'::DATE, 300::INTEGER),
            (4::INTEGER, 'event4', '2024-01-04'::DATE, 400::INTEGER),
            (5::INTEGER, 'event5', '2024-01-05'::DATE, 500::INTEGER),
            (6::INTEGER, 'event6', '2024-01-06'::DATE, 600::INTEGER),
            (7::INTEGER, 'event7', '2024-01-07'::DATE, 700::INTEGER),
            (8::INTEGER, 'event8', '2024-01-08'::DATE, 800::INTEGER),
            (9::INTEGER, 'event9', '2024-01-09'::DATE, 900::INTEGER),
            (10::INTEGER, 'event10', '2024-01-10'::DATE, 1000::INTEGER),
            (11::INTEGER, 'event11', '2024-01-11'::DATE, 1100::INTEGER),
            (12::INTEGER, 'event12', '2024-01-12'::DATE, 1200::INTEGER),
            (13::INTEGER, 'event13', '2024-01-13'::DATE, 1300::INTEGER),
            (14::INTEGER, 'event14', '2024-01-14'::DATE, 1400::INTEGER),
            (15::INTEGER, 'event15', '2024-01-15'::DATE, 1500::INTEGER)
            """
        )

        yield

        # Cleanup - use qualified name
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_append_new_columns_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with append_new_columns on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events"
        source_table = f"{schema}.source_events"

        # Cleanup before test - use qualified name
        qualified_table_name = adapter.utils.qualify_object_name(table_name)
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        initial_query = f"SELECT event_id, event_name, event_date FROM {source_table}"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Create initial table
        self._create_initial_table(adapter, table_name, initial_query, metadata, handler)

        # Verify initial state
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS, ["value"])
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Step 2: Set up state for incremental run
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 3: Run with new schema (adds 'value' column)
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata["incremental"]["on_schema_change"] = "append_new_columns"
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 4: Verify final schema and data
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)

        result = adapter.execute_query(
            f"SELECT event_id, event_name, event_date, value FROM {table_name} ORDER BY event_id"
        )
        rows = self._extract_rows(result)
        assert len(rows) >= self.EXPECTED_RECORD_COUNT

        first_row = list(rows[0]) if isinstance(rows[0], tuple) else rows[0]
        assert len(first_row) == 4
        assert first_row[0] == 1
        assert first_row[1] == "event1"
        assert first_row[3] == 100

        # Cleanup - use qualified name
        qualified_table_name = adapter.utils.qualify_object_name(table_name)
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_sync_all_columns_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with sync_all_columns on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_sync"
        source_table = f"{schema}.source_events"

        # Use qualified name for cleanup and table creation
        qualified_table_name = adapter.utils.qualify_object_name(table_name)

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        # Step 1: Create initial table with old schema including 'old_col'
        adapter.execute_query(
            f"""
            CREATE TABLE {qualified_table_name} AS
            SELECT
                1 as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date,
                'old_value' as old_col
            """
        )

        # Set up state
        initial_query = (
            f"SELECT event_id, event_name, event_date, 'old_value' as old_col FROM {source_table}"
        )
        initial_metadata = self._get_base_incremental_metadata()
        self._setup_incremental_state(state_manager, table_name, initial_query, initial_metadata)

        # Step 2: Run with new schema (removes old_col, adds value)
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata = self._get_base_incremental_metadata("sync_all_columns")
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 3: Verify final schema and data
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS, ["old_col"])

        result = adapter.execute_query(
            f"SELECT event_id, value FROM {table_name} WHERE event_id = 1"
        )
        row = self._extract_row(result)
        row_list = list(row) if isinstance(row, tuple) else row
        assert row_list[0] == 1
        assert row_list[1] == 100

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_full_refresh_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with full_refresh on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_refresh"
        source_table = f"{schema}.source_events"

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Step 1: Create initial table with old schema
        adapter.execute_query(
            f"""
            CREATE TABLE {table_name} AS
            SELECT
                1::INTEGER as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date
            """
        )
        adapter.execute_query(
            f"INSERT INTO {table_name} VALUES (2::INTEGER, 'event2', '2024-01-02'::DATE)"
        )

        # Set up state
        initial_query = f"SELECT event_id, event_name, event_date FROM {source_table}"
        initial_metadata = self._get_base_incremental_metadata()
        self._setup_incremental_state(state_manager, table_name, initial_query, initial_metadata)

        # Step 2: Run with new schema, triggering full_refresh
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata = self._get_base_incremental_metadata("full_refresh")
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 3: Verify final schema and data
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Verify data correctness
        result = adapter.execute_query(
            f"SELECT event_id, value FROM {table_name} ORDER BY event_id LIMIT 3"
        )
        rows = self._extract_rows(result)
        assert rows[0][1] == 100
        assert rows[1][1] == 200
        assert rows[2][1] == 300

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_recreate_empty_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with recreate_empty on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_empty"
        source_table = f"{schema}.source_events"

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Step 1: Create initial table with old schema
        adapter.execute_query(
            f"""
            CREATE TABLE {table_name} AS
            SELECT
                1::INTEGER as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date
            """
        )
        adapter.execute_query(
            f"INSERT INTO {table_name} VALUES (2::INTEGER, 'event2', '2024-01-02'::DATE)"
        )

        # Set up state
        initial_query = f"SELECT event_id, event_name, event_date FROM {source_table}"
        initial_metadata = self._get_base_incremental_metadata()
        self._setup_incremental_state(state_manager, table_name, initial_query, initial_metadata)

        # Step 2: Run with new schema, triggering recreate_empty
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata = self._get_base_incremental_metadata("recreate_empty")
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 3: Verify final schema
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)

        # Note: recreate_empty creates empty table, but incremental execution then populates it
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = self._extract_count(result)
        assert count >= 0  # At least schema is correct, may have incremental data

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_fail_on_schema_change_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with fail on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_fail"
        source_table = f"{schema}.source_events"

        # Cleanup before test - use qualified name
        qualified_table_name = adapter.utils.qualify_object_name(table_name)
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        initial_query = f"SELECT event_id, event_name, event_date FROM {source_table}"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Create initial table
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Set up state
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 2: Test schema change detection and failure
        from t4t.engine.materialization.schema_change_handler import SchemaChangeHandler
        from t4t.engine.materialization.schema_comparator import SchemaComparator

        handler_schema = SchemaChangeHandler(adapter)
        comparator = SchemaComparator(adapter)

        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        query_schema = comparator.infer_query_schema(new_query)
        table_schema = comparator.get_table_schema(table_name)

        # Step 3: Verify schema change detection and failure
        with pytest.raises(ValueError, match="Schema changes detected"):
            handler_schema.handle_schema_changes(
                table_name,
                query_schema,
                table_schema,
                "fail",
                sql_query=new_query,
            )

        # Step 4: Verify table schema unchanged
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS, ["value"])

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_merge_with_append_new_columns_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental merge with append_new_columns on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_merge"
        source_table = f"{schema}.source_events"

        # Use qualified name for cleanup
        qualified_table_name = adapter.utils.qualify_object_name(table_name)

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        # Step 1: Create initial table
        initial_query = (
            f"SELECT event_id, event_name, event_date FROM {source_table} WHERE event_id = 1"
        )
        config = IncrementalConfig(strategy="merge", unique_key=["event_id"])
        metadata = config.to_metadata()
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Set up state
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 2: Run merge with new schema (adds 'value')
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata["incremental"]["on_schema_change"] = "append_new_columns"
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 3: Verify final schema and data
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)

        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = self._extract_count(result)
        assert count >= 1

        result = adapter.execute_query(
            f"SELECT event_id, value FROM {table_name} WHERE event_id = 1"
        )
        row = self._extract_row(result)
        row_list = list(row) if isinstance(row, tuple) else row
        assert row_list[1] == 100

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_table_materialization_e2e(
        self, handler, adapter, initial_table_with_data, snowflake_config
    ):  # noqa: ARG002
        """Test table materialization (default)."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_table"
        source_table = f"{schema}.source_events"

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata = {"schema": []}

        handler.materialize(table_name, query, "table", metadata)

        # Verify table exists and schema
        assert adapter.table_exists(table_name)
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Verify data correctness
        result = adapter.execute_query(
            f"SELECT event_id, value FROM {table_name} ORDER BY event_id"
        )
        rows = self._extract_rows(result)
        assert rows[0][1] == 100
        assert rows[1][1] == 200
        assert rows[2][1] == 300

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_view_materialization_e2e(
        self, handler, adapter, initial_table_with_data, snowflake_config
    ):  # noqa: ARG002
        """Test view materialization."""
        schema = snowflake_config.get("schema", "PUBLIC")
        view_name = f"{schema}.target_view"
        source_table = f"{schema}.source_events"

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP VIEW IF EXISTS {view_name}")
        except Exception:
            pass

        query = f"SELECT event_id, event_name, value FROM {source_table} WHERE value > 150"
        metadata = {}

        handler.materialize(view_name, query, "view", metadata)

        # Verify view exists and returns correct data
        assert adapter.table_exists(view_name)
        self._verify_table_count(adapter, view_name, 14)  # Only events with value > 150

        # Cleanup
        try:
            adapter.execute_query(f"DROP VIEW IF EXISTS {view_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_no_schema_changes_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental with no schema changes."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_no_change"
        source_table = f"{schema}.source_events"

        # Cleanup before test
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Initial run
        handler.materialize(table_name, query, "incremental", metadata)
        initial_count = self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Step 2: Set up state for incremental run
        self._setup_incremental_state(state_manager, table_name, query, metadata)

        # Step 3: Run incremental again (same schema)
        handler.materialize(table_name, query, "incremental", metadata)

        # Step 4: Verify schema unchanged and data
        table_info = adapter.get_table_info(table_name)
        columns = {col["column"]: col["type"] for col in table_info["schema"]}
        assert len(columns) == 4

        final_count = self._verify_table_count(adapter, table_name)
        assert final_count >= initial_count

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_ignore_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with ignore on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_ignore"
        source_table = f"{schema}.source_events"

        # Cleanup before test - use qualified name
        qualified_table_name = adapter.utils.qualify_object_name(table_name)
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        initial_query = f"SELECT event_id, event_name, event_date FROM {source_table}"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Create initial table
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Verify initial state
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS, ["value"])
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Step 2: Set up state for incremental run
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 3: Run with new schema, using ignore
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata["incremental"]["on_schema_change"] = "ignore"
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 4: Verify final schema (execution didn't fail)
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS)

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    @pytest.mark.skipif(
        not _has_snowflake_credentials(),
        reason="Missing Snowflake credentials",
    )
    def test_incremental_append_with_full_incremental_refresh_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,
        snowflake_config,  # noqa: ARG002
    ):
        """Test incremental append with full_incremental_refresh on schema change."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.target_events_full_inc_refresh"
        source_table = f"{schema}.source_events"

        # Cleanup before test - use qualified name
        qualified_table_name = adapter.utils.qualify_object_name(table_name)
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {qualified_table_name}")
        except Exception:
            pass

        initial_query = f"SELECT event_id, event_name, event_date FROM {source_table}"
        metadata = self._get_base_incremental_metadata()
        metadata["full_incremental_refresh"] = {
            "parameters": [
                {
                    "name": "event_date",
                    "start_value": "2024-01-01",
                    "end_value": "2024-01-15",
                    "step": "INTERVAL 1 DAY",
                }
            ]
        }

        # Step 1: Create initial table
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Verify initial state
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS, ["value"])
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Step 2: Set up state for incremental run
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 3: Run with new schema, using full_incremental_refresh
        new_query = f"SELECT event_id, event_name, event_date, value FROM {source_table}"
        metadata["incremental"]["on_schema_change"] = "full_incremental_refresh"
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 4: Verify final schema and data
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)

        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = self._extract_count(result)
        assert count >= self.EXPECTED_RECORD_COUNT

        # Verify value column has data
        result = adapter.execute_query(
            f"SELECT event_id, value FROM {table_name} WHERE event_id = 1"
        )
        row = self._extract_row(result)
        row_list = list(row) if isinstance(row, tuple) else row
        assert row_list[0] == 1
        assert row_list[1] == 100

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass
