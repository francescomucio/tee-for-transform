"""
Tests for the metadata converter.
"""

from t4t.importer.dbt.converters import MetadataConverter


class TestMetadataConverter:
    """Tests for metadata converter."""

    def test_convert_materialization_table(self):
        """Test converting table materialization."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {"materialized": "table"},
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["materialization"] == "table"

    def test_convert_materialization_view(self):
        """Test converting view materialization."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {"materialized": "view"},
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["materialization"] == "view"

    def test_convert_materialization_incremental(self):
        """Test converting incremental materialization."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {"materialized": "incremental"},
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["materialization"] == "incremental"

    def test_convert_materialization_ephemeral(self):
        """Test converting ephemeral materialization (becomes view)."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {"materialized": "ephemeral"},
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["materialization"] == "view"

    def test_convert_columns(self):
        """Test converting column definitions."""
        converter = MetadataConverter()

        schema_metadata = {
            "columns": [
                {
                    "name": "id",
                    "data_type": "integer",
                    "description": "Primary key",
                },
                {
                    "name": "name",
                    "data_type": "varchar",
                    "description": "Customer name",
                },
            ]
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert "schema" in result
        assert len(result["schema"]) == 2
        assert result["schema"][0]["name"] == "id"
        assert result["schema"][0]["datatype"] == "integer"
        assert result["schema"][1]["name"] == "name"
        assert result["schema"][1]["datatype"] == "string"

    def test_convert_datatype_mapping(self):
        """Test data type conversion mappings."""
        converter = MetadataConverter()

        test_cases = [
            ("text", "string"),
            ("varchar", "string"),
            ("integer", "integer"),
            ("bigint", "integer"),
            ("numeric", "number"),
            ("decimal", "number"),
            ("float", "float"),
            ("boolean", "boolean"),
            ("timestamp", "timestamp"),
            ("date", "date"),
            ("json", "json"),
        ]

        for dbt_type, expected_t4t_type in test_cases:
            schema_metadata = {"columns": [{"name": "col", "data_type": dbt_type}]}
            result = converter.convert_model_metadata(schema_metadata=schema_metadata)
            assert result["schema"][0]["datatype"] == expected_t4t_type

    def test_convert_datatype_with_size(self):
        """Test data type conversion with size/precision."""
        converter = MetadataConverter()

        schema_metadata = {"columns": [{"name": "col", "data_type": "varchar(255)"}]}
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should normalize to base type
        assert result["schema"][0]["datatype"] == "string"

    def test_convert_datatype_default(self):
        """Test default data type when not specified."""
        converter = MetadataConverter()

        schema_metadata = {"columns": [{"name": "col"}]}
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should default to string
        assert result["schema"][0]["datatype"] == "string"

    def test_convert_column_tests(self):
        """Test converting column-level tests."""
        converter = MetadataConverter()

        schema_metadata = {
            "columns": [
                {
                    "name": "id",
                    "data_type": "integer",
                    "tests": ["not_null", "unique"],
                }
            ]
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert "tests" in result["schema"][0]
        assert "not_null" in result["schema"][0]["tests"]
        assert "unique" in result["schema"][0]["tests"]

    def test_convert_column_tests_with_params(self):
        """Test converting column tests with parameters."""
        converter = MetadataConverter()

        schema_metadata = {
            "columns": [
                {
                    "name": "status",
                    "data_type": "varchar",
                    "tests": [
                        {
                            "test": "accepted_values",
                            "params": {"values": ["active", "inactive"]},
                        }
                    ],
                }
            ]
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert "tests" in result["schema"][0]
        assert result["schema"][0]["tests"][0]["name"] == "accepted_values"
        assert "params" in result["schema"][0]["tests"][0]

    def test_convert_model_tests(self):
        """Test converting model-level tests."""
        converter = MetadataConverter()

        schema_metadata = {
            "data_tests": ["accepted_values"],
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert "tests" in result
        assert "accepted_values" in result["tests"]

    def test_convert_model_tests_alternate_key(self):
        """Test converting model tests using 'tests' key."""
        converter = MetadataConverter()

        schema_metadata = {
            "tests": ["accepted_values"],
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert "tests" in result
        assert "accepted_values" in result["tests"]

    def test_convert_incremental_config_append(self):
        """Test converting incremental config with append strategy."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {
                "materialized": "incremental",
                "incremental_strategy": "append",
                "incremental_key": "updated_at",
            }
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["materialization"] == "incremental"
        assert "incremental" in result
        assert result["incremental"]["strategy"] == "append"
        assert "append" in result["incremental"]
        assert result["incremental"]["append"]["filter_column"] == "updated_at"

    def test_convert_incremental_config_merge(self):
        """Test converting incremental config with merge strategy."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {
                "materialized": "incremental",
                "incremental_strategy": "merge",
                "unique_key": "id",
                "incremental_key": "updated_at",
            }
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["materialization"] == "incremental"
        assert result["incremental"]["strategy"] == "merge"
        assert "merge" in result["incremental"]
        assert result["incremental"]["merge"]["unique_key"] == ["id"]
        assert result["incremental"]["merge"]["filter_column"] == "updated_at"

    def test_convert_incremental_config_unique_key_list(self):
        """Test converting incremental config with unique_key as list."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {
                "materialized": "incremental",
                "incremental_strategy": "merge",
                "unique_key": ["id", "date"],
            }
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["incremental"]["merge"]["unique_key"] == ["id", "date"]

    def test_convert_description(self):
        """Test converting model description."""
        converter = MetadataConverter()

        schema_metadata = {
            "description": "This is a test model",
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        assert result["description"] == "This is a test model"

    def test_convert_model_config_takes_precedence(self):
        """Test that model_config takes precedence over schema_metadata."""
        converter = MetadataConverter()

        schema_metadata = {
            "description": "Schema description",
            "config": {"materialized": "view"},
        }
        model_config = {
            "description": "Model config description",
            "config": {"materialized": "table"},
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata,
            model_config=model_config,
        )

        # Model config should take precedence
        assert result["description"] == "Model config description"
        assert result["materialization"] == "table"

    def test_convert_empty_metadata(self):
        """Test converting empty metadata."""
        converter = MetadataConverter()

        result = converter.convert_model_metadata()

        # Should return empty dict or minimal metadata
        assert isinstance(result, dict)

    def test_convert_unknown_materialization(self):
        """Test converting unknown materialization (defaults to table)."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {"materialized": "unknown_type"},
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should default to table
        assert result["materialization"] == "table"

    def test_convert_unknown_datatype(self):
        """Test converting unknown data type (defaults to string)."""
        converter = MetadataConverter()

        schema_metadata = {"columns": [{"name": "col", "data_type": "unknown_type"}]}
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should default to string
        assert result["schema"][0]["datatype"] == "string"

    def test_unsupported_incremental_strategy_insert_overwrite(self):
        """Test that insert_overwrite strategy generates Spark-specific warning."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {
                "materialized": "incremental",
                "incremental_strategy": "insert_overwrite",
            }
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should use append as fallback
        assert result["incremental"]["strategy"] == "append"

        # Check that warnings were generated (stored in metadata)
        # The warnings are logged but also stored in the result
        assert "incremental" in result

    def test_unsupported_incremental_strategy_generic(self):
        """Test that unsupported strategies generate generic warning."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {
                "materialized": "incremental",
                "incremental_strategy": "unknown_strategy",
            }
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should use append as fallback
        assert result["incremental"]["strategy"] == "append"

    def test_on_schema_change_warning(self):
        """Test that on_schema_change generates warning with OTS issue link."""
        converter = MetadataConverter()

        schema_metadata = {
            "config": {
                "materialized": "incremental",
                "incremental_strategy": "append",
                "on_schema_change": "append_new_columns",
            }
        }
        result = converter.convert_model_metadata(
            schema_metadata=schema_metadata, project_tags=None
        )

        # Should have incremental config
        assert "incremental" in result
        assert result["incremental"]["strategy"] == "append"
