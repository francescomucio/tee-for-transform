"""
Tests for MotherDuck (cloud DuckDB) adapter support.

To run these tests, provide MotherDuck credentials via:
1. Config file: tests/.motherduck_config.json (recommended)
2. Environment variables: MOTHERDUCK_TOKEN, MOTHERDUCK_DB_NAME, MOTHERDUCK_SCHEMA

Example:
    pytest tests/adapters/duckdb/test_motherduck.py -v

Note: These tests are marked as integration tests and require a valid MotherDuck token.
The config file is gitignored and will not be committed to the repository.
"""

import json
import os
from contextlib import suppress
from pathlib import Path

import pytest

try:
    import duckdb
except ImportError:
    duckdb = None

from t4t.adapters.duckdb.adapter import DuckDBAdapter


def _get_config_file_path() -> Path:
    """Get the path to the MotherDuck config file."""
    test_file_dir = Path(__file__).parent  # tests/adapters/duckdb/
    project_root = test_file_dir.parent.parent.parent  # t4t-for-transform/
    return project_root / "tests" / ".motherduck_config.json"


def _load_motherduck_config() -> dict:
    """Load MotherDuck configuration from file or environment variables."""
    config_file = _get_config_file_path()

    if config_file.exists():
        try:
            with open(config_file) as f:
                file_config = json.load(f)
            return {
                "type": "duckdb",
                "path": f"md:{file_config.get('database', 'test_db')}",
                "schema": file_config.get("schema", "test_schema"),
                "extra": {"motherduck_token": file_config.get("token")}
                if file_config.get("token")
                else None,
            }
        except Exception as e:
            pytest.skip(f"Could not load MotherDuck config from {config_file}: {e}")

    # Fall back to environment variables
    return {
        "type": "duckdb",
        "path": f"md:{os.getenv('MOTHERDUCK_DB_NAME', 'test_db')}",
        "schema": os.getenv("MOTHERDUCK_SCHEMA", "test_schema"),
    }


def _get_motherduck_token(config: dict) -> str | None:
    """Extract MotherDuck token from config or environment."""
    if config.get("extra") and config["extra"].get("motherduck_token"):
        return config["extra"]["motherduck_token"]
    return os.getenv("MOTHERDUCK_TOKEN")


@pytest.mark.integration
class TestMotherDuckConnection:
    """Test MotherDuck connection functionality."""

    @pytest.fixture
    def motherduck_config(self):
        """Get MotherDuck configuration from local config file or environment variables."""
        return _load_motherduck_config()

    @pytest.fixture
    def motherduck_adapter(self, motherduck_config):
        """Create MotherDuck adapter instance."""
        token = _get_motherduck_token(motherduck_config)
        if not token:
            pytest.skip(
                "MotherDuck token not available. "
                "Set it in tests/.motherduck_config.json or export MOTHERDUCK_TOKEN='your_token'"
            )

        # Pre-install extension if possible (adapter will also try)
        if duckdb is not None:
            with suppress(Exception):
                conn = duckdb.connect(":memory:")
                with suppress(Exception):
                    conn.execute("INSTALL motherduck;")
                conn.close()

        adapter = DuckDBAdapter(motherduck_config)
        try:
            adapter.connect()
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["motherduck", "extension", "init", "load"]):
                full_error = str(e)
                if hasattr(e, "__cause__") and e.__cause__:
                    full_error += f"\nCaused by: {e.__cause__}"
                pytest.skip(
                    f"MotherDuck connection failed ({type(e).__name__}):\n{full_error}\n\n"
                    "The adapter attempted to install the extension and connect. "
                    "Check your MOTHERDUCK_TOKEN, network connectivity, and permissions."
                )
            raise
        yield adapter
        adapter.disconnect()

    def test_motherduck_connection(self, motherduck_adapter):
        """Test basic MotherDuck connection."""
        result = motherduck_adapter.execute_query("SELECT 1 as test_value")
        assert result == [(1,)]
        assert motherduck_adapter.connection is not None

    def test_motherduck_table_creation(self, motherduck_adapter):
        """Test creating a table in MotherDuck."""
        table_name = "test_motherduck_table"

        # Create table
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER,
                name VARCHAR
            )
        """
        motherduck_adapter.execute_query(create_sql)

        # Verify table exists
        assert motherduck_adapter.table_exists(table_name)

        # Clean up
        motherduck_adapter.drop_table(table_name)

    def test_motherduck_token_from_env(self):
        """Test that token is read from environment variable."""
        token = os.getenv("MOTHERDUCK_TOKEN")
        if not token:
            pytest.skip("MOTHERDUCK_TOKEN not set")

        adapter = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        connection_string = adapter._build_motherduck_connection_string("md:test_db")

        assert "motherduck_token=" in connection_string
        assert token in connection_string

    def test_motherduck_token_from_config_extra(self):
        """Test that token can be provided via config extra."""
        test_token = "test_token_12345"
        original_token = os.environ.pop("MOTHERDUCK_TOKEN", None)

        try:
            config = {
                "type": "duckdb",
                "path": "md:test_db",
                "extra": {"motherduck_token": test_token},
            }
            adapter = DuckDBAdapter(config)
            connection_string = adapter._build_motherduck_connection_string("md:test_db")

            assert "motherduck_token=" in connection_string
            assert test_token in connection_string
        finally:
            if original_token is not None:
                os.environ["MOTHERDUCK_TOKEN"] = original_token

    def test_motherduck_token_in_path(self):
        """Test that token already in path is preserved."""
        test_token = "test_token_12345"
        db_path = f"md:test_db?motherduck_token={test_token}"

        adapter = DuckDBAdapter({"type": "duckdb", "path": db_path})
        connection_string = adapter._build_motherduck_connection_string(db_path)

        assert connection_string == db_path
        assert test_token in connection_string

    def test_motherduck_connection_string_variants(self):
        """Test that both 'md:' and 'motherduck:' prefixes work."""
        adapter_md = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        adapter_motherduck = DuckDBAdapter({"type": "duckdb", "path": "motherduck:test_db"})

        connection_md = adapter_md._build_motherduck_connection_string("md:test_db")
        connection_motherduck = adapter_motherduck._build_motherduck_connection_string(
            "motherduck:test_db"
        )

        assert connection_md.startswith("md:")
        assert connection_motherduck.startswith("motherduck:")


class TestMotherDuckPathExtraction:
    """Test MotherDuck path extraction helper methods."""

    def test_extract_motherduck_path_direct_md(self):
        """Test extracting MotherDuck path from direct md: path."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        result = adapter._extract_motherduck_path("md:test_db")
        assert result == "md:test_db"

    def test_extract_motherduck_path_direct_motherduck(self):
        """Test extracting MotherDuck path from direct motherduck: path."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "motherduck:test_db"})
        result = adapter._extract_motherduck_path("motherduck:test_db")
        assert result == "motherduck:test_db"

    def test_extract_motherduck_path_resolved_absolute(self):
        """Test extracting MotherDuck path from resolved absolute path."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        resolved_path = "/home/user/project/md:test_db"
        result = adapter._extract_motherduck_path(resolved_path)
        assert result == "md:test_db"

    def test_extract_motherduck_path_resolved_with_query(self):
        """Test extracting MotherDuck path from resolved path with query parameters."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        resolved_path = "/home/user/project/md:test_db?motherduck_token=abc123"
        result = adapter._extract_motherduck_path(resolved_path)
        assert result == "md:test_db?motherduck_token=abc123"

    def test_extract_motherduck_path_non_motherduck(self):
        """Test that non-MotherDuck paths are returned unchanged."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "data/test.db"})
        result = adapter._extract_motherduck_path("data/test.db")
        assert result == "data/test.db"

    def test_extract_motherduck_path_memory(self):
        """Test that :memory: path is returned unchanged."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": ":memory:"})
        result = adapter._extract_motherduck_path(":memory:")
        assert result == ":memory:"

    def test_extract_motherduck_path_resolved_motherduck_prefix(self):
        """Test extracting MotherDuck path with motherduck: prefix in resolved path."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "motherduck:test_db"})
        resolved_path = "/home/user/project/motherduck:test_db"
        result = adapter._extract_motherduck_path(resolved_path)
        assert result == "motherduck:test_db"

    def test_is_motherduck_path_direct_md(self):
        """Test detecting MotherDuck path with direct md: prefix."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        assert adapter._is_motherduck_path("md:test_db") is True

    def test_is_motherduck_path_direct_motherduck(self):
        """Test detecting MotherDuck path with direct motherduck: prefix."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "motherduck:test_db"})
        assert adapter._is_motherduck_path("motherduck:test_db") is True

    def test_is_motherduck_path_resolved_absolute(self):
        """Test detecting MotherDuck path in resolved absolute path."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "md:test_db"})
        assert adapter._is_motherduck_path("/home/user/project/md:test_db") is True

    def test_is_motherduck_path_resolved_motherduck_prefix(self):
        """Test detecting MotherDuck path with motherduck: in resolved path."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "motherduck:test_db"})
        assert adapter._is_motherduck_path("/home/user/project/motherduck:test_db") is True

    def test_is_motherduck_path_false_for_regular_path(self):
        """Test that regular file paths return False."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "data/test.db"})
        assert adapter._is_motherduck_path("data/test.db") is False

    def test_is_motherduck_path_false_for_memory(self):
        """Test that :memory: path returns False."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": ":memory:"})
        assert adapter._is_motherduck_path(":memory:") is False

    def test_is_motherduck_path_false_for_absolute_file_path(self):
        """Test that absolute file paths return False."""
        adapter = DuckDBAdapter({"type": "duckdb", "path": "/home/user/data.db"})
        assert adapter._is_motherduck_path("/home/user/data.db") is False
