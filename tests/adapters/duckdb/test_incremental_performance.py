"""
Performance test cases for DuckDB incremental materialization.

These tests verify performance characteristics of incremental operations
with larger datasets. They are marked as slow tests and may be excluded
from regular test runs.
"""

import os
import tempfile
import time

import pytest

from tee.adapters.duckdb.adapter import DuckDBAdapter


@pytest.mark.slow
class TestDuckDBIncrementalPerformance:
    """Performance test cases for DuckDB incremental materialization."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file path (DuckDB will create the file)."""
        # Get a temporary file path without creating the file
        # DuckDB will create the database file when connecting
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
            temp_path = f.name
        # Delete the empty file so DuckDB can create a proper database file
        os.unlink(temp_path)
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def duckdb_config(self, temp_db_path):
        """Create DuckDB configuration."""
        return {"type": "duckdb", "path": temp_db_path, "schema": "test_schema"}

    @pytest.fixture
    def duckdb_adapter(self, duckdb_config):
        """Create DuckDB adapter instance."""
        adapter = DuckDBAdapter(duckdb_config)
        adapter.connect()
        yield adapter
        adapter.disconnect()

    def test_large_dataset_append_performance(self, duckdb_adapter):
        """Test append performance with large dataset."""
        # Create schema first
        duckdb_adapter.execute_query("CREATE SCHEMA IF NOT EXISTS test_schema")

        # Create source table with many rows
        create_sql = """
        CREATE TABLE test_schema.source_table AS
        SELECT
            row_number() OVER () as id,
            'User ' || row_number() OVER () as name,
            '2024-01-01'::timestamp + (row_number() OVER () * interval '1 hour') as created_at,
            '2024-01-01'::timestamp + (row_number() OVER () * interval '1 hour') as updated_at,
            CASE WHEN row_number() OVER () % 2 = 0 THEN 'active' ELSE 'inactive' END as status
        FROM generate_series(1, 1000)
        """
        duckdb_adapter.execute_query(create_sql)

        # Create target table
        target_sql = """
        CREATE TABLE test_schema.target_table AS
        SELECT * FROM test_schema.source_table WHERE 1=0
        """
        duckdb_adapter.execute_query(target_sql)

        # Execute incremental append
        source_sql = """
        SELECT id, name, created_at, updated_at, status
        FROM test_schema.source_table
        WHERE status = 'active'
        """

        start_time = time.time()
        duckdb_adapter.execute_incremental_append("test_schema.target_table", source_sql)
        end_time = time.time()

        # Verify data was inserted
        result = duckdb_adapter.execute_query("SELECT COUNT(*) FROM test_schema.target_table")
        count = result[0][0]
        assert count == 500  # Half should be active

        # Performance should be reasonable (less than 1 second for 1000 rows)
        execution_time = end_time - start_time
        assert execution_time < 1.0, f"Execution took {execution_time:.2f} seconds, expected < 1.0"

    def test_large_dataset_merge_performance(self, duckdb_adapter):
        """Test merge performance with large dataset."""
        # Create schema first
        duckdb_adapter.execute_query("CREATE SCHEMA IF NOT EXISTS test_schema")

        # Create source table with many rows
        create_sql = """
        CREATE TABLE test_schema.source_table AS
        SELECT
            row_number() OVER () as id,
            'User ' || row_number() OVER () as name,
            '2024-01-01'::timestamp + (row_number() OVER () * interval '1 hour') as created_at,
            '2024-01-01'::timestamp + (row_number() OVER () * interval '1 hour') as updated_at,
            CASE WHEN row_number() OVER () % 2 = 0 THEN 'active' ELSE 'inactive' END as status
        FROM generate_series(1, 1000)
        """
        duckdb_adapter.execute_query(create_sql)

        # Create target table with some active data (first 100 active records)
        # Active records have even IDs, so id <= 100 means IDs 2, 4, 6, ..., 100 (50 active records)
        target_sql = """
        CREATE TABLE test_schema.target_table AS
        SELECT * FROM test_schema.source_table WHERE id <= 100 AND status = 'active'
        """
        duckdb_adapter.execute_query(target_sql)

        # Execute incremental merge
        source_sql = """
        SELECT id, name, created_at, updated_at, status
        FROM test_schema.source_table
        WHERE status = 'active'
        """
        config = {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",
            "lookback": "1 hour",
        }

        start_time = time.time()
        duckdb_adapter.execute_incremental_merge("test_schema.target_table", source_sql, config)
        end_time = time.time()

        # Verify data was merged
        result = duckdb_adapter.execute_query("SELECT COUNT(*) FROM test_schema.target_table")
        count = result[0][0]
        assert count == 500  # All active records

        # Performance should be reasonable
        execution_time = end_time - start_time
        assert execution_time < 2.0, f"Execution took {execution_time:.2f} seconds, expected < 2.0"
