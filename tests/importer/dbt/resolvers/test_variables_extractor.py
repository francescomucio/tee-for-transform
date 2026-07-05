"""
Unit tests for VariablesExtractor.
"""

from pathlib import Path

from t4t.importer.dbt.resolvers import VariablesExtractor


class TestVariablesExtractor:
    """Test cases for VariablesExtractor."""

    def test_extract_variables_from_model(self, tmp_path: Path) -> None:
        """Test extracting variables from a model file."""
        model_file = tmp_path / "test_model.sql"
        model_file.write_text(
            "SELECT * FROM table WHERE env = {{ var('env') }} "
            "AND value = {{ var('value', 'default') }}"
        )

        model_files = {"models/test_model.sql": model_file}
        dbt_project = {"vars": {"env": "production"}}
        conversion_log = []

        extractor = VariablesExtractor()
        result = extractor.extract_variables(model_files, dbt_project, conversion_log)

        variables = result["variables"]
        assert "env" in variables
        assert "value" in variables
        assert variables["env"]["default_value"] == "production"
        assert variables["value"]["default_value"] == "default"

    def test_extract_variables_from_if_statement(self, tmp_path: Path) -> None:
        """Test extracting variables from if statements."""
        model_file = tmp_path / "test_model.sql"
        model_file.write_text("{% if var('include_email') %}\nSELECT email FROM users\n{% endif %}")

        model_files = {"models/test_model.sql": model_file}
        dbt_project = {"vars": {}}
        conversion_log = []

        extractor = VariablesExtractor()
        result = extractor.extract_variables(model_files, dbt_project, conversion_log)

        variables = result["variables"]
        assert "include_email" in variables

    def test_extract_variables_usage(self, tmp_path: Path) -> None:
        """Test tracking variable usage across models."""
        model1 = tmp_path / "model1.sql"
        model1.write_text("SELECT * FROM table WHERE env = {{ var('env') }}")

        model2 = tmp_path / "model2.sql"
        model2.write_text("SELECT * FROM table WHERE env = {{ var('env') }}")

        model_files = {
            "models/model1.sql": model1,
            "models/model2.sql": model2,
        }
        dbt_project = {"vars": {}}
        conversion_log = []

        extractor = VariablesExtractor()
        result = extractor.extract_variables(model_files, dbt_project, conversion_log)

        variables = result["variables"]
        assert "env" in variables
        assert len(variables["env"]["used_in"]) == 2
        assert "model1" in variables["env"]["used_in"]
        assert "model2" in variables["env"]["used_in"]
