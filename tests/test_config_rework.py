"""Tests for the reworked config system.

Covers:
- ``[environments.default]`` shared config merge
- Multi-engine ``[environments.<name>.connections.*]``
- ``SecretProvider`` protocol (``EnvSecretProvider``, ``FileSecretProvider``)
- ``ENVIRONMENTS__*__*`` dlt-style env var convention
- No legacy ``[connection]`` fallback
"""

from __future__ import annotations

import pytest

from t4t.adapters.base.config import (
    EnvSecretProvider,
    FileSecretProvider,
    SecretProvider,
    resolve_secret_ref,
)
from t4t.engine.config import DatabaseConfigManager, _parse_dlt_env_vars

# ══════════════════════════════════════════════════════════════════════════
# SecretProvider Protocol
# ══════════════════════════════════════════════════════════════════════════


class TestSecretProviderProtocol:
    """Tests for the SecretProvider protocol and built-in implementations."""

    def test_env_secret_provider_prefix(self) -> None:
        """EnvSecretProvider has the correct prefix."""
        provider = EnvSecretProvider()
        assert provider.prefix == "env:"

    def test_env_secret_provider_resolve(self, monkeypatch) -> None:
        """EnvSecretProvider resolves env var references."""
        monkeypatch.setenv("MY_DB_PASSWORD", "s3cret!")
        provider = EnvSecretProvider()
        result = provider.resolve("env:MY_DB_PASSWORD")
        assert result == "s3cret!"

    def test_env_secret_provider_missing(self) -> None:
        """EnvSecretProvider raises ValueError for missing env vars."""
        provider = EnvSecretProvider()
        with pytest.raises(ValueError, match="not set"):
            provider.resolve("env:NONEXISTENT_VAR")

    def test_file_secret_provider_prefix(self) -> None:
        """FileSecretProvider has the correct prefix."""
        provider = FileSecretProvider()
        assert provider.prefix == "file:"

    def test_file_secret_provider_resolve(self, tmp_path) -> None:
        """FileSecretProvider reads from file."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("my_secret_value\n")
        provider = FileSecretProvider()
        result = provider.resolve(f"file:{secret_file}")
        assert result == "my_secret_value"

    def test_file_secret_provider_not_found(self) -> None:
        """FileSecretProvider raises FileNotFoundError for missing files."""
        provider = FileSecretProvider()
        with pytest.raises(FileNotFoundError):
            provider.resolve("file:/nonexistent/path/secret.txt")

    def test_resolve_secret_ref_env(self, monkeypatch) -> None:
        """resolve_secret_ref handles env: references."""
        monkeypatch.setenv("MY_VAR", "resolved_value")
        result = resolve_secret_ref("env:MY_VAR")
        assert result == "resolved_value"

    def test_resolve_secret_ref_file(self, tmp_path) -> None:
        """resolve_secret_ref handles file: references."""
        secret_file = tmp_path / "pw.txt"
        secret_file.write_text("file_secret")
        result = resolve_secret_ref(f"file:{secret_file}")
        assert result == "file_secret"

    def test_resolve_secret_ref_literal(self) -> None:
        """resolve_secret_ref returns literals unchanged."""
        result = resolve_secret_ref("plain_password")
        assert result == "plain_password"

    def test_resolve_secret_ref_empty_string(self) -> None:
        """resolve_secret_ref returns empty string unchanged."""
        result = resolve_secret_ref("")
        assert result == ""

    def test_protocol_is_runtime_checkable(self) -> None:
        """SecretProvider is runtime-checkable via @runtime_checkable."""
        assert isinstance(EnvSecretProvider(), SecretProvider)
        assert isinstance(FileSecretProvider(), SecretProvider)

    def test_custom_provider(self) -> None:
        """Custom providers can be registered and used."""

        class VaultProvider:
            prefix = "vault:"

            def resolve(self, ref: str) -> str:
                return "vault_secret"

        provider = VaultProvider()
        assert isinstance(provider, SecretProvider)
        result = resolve_secret_ref("vault:path", providers=[provider])
        assert result == "vault_secret"


# ══════════════════════════════════════════════════════════════════════════
# DLT-style env var parsing
# ══════════════════════════════════════════════════════════════════════════


class TestDltEnvVars:
    """Tests for ENVIRONMENTS__*__* dlt-style env var parsing."""

    def test_no_env_vars(self, monkeypatch) -> None:
        """No ENVIRONMENTS__* vars → empty dict."""
        result = _parse_dlt_env_vars()
        assert result == {}

    def test_single_env_var(self, monkeypatch) -> None:
        """Single ENVIRONMENTS__DEV__CONNECTION__PASSWORD is parsed correctly."""
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTION__PASSWORD", "s3cret")
        result = _parse_dlt_env_vars()
        assert result == {
            "environments": {
                "dev": {
                    "connection": {
                        "password": "s3cret",
                    },
                },
            },
        }

    def test_multiple_env_vars(self, monkeypatch) -> None:
        """Multiple ENVIRONMENTS__* vars are merged correctly."""
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTION__PASSWORD", "dev_pw")
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTION__DATABASE", "dev_db")
        monkeypatch.setenv("ENVIRONMENTS__PROD__CONNECTION__PASSWORD", "prod_pw")
        result = _parse_dlt_env_vars()
        assert result["environments"]["dev"]["connection"]["password"] == "dev_pw"
        assert result["environments"]["dev"]["connection"]["database"] == "dev_db"
        assert result["environments"]["prod"]["connection"]["password"] == "prod_pw"

    def test_connections_multi_engine(self, monkeypatch) -> None:
        """ENVIRONMENTS__DEV__CONNECTIONS__ANALYTICS__PASSWORD is parsed."""
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTIONS__ANALYTICS__PASSWORD", "analytics_pw")
        result = _parse_dlt_env_vars()
        assert (
            result["environments"]["dev"]["connections"]["analytics"]["password"] == "analytics_pw"
        )

    def test_ignores_non_environments_vars(self, monkeypatch) -> None:
        """Non-ENVIRONMENTS__* vars are ignored."""
        monkeypatch.setenv("OTHER_VAR", "value")
        monkeypatch.setenv("T4T_DB_PASSWORD", "pw")
        result = _parse_dlt_env_vars()
        assert result == {}


# ══════════════════════════════════════════════════════════════════════════
# [environments.default] merge
# ══════════════════════════════════════════════════════════════════════════


class TestEnvironmentsDefault:
    """Tests for [environments.default] shared config."""

    def test_default_only(self, tmp_path) -> None:
        """[environments.default] alone provides the config."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"
        assert config.path == ":memory:"

    def test_default_plus_specific(self, tmp_path) -> None:
        """Specific env overrides default values."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = "data/default.duckdb"
database = "default_db"

[environments.dev.connection]
path = "data/dev.duckdb"
database = "dev_db"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"  # inherited from default
        assert config.path == "data/dev.duckdb"  # overridden
        assert config.database == "dev_db"  # overridden

    def test_default_plus_specific_no_override(self, tmp_path) -> None:
        """Specific env inherits default values it doesn't override."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = "data/default.duckdb"
warehouse = "COMPUTE_WH"

[environments.dev.connection]
path = "data/dev.duckdb"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"  # inherited
        assert config.path == "data/dev.duckdb"  # overridden
        assert config.warehouse == "COMPUTE_WH"  # inherited from default

    def test_default_naming_inherited(self, tmp_path) -> None:
        """Naming config from default is inherited."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"

[environments.default.naming]
schema_prefix = "dev_"

[environments.staging.naming]
schema_prefix = "stg_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("staging")
        assert config.naming is not None
        assert config.naming.schema_prefix == "stg_"

    def test_no_environments_raises_error(self, tmp_path) -> None:
        """No [environments.*] sections → empty config → ValueError."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[some_other_section]
key = "value"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        with pytest.raises(ValueError, match="No database configuration found"):
            manager.load_config("dev")

    def test_missing_environment_falls_back_to_default(self, tmp_path) -> None:
        """Requesting a non-existent env falls back to default if it exists."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("nonexistent")
        assert config.type == "duckdb"
        assert config.path == ":memory:"


# ══════════════════════════════════════════════════════════════════════════
# Multi-engine connections
# ══════════════════════════════════════════════════════════════════════════


class TestMultiEngine:
    """Tests for [environments.<name>.connections.*] multi-engine support."""

    def test_default_connection_only(self, tmp_path) -> None:
        """Default connection is the primary AdapterConfig."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"
        assert config.connections is None

    def test_additional_connections(self, tmp_path) -> None:
        """Additional named connections are stored in config.connections."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"

[environments.dev.connections.analytics]
type = "snowflake"
database = "ANALYTICS_DB"
warehouse = "ANALYTICS_WH"

[environments.dev.connections.reporting]
type = "postgresql"
database = "reporting_db"
host = "reporting.example.com"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"
        assert config.connections is not None
        assert "analytics" in config.connections
        assert "reporting" in config.connections
        assert config.connections["analytics"].type == "snowflake"
        assert config.connections["analytics"].database == "ANALYTICS_DB"
        assert config.connections["reporting"].type == "postgresql"
        assert config.connections["reporting"].host == "reporting.example.com"

    def test_additional_connections_with_default(self, tmp_path) -> None:
        """Additional connections work with [environments.default]."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"

[environments.dev.connections.analytics]
type = "snowflake"
database = "ANALYTICS_DB"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"  # from default
        assert config.connections is not None
        assert "analytics" in config.connections
        assert config.connections["analytics"].type == "snowflake"


# ══════════════════════════════════════════════════════════════════════════
# DLT-style env var integration
# ══════════════════════════════════════════════════════════════════════════


class TestDltEnvVarIntegration:
    """Tests for ENVIRONMENTS__*__* env vars overriding TOML config."""

    def test_dlt_env_overrides_toml(self, tmp_path, monkeypatch) -> None:
        """ENVIRONMENTS__*__* env vars override TOML values."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
password = "toml_password"
""")
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTION__PASSWORD", "env_password")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"
        assert config.password == "env_password"  # env var wins

    def test_dlt_env_with_default(self, tmp_path, monkeypatch) -> None:
        """ENVIRONMENTS__*__* env vars work with [environments.default]."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"

[environments.dev.connection]
database = "dev_db"
""")
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTION__PASSWORD", "env_pw")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"
        assert config.database == "dev_db"
        assert config.password == "env_pw"

    def test_dlt_env_multi_engine(self, tmp_path, monkeypatch) -> None:
        """ENVIRONMENTS__*__* env vars for additional connections."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"

[environments.dev.connections.analytics]
type = "snowflake"
database = "ANALYTICS_DB"
""")
        monkeypatch.setenv("ENVIRONMENTS__DEV__CONNECTIONS__ANALYTICS__PASSWORD", "analytics_pw")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.connections is not None
        assert config.connections["analytics"].password == "analytics_pw"


# ══════════════════════════════════════════════════════════════════════════
# Secret reference resolution in config
# ══════════════════════════════════════════════════════════════════════════


class TestSecretRefsInConfig:
    """Tests for env:/file: secret references in TOML config."""

    def test_env_ref_resolved(self, tmp_path, monkeypatch) -> None:
        """env: references in TOML are resolved."""
        monkeypatch.setenv("DEV_DB_PW", "resolved_pw")
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
password = "env:DEV_DB_PW"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.password == "resolved_pw"

    def test_file_ref_resolved(self, tmp_path) -> None:
        """file: references in TOML are resolved."""
        secret_file = tmp_path / "db_password.txt"
        secret_file.write_text("file_secret_value")
        toml = tmp_path / "pyproject.toml"
        toml.write_text(f"""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
password = "file:{secret_file}"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.password == "file_secret_value"

    def test_literal_password_warns(self, tmp_path, caplog) -> None:
        """Literal passwords trigger a debug warning."""
        caplog.set_level("DEBUG")
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
password = "plain_text_password"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.password == "plain_text_password"
        # Check that a debug message was logged about literal password
        assert any("Literal password" in record.message for record in caplog.records)


# ══════════════════════════════════════════════════════════════════════════
# Legacy [connection] removal
# ══════════════════════════════════════════════════════════════════════════


class TestNoLegacyConnection:
    """Tests that legacy [connection] fallback is removed."""

    def test_legacy_connection_not_supported(self, tmp_path) -> None:
        """Legacy [connection] section is no longer supported."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[connection]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        with pytest.raises(ValueError, match="No database configuration found"):
            manager.load_config("default")

    def test_legacy_connection_with_environments(self, tmp_path) -> None:
        """[connection] is ignored when [environments.*] exists."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[connection]
type = "postgresql"

[environments.dev.connection]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "duckdb"  # environments wins, not connection


# ══════════════════════════════════════════════════════════════════════════
# Naming config with new environments structure
# ══════════════════════════════════════════════════════════════════════════


class TestNamingWithNewConfig:
    """Tests that naming config works with the new environments structure."""

    def test_naming_in_environment(self, tmp_path) -> None:
        """Naming config in [environments.dev.naming] is parsed."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is not None
        assert config.naming.schema_prefix == "dev_"

    def test_naming_in_default(self, tmp_path) -> None:
        """Naming config in [environments.default.naming] is inherited."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"

[environments.default.naming]
schema_prefix = "shared_"

[environments.dev.connection]
database = "dev_db"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is not None
        assert config.naming.schema_prefix == "shared_"

    def test_naming_overridden_in_specific(self, tmp_path) -> None:
        """Specific env naming overrides default naming."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.default.connection]
type = "duckdb"
path = ":memory:"

[environments.default.naming]
schema_prefix = "shared_"

[environments.dev.naming]
schema_prefix = "dev_"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.naming is not None
        assert config.naming.schema_prefix == "dev_"


# ══════════════════════════════════════════════════════════════════════════
# T4T_DB_* legacy env vars
# ══════════════════════════════════════════════════════════════════════════


class TestLegacyEnvVars:
    """Tests that T4T_DB_* env vars still work for backward compat."""

    def test_t4t_db_type(self, tmp_path, monkeypatch) -> None:
        """T4T_DB_TYPE overrides TOML type."""
        monkeypatch.setenv("T4T_DB_TYPE", "postgresql")
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.type == "postgresql"

    def test_t4t_db_password(self, tmp_path, monkeypatch) -> None:
        """T4T_DB_PASSWORD overrides TOML password."""
        monkeypatch.setenv("T4T_DB_PASSWORD", "env_pw")
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "duckdb"
path = ":memory:"
password = "toml_pw"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.password == "env_pw"

    def test_t4t_db_port_int(self, tmp_path, monkeypatch) -> None:
        """T4T_DB_PORT is converted to int."""
        monkeypatch.setenv("T4T_DB_PORT", "5432")
        toml = tmp_path / "pyproject.toml"
        toml.write_text("""
[environments.dev.connection]
type = "postgresql"
host = "localhost"
""")
        manager = DatabaseConfigManager(str(tmp_path))
        config = manager.load_config("dev")
        assert config.port == 5432
        assert isinstance(config.port, int)
