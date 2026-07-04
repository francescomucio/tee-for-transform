"""
Pytest configuration and shared fixtures for TEE tests.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from t4t.adapters.duckdb.adapter import DuckDBAdapter
from t4t.engine.model_state import ModelStateManager


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with data subdirectory for state database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        # Create data directory for state database
        data_dir = tmpdir_path / "data"
        data_dir.mkdir()
        yield tmpdir_path


@pytest.fixture
def temp_state_db_path():
    """Create a temporary state database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    # Delete the empty file - StateManager will create it as a proper DuckDB database
    if os.path.exists(temp_path):
        os.unlink(temp_path)
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def duckdb_config():
    """Create DuckDB configuration."""
    return {"type": "duckdb", "path": ":memory:", "schema": "test_schema"}


@pytest.fixture
def duckdb_adapter(duckdb_config):
    """Create DuckDB adapter instance."""
    adapter = DuckDBAdapter(duckdb_config)
    adapter.connect()
    yield adapter
    adapter.disconnect()


@pytest.fixture
def state_manager(temp_state_db_path):
    """Create state manager instance."""
    import os

    # Ensure parent directory exists
    parent_dir = os.path.dirname(temp_state_db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    manager = ModelStateManager(state_database_path=temp_state_db_path)
    yield manager
    manager.close()


@pytest.fixture
def sample_append_config() -> dict[str, Any]:
    """Sample append configuration."""
    return {"filter_column": "created_at", "start_value": "2024-01-01", "lookback": "7 days"}


@pytest.fixture
def sample_merge_config() -> dict[str, Any]:
    """Sample merge configuration."""
    return {
        "unique_key": ["id"],
        "filter_column": "updated_at",
        "start_value": "auto",
        "lookback": "3 hours",
    }


@pytest.fixture
def sample_delete_insert_config() -> dict[str, Any]:
    """Sample delete+insert configuration."""
    return {
        "where_condition": "updated_at >= @start_date",
        "filter_column": "updated_at",
        "start_value": "@start_date",
    }


@pytest.fixture
def sample_incremental_config() -> dict[str, Any]:
    """Sample incremental configuration."""
    return {
        "strategy": "append",
        "append": {
            "filter_column": "created_at",
            "start_value": "2024-01-01",
            "lookback": "7 days",
        },
    }


@pytest.fixture
def sample_table_sql():
    """Sample table creation SQL."""
    return """
    CREATE TABLE test_schema.source_table (
        id INTEGER,
        name VARCHAR,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        status VARCHAR
    )
    """


@pytest.fixture
def sample_data_sql():
    """Sample data insertion SQL."""
    return """
    INSERT INTO test_schema.source_table VALUES
    (1, 'Alice', '2024-01-01 10:00:00', '2024-01-01 10:00:00', 'active'),
    (2, 'Bob', '2024-01-02 11:00:00', '2024-01-02 11:00:00', 'active'),
    (3, 'Charlie', '2024-01-03 12:00:00', '2024-01-03 12:00:00', 'inactive'),
    (4, 'David', '2024-01-04 13:00:00', '2024-01-04 13:00:00', 'active'),
    (5, 'Eve', '2024-01-05 14:00:00', '2024-01-05 14:00:00', 'active')
    """


@pytest.fixture
def large_dataset_sql():
    """Large dataset SQL for performance testing."""
    return """
    CREATE TABLE test_schema.large_source_table AS
    SELECT
        row_number() OVER () as id,
        'User ' || row_number() OVER () as name,
        '2024-01-01'::timestamp + (row_number() OVER () * interval '1 hour') as created_at,
        '2024-01-01'::timestamp + (row_number() OVER () * interval '1 hour') as updated_at,
        CASE WHEN row_number() OVER () % 2 = 0 THEN 'active' ELSE 'inactive' END as status
    FROM generate_series(1, 1000)
    """


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line(
        "markers",
        'snowflake_e2e: live Snowflake E2E; exclude with -m "not snowflake_e2e" for fast local runs',
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    # Collect items to remove (can't modify list while iterating)
    items_to_remove = []
    for item in items:
        # Skip imported test decorator function (not a test)
        if item.name == "test_decorator" and "test_test_decorator.py" in str(item.fspath):
            items_to_remove.append(item)
            continue

        # Add unit marker to tests in engine/incremental/ (incremental executor tests)
        if "engine/incremental/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to tests in adapters/duckdb/test_incremental.py
        if "adapters/duckdb/test_incremental.py" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add slow marker to performance tests
        if (
            "performance" in item.name
            or "large_dataset" in item.name
            or "test_incremental_performance.py" in str(item.fspath)
        ):
            item.add_marker(pytest.mark.slow)

        # Live Snowflake E2E (network + warehouse): exclude from default fast local runs
        fp = str(item.fspath)
        if (
            ("adapters/snowflake/" in fp and "_e2e.py" in fp)
            or "test_function_execution_snowflake.py" in fp
        ):
            item.add_marker(pytest.mark.snowflake_e2e)

    # Remove items that shouldn't be collected as tests
    for item in items_to_remove:
        items.remove(item)
