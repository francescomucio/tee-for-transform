"""
Unit tests for ReportGenerator.
"""

from pathlib import Path

from t4t.importer.dbt.generators import ReportGenerator


class TestReportGenerator:
    """Test cases for ReportGenerator."""

    def test_generate_markdown_report(self, tmp_path: Path) -> None:
        """Test generating Markdown report."""
        generator = ReportGenerator(target_path=tmp_path)

        conversion_results = {
            "total": 2,
            "converted": 1,
            "python_models": 1,
            "errors": 0,
            "conversion_log": [
                {
                    "model": "model1",
                    "status": "converted",
                    "table_name": "public.model1",
                    "warnings": [],
                },
                {
                    "model": "model2",
                    "status": "python_model",
                    "table_name": "public.model2",
                    "warnings": ["Complex Jinja detected"],
                },
            ],
        }

        generator.generate_reports(conversion_results)

        report_file = tmp_path / "IMPORT_REPORT.md"
        assert report_file.exists()

        content = report_file.read_text()
        assert "# dbt Import Report" in content
        assert "Total Models" in content
        assert "model1" in content
        assert "model2" in content

    def test_generate_json_log(self, tmp_path: Path) -> None:
        """Test generating JSON log."""
        generator = ReportGenerator(target_path=tmp_path)

        conversion_results = {
            "total": 1,
            "converted": 1,
            "python_models": 0,
            "errors": 0,
            "conversion_log": [
                {
                    "model": "model1",
                    "status": "converted",
                    "table_name": "public.model1",
                }
            ],
        }

        generator.generate_reports(conversion_results)

        log_file = tmp_path / "CONVERSION_LOG.json"
        assert log_file.exists()

        import json

        with log_file.open() as f:
            log_data = json.load(f)

        assert log_data["summary"]["total_models"] == 1
        assert len(log_data["models"]) == 1

    def test_generate_report_with_variables(self, tmp_path: Path) -> None:
        """Test generating report with variables section."""
        generator = ReportGenerator(target_path=tmp_path)

        conversion_results = {
            "total": 0,
            "converted": 0,
            "python_models": 0,
            "errors": 0,
            "conversion_log": [],
        }

        variables_info = {
            "variables": {
                "env": {
                    "name": "env",
                    "default_value": "production",
                    "defined_in": "dbt_project.yml",
                    "used_in": ["model1"],
                }
            },
            "usage": {"env": ["model1"]},
        }

        generator.generate_reports(conversion_results, variables_info=variables_info)

        report_file = tmp_path / "IMPORT_REPORT.md"
        content = report_file.read_text()

        assert "## Variables" in content
        assert "env" in content
