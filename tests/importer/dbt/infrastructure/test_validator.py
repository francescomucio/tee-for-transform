"""
Unit tests for dbt project validator.
"""

import tempfile
from pathlib import Path


from t4t.importer.dbt.infrastructure import ProjectValidator, ValidationResult


class TestProjectValidator:
    """Tests for ProjectValidator."""

    def test_validation_result_init(self):
        """Test ValidationResult initialization."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.error_count == 0
        assert len(result.syntax_errors) == 0
        assert len(result.dependency_errors) == 0
        assert len(result.metadata_errors) == 0
        assert len(result.execution_errors) == 0

    def test_validation_result_with_errors(self):
        """Test ValidationResult with errors."""
        result = ValidationResult()
        result.syntax_errors.append({"file": "test.sql", "error": "Parse error"})
        result.dependency_errors.append({"file": "test2.sql", "error": "Missing ref"})

        assert result.is_valid is False
        assert result.error_count == 2

    def test_validation_result_to_dict(self):
        """Test ValidationResult.to_dict()."""
        result = ValidationResult()
        result.syntax_errors.append({"file": "test.sql", "error": "Parse error"})

        data = result.to_dict()
        assert data["is_valid"] is False
        assert data["error_count"] == 1
        assert len(data["syntax_errors"]) == 1
        assert len(data["dependency_errors"]) == 0

    def test_validate_syntax_valid_sql(self):
        """Test syntax validation with valid SQL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create valid SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT id, name FROM users WHERE id > 0")

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_syntax()

            assert len(errors) == 0

    def test_validate_syntax_invalid_sql(self):
        """Test syntax validation with invalid SQL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create invalid SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT FROM WHERE")  # Invalid SQL

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_syntax()

            assert len(errors) > 0
            assert errors[0]["file"] == "models/public/test.sql"
            assert "error" in errors[0]

    def test_validate_syntax_empty_file(self):
        """Test syntax validation with empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create empty SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("")

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_syntax()

            # Empty files should be skipped
            assert len(errors) == 0

    def test_validate_dependencies_valid_refs(self):
        """Test dependency validation with valid references."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create SQL file with valid ref
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT * FROM @public.users")

            model_name_map = {"users": "public.users"}
            validator = ProjectValidator(
                target_path=target_path, model_name_map=model_name_map, verbose=False
            )
            errors = validator.validate_dependencies()

            # Should not error on qualified names
            assert len(errors) == 0

    def test_validate_dependencies_missing_ref(self):
        """Test dependency validation with missing reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create SQL file with missing ref
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT * FROM @missing_table")

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_dependencies()

            # Should detect missing reference
            assert len(errors) > 0
            assert "missing_table" in errors[0]["error"] or "Unresolved" in errors[0]["error"]

    def test_validate_metadata_valid(self):
        """Test metadata validation with valid metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT * FROM users")

            # Create valid metadata file
            metadata_file = models_dir / "test.py"
            metadata_file.write_text(
                """
table_name = "public.users"

@model(table_name=table_name)
def users():
    return exp.parse_one("SELECT * FROM users")
"""
            )

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_metadata()

            assert len(errors) == 0

    def test_validate_metadata_missing_fields(self):
        """Test metadata validation with missing required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT * FROM users")

            # Create invalid metadata file (missing table_name and @model)
            metadata_file = models_dir / "test.py"
            metadata_file.write_text("# Just a comment")

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_metadata()

            assert len(errors) > 0
            assert "missing required fields" in errors[0]["error"]

    def test_validate_execution_no_config(self):
        """Test execution validation without connection config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            errors = validator.validate_execution(connection_config=None)

            assert len(errors) > 0
            assert "Connection config required" in errors[0]["error"]

    def test_validate_all(self):
        """Test validate_all method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create valid SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT id, name FROM users")

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            result = validator.validate_all(validate_execution=False)

            assert isinstance(result, ValidationResult)
            assert result.is_valid is True
            assert result.error_count == 0

    def test_validate_all_with_errors(self):
        """Test validate_all with errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            models_dir = target_path / "models" / "public"
            models_dir.mkdir(parents=True)

            # Create invalid SQL file
            sql_file = models_dir / "test.sql"
            sql_file.write_text("SELECT FROM WHERE")  # Invalid

            validator = ProjectValidator(target_path=target_path, model_name_map={}, verbose=False)
            result = validator.validate_all(validate_execution=False)

            assert isinstance(result, ValidationResult)
            assert result.is_valid is False
            assert len(result.syntax_errors) > 0
