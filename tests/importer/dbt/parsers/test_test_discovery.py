"""
Unit tests for TestFileDiscovery.
"""

from pathlib import Path


from tee.importer.dbt.parsers import TestFileDiscovery


class TestTestFileDiscovery:
    """Test cases for TestFileDiscovery."""

    def test_discover_test_files_empty(self, tmp_path: Path) -> None:
        """Test discovering test files when tests directory doesn't exist."""
        discovery = TestFileDiscovery(source_path=tmp_path)
        test_files = discovery.discover_test_files()

        assert test_files == {}

    def test_discover_test_files_basic(self, tmp_path: Path) -> None:
        """Test discovering basic test files."""
        # Create tests directory structure
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create test files
        test1 = tests_dir / "test_model.sql"
        test1.write_text("SELECT * FROM {{ ref('model') }}")

        test2 = tests_dir / "schema" / "test_another.sql"
        test2.parent.mkdir()
        test2.write_text("SELECT * FROM {{ this }}")

        discovery = TestFileDiscovery(source_path=tmp_path)
        test_files = discovery.discover_test_files()

        assert len(test_files) == 2
        assert "tests/test_model.sql" in test_files
        assert "tests/schema/test_another.sql" in test_files

    def test_is_source_freshness_test_by_filename(self, tmp_path: Path) -> None:
        """Test detecting freshness test by filename."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        freshness_test = tests_dir / "test_source_freshness.sql"
        freshness_test.write_text("SELECT * FROM {{ source('schema', 'table') }}")

        discovery = TestFileDiscovery(source_path=tmp_path)
        assert discovery.is_source_freshness_test(freshness_test)

    def test_is_source_freshness_test_by_content(self, tmp_path: Path) -> None:
        """Test that content-based detection is not used (only filenames)."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Test with source() and freshness keywords but not a freshness filename
        # This should NOT be detected as freshness test (it's a regular singular test)
        regular_test = tests_dir / "check_recency.sql"
        regular_test.write_text(
            "SELECT * FROM {{ source('schema', 'table') }} "
            "WHERE max(updated_at) < current_timestamp - interval '24 hours'"
        )

        discovery = TestFileDiscovery(source_path=tmp_path)
        # Should NOT be detected as freshness test (only filename patterns are checked)
        assert not discovery.is_source_freshness_test(regular_test)

    def test_is_not_freshness_test(self, tmp_path: Path) -> None:
        """Test that regular tests are not identified as freshness tests."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        regular_test = tests_dir / "test_model.sql"
        regular_test.write_text("SELECT * FROM {{ ref('model') }} WHERE id IS NOT NULL")

        discovery = TestFileDiscovery(source_path=tmp_path)
        assert not discovery.is_source_freshness_test(regular_test)
