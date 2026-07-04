"""
Tests for seed file discovery and loading functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from t4t.engine.seeds import SeedDiscovery, SeedLoader


class TestSeedDiscovery:
    """Tests for SeedDiscovery class."""

    def test_discover_seed_files_no_folder(self, temp_project_dir):
        """Test discovery when seeds folder doesn't exist."""
        seeds_folder = temp_project_dir / "seeds"
        discovery = SeedDiscovery(seeds_folder)

        result = discovery.discover_seed_files()
        assert result == []

    def test_discover_seed_files_empty_folder(self, temp_project_dir):
        """Test discovery when seeds folder is empty."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        assert result == []

    def test_discover_seed_files_csv(self, temp_project_dir):
        """Test discovery of CSV files."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a CSV file
        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n2,Bob\n")

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        assert len(result) == 1
        assert result[0][0] == csv_file
        assert result[0][1] is None  # No schema

    def test_discover_seed_files_json(self, temp_project_dir):
        """Test discovery of JSON files."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a JSON file
        json_file = seeds_folder / "products.json"
        json_file.write_text('[{"id": 1, "name": "Product 1"}]')

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        assert len(result) == 1
        assert result[0][0] == json_file
        assert result[0][1] is None  # No schema

    def test_discover_seed_files_tsv(self, temp_project_dir):
        """Test discovery of TSV files."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a TSV file
        tsv_file = seeds_folder / "orders.tsv"
        tsv_file.write_text("id\tamount\n1\t100\n2\t200\n")

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        assert len(result) == 1
        assert result[0][0] == tsv_file
        assert result[0][1] is None  # No schema

    def test_discover_seed_files_with_schema(self, temp_project_dir):
        """Test discovery of seed files in subfolders (schema support)."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a schema subfolder
        schema_folder = seeds_folder / "my_schema"
        schema_folder.mkdir()

        # Create a file in the schema folder
        csv_file = schema_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        assert len(result) == 1
        assert result[0][0] == csv_file
        assert result[0][1] == "my_schema"  # Schema name from subfolder

    def test_discover_seed_files_multiple_schemas(self, temp_project_dir):
        """Test discovery of seed files in multiple schema folders."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create multiple schema folders
        schema1 = seeds_folder / "schema1"
        schema1.mkdir()
        schema2 = seeds_folder / "schema2"
        schema2.mkdir()

        # Create files in each schema
        file1 = schema1 / "users.csv"
        file1.write_text("id,name\n1,Alice\n")

        file2 = schema2 / "products.json"
        file2.write_text('[{"id": 1, "name": "Product"}]')

        # Create a file in root
        file3 = seeds_folder / "orders.tsv"
        file3.write_text("id\tamount\n1\t100\n")

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        assert len(result) == 3

        # Check that results are sorted
        schemas = [r[1] for r in result]
        assert schemas == [None, "schema1", "schema2"]  # None (root) comes first

    def test_discover_seed_files_cache(self, temp_project_dir):
        """Test that discovery results are cached."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        discovery = SeedDiscovery(seeds_folder)
        result1 = discovery.discover_seed_files()

        # Add another file
        json_file = seeds_folder / "products.json"
        json_file.write_text('[{"id": 1}]')

        # Result should be cached (same as before)
        result2 = discovery.discover_seed_files()
        assert len(result2) == len(result1)  # Still only 1 file (cached)

        # Clear cache and rediscover
        discovery.clear_cache()
        result3 = discovery.discover_seed_files()
        assert len(result3) == 2  # Now finds both files

    def test_discover_seed_files_ignores_other_files(self, temp_project_dir):
        """Test that only CSV, JSON, TSV files are discovered."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create various file types
        (seeds_folder / "users.csv").write_text("id,name\n1,Alice\n")
        (seeds_folder / "products.json").write_text('[{"id": 1}]')
        (seeds_folder / "orders.tsv").write_text("id\tamount\n1\t100\n")
        (seeds_folder / "readme.txt").write_text("Readme")
        (seeds_folder / "data.xlsx").write_text("Excel")

        discovery = SeedDiscovery(seeds_folder)
        result = discovery.discover_seed_files()

        # Should only find CSV, JSON, TSV
        assert len(result) == 3
        extensions = [r[0].suffix for r in result]
        assert set(extensions) == {".csv", ".json", ".tsv"}


class TestSeedLoader:
    """Tests for SeedLoader class."""

    def test_load_csv_file(self, duckdb_adapter, temp_project_dir):
        """Test loading a CSV file."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a CSV file
        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name,age\n1,Alice,30\n2,Bob,25\n")

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(csv_file, "users")

        # Verify table was created
        result = duckdb_adapter.execute_query("SELECT * FROM users ORDER BY id")
        assert len(result) == 2
        assert result[0] == (1, "Alice", 30)
        assert result[1] == (2, "Bob", 25)

    def test_load_csv_file_with_schema(self, duckdb_adapter, temp_project_dir):
        """Test loading a CSV file into a schema."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(csv_file, "users", schema_name="my_schema")

        # Verify table was created in schema
        result = duckdb_adapter.execute_query("SELECT * FROM my_schema.users ORDER BY id")
        assert len(result) == 1
        assert result[0] == (1, "Alice")

    def test_load_tsv_file(self, duckdb_adapter, temp_project_dir):
        """Test loading a TSV file."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        tsv_file = seeds_folder / "orders.tsv"
        tsv_file.write_text("id\tamount\tstatus\n1\t100\tpending\n2\t200\tcompleted\n")

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(tsv_file, "orders")

        # Verify table was created
        result = duckdb_adapter.execute_query("SELECT * FROM orders ORDER BY id")
        assert len(result) == 2
        assert result[0] == (1, 100, "pending")
        assert result[1] == (2, 200, "completed")

    def test_load_json_file_array(self, duckdb_adapter, temp_project_dir):
        """Test loading a JSON file with array of objects."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        json_file = seeds_folder / "products.json"
        json_file.write_text(
            '[{"id": 1, "name": "Product 1", "price": 10.99}, {"id": 2, "name": "Product 2", "price": 20.50}]'
        )

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(json_file, "products")

        # Verify table was created
        result = duckdb_adapter.execute_query("SELECT * FROM products ORDER BY id")
        assert len(result) == 2
        # DuckDB may return different types, so check values
        assert result[0][0] == 1
        assert result[1][0] == 2

    def test_load_json_file_single_object(self, duckdb_adapter, temp_project_dir):
        """Test loading a JSON file with single object."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        json_file = seeds_folder / "config.json"
        json_file.write_text('{"key": "value", "number": 42}')

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(json_file, "config")

        # Verify table was created with one row
        result = duckdb_adapter.execute_query("SELECT * FROM config")
        assert len(result) == 1

    def test_load_empty_csv_file(self, duckdb_adapter, temp_project_dir):
        """Test loading an empty CSV file (header only)."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "empty.csv"
        csv_file.write_text("id,name\n")

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(csv_file, "empty")

        # Verify table was created (empty)
        result = duckdb_adapter.execute_query("SELECT COUNT(*) FROM empty")
        assert result[0][0] == 0

    def test_load_seed_file_not_found(self, duckdb_adapter):
        """Test loading a non-existent file raises error."""
        loader = SeedLoader(duckdb_adapter)

        with pytest.raises(FileNotFoundError):
            loader.load_seed_file(Path("/nonexistent/file.csv"), "table")

    def test_load_seed_file_unsupported_format(self, duckdb_adapter, temp_project_dir):
        """Test loading an unsupported file format raises error."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        txt_file = seeds_folder / "data.txt"
        txt_file.write_text("Some text")

        loader = SeedLoader(duckdb_adapter)

        with pytest.raises(ValueError, match="Unsupported seed file type"):
            loader.load_seed_file(txt_file, "data")

    def test_load_all_seeds(self, duckdb_adapter, temp_project_dir):
        """Test loading multiple seed files."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create multiple seed files
        (seeds_folder / "users.csv").write_text("id,name\n1,Alice\n")
        (seeds_folder / "products.json").write_text('[{"id": 1, "name": "Product"}]')

        # Create schema folder
        schema_folder = seeds_folder / "my_schema"
        schema_folder.mkdir()
        (schema_folder / "orders.tsv").write_text("id\tamount\n1\t100\n")

        seed_files = [
            (seeds_folder / "users.csv", None),
            (seeds_folder / "products.json", None),
            (schema_folder / "orders.tsv", "my_schema"),
        ]

        loader = SeedLoader(duckdb_adapter)
        results = loader.load_all_seeds(seed_files)

        assert len(results["loaded_tables"]) == 3
        assert len(results["failed_tables"]) == 0
        assert results["total_seeds"] == 3

        # Verify tables exist
        assert "users" in results["loaded_tables"]
        assert "products" in results["loaded_tables"]
        assert "my_schema.orders" in results["loaded_tables"]

    def test_load_all_seeds_with_failures(self, duckdb_adapter, temp_project_dir):
        """Test loading seeds when some fail."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create valid and invalid files
        (seeds_folder / "users.csv").write_text("id,name\n1,Alice\n")
        # Create an invalid CSV file with no header (empty first line, then data)
        # This will cause csv.DictReader to have None fieldnames
        (seeds_folder / "invalid.csv").write_text("\n1,Alice\n2,Bob\n")

        seed_files = [
            (seeds_folder / "users.csv", None),
            (seeds_folder / "invalid.csv", None),
        ]

        loader = SeedLoader(duckdb_adapter)
        results = loader.load_all_seeds(seed_files)

        # Should have one success and one failure
        assert len(results["loaded_tables"]) == 1
        assert len(results["failed_tables"]) == 1
        assert results["total_seeds"] == 2

    def test_load_csv_generic_adapter(self, temp_project_dir):
        """Test loading CSV with generic adapter (non-DuckDB)."""
        # Create a mock adapter
        mock_adapter = Mock()
        mock_adapter.config.type = "postgresql"
        mock_adapter.execute_query = Mock()

        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n2,Bob\n")

        loader = SeedLoader(mock_adapter)
        loader.load_seed_file(csv_file, "users")

        # Should use generic INSERT statements
        assert mock_adapter.execute_query.called
        # Check that CREATE TABLE was called
        create_calls = [
            call[0][0]
            for call in mock_adapter.execute_query.call_args_list
            if "CREATE TABLE" in call[0][0]
        ]
        assert len(create_calls) > 0

    def test_create_schema_if_needed(self, duckdb_adapter):
        """Test that schemas are created when needed."""
        loader = SeedLoader(duckdb_adapter)

        # Load a file with schema
        temp_file = Path(tempfile.mkstemp(suffix=".csv")[1])
        try:
            temp_file.write_text("id,name\n1,Alice\n")

            loader.load_seed_file(temp_file, "users", schema_name="test_schema")

            # Verify schema exists
            result = duckdb_adapter.execute_query(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'test_schema'"
            )
            assert len(result) > 0
        finally:
            temp_file.unlink()

    def test_table_name_from_file_stem(self, duckdb_adapter, temp_project_dir):
        """Test that table name is derived from file stem."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "my_users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        loader = SeedLoader(duckdb_adapter)
        loader.load_seed_file(csv_file, "my_users")

        # Table should be named "my_users" (from file stem)
        result = duckdb_adapter.execute_query("SELECT * FROM my_users")
        assert len(result) == 1


class TestSeedIntegration:
    """Integration tests for seed loading."""

    def test_seed_discovery_and_loading_integration(self, duckdb_adapter, temp_project_dir):
        """Test full integration of discovery and loading."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create seed files in different locations
        (seeds_folder / "users.csv").write_text("id,name\n1,Alice\n2,Bob\n")

        schema_folder = seeds_folder / "production"
        schema_folder.mkdir()
        (schema_folder / "orders.json").write_text('[{"id": 1, "amount": 100}]')

        # Discover seeds
        discovery = SeedDiscovery(seeds_folder)
        seed_files = discovery.discover_seed_files()

        assert len(seed_files) == 2

        # Load seeds
        loader = SeedLoader(duckdb_adapter)
        results = loader.load_all_seeds(seed_files)

        assert len(results["loaded_tables"]) == 2
        assert "users" in results["loaded_tables"]
        assert "production.orders" in results["loaded_tables"]

        # Verify data
        users = duckdb_adapter.execute_query("SELECT * FROM users ORDER BY id")
        assert len(users) == 2

        orders = duckdb_adapter.execute_query("SELECT * FROM production.orders")
        assert len(orders) == 1
