"""Tests for secret reference resolution in database configuration.

Covers:
- env:VAR reference resolution
- file:/path reference resolution
- Literal values pass through unchanged
- Unknown reference prefix → ValueError
- Redaction of secrets in log output
- Literal secret warning
- T4T_DB_* env var overrides still work
"""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from t4t.engine.config import DatabaseConfigManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> DatabaseConfigManager:
    """Return a DatabaseConfigManager with a temp project root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield DatabaseConfigManager(project_root=tmpdir)


# ---------------------------------------------------------------------------
# _resolve_secret_refs
# ---------------------------------------------------------------------------


class TestResolveSecretRefs:
    """Tests for _resolve_secret_refs()."""

    def test_env_ref_resolved(self, manager: DatabaseConfigManager) -> None:
        """env:VAR is replaced by the environment variable value."""
        with patch.dict(os.environ, {"MY_DB_PW": "s3cret!"}, clear=False):
            result = manager._resolve_secret_refs({"password": "env:MY_DB_PW"})
        assert result == {"password": "s3cret!"}

    def test_env_ref_missing_raises(self, manager: DatabaseConfigManager) -> None:
        """Missing env var raises ValueError."""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ValueError, match="MY_MISSING_VAR"),
        ):
            manager._resolve_secret_refs({"password": "env:MY_MISSING_VAR"})

    def test_env_ref_empty_name_raises(self, manager: DatabaseConfigManager) -> None:
        """Empty env: reference raises ValueError."""
        with pytest.raises(ValueError, match="Empty env: reference"):
            manager._resolve_secret_refs({"password": "env:"})

    def test_file_ref_resolved(self, manager: DatabaseConfigManager) -> None:
        """file:/path is replaced by the file content (trailing newline stripped)."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("my-token\n")
            fpath = f.name
        try:
            result = manager._resolve_secret_refs({"token": f"file:{fpath}"})
            assert result == {"token": "my-token"}
        finally:
            os.unlink(fpath)

    def test_file_ref_no_trailing_newline(self, manager: DatabaseConfigManager) -> None:
        """File content without trailing newline is read as-is."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("no-newline-here")
            fpath = f.name
        try:
            result = manager._resolve_secret_refs({"token": f"file:{fpath}"})
            assert result == {"token": "no-newline-here"}
        finally:
            os.unlink(fpath)

    def test_file_ref_missing_raises(self, manager: DatabaseConfigManager) -> None:
        """Missing file raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            manager._resolve_secret_refs({"password": "file:/nonexistent/secret"})

    def test_file_ref_empty_path_raises(self, manager: DatabaseConfigManager) -> None:
        """Empty file: reference raises ValueError."""
        with pytest.raises(ValueError, match="Empty file: reference"):
            manager._resolve_secret_refs({"password": "file:"})

    def test_literal_values_pass_through(self, manager: DatabaseConfigManager) -> None:
        """Non-reference values are returned unchanged."""
        config = {
            "type": "snowflake",
            "host": "myhost.snowflake.com",
            "port": 443,
            "user": "admin",
        }
        result = manager._resolve_secret_refs(config)
        assert result == config

    def test_non_string_values_pass_through(self, manager: DatabaseConfigManager) -> None:
        """Non-string values (int, None) are returned unchanged."""
        config = {"port": 443, "extra": None}
        result = manager._resolve_secret_refs(config)
        assert result == config

    def test_unknown_prefix_raises(self, manager: DatabaseConfigManager) -> None:
        """Unknown reference prefix raises ValueError."""
        with pytest.raises(ValueError, match="Unknown reference prefix"):
            manager._resolve_secret_refs({"password": "vault:my-secret"})

    def test_mixed_config(self, manager: DatabaseConfigManager) -> None:
        """Mixed literal and reference values are handled correctly."""
        with patch.dict(os.environ, {"SF_PW": "real-password"}, clear=False):
            config = {
                "type": "snowflake",
                "user": "admin",
                "password": "env:SF_PW",
                "host": "snowflake.example.com",
            }
            result = manager._resolve_secret_refs(config)
        assert result == {
            "type": "snowflake",
            "user": "admin",
            "password": "real-password",
            "host": "snowflake.example.com",
        }

    def test_env_ref_with_t4t_override(self, manager: DatabaseConfigManager) -> None:
        """T4T_DB_* env var overrides a TOML env: reference.

        This tests the full precedence: TOML has env: reference, but
        T4T_DB_PASSWORD env var overrides it in _merge_configs.
        """
        with patch.dict(
            os.environ,
            {"SF_PW": "from-env-ref", "T4T_DB_PASSWORD": "from-override"},
            clear=False,
        ):
            toml_config = {"password": "env:SF_PW"}
            env_config = {"password": "from-override"}
            merged = manager._merge_configs(toml_config, env_config)
        assert merged["password"] == "from-override"


# ---------------------------------------------------------------------------
# _redact_secrets
# ---------------------------------------------------------------------------


class TestRedactSecrets:
    """Tests for _redact_secrets()."""

    def test_password_redacted(self, manager: DatabaseConfigManager) -> None:
        """password key is redacted."""
        result = manager._redact_secrets({"password": "s3cret"})
        assert result["password"] == "****"

    def test_token_redacted(self, manager: DatabaseConfigManager) -> None:
        """token key is redacted."""
        result = manager._redact_secrets({"token": "my-token"})
        assert result["token"] == "****"

    def test_secret_redacted(self, manager: DatabaseConfigManager) -> None:
        """secret key is redacted."""
        result = manager._redact_secrets({"secret": "my-secret"})
        assert result["secret"] == "****"

    def test_non_secret_keys_preserved(self, manager: DatabaseConfigManager) -> None:
        """Non-secret keys are preserved as-is."""
        config = {"type": "snowflake", "host": "example.com", "user": "admin"}
        result = manager._redact_secrets(config)
        assert result == config

    def test_mixed_config(self, manager: DatabaseConfigManager) -> None:
        """Mixed config redacts only secret keys."""
        config = {
            "type": "snowflake",
            "password": "s3cret",
            "host": "example.com",
            "token": "abc123",
        }
        result = manager._redact_secrets(config)
        assert result == {
            "type": "snowflake",
            "password": "****",
            "host": "example.com",
            "token": "****",
        }


# ---------------------------------------------------------------------------
# _warn_literal_secrets
# ---------------------------------------------------------------------------


class TestWarnLiteralSecrets:
    """Tests for _warn_literal_secrets()."""

    def test_literal_password_warns(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Literal password value triggers a warning."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"password": "plaintext"})
        assert any("Literal password" in msg for msg in caplog.messages)

    def test_literal_token_warns(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Literal token value triggers a warning."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"token": "plaintext"})
        assert any("Literal token" in msg for msg in caplog.messages)

    def test_literal_secret_warns(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Literal secret value triggers a warning."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"secret": "plaintext"})
        assert any("Literal secret" in msg for msg in caplog.messages)

    def test_env_ref_does_not_warn(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """env: reference does not trigger a warning."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"password": "env:MY_PW"})
        assert not caplog.messages

    def test_file_ref_does_not_warn(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """file: reference does not trigger a warning."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"password": "file:/run/secrets/pw"})
        assert not caplog.messages

    def test_no_secret_keys_no_warning(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Config without secret keys produces no warnings."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"type": "snowflake", "host": "example.com"})
        assert not caplog.messages

    def test_none_value_no_warning(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """None value for a secret key produces no warning."""
        caplog.set_level(logging.WARNING)
        manager._warn_literal_secrets({"password": None})
        assert not caplog.messages


# ---------------------------------------------------------------------------
# Integration: _merge_configs with secret resolution
# ---------------------------------------------------------------------------


class TestMergeConfigsWithSecrets:
    """Tests for _merge_configs() with secret reference resolution."""

    def test_toml_env_ref_resolved_in_merge(self, manager: DatabaseConfigManager) -> None:
        """env: reference in TOML config is resolved during merge."""
        with patch.dict(os.environ, {"SF_PW": "resolved-pw"}, clear=False):
            merged = manager._merge_configs(
                {"password": "env:SF_PW", "type": "snowflake"},
                {},
            )
        assert merged["password"] == "resolved-pw"

    def test_t4t_override_takes_precedence(self, manager: DatabaseConfigManager) -> None:
        """T4T_DB_PASSWORD env var overrides TOML env: reference."""
        with patch.dict(
            os.environ,
            {"SF_PW": "from-toml-ref", "T4T_DB_PASSWORD": "from-override"},
            clear=False,
        ):
            merged = manager._merge_configs(
                {"password": "env:SF_PW", "type": "snowflake"},
                {"password": "from-override"},
            )
        assert merged["password"] == "from-override"

    def test_toml_file_ref_resolved_in_merge(self, manager: DatabaseConfigManager) -> None:
        """file: reference in TOML config is resolved during merge."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("file-secret\n")
            fpath = f.name
        try:
            merged = manager._merge_configs(
                {"password": f"file:{fpath}", "type": "snowflake"},
                {},
            )
            assert merged["password"] == "file-secret"
        finally:
            os.unlink(fpath)

    def test_literal_values_unchanged(self, manager: DatabaseConfigManager) -> None:
        """Literal values in TOML config pass through unchanged."""
        merged = manager._merge_configs(
            {"type": "duckdb", "path": "/data/mydb.duckdb"},
            {},
        )
        assert merged == {"type": "duckdb", "path": "/data/mydb.duckdb"}


# ---------------------------------------------------------------------------
# Integration: full load_config flow
# ---------------------------------------------------------------------------


class TestLoadConfigWithSecrets:
    """End-to-end tests for load_config() with secret references."""

    def test_load_config_with_env_ref(self, manager: DatabaseConfigManager) -> None:
        """Full load_config resolves env: references."""
        # Create a minimal pyproject.toml
        toml_content = """
[tool.t4t.database]
type = "snowflake"
user = "admin"
password = "env:SF_PW"
host = "snowflake.example.com"
"""
        toml_file = manager.project_root / "pyproject.toml"
        toml_file.write_text(toml_content)

        with patch.dict(os.environ, {"SF_PW": "real-password"}, clear=False):
            config = manager.load_config("default")

        assert config.type == "snowflake"
        assert config.user == "admin"
        assert config.password == "real-password"
        assert config.host == "snowflake.example.com"

    def test_load_config_with_file_ref(self, manager: DatabaseConfigManager) -> None:
        """Full load_config resolves file: references."""
        toml_content = """
[tool.t4t.database]
type = "snowflake"
user = "admin"
password = "file:/tmp/test_secret_file"
host = "snowflake.example.com"
"""
        toml_file = manager.project_root / "pyproject.toml"
        toml_file.write_text(toml_content)

        secret_path = Path("/tmp/test_secret_file")
        try:
            secret_path.write_text("file-password\n")
            config = manager.load_config("default")
            assert config.password == "file-password"
        finally:
            secret_path.unlink(missing_ok=True)

    def test_t4t_env_override_still_works(self, manager: DatabaseConfigManager) -> None:
        """T4T_DB_PASSWORD env var overrides TOML env: reference in full flow."""
        toml_content = """
[tool.t4t.database]
type = "snowflake"
user = "admin"
password = "env:SF_PW"
host = "snowflake.example.com"
"""
        toml_file = manager.project_root / "pyproject.toml"
        toml_file.write_text(toml_content)

        with patch.dict(
            os.environ,
            {"SF_PW": "from-toml-ref", "T4T_DB_PASSWORD": "from-override"},
            clear=False,
        ):
            config = manager.load_config("default")

        assert config.password == "from-override"

    def test_literal_password_warns_in_load(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Literal password in TOML triggers warning during load."""
        caplog.set_level(logging.WARNING)

        toml_content = """
[tool.t4t.database]
type = "snowflake"
password = "plaintext-password"
"""
        toml_file = manager.project_root / "pyproject.toml"
        toml_file.write_text(toml_content)

        manager.load_config("default")
        assert any("Literal password" in msg for msg in caplog.messages)

    def test_env_ref_no_warning(
        self, manager: DatabaseConfigManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """env: reference does not trigger literal warning."""
        caplog.set_level(logging.WARNING)

        toml_content = """
[tool.t4t.database]
type = "snowflake"
password = "env:SF_PW"
"""
        toml_file = manager.project_root / "pyproject.toml"
        toml_file.write_text(toml_content)

        with patch.dict(os.environ, {"SF_PW": "real-pw"}, clear=False):
            manager.load_config("default")
        assert not any("Literal" in msg for msg in caplog.messages)
