"""
Unit tests for TestConverter.
"""

from pathlib import Path


from tee.importer.dbt.converters import TestConverter


class TestTestConverter:
    """Test cases for TestConverter."""

    def test_convert_test_file_basic(self, tmp_path: Path) -> None:
        """Test converting a basic test file."""
        source_path = tmp_path / "source"
        source_path.mkdir()
        tests_dir = source_path / "tests"
        tests_dir.mkdir()

        target_path = tmp_path / "target"
        target_path.mkdir()

        # Create test file
        test_file = tests_dir / "test_model.sql"
        test_file.write_text("SELECT * FROM {{ ref('model') }} WHERE id IS NOT NULL")

        model_name_map = {"model": "public.model_table"}
        converter = TestConverter(
            target_path=target_path,
            model_name_map=model_name_map,
        )

        result = converter.convert_test_file(
            test_file, "tests/test_model.sql", is_freshness_test=False
        )

        assert result["converted"] is True
        assert result["errors"] == []

        # Check that converted file exists
        target_test = target_path / "tests" / "test_model.sql"
        assert target_test.exists()

        # Check that ref() was converted to actual table name
        content = target_test.read_text()
        assert "public.model_table" in content
        assert "{{ ref(" not in content

    def test_convert_test_file_with_this(self, tmp_path: Path) -> None:
        """Test converting test file with {{ this }}."""
        source_path = tmp_path / "source"
        source_path.mkdir()
        tests_dir = source_path / "tests"
        tests_dir.mkdir()

        target_path = tmp_path / "target"
        target_path.mkdir()

        test_file = tests_dir / "test_my_model.sql"
        test_file.write_text("SELECT * FROM {{ this }} WHERE name IS NOT NULL")

        converter = TestConverter(
            target_path=target_path,
            model_name_map={},
        )

        result = converter.convert_test_file(
            test_file, "tests/test_my_model.sql", is_freshness_test=False
        )

        assert result["converted"] is True

        target_test = target_path / "tests" / "test_my_model.sql"
        content = target_test.read_text()
        # Should use @table_name placeholder
        assert "@table_name" in content
        assert "{{ this }}" not in content

    def test_convert_test_file_with_source(self, tmp_path: Path) -> None:
        """Test converting test file with {{ source() }}."""
        source_path = tmp_path / "source"
        source_path.mkdir()
        tests_dir = source_path / "tests"
        tests_dir.mkdir()

        target_path = tmp_path / "target"
        target_path.mkdir()

        test_file = tests_dir / "test_source.sql"
        test_file.write_text("SELECT * FROM {{ source('staging', 'users') }}")

        converter = TestConverter(
            target_path=target_path,
            model_name_map={},
        )

        result = converter.convert_test_file(
            test_file, "tests/test_source.sql", is_freshness_test=False
        )

        assert result["converted"] is True

        target_test = target_path / "tests" / "test_source.sql"
        content = target_test.read_text()
        assert "staging.users" in content
        assert "{{ source(" not in content

    def test_convert_test_file_with_vars(self, tmp_path: Path) -> None:
        """Test converting test file with {{ var() }}."""
        source_path = tmp_path / "source"
        source_path.mkdir()
        tests_dir = source_path / "tests"
        tests_dir.mkdir()

        target_path = tmp_path / "target"
        target_path.mkdir()

        test_file = tests_dir / "test_var.sql"
        test_file.write_text(
            "SELECT * FROM table WHERE date >= {{ var('start_value', '2024-01-01') }}"
        )

        converter = TestConverter(
            target_path=target_path,
            model_name_map={},
        )

        result = converter.convert_test_file(
            test_file, "tests/test_var.sql", is_freshness_test=False
        )

        assert result["converted"] is True

        target_test = target_path / "tests" / "test_var.sql"
        content = target_test.read_text()
        assert "@start_value:2024-01-01" in content or "@start_value:'2024-01-01'" in content
        assert "{{ var(" not in content

    def test_skip_freshness_test(self, tmp_path: Path) -> None:
        """Test that freshness tests are skipped."""
        source_path = tmp_path / "source"
        source_path.mkdir()
        tests_dir = source_path / "tests"
        tests_dir.mkdir()

        target_path = tmp_path / "target"
        target_path.mkdir()

        test_file = tests_dir / "test_freshness.sql"
        test_file.write_text("SELECT * FROM {{ source('schema', 'table') }}")

        converter = TestConverter(
            target_path=target_path,
            model_name_map={},
        )

        result = converter.convert_test_file(
            test_file, "tests/test_freshness.sql", is_freshness_test=True
        )

        assert result["skipped"] is True
        assert result["converted"] is False
        assert len(result["warnings"]) > 0
        assert "freshness" in result["warnings"][0].lower()

        # Check that file was not created
        target_test = target_path / "tests" / "test_freshness.sql"
        assert not target_test.exists()

    def test_convert_all_tests(self, tmp_path: Path) -> None:
        """Test converting multiple test files."""
        source_path = tmp_path / "source"
        source_path.mkdir()
        tests_dir = source_path / "tests"
        tests_dir.mkdir()

        target_path = tmp_path / "target"
        target_path.mkdir()

        # Create multiple test files
        test1 = tests_dir / "test1.sql"
        test1.write_text("SELECT * FROM {{ ref('model1') }}")

        test2 = tests_dir / "test2.sql"
        test2.write_text("SELECT * FROM {{ ref('model2') }}")

        freshness_test = tests_dir / "test_freshness.sql"
        freshness_test.write_text("SELECT * FROM {{ source('schema', 'table') }}")

        test_files = {
            "tests/test1.sql": test1,
            "tests/test2.sql": test2,
            "tests/test_freshness.sql": freshness_test,
        }

        freshness_tests = {"tests/test_freshness.sql"}

        model_name_map = {"model1": "public.model1", "model2": "public.model2"}
        converter = TestConverter(
            target_path=target_path,
            model_name_map=model_name_map,
        )

        results = converter.convert_all_tests(test_files, freshness_tests)

        assert results["total"] == 3
        assert results["converted"] == 2
        assert results["skipped"] == 1
        assert results["errors"] == 0
        assert len(results["conversion_log"]) == 3
