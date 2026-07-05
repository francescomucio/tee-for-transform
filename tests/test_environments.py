"""Tests for first-class environments in project.toml ([environments.*])."""

import tempfile
from pathlib import Path

import pytest

from t4t.cli.utils import load_project_config
from t4t.engine.config import DatabaseConfigManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_toml_with_environments():
    """Create a project.toml with [environments.dev] and [environments.prod]."""
    content = """
project_folder = "my_project"
default_environment = "dev"

[environments.dev]
[environments.dev.connection]
type = "duckdb"
path = "data/dev.duckdb"
[environments.dev.variables]
row_limit = 1000
env_name = "dev"

[environments.prod]
protected = true
[environments.prod.connection]
type = "snowflake"
database = "ANALYTICS"
[environments.prod.variables]
row_limit = 0
env_name = "prod"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "project.toml"
        path.write_text(content)
        yield tmpdir


@pytest.fixture
def project_toml_legacy():
    """Create a project.toml with legacy [connection] section."""
    content = """
project_folder = "my_project"

[connection]
type = "duckdb"
path = "data/default.duckdb"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "project.toml"
        path.write_text(content)
        yield tmpdir


@pytest.fixture
def project_toml_no_environments():
    """Create a project.toml with no environments and no connection."""
    content = """
project_folder = "my_project"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "project.toml"
        path.write_text(content)
        yield tmpdir


# ---------------------------------------------------------------------------
# Tests: load_project_config
# ---------------------------------------------------------------------------


class TestLoadProjectConfigEnvironments:
    """Tests for load_project_config with [environments.*]."""

    def test_legacy_connection_still_works(self, project_toml_legacy):
        """Legacy [connection] section must keep working."""
        config = load_project_config(project_toml_legacy)
        assert config["connection"]["type"] == "duckdb"
        assert config["connection"]["path"] == "data/default.duckdb"

    def test_legacy_connection_with_vars(self, project_toml_legacy):
        """Legacy [connection] with CLI vars."""
        config = load_project_config(project_toml_legacy, vars_dict={"row_limit": 500})
        assert config["connection"]["type"] == "duckdb"
        assert config["vars"] == {"row_limit": 500}

    def test_environment_dev(self, project_toml_with_environments):
        """Load connection from [environments.dev]."""
        config = load_project_config(project_toml_with_environments, env_name="dev")
        assert config["connection"]["type"] == "duckdb"
        assert config["connection"]["path"] == "data/dev.duckdb"

    def test_environment_prod(self, project_toml_with_environments):
        """Load connection from [environments.prod]."""
        config = load_project_config(project_toml_with_environments, env_name="prod")
        assert config["connection"]["type"] == "snowflake"
        assert config["connection"]["database"] == "ANALYTICS"

    def test_environment_variables_merged(self, project_toml_with_environments):
        """Env-level variables are loaded."""
        config = load_project_config(project_toml_with_environments, env_name="dev")
        assert config["vars"]["row_limit"] == 1000
        assert config["vars"]["env_name"] == "dev"

    def test_environment_variables_cli_wins(self, project_toml_with_environments):
        """CLI vars override env-level variables."""
        config = load_project_config(
            project_toml_with_environments,
            env_name="dev",
            vars_dict={"row_limit": 999, "cli_override": True},
        )
        # CLI value wins
        assert config["vars"]["row_limit"] == 999
        # Env-level var still present
        assert config["vars"]["env_name"] == "dev"
        # CLI-only var present
        assert config["vars"]["cli_override"] is True

    def test_unknown_environment_error(self, project_toml_with_environments):
        """Unknown env name raises ValueError listing available envs."""
        with pytest.raises(ValueError, match="Unknown environment 'nonexistent'"):
            load_project_config(project_toml_with_environments, env_name="nonexistent")

    def test_unknown_environment_lists_available(self, project_toml_with_environments):
        """Error message lists available environments."""
        with pytest.raises(ValueError, match="Available environments: dev, prod"):
            load_project_config(project_toml_with_environments, env_name="nonexistent")

    def test_legacy_missing_connection_error(self, project_toml_no_environments):
        """Legacy mode without [connection] raises error."""
        with pytest.raises(ValueError, match="project.toml must contain 'connection'"):
            load_project_config(project_toml_no_environments)

    def test_default_environment_used_when_no_env_specified(self, project_toml_with_environments):
        """default_environment is used when no env is specified."""
        config = load_project_config(project_toml_with_environments)
        assert config["connection"]["type"] == "duckdb"
        assert config["connection"]["path"] == "data/dev.duckdb"
        assert config["vars"]["row_limit"] == 1000

    def test_default_environment_overridden_by_explicit_env(self, project_toml_with_environments):
        """Explicit env_name overrides default_environment."""
        config = load_project_config(project_toml_with_environments, env_name="prod")
        assert config["connection"]["type"] == "snowflake"
        assert config["connection"]["database"] == "ANALYTICS"
        assert config["vars"]["row_limit"] == 0


# ---------------------------------------------------------------------------
# Tests: DatabaseConfigManager
# ---------------------------------------------------------------------------


class TestDatabaseConfigManagerEnvironments:
    """Tests for DatabaseConfigManager with [environments.*]."""

    def test_legacy_connection(self, project_toml_legacy):
        """Legacy [connection] still works via DatabaseConfigManager."""
        manager = DatabaseConfigManager(project_root=project_toml_legacy)
        config = manager.load_config()
        assert config.type == "duckdb"
        assert config.path == "data/default.duckdb"

    def test_environment_dev(self, project_toml_with_environments):
        """Load from [environments.dev] via DatabaseConfigManager."""
        manager = DatabaseConfigManager(project_root=project_toml_with_environments)
        config = manager.load_config(env_name="dev")
        assert config.type == "duckdb"
        assert config.path == "data/dev.duckdb"

    def test_environment_prod(self, project_toml_with_environments):
        """Load from [environments.prod] via DatabaseConfigManager."""
        manager = DatabaseConfigManager(project_root=project_toml_with_environments)
        config = manager.load_config(env_name="prod")
        assert config.type == "snowflake"
        assert config.database == "ANALYTICS"

    def test_unknown_environment_error(self, project_toml_with_environments):
        """Unknown env name raises ValueError."""
        manager = DatabaseConfigManager(project_root=project_toml_with_environments)
        with pytest.raises(ValueError, match="Unknown environment 'bad'"):
            manager.load_config(env_name="bad")

    def test_unknown_environment_lists_available(self, project_toml_with_environments):
        """Error message lists available environments."""
        manager = DatabaseConfigManager(project_root=project_toml_with_environments)
        with pytest.raises(ValueError, match="Available environments: dev, prod"):
            manager.load_config(env_name="bad")

    def test_no_toml_file(self):
        """No TOML file returns empty config (no error)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DatabaseConfigManager(project_root=tmpdir)
            with pytest.raises(ValueError, match="No database configuration found"):
                manager.load_config(env_name="dev")

    def test_default_environment_via_manager(self, project_toml_with_environments):
        """DatabaseConfigManager uses default_environment when no env_name given."""
        manager = DatabaseConfigManager(project_root=project_toml_with_environments)
        config = manager.load_config()
        assert config.type == "duckdb"
        assert config.path == "data/dev.duckdb"
        # _env_variables and _protected should be in extra
        assert config.extra is not None
        assert config.extra.get("env_variables", {}).get("row_limit") == 1000

    def test_default_environment_overridden_via_manager(self, project_toml_with_environments):
        """Explicit env_name overrides default_environment in DatabaseConfigManager."""
        manager = DatabaseConfigManager(project_root=project_toml_with_environments)
        config = manager.load_config(env_name="prod")
        assert config.type == "snowflake"
        assert config.database == "ANALYTICS"
        # protected flag should be in extra
        assert config.extra is not None
        assert config.extra.get("protected") is True
