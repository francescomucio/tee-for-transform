"""
Tests for the model converter.
"""

import tempfile
from pathlib import Path


from t4t.importer.dbt.converters import ModelConverter


class TestModelConverter:
    """Tests for model converter."""

    def test_extract_model_name(self):
        """Test extracting model name from file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            sql_file = Path("/path/to/models/customers.sql")
            rel_path = "models/customers.sql"
            model_name = converter._extract_model_name(sql_file, rel_path)

            assert model_name == "customers"

    def test_determine_table_name_no_metadata(self):
        """Test determining table name without metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            sql_file = Path("/path/to/models/customers.sql")
            table_name = converter._determine_table_name("customers", None, sql_file)

            # Should use model name and default schema
            assert table_name == "public.customers"

    def test_default_schema_configurable(self):
        """Test that default schema can be configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
                default_schema="custom_schema",
            )

            sql_file = Path("/path/to/models/customers.sql")
            table_name = converter._determine_table_name("customers", None, sql_file)

            # Should use custom schema
            assert table_name == "custom_schema.customers"

    def test_determine_table_name_with_alias(self):
        """Test determining table name with alias in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            sql_file = Path("/path/to/models/customers.sql")
            schema_metadata = {"alias": "customers_final"}
            table_name = converter._determine_table_name("customers", schema_metadata, sql_file)

            assert table_name == "public.customers_final"

    def test_determine_table_name_with_schema_folder(self):
        """Test determining table name from folder structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            # File in staging/ folder
            sql_file = Path("/path/to/models/staging/customers.sql")
            table_name = converter._determine_table_name("customers", None, sql_file)

            # Should use folder name as schema
            assert table_name == "staging.customers"

    def test_write_sql_model_preserve_filenames(self):
        """Test writing SQL model with preserve_filenames=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
                preserve_filenames=True,
            )

            original_file = Path("/path/to/models/customers.sql")
            rel_path = "models/customers.sql"
            sql_content = "SELECT * FROM users"

            converter._write_sql_model("public.customers", sql_content, original_file, rel_path)

            # Should preserve original path structure
            target_file = target_path / "models" / "customers.sql"
            assert target_file.exists()
            assert target_file.read_text() == sql_content

    def test_write_sql_model_use_table_name(self):
        """Test writing SQL model using table name for file name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
                preserve_filenames=False,
            )

            original_file = Path("/path/to/models/customers.sql")
            rel_path = "models/customers.sql"
            sql_content = "SELECT * FROM users"

            converter._write_sql_model("staging.customers", sql_content, original_file, rel_path)

            # Should use schema/table structure
            target_file = target_path / "models" / "staging" / "customers.sql"
            assert target_file.exists()
            assert target_file.read_text() == sql_content

    def test_convert_models_basic(self):
        """Test converting basic models."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Create a simple model
            model_file = source_path / "models" / "customers.sql"
            model_file.write_text("SELECT * FROM users")

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            model_files = {"models/customers.sql": model_file}
            schema_metadata = {}

            result = converter.convert_models(model_files, schema_metadata)

            assert result["converted"] == 1
            assert result["errors"] == 0
            assert result["total"] == 1

            # Check that SQL file was created
            target_sql = target_path / "models" / "public" / "customers.sql"
            assert target_sql.exists()

    def test_convert_models_with_refs(self):
        """Test converting models with ref() calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Create models
            customers_file = source_path / "models" / "customers.sql"
            customers_file.write_text("SELECT * FROM users")

            orders_file = source_path / "models" / "orders.sql"
            orders_file.write_text("SELECT * FROM {{ ref('customers') }}")

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            model_files = {
                "models/customers.sql": customers_file,
                "models/orders.sql": orders_file,
            }
            schema_metadata = {}

            result = converter.convert_models(model_files, schema_metadata)

            assert result["converted"] == 2
            assert result["errors"] == 0

            # Check that ref was converted
            orders_sql = target_path / "models" / "public" / "orders.sql"
            assert orders_sql.exists()
            content = orders_sql.read_text()
            assert "{{ ref(" not in content
            assert "public.customers" in content

    def test_convert_models_with_metadata(self):
        """Test converting models with metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            model_file = source_path / "models" / "customers.sql"
            model_file.write_text("SELECT * FROM users")

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            model_files = {"models/customers.sql": model_file}
            schema_metadata = {
                "customers": {
                    "description": "Customer table",
                    "columns": [
                        {"name": "id", "data_type": "integer"},
                    ],
                }
            }

            result = converter.convert_models(model_files, schema_metadata)

            assert result["converted"] == 1

            # Check that metadata file was created
            metadata_file = target_path / "models" / "public" / "customers.py"
            assert metadata_file.exists()

            # Check that table_name is included in metadata
            metadata_content = metadata_file.read_text()
            assert '"table_name": "public.customers"' in metadata_content

    def test_convert_models_complex_jinja(self):
        """Test converting models with complex Jinja (Python models)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            model_file = source_path / "models" / "complex.sql"
            model_file.write_text("""
            {% for table in tables %}
            SELECT * FROM {{ table }}
            {% endfor %}
            """)

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            model_files = {"models/complex.sql": model_file}
            schema_metadata = {}

            result = converter.convert_models(model_files, schema_metadata)

            # Should detect complex Jinja and mark as Python model
            assert result["python_models"] == 1
            assert result["converted"] == 0

            # Check conversion log
            assert len(result["conversion_log"]) == 1
            assert result["conversion_log"][0]["status"] == "python_model"

    def test_convert_models_error_handling(self):
        """Test error handling during model conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Create a file that will cause an error (invalid path)
            # This will fail when trying to read it in _build_model_name_map
            model_file = Path("/nonexistent/path/model.sql")

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            model_files = {"models/error.sql": model_file}
            schema_metadata = {}

            # This should handle the FileNotFoundError gracefully
            result = converter.convert_models(model_files, schema_metadata)

            # Should have caught the error
            assert result["errors"] >= 1
            assert result["converted"] == 0

            # Check conversion log has error entry
            assert len(result["conversion_log"]) >= 1
            assert result["conversion_log"][0]["status"] == "error"

    def test_convert_models_two_pass(self):
        """Test that two-pass conversion correctly builds model_name_map."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            (source_path / "models").mkdir()

            target_path = Path(tmpdir) / "target"

            # Create models with refs
            customers_file = source_path / "models" / "customers.sql"
            customers_file.write_text("SELECT * FROM users")

            orders_file = source_path / "models" / "orders.sql"
            orders_file.write_text("SELECT * FROM {{ ref('customers') }}")

            # Add alias and metadata for customers (metadata file is only created if metadata exists)
            schema_metadata = {
                "customers": {
                    "alias": "customers_final",
                    "description": "Customer table",
                    "columns": [{"name": "id", "data_type": "integer"}],
                },
            }

            dbt_project = {"name": "test_project"}
            converter = ModelConverter(
                target_path=target_path,
                dbt_project=dbt_project,
            )

            model_files = {
                "models/customers.sql": customers_file,
                "models/orders.sql": orders_file,
            }

            result = converter.convert_models(model_files, schema_metadata)

            assert result["converted"] == 2

            # Check that orders.sql references the aliased table name
            orders_sql = target_path / "models" / "public" / "orders.sql"
            content = orders_sql.read_text()
            # Should use the alias, not the model name
            assert "public.customers_final" in content

            # Check that metadata file includes table_name with alias (if metadata file exists)
            customers_metadata = target_path / "models" / "public" / "customers.py"
            if customers_metadata.exists():
                metadata_content = customers_metadata.read_text()
                assert '"table_name": "public.customers_final"' in metadata_content
