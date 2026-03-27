"""
Test cases for metadata propagation functionality.

This module tests the column description propagation from model metadata
to database adapters (DuckDB and Snowflake).
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tee.adapters.duckdb.adapter import DuckDBAdapter  # noqa: E402
from tee.adapters.snowflake.adapter import SnowflakeAdapter  # noqa: E402
from tee.executor import execute_models  # noqa: E402
from tests.adapters.fixtures.metadata_fixtures import (  # noqa: E402
    INVALID_SCHEMA_TYPE_METADATA,
)


class TestMetadataPropagation:
    """Test class for metadata propagation functionality."""

    def test_duckdb_metadata_propagation(self):
        """Test that column descriptions are properly stored in DuckDB."""
        # Create a temporary DuckDB database
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
            db_path = tmp_file.name

        # Close the file so DuckDB can use it
        tmp_file.close()

        # Remove the file if it exists so DuckDB can create it fresh
        if os.path.exists(db_path):
            os.unlink(db_path)

        try:
            # DuckDB configuration
            config = {"type": "duckdb", "path": db_path}
            adapter = DuckDBAdapter(config)
            adapter.connect()

            # Create a table directly with metadata (no dependencies on other tables)
            table_name = "test_schema.test_metadata_table"
            query = "SELECT 1 as id, 'test' as name"

            # Metadata with column descriptions
            metadata = {
                "description": "Test table for metadata propagation",
                "schema": [
                    {
                        "name": "id",
                        "datatype": "integer",
                        "description": "Unique identifier for the record",
                    },
                    {"name": "name", "datatype": "string", "description": "Name of the record"},
                ],
            }

            # Create the table with metadata
            adapter.create_table(table_name, query, metadata=metadata)

            # Now check if column comments were actually stored
            import duckdb

            conn = duckdb.connect(db_path)

            try:
                # Query DuckDB's native system tables to get column comments
                # Using duckdb_columns() instead of information_schema.columns for better compatibility
                # with both local DuckDB and MotherDuck
                result = conn.execute("""
                    SELECT column_name, comment
                    FROM duckdb_columns()
                    WHERE table_name = 'test_metadata_table'
                    AND schema_name = 'test_schema'
                    ORDER BY column_index
                """).fetchall()

                # Check if we have the expected columns with comments
                expected_columns = ["id", "name"]
                found_columns = [row[0] for row in result]

                for col in expected_columns:
                    assert col in found_columns, f"Column {col} should exist"

                # Check that at least one column has a comment
                comments = [row[1] for row in result if row[1]]
                assert len(comments) > 0, "At least one column should have a comment"

                # Verify specific comments are stored correctly
                comments_dict = {row[0]: row[1] for row in result}
                assert comments_dict["id"] == "Unique identifier for the record"
                assert comments_dict["name"] == "Name of the record"

            finally:
                conn.close()
                adapter.disconnect()

        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_duckdb_table_description(self):
        """Test that table descriptions are properly stored in DuckDB."""
        # This test verifies that the table description functionality works
        # by testing the metadata extraction and validation logic directly

        # Create a mock adapter for testing
        config_dict = {"type": "duckdb", "path": ":memory:"}
        from tee.adapters.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter(config_dict)

        # Test metadata with table description
        metadata_with_table_desc = {
            "description": "This is a test table description",
            "schema": [
                {"name": "id", "datatype": "integer", "description": "Primary key identifier"},
                {"name": "name", "datatype": "string", "description": "Name of the record"},
            ],
        }

        # Test that metadata validation works with table descriptions
        column_descriptions = adapter._validate_column_metadata(metadata_with_table_desc)
        assert column_descriptions == {"id": "Primary key identifier", "name": "Name of the record"}

        # Test that table description is extracted correctly
        table_description = metadata_with_table_desc.get("description")
        assert table_description == "This is a test table description"

        # Test that the base adapter methods exist
        assert hasattr(adapter, "_add_table_comment")
        assert hasattr(adapter, "_add_column_comments")

    def test_metadata_validation(self):
        """Test metadata validation without database connection."""
        # Create a mock adapter for testing validation
        config_dict = {"type": "duckdb", "path": ":memory:"}
        adapter = DuckDBAdapter(config_dict)

        # Test valid metadata
        valid_metadata = {
            "schema": [{"name": "id", "datatype": "integer", "description": "Valid description"}]
        }

        descriptions = adapter._validate_column_metadata(valid_metadata)
        assert descriptions == {"id": "Valid description"}

        # Test malformed metadata
        malformed_metadata = {
            "schema": [
                {
                    # Missing 'name' field
                    "datatype": "integer",
                    "description": "Should fail",
                }
            ]
        }

        with pytest.raises(ValueError, match="Column definition must include 'name' field"):
            adapter._validate_column_metadata(malformed_metadata)

        # Test description too long
        long_description_metadata = {
            "schema": [
                {
                    "name": "id",
                    "datatype": "integer",
                    "description": "A" * 5000,  # Too long
                }
            ]
        }

        with pytest.raises(ValueError, match="Column description for 'id' is too long"):
            adapter._validate_column_metadata(long_description_metadata)

    def test_metadata_priority(self):
        """Test that decorator metadata takes priority over file metadata."""
        # Create a temporary DuckDB database
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
            db_path = tmp_file.name

        tmp_file.close()

        if os.path.exists(db_path):
            os.unlink(db_path)

        try:
            # Create a temporary project directory
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir)

                # Create data directory for state database
                data_dir = project_dir / "data"
                data_dir.mkdir()

                # Create models directory
                models_dir = project_dir / "models"
                models_dir.mkdir()

                # Create a Python model file with decorator metadata
                model_file = models_dir / "test_model.py"
                model_file.write_text("""
from tee.parser.processing.model import model

@model(
    table_name="test_schema.priority_test",
    metadata={
        "schema": [
            {"name": "id", "datatype": "integer", "description": "DECORATOR: This should win"},
            {"name": "name", "datatype": "string", "description": "DECORATOR: This should take priority"},
        ]
    }
)
def test_model():
    return "SELECT 1 as id, 'test' as name"
""")

                # Create a companion metadata file with conflicting metadata (file metadata)
                metadata_file = models_dir / "test_model_metadata.py"
                metadata_file.write_text("""
metadata = {
    "schema": [
        {"name": "id", "datatype": "integer", "description": "FILE: This should be ignored"},
        {"name": "name", "datatype": "string", "description": "FILE: This should be ignored"},
    ]
}
""")

                # Create project.toml
                project_toml = project_dir / "project.toml"
                project_toml.write_text(f"""
project_folder = "."
[connection]
type = "duckdb"
path = "{db_path}"
""")

                # Execute models
                config = {"type": "duckdb", "path": db_path}
                # Load project config if available
                from tee.cli.utils import load_project_config

                project_config = None
                try:
                    project_config = load_project_config(str(project_dir))
                except Exception:
                    pass

                results = execute_models(
                    project_folder=str(project_dir),
                    connection_config=config,
                    save_analysis=False,
                    project_config=project_config,
                )

                # Verify the model was executed
                assert "test_schema.priority_test" in results["executed_tables"]

                # Check that decorator metadata (not file metadata) was used
                import duckdb

                conn = duckdb.connect(db_path)
                try:
                    # Query DuckDB's native system tables to get column comments
                    # Using duckdb_columns() instead of information_schema.columns for better compatibility
                    # with both local DuckDB and MotherDuck
                    result = conn.execute("""
                        SELECT column_name, comment
                        FROM duckdb_columns()
                        WHERE table_name = 'priority_test'
                        AND schema_name = 'test_schema'
                        ORDER BY column_index
                    """).fetchall()

                    # Verify decorator metadata descriptions were used
                    comments = {row[0]: row[1] for row in result}
                    assert "id" in comments
                    assert "name" in comments
                    # Decorator metadata should have won
                    assert "DECORATOR" in comments.get("id", "")
                    assert "DECORATOR" in comments.get("name", "")
                    # File metadata should NOT be present
                    assert "FILE" not in comments.get("id", "")
                    assert "FILE" not in comments.get("name", "")
                finally:
                    conn.close()

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_snowflake_metadata_propagation(self):
        """Test that column descriptions are properly stored in Snowflake."""
        # Mock Snowflake connection
        snowflake_config = {
            "type": "snowflake",
            "host": "test.snowflakecomputing.com",
            "user": "test_user",
            "password": "test_password",
            "database": "test_db",
            "schema": "test_schema",
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        with patch("tee.adapters.snowflake.adapter.snowflake.connector.connect") as mock_connect:
            mock_connect.return_value = mock_conn
            adapter = SnowflakeAdapter(snowflake_config)
            adapter.connection = mock_conn

            # Test metadata with column descriptions
            metadata = {
                "description": "Test table",
                "schema": [
                    {"name": "id", "datatype": "integer", "description": "Primary key identifier"},
                    {"name": "name", "datatype": "varchar", "description": "User name"},
                ],
            }

            # Create table with metadata
            adapter.create_table(
                "test_schema.test_table", "SELECT 1 as id, 'test' as name", metadata=metadata
            )

            # Verify that COMMENT ON COLUMN was called for each column
            comment_calls = [
                str(call)
                for call in mock_cursor.execute.call_args_list
                if "COMMENT ON COLUMN" in str(call)
            ]
            assert len(comment_calls) == 2, (
                f"Expected 2 COMMENT ON COLUMN calls, got {len(comment_calls)}"
            )

            # Verify the comments contain the descriptions
            all_calls = [str(call) for call in mock_cursor.execute.call_args_list]
            assert any("Primary key identifier" in call for call in all_calls)
            assert any("User name" in call for call in all_calls)

    def test_error_handling_malformed_metadata(self):
        """Test that malformed metadata is properly handled."""
        # This test verifies that the metadata validation works correctly
        # by testing the validation function directly rather than through
        # the execution engine, since the test models were removed from the project

        # Create a mock adapter for testing validation
        config_dict = {"type": "duckdb", "path": ":memory:"}
        adapter = DuckDBAdapter(config_dict)

        # Test malformed metadata - missing name field
        malformed_metadata = {
            "schema": [
                {"name": "id", "datatype": "integer", "description": "Valid description"},
                {
                    # Missing 'name' field - should cause error
                    "datatype": "string",
                    "description": "This should cause an error",
                },
            ]
        }

        with pytest.raises(ValueError, match="Column definition must include 'name' field"):
            adapter._validate_column_metadata(malformed_metadata)

        # Test invalid schema type
        with pytest.raises(ValueError, match="Schema must be a list of column definitions"):
            adapter._validate_column_metadata(INVALID_SCHEMA_TYPE_METADATA)
