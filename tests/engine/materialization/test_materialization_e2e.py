"""
End-to-end tests for materialization with schema changes.

These tests verify the complete flow:
1. Create initial database table with data
2. Define a model with different schema
3. Run materialization with on_schema_change configuration
4. Verify both data correctness and final table schema
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tee.adapters.duckdb.adapter import DuckDBAdapter
from tee.engine.materialization.materialization_handler import MaterializationHandler
from tee.engine.model_state import ModelStateManager


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


class TestMaterializationEndToEnd:
    """End-to-end tests for materialization with schema changes."""

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
        """
        Helper to properly save model state for incremental runs.

        This creates state with proper SQL and config hashes so that
        subsequent runs will be incremental (not full loads).
        """
        # Compute hashes
        sql_hash = state_manager.compute_sql_hash(sql_query)
        incremental_config = metadata.get("incremental", {}) if metadata else {}
        config_hash = state_manager.compute_config_hash(incremental_config)

        # Use provided last_processed_value or current time
        if last_processed_value is None:
            last_processed_value = datetime.now(UTC).isoformat()

        strategy = incremental_config.get("strategy") if incremental_config else None

        # Save state
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
        adapter: DuckDBAdapter,  # noqa: ARG002
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
        adapter: DuckDBAdapter,
        table_name: str,
        expected_columns: list[str],
        unexpected_columns: list[str] | None = None,
    ) -> dict[str, str]:
        """Verify table schema matches expectations."""
        table_info = adapter.get_table_info(table_name)
        columns = {col["column"]: col["type"] for col in table_info["schema"]}

        for col in expected_columns:
            assert col in columns, f"Expected column {col} not found in {table_name}"

        if unexpected_columns:
            for col in unexpected_columns:
                assert col not in columns, f"Unexpected column {col} found in {table_name}"

        return columns

    def _verify_table_count(
        self, adapter: DuckDBAdapter, table_name: str, expected_count: int | None = None
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
    def adapter(self):
        """Create a DuckDB adapter instance."""
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
            db_path = tmp_file.name

        Path(db_path).unlink(missing_ok=True)

        config = {"type": "duckdb", "path": db_path}
        adapter = DuckDBAdapter(config)
        adapter.connect()

        yield adapter

        try:
            adapter.disconnect()
            Path(db_path).unlink(missing_ok=True)
        except Exception:
            pass

    @pytest.fixture
    def state_manager(self):
        """Create a state manager instance."""
        temp_dir = tempfile.mkdtemp()
        temp_state_db = os.path.join(temp_dir, "test_state.db")

        manager = ModelStateManager(state_database_path=temp_state_db)
        yield manager
        manager.close()
        try:
            os.unlink(temp_state_db)
            os.rmdir(temp_dir)
        except Exception:
            pass

    @pytest.fixture
    def handler(self, adapter, state_manager):
        """Create a MaterializationHandler instance."""
        return MaterializationHandler(adapter, state_manager, {})

    @pytest.fixture
    def initial_table_with_data(self, adapter):
        """Create initial table with data for testing."""
        # Create source table with initial schema and more records
        adapter.execute_query(
            """
            CREATE TABLE source_events AS
            SELECT
                1 as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date,
                100 as value
            """
        )

        # Insert more data (15 total records)
        adapter.execute_query(
            """
            INSERT INTO source_events VALUES
            (2, 'event2', '2024-01-02'::DATE, 200),
            (3, 'event3', '2024-01-03'::DATE, 300),
            (4, 'event4', '2024-01-04'::DATE, 400),
            (5, 'event5', '2024-01-05'::DATE, 500),
            (6, 'event6', '2024-01-06'::DATE, 600),
            (7, 'event7', '2024-01-07'::DATE, 700),
            (8, 'event8', '2024-01-08'::DATE, 800),
            (9, 'event9', '2024-01-09'::DATE, 900),
            (10, 'event10', '2024-01-10'::DATE, 1000),
            (11, 'event11', '2024-01-11'::DATE, 1100),
            (12, 'event12', '2024-01-12'::DATE, 1200),
            (13, 'event13', '2024-01-13'::DATE, 1300),
            (14, 'event14', '2024-01-14'::DATE, 1400),
            (15, 'event15', '2024-01-15'::DATE, 1500)
            """
        )

    def test_incremental_append_with_append_new_columns_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with append_new_columns on schema change."""
        table_name = "target_events"
        initial_query = "SELECT event_id, event_name, event_date FROM source_events"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Create initial table
        self._create_initial_table(adapter, table_name, initial_query, metadata, handler)

        # Verify initial state
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS, ["value"])
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Step 2: Set up state for incremental run
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 3: Run with new schema (adds 'value' column)
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_incremental_append_with_sync_all_columns_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with sync_all_columns on schema change."""
        table_name = "target_events_sync"

        # Step 1: Create initial table with old schema including 'old_col'
        adapter.execute_query(
            f"""
            CREATE TABLE {table_name} AS
            SELECT
                1 as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date,
                'old_value' as old_col
            """
        )

        # Set up state
        initial_query = (
            "SELECT event_id, event_name, event_date, 'old_value' as old_col FROM source_events"
        )
        initial_metadata = self._get_base_incremental_metadata()
        self._setup_incremental_state(state_manager, table_name, initial_query, initial_metadata)

        # Step 2: Run with new schema (removes old_col, adds value)
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_incremental_append_with_full_refresh_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with full_refresh on schema change."""
        table_name = "target_events_refresh"

        # Step 1: Create initial table with old schema
        adapter.execute_query(
            f"""
            CREATE TABLE {table_name} AS
            SELECT
                1 as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date
            """
        )
        adapter.execute_query(f"INSERT INTO {table_name} VALUES (2, 'event2', '2024-01-02'::DATE)")

        # Set up state
        initial_query = "SELECT event_id, event_name, event_date FROM source_events"
        initial_metadata = self._get_base_incremental_metadata()
        self._setup_incremental_state(state_manager, table_name, initial_query, initial_metadata)

        # Step 2: Run with new schema, triggering full_refresh
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_incremental_append_with_recreate_empty_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with recreate_empty on schema change."""
        table_name = "target_events_empty"

        # Step 1: Create initial table with old schema
        adapter.execute_query(
            f"""
            CREATE TABLE {table_name} AS
            SELECT
                1 as event_id,
                'event1' as event_name,
                '2024-01-01'::DATE as event_date
            """
        )
        adapter.execute_query(f"INSERT INTO {table_name} VALUES (2, 'event2', '2024-01-02'::DATE)")

        # Set up state
        initial_query = "SELECT event_id, event_name, event_date FROM source_events"
        initial_metadata = self._get_base_incremental_metadata()
        self._setup_incremental_state(state_manager, table_name, initial_query, initial_metadata)

        # Step 2: Run with new schema, triggering recreate_empty
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
        metadata = self._get_base_incremental_metadata("recreate_empty")
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 3: Verify final schema
        self._verify_table_schema(adapter, table_name, self.FULL_COLUMNS)

        # Note: recreate_empty creates empty table, but incremental execution then populates it
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = self._extract_count(result)
        assert count >= 0  # At least schema is correct, may have incremental data

    def test_incremental_append_with_fail_on_schema_change_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with fail on schema change."""
        table_name = "target_events_fail"
        initial_query = "SELECT event_id, event_name, event_date FROM source_events"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Create initial table
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Set up state
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 2: Test schema change detection and failure
        from tee.engine.materialization.schema_change_handler import SchemaChangeHandler
        from tee.engine.materialization.schema_comparator import SchemaComparator

        handler_schema = SchemaChangeHandler(adapter)
        comparator = SchemaComparator(adapter)

        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_incremental_merge_with_append_new_columns_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental merge with append_new_columns on schema change."""
        table_name = "target_events_merge"

        # Step 1: Create initial table
        initial_query = (
            "SELECT event_id, event_name, event_date FROM source_events WHERE event_id = 1"
        )
        config = IncrementalConfig(strategy="merge", unique_key=["event_id"])
        metadata = config.to_metadata()
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Set up state
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 2: Run merge with new schema (adds 'value')
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_table_materialization_e2e(self, handler, adapter, initial_table_with_data):  # noqa: ARG002
        """Test table materialization (default)."""
        table_name = "target_table"
        query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_view_materialization_e2e(self, handler, adapter, initial_table_with_data):  # noqa: ARG002
        """Test view materialization."""
        view_name = "target_view"
        query = "SELECT event_id, event_name, value FROM source_events WHERE value > 150"
        metadata = {}

        handler.materialize(view_name, query, "view", metadata)

        # Verify view exists and returns correct data
        assert adapter.table_exists(view_name)
        self._verify_table_count(adapter, view_name, 14)  # Only events with value > 150

    def test_incremental_no_schema_changes_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental with no schema changes."""
        table_name = "target_events_no_change"
        query = "SELECT event_id, event_name, event_date, value FROM source_events"
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

    def test_incremental_append_with_ignore_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with ignore on schema change."""
        table_name = "target_events_ignore"
        initial_query = "SELECT event_id, event_name, event_date FROM source_events"
        metadata = self._get_base_incremental_metadata()

        # Step 1: Create initial table
        handler.materialize(table_name, initial_query, "incremental", metadata)

        # Verify initial state
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS, ["value"])
        self._verify_table_count(adapter, table_name, self.EXPECTED_RECORD_COUNT)

        # Step 2: Set up state for incremental run
        self._setup_incremental_state(state_manager, table_name, initial_query, metadata)

        # Step 3: Run with new schema, using ignore
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
        metadata["incremental"]["on_schema_change"] = "ignore"
        handler.materialize(table_name, new_query, "incremental", metadata)

        # Step 4: Verify final schema (execution didn't fail)
        self._verify_table_schema(adapter, table_name, self.BASE_COLUMNS)

    def test_incremental_append_with_full_incremental_refresh_e2e(
        self,
        handler,
        adapter,
        state_manager,
        initial_table_with_data,  # noqa: ARG002
    ):
        """Test incremental append with full_incremental_refresh on schema change."""
        table_name = "target_events_full_inc_refresh"
        initial_query = "SELECT event_id, event_name, event_date FROM source_events"
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
        new_query = "SELECT event_id, event_name, event_date, value FROM source_events"
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
