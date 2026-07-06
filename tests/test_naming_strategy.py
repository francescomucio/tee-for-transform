"""Tests for env-aware naming strategy (schema_prefix)."""

from __future__ import annotations

from typing import Any

from t4t.adapters.base import DatabaseAdapter, NamingConfig
from t4t.adapters.base.config import AdapterConfig
from t4t.engine.config import DatabaseConfigManager

# ── NamingConfig tests ────────────────────────────────────────────────────


class TestNamingConfig:
    """Tests for the NamingConfig dataclass."""

    def test_default_values(self) -> None:
        """All fields default to None."""
        nc = NamingConfig()
        assert nc.schema_prefix is None
        assert nc.schema_suffix is None
        assert nc.database is None

    def test_schema_prefix_only(self) -> None:
        """schema_prefix can be set independently."""
        nc = NamingConfig(schema_prefix="dev_")
        assert nc.schema_prefix == "dev_"
        assert nc.schema_suffix is None
        assert nc.database is None

    def test_all_fields(self) -> None:
        """All fields can be set at once."""
        nc = NamingConfig(
            schema_prefix="stg_",
            schema_suffix="_test",
            database="analytics",
        )
        assert nc.schema_prefix == "stg_"
        assert nc.schema_suffix == "_test"
        assert nc.database == "analytics"

    def test_empty_prefix(self) -> None:
        """Empty string prefix is valid (no-op)."""
        nc = NamingConfig(schema_prefix="")
        assert nc.schema_prefix == ""


# ── AdapterConfig naming field tests ──────────────────────────────────────


class TestAdapterConfigNaming:
    """Tests for the naming field on AdapterConfig."""

    def test_naming_defaults_to_none(self) -> None:
        """Legacy configs without naming should work unchanged."""
        config = AdapterConfig(type="duckdb", path=":memory:")
        assert config.naming is None

    def test_naming_with_prefix(self) -> None:
        """Naming config is properly stored on AdapterConfig."""
        naming = NamingConfig(schema_prefix="dev_")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        assert config.naming is not None
        assert config.naming.schema_prefix == "dev_"

    def test_naming_roundtrip(self) -> None:
        """NamingConfig survives round-trip through AdapterConfig."""
        original = NamingConfig(schema_prefix="prod_")
        config = AdapterConfig(type="postgresql", naming=original)
        assert config.naming == original
        assert config.naming.schema_prefix == "prod_"


# ── apply_naming() tests ─────────────────────────────────────────────────


class FakeAdapter(DatabaseAdapter):
    """Minimal adapter stub for testing apply_naming()."""

    REQUIRED_FIELDS = ["type"]

    def get_default_dialect(self) -> str:
        return "duckdb"

    def get_supported_materializations(self):
        from t4t.adapters.base.config import MaterializationType

        return [MaterializationType.TABLE, MaterializationType.VIEW]

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def execute_query(self, query: str) -> Any:
        return None

    def create_table(self, table_name: str, query: str, metadata=None) -> None:
        pass

    def create_view(self, view_name: str, query: str, metadata=None) -> None:
        pass

    def table_exists(self, table_name: str) -> bool:
        return False

    def drop_table(self, table_name: str) -> None:
        pass

    def get_table_info(self, table_name: str) -> dict[str, Any]:
        return {"row_count": 0}

    def describe_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        return []

    def add_column(self, table_name: str, column: dict[str, Any]) -> None:
        pass

    def drop_column(self, table_name: str, column_name: str) -> None:
        pass

    def create_function(self, function_name: str, function_sql: str, metadata=None) -> None:
        pass

    def function_exists(self, function_name: str, signature: str | None = None) -> bool:
        return False

    def drop_function(self, function_name: str) -> None:
        pass


class TestApplyNaming:
    """Tests for DatabaseAdapter.apply_naming()."""

    def test_no_naming_config(self) -> None:
        """Without naming config, names pass through unchanged."""
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:"})
        assert adapter.apply_naming("my_schema.my_table") == "my_schema.my_table"
        assert adapter.apply_naming("unqualified") == "unqualified"

    def test_schema_prefix_qualified(self) -> None:
        """schema_prefix is prepended to the schema part of qualified names."""
        naming = NamingConfig(schema_prefix="dev_")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:", "_naming_config": naming})
        adapter.config = config
        assert adapter.apply_naming("my_schema.my_table") == "dev_my_schema.my_table"

    def test_schema_prefix_unqualified(self) -> None:
        """Unqualified names get the default schema with prefix."""
        naming = NamingConfig(schema_prefix="dev_")
        config = AdapterConfig(type="duckdb", path=":memory:", schema="public", naming=naming)
        adapter = FakeAdapter(
            {"type": "duckdb", "path": ":memory:", "schema": "public", "_naming_config": naming}
        )
        adapter.config = config
        assert adapter.apply_naming("my_table") == "dev_public.my_table"

    def test_schema_prefix_unqualified_no_default_schema(self) -> None:
        """Without a default schema, 'public' is used as fallback."""
        naming = NamingConfig(schema_prefix="test_")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:", "_naming_config": naming})
        adapter.config = config
        assert adapter.apply_naming("my_table") == "test_public.my_table"

    def test_schema_prefix_with_dotted_schema(self) -> None:
        """Three-part names (database.schema.table) prefix the schema, not the database."""
        naming = NamingConfig(schema_prefix="dev_")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:", "_naming_config": naming})
        adapter.config = config
        # The second-to-last part (schema) gets the prefix, not the first part (database)
        result = adapter.apply_naming("my_db.my_schema.my_table")
        assert result == "my_db.dev_my_schema.my_table"

    def test_empty_prefix(self) -> None:
        """Empty prefix is effectively a no-op."""
        naming = NamingConfig(schema_prefix="")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:", "_naming_config": naming})
        adapter.config = config
        assert adapter.apply_naming("my_schema.my_table") == "my_schema.my_table"

    def test_schema_prefix_with_function_name(self) -> None:
        """Function names are also prefixed correctly."""
        naming = NamingConfig(schema_prefix="dev_")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:", "_naming_config": naming})
        adapter.config = config
        assert adapter.apply_naming("my_schema.my_function") == "dev_my_schema.my_function"

    def test_schema_prefix_preserves_rest(self) -> None:
        """The object name part after the schema is preserved exactly."""
        naming = NamingConfig(schema_prefix="stg_")
        config = AdapterConfig(type="duckdb", path=":memory:", naming=naming)
        adapter = FakeAdapter({"type": "duckdb", "path": ":memory:", "_naming_config": naming})
        adapter.config = config
        assert (
            adapter.apply_naming("analytics.orders_enriched_v2")
            == "stg_analytics.orders_enriched_v2"
        )


# ── DatabaseConfigManager environment parsing tests ──────────────────────


class TestDatabaseConfigManagerNaming:
    """Tests for parsing naming config from [environments.<name>.naming]."""

    def test_no_environments_section(self, tmp_path) -> None:
        """No environments section → no naming config."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is None

    def test_environment_with_naming(self, tmp_path) -> None:
        """[environments.dev.naming] is parsed into NamingConfig."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is not None
        assert config.naming.schema_prefix == "dev_"
        assert config.naming.schema_suffix is None
        assert config.naming.database is None

    def test_environment_without_naming(self, tmp_path) -> None:
        """[environments.dev] without naming → no naming config."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"

[environments.dev]
some_other_key = "value"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is None

    def test_different_environments_have_different_naming(self, tmp_path) -> None:
        """Each environment gets its own naming config."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"

[environments.staging.naming]
schema_prefix = "stg_"

[environments.prod.naming]
schema_prefix = ""
""")
        manager = DatabaseConfigManager(str(tmp_path))

        dev_config = manager.load_config("dev")
        assert dev_config.naming is not None
        assert dev_config.naming.schema_prefix == "dev_"

        staging_config = manager.load_config("staging")
        assert staging_config.naming is not None
        assert staging_config.naming.schema_prefix == "stg_"

        prod_config = manager.load_config("prod")
        assert prod_config.naming is not None
        assert prod_config.naming.schema_prefix == ""

    def test_naming_with_databases_section(self, tmp_path) -> None:
        """Naming works with [tool.t4t.databases.<name>] too."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.databases.dev]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is not None
        assert config.naming.schema_prefix == "dev_"

    def test_naming_with_project_toml(self, tmp_path) -> None:
        """Naming works with project.toml fallback."""
        toml = tmp_path / "project.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is not None
        assert config.naming.schema_prefix == "dev_"

    def test_environment_does_not_affect_other_configs(self, tmp_path) -> None:
        """Loading a config without an environment section doesn't get naming."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("default")
        assert config.naming is None


# ── End-to-end integration tests ─────────────────────────────────────────


class TestNamingIntegration:
    """End-to-end tests combining config parsing and apply_naming()."""

    def test_full_flow_qualified_name(self, tmp_path) -> None:
        """End-to-end: config → adapter → apply_naming with qualified name."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")

        from t4t.adapters.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter(
            {"type": "duckdb", "path": ":memory:", "_naming_config": config.naming}
        )
        adapter.config = config

        result = adapter.apply_naming("my_schema.my_table")
        assert result == "dev_my_schema.my_table"

    def test_full_flow_unqualified_name(self, tmp_path) -> None:
        """End-to-end: config → adapter → apply_naming with unqualified name."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"
schema = "analytics"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")

        from t4t.adapters.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter(
            {
                "type": "duckdb",
                "path": ":memory:",
                "schema": "analytics",
                "_naming_config": config.naming,
            }
        )
        adapter.config = config

        result = adapter.apply_naming("my_table")
        assert result == "dev_analytics.my_table"

    def test_no_naming_legacy_mode(self, tmp_path) -> None:
        """Without naming config, everything works as before."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[tool.t4t.database]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("default")

        from t4t.adapters.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter({"type": "duckdb", "path": ":memory:"})
        adapter.config = config

        assert adapter.apply_naming("my_schema.my_table") == "my_schema.my_table"
        assert adapter.apply_naming("my_table") == "my_table"
