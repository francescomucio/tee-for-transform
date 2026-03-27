"""
Tests for the seed converter.
"""

import tempfile
from pathlib import Path


from tee.importer.dbt.converters import SeedConverter


class TestSeedConverter:
    """Tests for seed converter."""

    def test_convert_seeds_csv(self):
        """Test converting CSV seed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            seeds_path = source_path / "seeds"
            seeds_path.mkdir()

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            # Create a CSV seed file
            seed_file = seeds_path / "customers.csv"
            seed_file.write_text("id,name\n1,Alice\n2,Bob")

            dbt_project = {"name": "test_project", "seed-paths": ["seeds"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            assert result["copied"] == 1
            assert result["errors"] == 0

            # Check that file was copied
            target_file = target_path / "seeds" / "customers.csv"
            assert target_file.exists()
            assert target_file.read_text() == seed_file.read_text()

    def test_convert_seeds_multiple_files(self):
        """Test converting multiple seed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            seeds_path = source_path / "seeds"
            seeds_path.mkdir()

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            # Create multiple seed files
            seed_file1 = seeds_path / "customers.csv"
            seed_file1.write_text("id,name\n1,Alice")

            seed_file2 = seeds_path / "orders.csv"
            seed_file2.write_text("id,customer_id\n1,1")

            dbt_project = {"name": "test_project", "seed-paths": ["seeds"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            assert result["copied"] == 2
            assert result["errors"] == 0

            # Check that both files were copied
            assert (target_path / "seeds" / "customers.csv").exists()
            assert (target_path / "seeds" / "orders.csv").exists()

    def test_convert_seeds_nested_structure(self):
        """Test converting seeds with nested directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            seeds_path = source_path / "seeds"
            seeds_path.mkdir()
            (seeds_path / "raw").mkdir()

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            # Create nested seed file
            seed_file = seeds_path / "raw" / "users.csv"
            seed_file.write_text("id,name\n1,Alice")

            dbt_project = {"name": "test_project", "seed-paths": ["seeds"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            assert result["copied"] == 1

            # Check that nested structure was preserved
            target_file = target_path / "seeds" / "raw" / "users.csv"
            assert target_file.exists()

    def test_convert_seeds_multiple_extensions(self):
        """Test converting seeds with different file extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            seeds_path = source_path / "seeds"
            seeds_path.mkdir()

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            # Create different file types
            csv_file = seeds_path / "customers.csv"
            csv_file.write_text("id,name\n1,Alice")

            tsv_file = seeds_path / "orders.tsv"
            tsv_file.write_text("id\tcustomer_id\n1\t1")

            json_file = seeds_path / "products.json"
            json_file.write_text('{"id": 1, "name": "Product"}')

            dbt_project = {"name": "test_project", "seed-paths": ["seeds"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            # Should copy all supported file types
            assert result["copied"] >= 3

            assert (target_path / "seeds" / "customers.csv").exists()
            assert (target_path / "seeds" / "orders.tsv").exists()
            assert (target_path / "seeds" / "products.json").exists()

    def test_convert_seeds_missing_path(self):
        """Test converting seeds when seed path doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            # Don't create seeds directory

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            dbt_project = {"name": "test_project", "seed-paths": ["seeds"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            # Should handle missing path gracefully
            assert result["copied"] == 0
            assert result["errors"] == 0

    def test_convert_seeds_custom_path(self):
        """Test converting seeds with custom seed path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            custom_seeds_path = source_path / "data"
            custom_seeds_path.mkdir()

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            seed_file = custom_seeds_path / "customers.csv"
            seed_file.write_text("id,name\n1,Alice")

            dbt_project = {"name": "test_project", "seed-paths": ["data"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            assert result["copied"] == 1
            assert (target_path / "seeds" / "customers.csv").exists()

    def test_convert_seeds_multiple_paths(self):
        """Test converting seeds from multiple seed paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            seeds_path1 = source_path / "seeds"
            seeds_path1.mkdir()
            seeds_path2 = source_path / "data"
            seeds_path2.mkdir()

            target_path = Path(tmpdir) / "target"
            target_path.mkdir()

            seed_file1 = seeds_path1 / "customers.csv"
            seed_file1.write_text("id,name\n1,Alice")

            seed_file2 = seeds_path2 / "orders.csv"
            seed_file2.write_text("id,customer_id\n1,1")

            dbt_project = {"name": "test_project", "seed-paths": ["seeds", "data"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            result = converter.convert_seeds()

            assert result["copied"] == 2
            assert (target_path / "seeds" / "customers.csv").exists()
            assert (target_path / "seeds" / "orders.csv").exists()

    def test_convert_seeds_error_handling(self):
        """Test error handling during seed conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            source_path.mkdir()
            seeds_path = source_path / "seeds"
            seeds_path.mkdir()

            target_path = Path(tmpdir) / "target"
            # Don't create target directory - will cause error on copy

            # Create a seed file
            seed_file = seeds_path / "customers.csv"
            seed_file.write_text("id,name\n1,Alice")

            dbt_project = {"name": "test_project", "seed-paths": ["seeds"]}
            converter = SeedConverter(
                source_path=source_path,
                target_path=target_path,
                dbt_project=dbt_project,
            )

            # Should handle error gracefully
            result = converter.convert_seeds()

            # May have errors, but should not crash
            assert "errors" in result
