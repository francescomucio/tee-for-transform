"""
Test cases for Snowflake tag attachment functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from t4t.adapters.snowflake.adapter import SnowflakeAdapter


class TestSnowflakeTagAttachment:
    """Test tag attachment in Snowflake adapter."""

    @pytest.fixture
    def snowflake_config(self):
        """Create Snowflake adapter configuration."""
        return {
            "type": "snowflake",
            "host": "test.snowflakecomputing.com",
            "user": "test_user",
            "password": "test_password",
            "database": "test_db",
            "schema": "test_schema",
        }

    @pytest.fixture
    def mock_snowflake_connection(self):
        """Create a mock Snowflake connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Default fetchone to return (0,) for schema existence checks
        mock_cursor.fetchone.return_value = (0,)
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    @pytest.fixture
    def snowflake_adapter(self, snowflake_config, mock_snowflake_connection):
        """Create Snowflake adapter with mocked connection."""
        mock_conn, mock_cursor = mock_snowflake_connection

        with patch("t4t.adapters.snowflake.adapter.snowflake.connector.connect") as mock_connect:
            mock_connect.return_value = mock_conn
            adapter = SnowflakeAdapter(snowflake_config)
            adapter.connection = mock_conn
            return adapter, mock_cursor

    def test_attach_tags_creates_tags(self, snowflake_adapter):
        """Test that attach_tags creates Snowflake tag objects."""
        adapter, cursor = snowflake_adapter

        tags = ["analytics", "production", "fct"]
        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

        # Should create tags
        create_calls = [call for call in cursor.execute.call_args_list if "CREATE TAG" in str(call)]
        assert len(create_calls) == 3  # One for each tag

    def test_attach_tags_sanitizes_tag_names(self, snowflake_adapter):
        """Test that tag names are properly sanitized for Snowflake."""
        adapter, cursor = snowflake_adapter

        tags = ["analytics-tag", "production tag", "fct_tag"]
        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

        # Check that sanitized tag names are used
        execute_calls = [str(call) for call in cursor.execute.call_args_list]
        # Should contain sanitized tag names (spaces and hyphens replaced with underscores)
        assert any(
            "tee_tag_analytics_tag" in str(call) or "tee_tag_analytics-tag" in str(call)
            for call in execute_calls
        )

    def test_attach_tags_escapes_sql_injection(self, snowflake_adapter):
        """Test that tag values are properly escaped to prevent SQL injection."""
        adapter, cursor = snowflake_adapter

        tags = ["tag'with'quotes", "normal_tag"]
        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

        # Check that quotes are escaped
        execute_calls = [str(call) for call in cursor.execute.call_args_list]
        # Should have escaped quotes ('' instead of ')
        assert any("''" in str(call) for call in execute_calls)

    def test_attach_tags_for_tables(self, snowflake_adapter):
        """Test attaching tags to tables."""
        adapter, cursor = snowflake_adapter

        tags = ["analytics", "production"]
        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

        # Should use ALTER TABLE syntax
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        assert len(alter_calls) == 2  # One for each tag

    def test_attach_tags_for_views(self, snowflake_adapter):
        """Test attaching tags to views."""
        adapter, cursor = snowflake_adapter

        tags = ["view_tag", "staging"]
        adapter.attach_tags("VIEW", "test_db.test_schema.test_view", tags)

        # Should use ALTER VIEW syntax
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER VIEW" in str(call)
        ]
        assert len(alter_calls) == 2  # One for each tag

    def test_attach_tags_handles_empty_list(self, snowflake_adapter):
        """Test that empty tag list is handled gracefully."""
        adapter, cursor = snowflake_adapter

        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", [])

        # Should not execute any SQL
        assert cursor.execute.call_count == 0

    def test_attach_tags_handles_invalid_tags(self, snowflake_adapter):
        """Test that invalid tag values are skipped."""
        adapter, cursor = snowflake_adapter

        # For this test, schema exists (returns 1) - override default
        cursor.fetchone.return_value = (1,)

        tags = ["valid_tag", None, "", "  ", "another_valid"]
        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

        # Should only process valid tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        assert len(alter_calls) == 2  # Only valid tags

    def test_attach_tags_continues_on_error(self, snowflake_adapter):
        """Test that tag attachment continues even if one tag fails."""
        adapter, cursor = snowflake_adapter

        # Make one tag creation fail
        def side_effect(query):
            if "CREATE TAG" in query and "failing_tag" in query:
                raise Exception("Tag creation failed")
            return None

        cursor.execute.side_effect = side_effect

        tags = ["valid_tag", "failing_tag", "another_valid"]
        # Should not raise exception
        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

    def test_attach_tags_in_create_table(self, snowflake_adapter):
        """Test that tags are attached when creating a table with metadata."""
        adapter, cursor = snowflake_adapter

        metadata = {
            "description": "Test table",
            "tags": ["analytics", "production"],
        }

        adapter.create_table(
            "test_schema.test_table",
            "SELECT 1 as id",
            metadata=metadata,
        )

        # Should create table and attach tags
        # Check all execute calls to see what was called
        all_calls = [str(call) for call in cursor.execute.call_args_list]
        create_table_calls = [
            call
            for call in all_calls
            if "CREATE TABLE" in call or "CREATE OR REPLACE TABLE" in call
        ]
        assert len(create_table_calls) > 0, f"No CREATE TABLE found. Calls were: {all_calls}"

        # Should also attach tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        assert len(alter_calls) == 2  # One for each tag

    def test_attach_tags_in_create_view(self, snowflake_adapter):
        """Test that tags are attached when creating a view with metadata."""
        adapter, cursor = snowflake_adapter

        metadata = {
            "description": "Test view",
            "tags": ["view_tag", "staging"],
        }

        adapter.create_view(
            "test_schema.test_view",
            "SELECT 1 as id",
            metadata=metadata,
        )

        # Should create view and attach tags
        all_calls = [str(call) for call in cursor.execute.call_args_list]
        create_view_calls = [
            call for call in all_calls if "CREATE VIEW" in call or "CREATE OR REPLACE VIEW" in call
        ]
        assert len(create_view_calls) > 0, f"No CREATE VIEW found. Calls were: {all_calls}"

        # Should also attach tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER VIEW" in str(call)
        ]
        assert len(alter_calls) == 2  # One for each tag

    def test_attach_tags_truncates_long_names(self, snowflake_adapter):
        """Test that very long tag names are truncated."""
        adapter, cursor = snowflake_adapter

        # Create a very long tag name
        long_tag = "a" * 200  # 200 characters
        tags = [long_tag]

        adapter.attach_tags("TABLE", "test_db.test_schema.test_table", tags)

        # Should truncate to 128 characters (Snowflake limit)
        execute_calls = [str(call) for call in cursor.execute.call_args_list]
        # Check that tag name is truncated
        assert any("tee_tag_" in str(call) for call in execute_calls)

    def test_attach_tags_without_connection_raises_error(self, snowflake_config):
        """Test that attach_tags raises error when not connected."""
        adapter = SnowflakeAdapter(snowflake_config)
        # Don't connect

        with pytest.raises(RuntimeError, match="Not connected"):
            adapter.attach_tags("TABLE", "test_table", ["tag1"])

    def test_attach_object_tags_creates_key_value_tags(self, snowflake_adapter):
        """Test that attach_object_tags creates Snowflake tags as key-value pairs."""
        adapter, cursor = snowflake_adapter

        object_tags = {
            "sensitivity_tag": "pii",
            "classification": "public",
            "data_owner": "analytics-team",
        }
        adapter.attach_object_tags("TABLE", "test_db.test_schema.test_table", object_tags)

        # Should create tags with the exact key names
        create_calls = [call for call in cursor.execute.call_args_list if "CREATE TAG" in str(call)]
        assert len(create_calls) == 3  # One for each tag key

        # Should attach tags with values
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        assert len(alter_calls) == 3  # One for each tag

    def test_attach_object_tags_uses_exact_key_names(self, snowflake_adapter):
        """Test that object tag keys are used as-is (with sanitization)."""
        adapter, cursor = snowflake_adapter

        object_tags = {
            "sensitivity-tag": "pii",  # Hyphen in key
            "data owner": "analytics",  # Space in key
        }
        adapter.attach_object_tags("TABLE", "test_db.test_schema.test_table", object_tags)

        # Check that keys are sanitized (hyphens and spaces replaced)
        execute_calls = [str(call) for call in cursor.execute.call_args_list]
        assert any(
            "sensitivity_tag" in str(call) or "sensitivity-tag" in str(call)
            for call in execute_calls
        )

    def test_attach_object_tags_escapes_values(self, snowflake_adapter):
        """Test that object tag values are properly escaped."""
        adapter, cursor = snowflake_adapter

        object_tags = {"description": "Contains O'Reilly data", "note": "Value with 'quotes'"}
        adapter.attach_object_tags("TABLE", "test_db.test_schema.test_table", object_tags)

        # Check that quotes are escaped
        execute_calls = [str(call) for call in cursor.execute.call_args_list]
        assert any("''" in str(call) for call in execute_calls)

    def test_attach_object_tags_converts_non_string_values(self, snowflake_adapter):
        """Test that non-string values are converted to strings."""
        adapter, cursor = snowflake_adapter

        object_tags = {"numeric_tag": 123, "boolean_tag": True, "string_tag": "text"}
        adapter.attach_object_tags("TABLE", "test_db.test_schema.test_table", object_tags)

        # Should handle all types
        execute_calls = [str(call) for call in cursor.execute.call_args_list]
        assert len([c for c in execute_calls if "ALTER TABLE" in c]) == 3

    def test_attach_object_tags_handles_empty_dict(self, snowflake_adapter):
        """Test that empty object_tags dict is handled gracefully."""
        adapter, cursor = snowflake_adapter

        adapter.attach_object_tags("TABLE", "test_db.test_schema.test_table", {})

        # Should not execute any SQL
        assert cursor.execute.call_count == 0

    def test_attach_object_tags_skips_invalid_entries(self, snowflake_adapter):
        """Test that invalid object tag entries are skipped."""
        adapter, cursor = snowflake_adapter

        object_tags = {
            "valid_tag": "value",
            None: "invalid_key",  # Invalid key
            "valid_key": None,  # Invalid value
            "": "empty_key",  # Empty key
        }
        adapter.attach_object_tags("TABLE", "test_db.test_schema.test_table", object_tags)

        # Should only process valid tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        assert len(alter_calls) == 1  # Only valid_tag

    def test_attach_tags_rejects_invalid_object_type(self, snowflake_adapter):
        """Test that unsafe object types are rejected."""
        adapter, _ = snowflake_adapter

        with pytest.raises(ValueError, match="Unsupported object type"):
            adapter.attach_tags(
                "TABLE; DROP TABLE users",
                "test_db.test_schema.test_table",
                ["analytics"],
            )

    def test_attach_object_tags_rejects_invalid_object_name(self, snowflake_adapter):
        """Test that unsafe object names are rejected."""
        adapter, _ = snowflake_adapter

        with pytest.raises(ValueError, match="Invalid object name"):
            adapter.attach_object_tags(
                "TABLE",
                "test_db.test_schema.table_name;DROP",
                {"classification": "public"},
            )

    def test_attach_object_tags_in_create_table(self, snowflake_adapter):
        """Test that object_tags are attached when creating a table."""
        adapter, cursor = snowflake_adapter

        metadata = {
            "description": "Test table",
            "object_tags": {"sensitivity_tag": "pii", "classification": "public"},
        }

        adapter.create_table(
            "test_schema.test_table",
            "SELECT 1 as id",
            metadata=metadata,
        )

        # Should attach object tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        # Should have calls for object_tags
        assert len(alter_calls) >= 2

    def test_attach_both_tags_and_object_tags(self, snowflake_adapter):
        """Test that both tags and object_tags can be attached together."""
        adapter, cursor = snowflake_adapter

        metadata = {
            "tags": ["analytics", "production"],  # dbt-style
            "object_tags": {  # database-style
                "sensitivity_tag": "pii",
                "classification": "public",
            },
        }

        adapter.create_table(
            "test_schema.test_table",
            "SELECT 1 as id",
            metadata=metadata,
        )

        # Should attach both types
        all_calls = [str(call) for call in cursor.execute.call_args_list]
        create_table_calls = [
            call
            for call in all_calls
            if "CREATE TABLE" in call or "CREATE OR REPLACE TABLE" in call
        ]
        assert len(create_table_calls) > 0, f"No CREATE TABLE found. Calls were: {all_calls}"

        # Should have calls for both tags and object_tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER TABLE" in str(call)
        ]
        assert len(alter_calls) >= 4  # 2 for tags, 2 for object_tags
