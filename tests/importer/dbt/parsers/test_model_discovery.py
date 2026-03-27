"""
Tests for the model file discovery.
"""

import tempfile
from pathlib import Path


from tee.importer.dbt.parsers import ModelFileDiscovery


class TestModelFileDiscovery:
    """Tests for model file discovery."""

    def test_discover_models_basic(self):
        """Test discovering basic model files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            # Create model files
            model_file1 = models_path / "customers.sql"
            model_file1.write_text("SELECT * FROM users")

            model_file2 = models_path / "orders.sql"
            model_file2.write_text("SELECT * FROM orders")

            discovery = ModelFileDiscovery(project_path)
            models = discovery.discover_models()

            assert len(models) == 2
            assert "models/customers.sql" in models
            assert "models/orders.sql" in models

    def test_discover_models_nested_structure(self):
        """Test discovering models in nested directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()
            (models_path / "staging").mkdir()
            (models_path / "marts").mkdir()

            # Create nested model files
            staging_file = models_path / "staging" / "stg_customers.sql"
            staging_file.write_text("SELECT * FROM raw.customers")

            marts_file = models_path / "marts" / "customers.sql"
            marts_file.write_text("SELECT * FROM staging.stg_customers")

            discovery = ModelFileDiscovery(project_path)
            models = discovery.discover_models()

            assert len(models) == 2
            assert "models/staging/stg_customers.sql" in models
            assert "models/marts/customers.sql" in models

    def test_discover_models_skip_directories(self):
        """Test that discovery skips excluded directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            # Create model file
            model_file = models_path / "customers.sql"
            model_file.write_text("SELECT * FROM users")

            # Create excluded directory
            (models_path / "__pycache__").mkdir()
            cache_file = models_path / "__pycache__" / "model.sql"
            cache_file.write_text("cached content")

            discovery = ModelFileDiscovery(project_path)
            models = discovery.discover_models()

            # Should not include files in excluded directories
            assert len(models) == 1
            assert "models/customers.sql" in models
            assert "models/__pycache__/model.sql" not in models

    def test_discover_models_custom_path(self):
        """Test discovering models with custom model path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            custom_models_path = project_path / "transformations"
            custom_models_path.mkdir()

            model_file = custom_models_path / "customers.sql"
            model_file.write_text("SELECT * FROM users")

            discovery = ModelFileDiscovery(project_path, model_paths=["transformations"])
            models = discovery.discover_models()

            assert len(models) == 1
            assert "transformations/customers.sql" in models

    def test_discover_models_multiple_paths(self):
        """Test discovering models from multiple model paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path1 = project_path / "models"
            models_path1.mkdir()
            models_path2 = project_path / "analyses"
            models_path2.mkdir()

            model_file1 = models_path1 / "customers.sql"
            model_file1.write_text("SELECT * FROM users")

            model_file2 = models_path2 / "analysis.sql"
            model_file2.write_text("SELECT * FROM analysis")

            discovery = ModelFileDiscovery(project_path, model_paths=["models", "analyses"])
            models = discovery.discover_models()

            assert len(models) == 2
            assert "models/customers.sql" in models
            assert "analyses/analysis.sql" in models

    def test_discover_models_missing_path(self):
        """Test discovering models when model path doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            # Don't create models directory

            discovery = ModelFileDiscovery(project_path)
            models = discovery.discover_models()

            # Should return empty dict
            assert models == {}

    def test_discover_schema_files(self):
        """Test discovering schema.yml files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            # Create schema files
            schema_file1 = models_path / "schema.yml"
            schema_file1.write_text("models: []")

            schema_file2 = models_path / "staging" / "_schema.yml"
            schema_file2.parent.mkdir()
            schema_file2.write_text("models: []")

            discovery = ModelFileDiscovery(project_path)
            schema_files = discovery.discover_schema_files()

            assert len(schema_files) == 2
            assert "models/schema.yml" in schema_files
            assert "models/staging/_schema.yml" in schema_files

    def test_discover_schema_files_yaml_extension(self):
        """Test discovering schema files with .yaml extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            schema_file = models_path / "schema.yaml"
            schema_file.write_text("models: []")

            discovery = ModelFileDiscovery(project_path)
            schema_files = discovery.discover_schema_files()

            assert len(schema_files) == 1
            assert "models/schema.yaml" in schema_files

    def test_discover_source_files(self):
        """Test discovering __sources.yml files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            # Create source files
            source_file1 = models_path / "__sources.yml"
            source_file1.write_text("sources: []")

            source_file2 = models_path / "staging" / "__sources.yml"
            source_file2.parent.mkdir()
            source_file2.write_text("sources: []")

            discovery = ModelFileDiscovery(project_path)
            source_files = discovery.discover_source_files()

            assert len(source_files) == 2
            assert any(f.name == "__sources.yml" for f in source_files)

    def test_discover_source_files_yaml_extension(self):
        """Test discovering source files with .yaml extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            source_file = models_path / "__sources.yaml"
            source_file.write_text("sources: []")

            discovery = ModelFileDiscovery(project_path)
            source_files = discovery.discover_source_files()

            assert len(source_files) == 1
            assert any(f.name == "__sources.yaml" for f in source_files)

    def test_discover_models_empty_directory(self):
        """Test discovering models in empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            models_path = project_path / "models"
            models_path.mkdir()

            discovery = ModelFileDiscovery(project_path)
            models = discovery.discover_models()

            assert models == {}

    def test_should_skip_file(self):
        """Test the _should_skip_file method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            discovery = ModelFileDiscovery(project_path)

            # Test skipping various directories
            assert discovery._should_skip_file(Path("/path/to/__pycache__/file.sql")) is True
            assert discovery._should_skip_file(Path("/path/to/.git/file.sql")) is True
            assert discovery._should_skip_file(Path("/path/to/target/file.sql")) is True
            assert discovery._should_skip_file(Path("/path/to/dbt_packages/file.sql")) is True
            assert discovery._should_skip_file(Path("/path/to/.dbt/file.sql")) is True
            assert discovery._should_skip_file(Path("/path/to/models/file.sql")) is False
