"""
Tests for config extractor.
"""

from t4t.importer.dbt.parsers import ConfigExtractor


class TestConfigExtractor:
    """Tests for ConfigExtractor."""

    def test_extract_config_simple_schema(self):
        """Test extracting simple schema config."""
        sql = """{{ config(schema='custom') }}

SELECT * FROM staging.customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert config == {"schema": "custom"}

    def test_extract_config_multiple_params(self):
        """Test extracting config with multiple parameters."""
        sql = """{{ config(materialized='table', schema='staging', tags=['tag1', 'tag2']) }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert config["materialized"] == "table"
        assert config["schema"] == "staging"
        assert config["tags"] == ["tag1", "tag2"]

    def test_extract_config_dict_format(self):
        """Test extracting config with dictionary format."""
        sql = """{{ config({"schema": "custom", "materialized": "view"}) }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert config["schema"] == "custom"
        assert config["materialized"] == "view"

    def test_extract_config_plus_schema(self):
        """Test extracting +schema config."""
        sql = """{{ config(+schema='staging') }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        # Note: +schema is handled as a key, but we'll normalize it in schema resolver
        assert "+schema" in config or "schema" in config

    def test_extract_config_no_config(self):
        """Test extracting from SQL with no config block."""
        sql = """SELECT * FROM customers"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert config == {}

    def test_extract_config_boolean_values(self):
        """Test extracting config with boolean values."""
        sql = """{{ config(enabled=true, full_refresh=false) }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert config["enabled"] is True
        assert config["full_refresh"] is False

    def test_extract_config_numeric_values(self):
        """Test extracting config with numeric values."""
        sql = """{{ config(unique_key=123, batch_size=1000) }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        assert config["unique_key"] == 123
        assert config["batch_size"] == 1000

    def test_extract_config_multiple_config_blocks(self):
        """Test extracting from SQL with multiple config blocks (last one wins)."""
        sql = """{{ config(schema='first') }}
{{ config(schema='second', materialized='table') }}

SELECT * FROM customers
"""
        extractor = ConfigExtractor()
        config = extractor.extract_config(sql)

        # Last config block should win
        assert config["schema"] == "second"
        assert config["materialized"] == "table"
