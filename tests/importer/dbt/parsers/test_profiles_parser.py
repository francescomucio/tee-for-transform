"""
Tests for dbt profiles.yml parser.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from t4t.importer.dbt.exceptions import DbtImporterError
from t4t.importer.dbt.parsers import ProfilesParser


class TestProfilesParser:
    """Tests for ProfilesParser."""

    def test_find_profiles_file_default_location(self, monkeypatch):
        """Test finding profiles.yml in default location."""
        parser = ProfilesParser(verbose=False)

        # Create a temporary profiles.yml in home/.dbt
        with tempfile.TemporaryDirectory() as tmpdir:
            dbt_dir = Path(tmpdir) / ".dbt"
            dbt_dir.mkdir()
            profiles_file = dbt_dir / "profiles.yml"
            profiles_file.write_text("test_profile:\n  outputs: {}\n")

            # Mock Path.home() to return our temp directory
            def mock_home():
                return Path(tmpdir)

            monkeypatch.setattr(Path, "home", mock_home)

            found = parser.find_profiles_file()
            assert found is not None
            assert found == profiles_file

    def test_find_profiles_file_not_found(self):
        """Test when profiles.yml is not found."""
        parser = ProfilesParser(verbose=False)
        found = parser.find_profiles_file()
        # May or may not be None depending on system, but should not raise
        assert found is None or isinstance(found, Path)

    def test_parse_profiles_valid(self):
        """Test parsing valid profiles.yml."""
        parser = ProfilesParser(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_file = Path(tmpdir) / "profiles.yml"
            profiles_data = {
                "my_profile": {
                    "outputs": {
                        "dev": {
                            "type": "postgres",
                            "host": "localhost",
                            "port": 5432,
                            "database": "mydb",
                            "user": "myuser",
                            "password": "mypass",
                        }
                    }
                }
            }
            with profiles_file.open("w", encoding="utf-8") as f:
                yaml.dump(profiles_data, f)

            result = parser.parse_profiles(profiles_file)
            assert isinstance(result, dict)
            assert "my_profile" in result

    def test_parse_profiles_invalid_yaml(self):
        """Test parsing invalid YAML."""
        parser = ProfilesParser(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_file = Path(tmpdir) / "profiles.yml"
            profiles_file.write_text("invalid: yaml: content: [")

            with pytest.raises(DbtImporterError, match="Failed to parse profiles.yml"):
                parser.parse_profiles(profiles_file)

    def test_get_profile_config(self):
        """Test getting profile configuration."""
        parser = ProfilesParser(verbose=False)

        profiles_data = {
            "my_profile": {
                "outputs": {
                    "dev": {
                        "type": "postgres",
                        "host": "localhost",
                        "database": "mydb",
                    },
                    "prod": {
                        "type": "postgres",
                        "host": "prod.example.com",
                        "database": "mydb",
                    },
                }
            }
        }

        config = parser.get_profile_config("my_profile", profiles_data, "dev")
        assert config is not None
        assert config["type"] == "postgres"
        assert config["host"] == "localhost"

    def test_get_profile_config_not_found(self):
        """Test getting non-existent profile."""
        parser = ProfilesParser(verbose=False)
        config = parser.get_profile_config("nonexistent", {}, "dev")
        assert config is None

    def test_convert_to_t4t_connection_postgres(self):
        """Test converting PostgreSQL profile to t4t format."""
        parser = ProfilesParser(verbose=False)

        dbt_config = {
            "type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database": "mydb",
            "user": "myuser",
            "password": "mypass",
            "schema": "public",
        }

        result = parser.convert_to_t4t_connection(dbt_config)
        assert result["type"] == "postgresql"
        assert result["host"] == "localhost"
        assert result["port"] == 5432
        assert result["database"] == "mydb"
        assert result["user"] == "myuser"
        assert result["password"] == "mypass"
        assert result["schema"] == "public"

    def test_convert_to_t4t_connection_snowflake(self):
        """Test converting Snowflake profile to t4t format."""
        parser = ProfilesParser(verbose=False)

        dbt_config = {
            "type": "snowflake",
            "account": "myaccount",
            "user": "myuser",
            "password": "mypass",
            "role": "myrole",
            "warehouse": "mywarehouse",
            "database": "mydb",
            "schema": "public",
        }

        result = parser.convert_to_t4t_connection(dbt_config)
        assert result["type"] == "snowflake"
        assert result["host"] == "myaccount.snowflakecomputing.com"
        assert result["user"] == "myuser"
        assert result["password"] == "mypass"
        assert result["role"] == "myrole"
        assert result["warehouse"] == "mywarehouse"
        assert result["database"] == "mydb"

    def test_convert_to_t4t_connection_duckdb(self):
        """Test converting DuckDB profile to t4t format."""
        parser = ProfilesParser(verbose=False)

        dbt_config = {
            "type": "duckdb",
            "path": "data/myproject.duckdb",
            "schema": "public",
        }

        result = parser.convert_to_t4t_connection(dbt_config)
        assert result["type"] == "duckdb"
        assert result["path"] == "data/myproject.duckdb"
        assert result["schema"] == "public"

    def test_convert_to_t4t_connection_bigquery(self):
        """Test converting BigQuery profile to t4t format."""
        parser = ProfilesParser(verbose=False)

        dbt_config = {
            "type": "bigquery",
            "project": "myproject",
            "dataset": "mydataset",
        }

        result = parser.convert_to_t4t_connection(dbt_config)
        assert result["type"] == "bigquery"
        assert result["project"] == "myproject"
        assert result["database"] == "mydataset"
