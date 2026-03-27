"""
Test cases for dbt to t4t conversion examples.

These tests verify that the conversion matches the expected examples.
"""

import tempfile
from pathlib import Path

import yaml

from tee.importer.dbt.converters import JinjaConverter, MetadataConverter, PythonModelGenerator


class TestConversionExamples:
    """Test conversion examples match expected output."""

    def test_example_1_ref_conversion(self):
        """Test Example 1: Simple model with ref()."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"raw_customers": "staging.raw_customers"}

        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = """
SELECT
    id,
    name,
    email,
    created_at
FROM {{ ref('raw_customers') }}
WHERE deleted_at IS NULL
"""

        result = converter.convert(sql, "customers")

        assert result["is_python_model"] is False
        assert "staging.raw_customers" in result["sql"]
        assert "{{ ref(" not in result["sql"]

    def test_example_2_source_conversion(self):
        """Test Example 2: Model with source()."""
        dbt_project = {"name": "test_project"}
        source_map = {"raw_data": {"orders": "raw_data.orders"}}

        converter = JinjaConverter(
            dbt_project=dbt_project,
            source_map=source_map,
        )

        sql = "SELECT * FROM {{ source('raw_data', 'orders') }}"

        result = converter.convert(sql, "orders")

        assert result["is_python_model"] is False
        assert "raw_data.orders" in result["sql"]
        assert "{{ source(" not in result["sql"]

    def test_example_3_var_with_default(self):
        """Test Example 3: Variable with default."""
        dbt_project = {"name": "test_project"}

        converter = JinjaConverter(dbt_project=dbt_project)

        sql = "SELECT DATE_TRUNC('{{ var('granularity', 'day') }}', order_date) as period"

        result = converter.convert(sql, "revenue")

        assert result["is_python_model"] is False
        assert "@granularity:day" in result["sql"]
        assert "{{ var(" not in result["sql"]
        assert "granularity" in result["variables"]

    def test_example_4_var_without_default(self):
        """Test Example 4: Variable without default."""
        dbt_project = {"name": "test_project"}

        converter = JinjaConverter(dbt_project=dbt_project)

        sql = "SELECT * FROM table WHERE env = '{{ var('env') }}'"

        result = converter.convert(sql, "filtered")

        assert result["is_python_model"] is False
        assert "@env" in result["sql"]
        assert "{{ var(" not in result["sql"]
        assert len(result["conversion_warnings"]) > 0
        assert "env" in result["conversion_warnings"][0]
        assert "env" in result["variables"]

    def test_example_5_simple_if_statement(self):
        """Test Example 5: Simple if statement converts to Python model."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"staging_customers": "staging.staging_customers"}

        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = """
SELECT id, name
{% if var('include_email', false) %}
, email
{% endif %}
FROM {{ ref('staging_customers') }}
"""

        result = converter.convert(sql, "customers")

        # Should be detected as Python model (has if statement)
        assert result["is_python_model"] is True
        assert "include_email" in result["variables"]

        # Parse metadata from schema.yml (like real import does)
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yml"
            schema_content = {
                "models": [
                    {
                        "name": "customers",
                        "description": "Customer table with optional email field",
                        "config": {"materialized": "table"},
                    }
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            from tee.importer.dbt.parsers import SchemaParser

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)
            metadata_converter = MetadataConverter()
            t4t_metadata = metadata_converter.convert_model_metadata(
                schema_metadata=models.get("customers")
            )

            # Generate Python model with real metadata
            generator = PythonModelGenerator()
            # Use SQL with refs converted if available
            sql_for_python = result.get("sql_with_refs_converted", sql)
            python_code = generator.generate(
                sql_content=sql_for_python,
                model_name="customers",
                table_name="marts.customers",
                metadata=t4t_metadata,
                variables=result["variables"],
                conversion_warnings=result["conversion_warnings"],
            )

            # Check that Python code contains expected elements
            assert "def customers():" in python_code
            assert "@model" in python_code
            assert "variables=[" in python_code
            assert "include_email" in python_code
            assert "if include_email:" in python_code
            assert "sql_parts.append" in python_code
            assert "staging.staging_customers" in python_code
            assert "return sql" in python_code
            # Check that description comes from schema.yml
            assert "Customer table with optional email field" in python_code

    def test_metadata_from_schema_yml_same_folder(self):
        """Test that metadata is extracted from schema.yml in same folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create model file
            model_dir = Path(tmpdir) / "models" / "staging"
            model_dir.mkdir(parents=True)
            model_file = model_dir / "customers.sql"
            model_file.write_text("SELECT * FROM table")

            # Create schema.yml in same folder
            schema_file = model_dir / "schema.yml"
            schema_content = {
                "models": [
                    {
                        "name": "customers",
                        "description": "Customer staging table",
                        "config": {
                            "materialized": "table",
                            "meta": {"owner": "analytics-team"},
                        },
                        "columns": [
                            {
                                "name": "id",
                                "description": "Customer ID",
                                "data_type": "integer",
                            }
                        ],
                    }
                ]
            }
            with schema_file.open("w", encoding="utf-8") as f:
                yaml.dump(schema_content, f)

            # Parse schema file
            from tee.importer.dbt.parsers import SchemaParser

            parser = SchemaParser()
            models = parser.parse_schema_file(schema_file)

            assert "customers" in models
            assert models["customers"]["description"] == "Customer staging table"
            assert "meta" in models["customers"]["config"]

            # Convert metadata
            converter = MetadataConverter()
            t4t_metadata = converter.convert_model_metadata(schema_metadata=models["customers"])

            assert t4t_metadata["description"] == "Customer staging table"
            assert "meta" in t4t_metadata
            assert t4t_metadata["meta"]["owner"] == "analytics-team"

    def test_no_description_logs_warning(self):
        """Test that missing description logs a warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "models" / "staging"
            model_dir.mkdir(parents=True)
            model_file = model_dir / "customers.sql"
            model_file.write_text("SELECT * FROM table")

            # No schema.yml file

            # This would be tested in the model converter
            # For now, just verify the metadata converter handles None
            converter = MetadataConverter()
            t4t_metadata = converter.convert_model_metadata(schema_metadata=None)

            # Should return empty or minimal metadata
            assert isinstance(t4t_metadata, dict)
            assert "description" not in t4t_metadata or t4t_metadata.get("description") is None
