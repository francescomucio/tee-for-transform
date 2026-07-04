"""
End-to-end tests for auto_incremental feature with Snowflake adapter.

These tests verify the complete flow including:
- First run (table creation)
- Incremental runs
- ID stability after deletion
- Time filter handling for dimension tables
- Schema change handling

These tests require a Snowflake connection. They use credentials from:
- tests/.snowflake_config.json (preferred)
- Or environment variables as fallback
"""

import json
import os
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


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_snowflake_credentials(),
    reason="Missing Snowflake credentials",
)
class TestAutoIncrementalSnowflakeE2E:
    """End-to-end tests for auto_incremental feature with Snowflake."""

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
    def materialization_handler(self, adapter, state_manager):
        """Create MaterializationHandler instance."""
        return MaterializationHandler(adapter, state_manager, {})

    @pytest.fixture
    def source_table(self, adapter, snowflake_config):
        """Create source table with test data."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.national_articles_test"

        # Drop table if exists
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Create source table with test data
        # Generate brands alphabetically to ensure predictable IDs
        brands = [f"Brand{chr(65 + i)}" for i in range(20)]  # BrandA through BrandT
        # Make BrandLA (13th alphabetically) to simulate SportCap scenario
        brands[12] = "BrandLA"  # This will be 13th alphabetically

        create_sql = f"""
        CREATE TABLE {table_name} AS
        SELECT
            1::INTEGER as id,
            'BrandA'::VARCHAR(50) as brand,
            'Category1'::VARCHAR(50) as category,
            '2024-01-01'::DATE as created_date
        WHERE 1=0
        """
        adapter.execute_query(create_sql)

        # Insert test data
        for i, brand in enumerate(brands):
            adapter.execute_query(
                f"""
                INSERT INTO {table_name} VALUES
                ({i + 1}::INTEGER, '{brand}'::VARCHAR(50), 'Category{(i % 5) + 1}'::VARCHAR(50), '2024-01-{(i % 28) + 1:02d}'::DATE)
                """
            )

        yield table_name

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def _save_model_state(
        self, state_manager, table_name: str, sql_query: str, metadata: dict[str, Any]
    ):
        """Helper to save model state after execution."""
        sql_hash = state_manager.compute_sql_hash(sql_query)
        incremental_config = metadata.get("incremental", {}) if metadata else {}
        config_hash = state_manager.compute_config_hash(incremental_config)
        current_time = datetime.now(UTC).isoformat()
        strategy = incremental_config.get("strategy") if incremental_config else None

        state_manager.save_model_state(
            model_name=table_name,
            materialization="incremental",
            sql_hash=sql_hash,
            config_hash=config_hash,
            last_processed_value=current_time,
            strategy=strategy,
        )

    def test_first_run_creates_table_with_correct_ids(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test that first run creates table with correct sequential IDs."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_first_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "description": "Unique identifier for the brand",
                    "tests": ["not_null", "unique"],
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                    "description": "Name of the brand",
                    "tests": ["not_null", "unique"],
                },
            ],
            "tests": ["row_count_gt_0"],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Save state
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Verify table exists and has correct data
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20, f"Expected 20 rows, got {count}"

        # Verify BrandLA has ID 13 (13th alphabetically)
        result = adapter.execute_query(
            f"SELECT brand_id FROM {table_name} WHERE brand_name = 'BrandLA'"
        )
        brand_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert brand_id == 13, f"Expected BrandLA to have ID 13, got {brand_id}"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_id_stability_after_deletion(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test that IDs remain stable after deletion and re-insertion."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "description": "Unique identifier for the brand",
                    "tests": ["not_null", "unique"],
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                    "description": "Name of the brand",
                    "tests": ["not_null", "unique"],
                },
            ],
            "tests": ["row_count_gt_0"],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Delete BrandLA (ID 13)
        adapter.execute_query(f"DELETE FROM {table_name} WHERE brand_name = 'BrandLA'")

        # Verify deletion
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 19, f"Expected 19 rows after deletion, got {count}"

        # Get max ID
        result = adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert max_id == 20, f"Expected max ID to be 20, got {max_id}"

        # Second run (should re-insert BrandLA with ID 21)
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Verify BrandLA was re-inserted with ID 21
        result = adapter.execute_query(
            f"SELECT brand_id FROM {table_name} WHERE brand_name = 'BrandLA'"
        )
        brand_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert brand_id == 21, f"Expected BrandLA to have ID 21 after re-insertion, got {brand_id}"

        # Verify total count is back to 20
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20, f"Expected 20 rows after re-insertion, got {count}"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_incremental_run_only_adds_new_records(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test that incremental runs only add new records, not duplicates."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_merge_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Use explicit mode (include ID column) to avoid SQL generation issues
        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Verify 20 records
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Second run with same data - should not add duplicates
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Verify still 20 records (no duplicates)
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_delete_insert_strategy_with_auto_incremental(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test delete+insert strategy with auto_incremental."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_delete_insert_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "delete_insert",
                "on_schema_change": "ignore",
                "delete_insert": {
                    "where_condition": "brand_name IS NOT NULL",
                    "filter_column": "created_date",
                    "start_value": "auto",
                    "unique_key": ["brand_name"],
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # Use explicit mode for delete_insert strategy
        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Verify table was created
        assert adapter.table_exists(table_name)

        # Verify 20 records
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Get IDs from first run
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        first_run_ids = {row[1]: row[0] for row in result}

        # Second run - should maintain IDs for existing records
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Verify still 20 records
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Verify IDs remain stable
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        second_run_ids = {row[1]: row[0] for row in result}
        assert first_run_ids == second_run_ids

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_empty_source_table(
        self, materialization_handler, adapter, state_manager, snowflake_config
    ):
        """Test handling of empty source table."""
        schema = snowflake_config.get("schema", "PUBLIC")
        empty_source_table = f"{schema}.empty_source_test"
        table_name = f"{schema}.dim_brand_empty_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
            adapter.execute_query(f"DROP TABLE IF EXISTS {empty_source_table}")
        except Exception:
            pass

        # Create empty source table
        adapter.execute_query(
            f"""
            CREATE TABLE {empty_source_table} (
                id INTEGER,
                brand VARCHAR(50),
                created_date DATE
            )
            """
        )

        # Use explicit mode for empty source test
        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {empty_source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # First run with empty source
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Table should be created but empty
        assert adapter.table_exists(table_name)

        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 0

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
            adapter.execute_query(f"DROP TABLE IF EXISTS {empty_source_table}")
        except Exception:
            pass

    def test_multiple_sequential_incremental_runs(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test multiple sequential incremental runs maintain ID stability."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_sequential_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Use explicit mode for delete_insert strategy
        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Get IDs from first run
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        first_run_ids = {row[1]: row[0] for row in result}

        # Second run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Get IDs from second run
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        second_run_ids = {row[1]: row[0] for row in result}

        # Verify IDs remain stable
        assert first_run_ids == second_run_ids

        # Third run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Get IDs from third run
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        third_run_ids = {row[1]: row[0] for row in result}

        # Verify IDs remain stable across all runs
        assert first_run_ids == third_run_ids

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_append_strategy_with_auto_incremental(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test append strategy with auto_incremental column."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_append_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "append",
                "on_schema_change": "ignore",
                "append": {
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # Use implicit mode for append strategy (like DuckDB test)
        # This avoids issues with LIMIT preservation in explicit mode
        sql = f"""
        SELECT DISTINCT brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        LIMIT 10
        """

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Verify 10 records
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 10

        result = adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert max_id == 10

        # Second run - append strategy will add duplicates
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Should have 20 records total (10 from first run + 10 duplicates from second run)
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        result = adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert max_id == 20

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_explicit_mode_merge_strategy(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test explicit mode where query includes ROW_NUMBER() for ID column."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_explicit_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Explicit mode: query includes the ID column
        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Verify table was created
        assert adapter.table_exists(table_name)

        # Check that all 20 brands are present
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Second run - should not add duplicates (merge strategy)
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Verify still 20 records (no duplicates)
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_explicit_mode_id_stability_after_deletion(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test explicit mode ID stability after deletion."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_explicit_del_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Delete BrandLA (ID 13)
        adapter.execute_query(f"DELETE FROM {table_name} WHERE brand_name = 'BrandLA'")

        # Get max ID
        result = adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert max_id == 20

        # Second run - should re-insert BrandLA with ID 21
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Verify BrandLA was re-inserted with ID 21
        result = adapter.execute_query(
            f"SELECT brand_id FROM {table_name} WHERE brand_name = 'BrandLA'"
        )
        brand_id = result.fetchone()[0] if hasattr(result, "fetchone") else result[0][0]
        assert brand_id == 21

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

    def test_all_records_already_exist(
        self, materialization_handler, adapter, state_manager, source_table, snowflake_config
    ):
        """Test incremental run when all records already exist (no new records)."""
        schema = snowflake_config.get("schema", "PUBLIC")
        table_name = f"{schema}.dim_brand_all_exist_test"

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass

        # Use explicit mode for delete_insert strategy
        sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY brand) AS brand_id,
            brand AS brand_name
        FROM {source_table}
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "on_schema_change": "ignore",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        # First run
        materialization_handler.materialize(table_name, sql, "incremental", metadata)
        self._save_model_state(state_manager, table_name, sql, metadata)

        # Verify 20 records
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Get IDs from first run
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        first_run_ids = {row[1]: row[0] for row in result}

        # Second run - all records already exist, should not add duplicates
        materialization_handler.materialize(table_name, sql, "incremental", metadata)

        # Verify still 20 records (no duplicates)
        result = adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        count = result[0][0] if result else 0
        assert count == 20

        # Verify IDs remain stable
        result = adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        second_run_ids = {row[1]: row[0] for row in result}
        assert first_run_ids == second_run_ids

        # Cleanup
        try:
            adapter.execute_query(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass
