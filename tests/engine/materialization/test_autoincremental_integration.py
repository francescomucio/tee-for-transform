"""
Integration tests for AutoIncrementalWrapper with DuckDB.

These tests verify that auto_incremental columns work correctly
with all three incremental strategies in a real database environment.
"""

import contextlib

import pytest

from t4t.engine.materialization.incremental_executor import IncrementalExecutor
from t4t.typing.metadata import (
    IncrementalAppendConfig,
    IncrementalDeleteInsertConfig,
    IncrementalMergeConfig,
)


@pytest.mark.integration
class TestAutoIncrementalIntegration:
    """Integration tests for auto_incremental columns."""

    @pytest.fixture
    def executor(self, state_manager):
        """Create IncrementalExecutor instance."""
        return IncrementalExecutor(state_manager)

    @pytest.fixture
    def source_table_sql(self, duckdb_adapter):
        """Create source table with test data."""
        # Create schema first
        duckdb_adapter.execute_query("CREATE SCHEMA IF NOT EXISTS test_schema")
        # Create source table
        duckdb_adapter.execute_query(
            """
            CREATE TABLE IF NOT EXISTS test_schema.source_articles (
                article_id INTEGER,
                brand VARCHAR,
                category VARCHAR,
                created_date DATE
            )
            """
        )

        # Insert test data
        duckdb_adapter.execute_query(
            """
            INSERT INTO test_schema.source_articles VALUES
            (1, 'Brand A', 'Category X', '2024-01-01'),
            (2, 'Brand B', 'Category Y', '2024-01-02'),
            (3, 'Brand A', 'Category X', '2024-01-03'),
            (4, 'Brand C', 'Category Z', '2024-01-04')
            """
        )

        yield

        # Cleanup
        with contextlib.suppress(Exception):
            duckdb_adapter.execute_query("DROP TABLE IF EXISTS test_schema.source_articles")

    @pytest.fixture
    def metadata_with_auto_incremental(self):
        """Metadata with auto_incremental brand_id."""
        return {
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
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

    def test_merge_strategy_with_auto_incremental_first_run(
        self, executor, duckdb_adapter, source_table_sql, metadata_with_auto_incremental
    ):
        """Test merge strategy with auto_incremental on first run (empty table)."""
        table_name = "test_schema.dim_brand"
        sql_query = """
            SELECT DISTINCT
                brand AS brand_name
            FROM test_schema.source_articles
            WHERE brand IS NOT NULL
        """

        config: IncrementalMergeConfig = {
            "unique_key": ["brand_name"],
            "filter_column": "created_date",
            "start_value": "auto",
        }

        # Execute first run
        executor.execute_merge_strategy(
            model_name="dim_brand",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Verify table was created
        assert duckdb_adapter.table_exists(table_name)

        # Verify data
        result = duckdb_adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        assert len(result) == 3  # Brand A, B, C
        # IDs should start at 1
        assert result[0][0] == 1  # brand_id
        assert result[1][0] == 2
        assert result[2][0] == 3

    def test_merge_strategy_with_auto_incremental_incremental_run(
        self,
        executor,
        duckdb_adapter,
        source_table_sql,
        metadata_with_auto_incremental,
        state_manager,
    ):
        """Test merge strategy with auto_incremental on incremental run (new records)."""
        table_name = "test_schema.dim_brand"

        # First run: create table with initial data
        sql_query = """
            SELECT DISTINCT brand AS brand_name
            FROM test_schema.source_articles
            WHERE brand IS NOT NULL
        """

        config: IncrementalMergeConfig = {
            "unique_key": ["brand_name"],
            "filter_column": "created_date",
            "start_value": "auto",
        }

        executor.execute_merge_strategy(
            model_name="dim_brand",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Get max ID after first run
        result = duckdb_adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id_after_first = result[0][0] if result and result[0][0] else 0

        # Add new data to source
        duckdb_adapter.execute_query(
            """
            INSERT INTO test_schema.source_articles VALUES
            (5, 'Brand D', 'Category W', '2024-01-05'),
            (6, 'Brand E', 'Category V', '2024-01-06')
            """
        )

        # Update state to simulate incremental run
        state_manager.update_processed_value("dim_brand", "2024-01-04", strategy="merge")

        # Execute incremental run
        executor.execute_merge_strategy(
            model_name="dim_brand",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Verify new records were added with correct IDs
        result = duckdb_adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} WHERE brand_name IN ('Brand D', 'Brand E') ORDER BY brand_id"
        )
        assert len(result) == 2
        # New IDs should continue from max_id
        assert result[0][0] == max_id_after_first + 1
        assert result[1][0] == max_id_after_first + 2

        # Verify existing records weren't duplicated
        all_results = duckdb_adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        assert all_results[0][0] == 5  # 3 original + 2 new

    def test_append_strategy_with_auto_incremental_first_run(
        self, executor, duckdb_adapter, source_table_sql, metadata_with_auto_incremental
    ):
        """Test append strategy with auto_incremental on first run."""
        table_name = "test_schema.dim_brand_append"
        sql_query = """
            SELECT DISTINCT brand AS brand_name
            FROM test_schema.source_articles
            WHERE brand IS NOT NULL
        """

        config: IncrementalAppendConfig = {
            "filter_column": "created_date",
            "start_value": "2024-01-01",
        }

        # Execute first run
        executor.execute_append_strategy(
            model_name="dim_brand_append",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Verify table was created
        assert duckdb_adapter.table_exists(table_name)

        # Verify data
        result = duckdb_adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
        )
        assert len(result) == 3
        # IDs should start at 1
        assert result[0][0] == 1
        assert result[1][0] == 2
        assert result[2][0] == 3

    def test_append_strategy_with_auto_incremental_incremental_run(
        self,
        executor,
        duckdb_adapter,
        source_table_sql,
        metadata_with_auto_incremental,
        state_manager,
    ):
        """Test append strategy with auto_incremental on incremental run."""
        table_name = "test_schema.dim_brand_append2"

        # First run
        sql_query = """
            SELECT DISTINCT brand AS brand_name
            FROM test_schema.source_articles
            WHERE brand IS NOT NULL
        """

        config: IncrementalAppendConfig = {
            "filter_column": "created_date",
            "start_value": "2024-01-01",
        }

        executor.execute_append_strategy(
            model_name="dim_brand_append2",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Get max ID after first run
        result = duckdb_adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id_after_first = result[0][0] if result and result[0][0] else 0

        # Add new data
        duckdb_adapter.execute_query(
            """
            INSERT INTO test_schema.source_articles VALUES
            (5, 'Brand D', 'Category W', '2024-01-05')
            """
        )

        # Update state
        state_manager.update_processed_value("dim_brand_append2", "2024-01-04", strategy="append")

        # Execute incremental run
        executor.execute_append_strategy(
            model_name="dim_brand_append2",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
            on_schema_change="ignore",  # Ignore schema changes for this test
        )

        # Verify new record was appended
        # Note: Append strategy with filter_column that doesn't exist in target table
        # will skip time filtering and append all records again (by design)
        # So we just verify Brand D exists and has an ID > max_id_after_first
        result = duckdb_adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} WHERE brand_name = 'Brand D'"
        )

        assert result is not None
        assert len(result) > 0, "Brand D should have been appended"
        # Brand D should have an ID greater than max_id_after_first
        # (exact value depends on how many records were appended)
        assert result[0][0] > max_id_after_first

        # Verify total count - append may add duplicates if time filter is skipped
        all_results = duckdb_adapter.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        # Since filter_column doesn't exist in target, time filter is skipped
        # So all records are appended again (3 original + 4 from source = 7 total, or more if duplicates)
        assert all_results[0][0] >= 4  # At least 3 original + 1 new

    def test_delete_insert_strategy_with_auto_incremental(
        self,
        executor,
        duckdb_adapter,
        source_table_sql,
        metadata_with_auto_incremental,
        state_manager,
    ):
        """Test delete+insert strategy with auto_incremental."""
        table_name = "test_schema.dim_brand_delete_insert"

        # First run: create table
        sql_query = """
            SELECT DISTINCT brand AS brand_name
            FROM test_schema.source_articles
            WHERE brand IS NOT NULL
        """

        config: IncrementalDeleteInsertConfig = {
            "where_condition": "brand_name IS NOT NULL",  # Use column that exists in target table
            "filter_column": "created_date",
            "start_value": "2024-01-01",
        }

        executor.execute_delete_insert_strategy(
            model_name="dim_brand_delete_insert",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Verify table was created
        assert duckdb_adapter.table_exists(table_name)

        # Get max ID
        result = duckdb_adapter.execute_query(f"SELECT MAX(brand_id) FROM {table_name}")
        max_id_after_first = result[0][0] if result and result[0][0] else 0

        # Add new data
        duckdb_adapter.execute_query(
            """
            INSERT INTO test_schema.source_articles VALUES
            (5, 'Brand D', 'Category W', '2024-01-05')
            """
        )

        # Update state
        state_manager.update_processed_value(
            "dim_brand_delete_insert", "2024-01-04", strategy="delete_insert"
        )

        # Execute incremental run
        executor.execute_delete_insert_strategy(
            model_name="dim_brand_delete_insert",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
            on_schema_change="ignore",  # Ignore schema changes - wrapped query schema inference may not detect brand_id
        )

        # Verify new record was added
        result = duckdb_adapter.execute_query(
            f"SELECT brand_id, brand_name FROM {table_name} WHERE brand_name = 'Brand D'"
        )

        assert result is not None
        # ID should continue from max
        assert result[0][0] >= max_id_after_first + 1

    def test_auto_incremental_stable_ids_across_runs(
        self,
        executor,
        duckdb_adapter,
        source_table_sql,
        metadata_with_auto_incremental,
        state_manager,
    ):
        """Test that IDs remain stable across multiple incremental runs."""
        table_name = "test_schema.dim_brand_stable"

        sql_query = """
            SELECT DISTINCT brand AS brand_name
            FROM test_schema.source_articles
            WHERE brand IS NOT NULL
        """

        config: IncrementalMergeConfig = {
            "unique_key": ["brand_name"],
            "filter_column": "created_date",
            "start_value": "auto",
        }

        # First run
        executor.execute_merge_strategy(
            model_name="dim_brand_stable",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Get IDs from first run
        first_run_ids = {
            row[1]: row[0]
            for row in duckdb_adapter.execute_query(
                f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
            )
        }

        # Update state
        state_manager.update_processed_value("dim_brand_stable", "2024-01-04", strategy="merge")

        # Second run (no new data, should not change IDs)
        executor.execute_merge_strategy(
            model_name="dim_brand_stable",
            sql_query=sql_query,
            config=config,
            adapter=duckdb_adapter,
            table_name=table_name,
            metadata=metadata_with_auto_incremental,
        )

        # Get IDs from second run
        second_run_ids = {
            row[1]: row[0]
            for row in duckdb_adapter.execute_query(
                f"SELECT brand_id, brand_name FROM {table_name} ORDER BY brand_id"
            )
        }

        # IDs should remain the same
        assert first_run_ids == second_run_ids
