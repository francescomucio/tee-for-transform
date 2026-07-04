"""
Test cases for Snowflake schema-level tag attachment functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from t4t.adapters.snowflake.adapter import SnowflakeAdapter


class TestSnowflakeSchemaTagAttachment:
    """Test schema-level tag attachment in Snowflake adapter."""

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

    def test_create_schema_with_tags(self, snowflake_adapter):
        """Test that schema is created with tags when metadata is provided."""
        adapter, cursor = snowflake_adapter
        # Mock schema doesn't exist
        cursor.fetchone.return_value = (0,)

        schema_metadata = {
            "tags": ["analytics", "production"],
            "object_tags": {"sensitivity_tag": "pii"},
        }

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Should create schema
        create_calls = [
            str(call) for call in cursor.execute.call_args_list if "CREATE SCHEMA" in str(call)
        ]
        assert len(create_calls) > 0

        # Should attach tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) >= 3  # 2 for tags, 1 for object_tags

    def test_attach_tags_to_existing_schema_with_force_update(self, snowflake_adapter):
        """Test that tags can be attached to existing schema with force_update flag."""
        adapter, cursor = snowflake_adapter
        # Mock schema exists
        cursor.fetchone.return_value = (1,)

        schema_metadata = {"tags": ["analytics"], "force_tag_update": True}

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Should attach tags even though schema exists
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) > 0

    def test_do_not_attach_tags_to_existing_schema_without_force(self, snowflake_adapter):
        """Test that tags are not attached to existing schema without force_update."""
        adapter, cursor = snowflake_adapter
        # Mock schema exists
        cursor.fetchone.return_value = (1,)

        schema_metadata = {
            "tags": ["analytics"],
            # No force_tag_update
        }

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Should not attach tags to existing schema
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) == 0

    def test_attach_schema_tags_dbt_style(self, snowflake_adapter):
        """Test attaching dbt-style tags to schema."""
        adapter, cursor = snowflake_adapter
        cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        schema_metadata = {"tags": ["analytics", "production"]}

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Should use ALTER SCHEMA syntax
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) == 2  # One for each tag

    def test_attach_schema_object_tags(self, snowflake_adapter):
        """Test attaching database-style object tags to schema."""
        adapter, cursor = snowflake_adapter
        cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        schema_metadata = {"object_tags": {"sensitivity_tag": "pii", "classification": "public"}}

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Should attach object tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) == 2  # One for each object tag

    def test_attach_both_tags_and_object_tags_to_schema(self, snowflake_adapter):
        """Test attaching both tag types to schema."""
        adapter, cursor = snowflake_adapter
        cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        schema_metadata = {
            "tags": ["analytics", "production"],  # dbt-style
            "object_tags": {  # database-style
                "sensitivity_tag": "pii",
                "classification": "public",
            },
        }

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Should attach both types
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) == 4  # 2 for tags, 2 for object_tags

    def test_schema_tag_attachment_handles_errors_gracefully(self, snowflake_adapter):
        """Test that schema tag attachment errors don't break schema creation."""
        adapter, cursor = snowflake_adapter
        cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        # Make tag attachment fail
        def side_effect(query):
            if "ALTER SCHEMA" in query:
                raise Exception("Tag attachment failed")
            return None

        cursor.execute.side_effect = side_effect

        schema_metadata = {"tags": ["analytics"]}

        # Should not raise exception
        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Schema should still be created
        create_calls = [
            str(call) for call in cursor.execute.call_args_list if "CREATE SCHEMA" in str(call)
        ]
        assert len(create_calls) > 0

    def test_schema_tag_attachment_with_no_metadata(self, snowflake_adapter):
        """Test that schema creation works without metadata."""
        adapter, cursor = snowflake_adapter
        cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        adapter._create_schema_if_needed("my_schema.table", None)

        # Should create schema
        create_calls = [
            str(call) for call in cursor.execute.call_args_list if "CREATE SCHEMA" in str(call)
        ]
        assert len(create_calls) > 0

        # Should not attach tags
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert len(alter_calls) == 0

    def test_schema_tag_attachment_uses_qualified_schema_name(self, snowflake_adapter):
        """Test that schema tags use fully qualified schema name."""
        adapter, cursor = snowflake_adapter
        cursor.fetchone.return_value = (0,)  # Schema doesn't exist

        schema_metadata = {"tags": ["analytics"]}

        adapter._create_schema_if_needed("my_schema.table", schema_metadata)

        # Check that qualified name (database.schema) is used
        alter_calls = [
            str(call) for call in cursor.execute.call_args_list if "ALTER SCHEMA" in str(call)
        ]
        assert any("test_db.my_schema" in str(call) for call in alter_calls)
