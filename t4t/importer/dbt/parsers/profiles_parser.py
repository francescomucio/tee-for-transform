"""
dbt profiles.yml parser.

Parses dbt profiles.yml file to extract connection information.
"""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from t4t.importer.dbt.constants import PROFILES_FILE
from t4t.importer.dbt.exceptions import DbtImporterError

logger = logging.getLogger(__name__)


class ProfilesParser:
    """Parser for dbt profiles.yml file."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize profiles parser.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def find_profiles_file(self, project_path: Path | None = None) -> Path | None:
        """
        Find profiles.yml file in standard locations.

        dbt looks for profiles.yml in:
        1. ~/.dbt/profiles.yml (default location)
        2. DBT_PROFILES_DIR environment variable
        3. Project directory (less common)

        Args:
            project_path: Optional project path to check

        Returns:
            Path to profiles.yml if found, None otherwise
        """
        # Check DBT_PROFILES_DIR environment variable first
        dbt_profiles_dir = os.environ.get("DBT_PROFILES_DIR")
        if dbt_profiles_dir:
            profiles_path = Path(dbt_profiles_dir) / PROFILES_FILE
            if profiles_path.exists():
                if self.verbose:
                    logger.info(f"Found profiles.yml at: {profiles_path} (from DBT_PROFILES_DIR)")
                return profiles_path

        # Check default location: ~/.dbt/profiles.yml
        default_profiles = Path.home() / ".dbt" / PROFILES_FILE
        if default_profiles.exists():
            if self.verbose:
                logger.info(f"Found profiles.yml at: {default_profiles} (default location)")
            return default_profiles

        # Check project directory (less common, but some projects have it)
        if project_path:
            project_profiles = project_path / PROFILES_FILE
            if project_profiles.exists():
                if self.verbose:
                    logger.info(f"Found profiles.yml at: {project_profiles} (project directory)")
                return project_profiles

        if self.verbose:
            logger.warning("profiles.yml not found in standard locations")
        return None

    def parse_profiles(self, profiles_path: Path) -> dict[str, Any]:
        """
        Parse profiles.yml file.

        Args:
            profiles_path: Path to profiles.yml file

        Returns:
            Dictionary mapping profile names to their configurations

        Raises:
            DbtImporterError: If parsing fails
        """
        try:
            with profiles_path.open("r", encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                raise DbtImporterError(f"profiles.yml is not a valid YAML dictionary")

            if self.verbose:
                logger.info(f"Parsed {len(content)} profile(s) from {profiles_path}")

            return content

        except yaml.YAMLError as e:
            raise DbtImporterError(f"Failed to parse profiles.yml: {e}") from e
        except Exception as e:
            raise DbtImporterError(f"Error reading profiles.yml: {e}") from e

    def get_profile_config(
        self, profile_name: str, profiles_data: dict[str, Any], target: str = "dev"
    ) -> dict[str, Any] | None:
        """
        Get configuration for a specific profile and target.

        Args:
            profile_name: Name of the profile (from dbt_project.yml)
            profiles_data: Parsed profiles.yml data
            target: Target name (default: "dev")

        Returns:
            Profile configuration dictionary or None if not found
        """
        if profile_name not in profiles_data:
            if self.verbose:
                logger.warning(f"Profile '{profile_name}' not found in profiles.yml")
            return None

        profile = profiles_data[profile_name]

        # Get outputs (targets) for this profile
        outputs = profile.get("outputs", {})
        if not outputs:
            if self.verbose:
                logger.warning(f"Profile '{profile_name}' has no outputs")
            return None

        # Get the specified target, or default to first target
        if target in outputs:
            target_config = outputs[target]
        elif len(outputs) == 1:
            # Only one target, use it
            target_config = list(outputs.values())[0]
            if self.verbose:
                logger.info(f"Using only available target in profile '{profile_name}'")
        else:
            # Try 'dev' as fallback
            if "dev" in outputs:
                target_config = outputs["dev"]
                if self.verbose:
                    logger.info(f"Target '{target}' not found, using 'dev'")
            else:
                # Use first available target
                target_config = list(outputs.values())[0]
                if self.verbose:
                    logger.warning(
                        f"Target '{target}' not found, using first available target: {list(outputs.keys())[0]}"
                    )

        return target_config

    def convert_to_t4t_connection(self, dbt_profile_config: dict[str, Any]) -> dict[str, Any]:
        """
        Convert dbt profile configuration to t4t connection format.

        Args:
            dbt_profile_config: dbt profile configuration dictionary

        Returns:
            t4t connection configuration dictionary
        """
        connection_type = dbt_profile_config.get("type", "").lower()

        # Map dbt connection types to t4t types
        type_mapping = {
            "postgres": "postgresql",
            "postgresql": "postgresql",
            "redshift": "postgresql",  # Redshift uses PostgreSQL protocol
            "snowflake": "snowflake",
            "bigquery": "bigquery",
            "duckdb": "duckdb",
            "sqlite": "sqlite",
        }

        t4t_type = type_mapping.get(connection_type, connection_type)

        # Build connection config based on type
        connection_config: dict[str, Any] = {"type": t4t_type}

        if connection_type in ("postgres", "postgresql", "redshift"):
            # PostgreSQL/Redshift connection
            connection_config["host"] = dbt_profile_config.get("host", "localhost")
            connection_config["port"] = dbt_profile_config.get("port", 5432)
            connection_config["database"] = dbt_profile_config.get("database", "")
            connection_config["user"] = dbt_profile_config.get("user", "")
            connection_config["password"] = dbt_profile_config.get("password", "")
            if "schema" in dbt_profile_config:
                connection_config["schema"] = dbt_profile_config["schema"]

        elif connection_type == "snowflake":
            # Snowflake connection
            connection_config["host"] = dbt_profile_config.get("account", "")
            if not connection_config["host"].endswith(".snowflakecomputing.com"):
                connection_config["host"] = f"{connection_config['host']}.snowflakecomputing.com"
            connection_config["user"] = dbt_profile_config.get("user", "")
            connection_config["password"] = dbt_profile_config.get("password", "")
            connection_config["role"] = dbt_profile_config.get("role", "")
            connection_config["warehouse"] = dbt_profile_config.get("warehouse", "")
            connection_config["database"] = dbt_profile_config.get("database", "")
            if "schema" in dbt_profile_config:
                connection_config["schema"] = dbt_profile_config["schema"]

        elif connection_type == "bigquery":
            # BigQuery connection
            connection_config["project"] = dbt_profile_config.get("project", "")
            connection_config["database"] = dbt_profile_config.get("dataset", "")
            # BigQuery may have method, keyfile, etc. - log if present
            if "method" in dbt_profile_config:
                if self.verbose:
                    logger.info(
                        "BigQuery authentication method will need to be configured manually"
                    )

        elif connection_type == "duckdb":
            # DuckDB connection
            connection_config["path"] = dbt_profile_config.get("path", "data/project.duckdb")
            if "schema" in dbt_profile_config:
                connection_config["schema"] = dbt_profile_config["schema"]

        elif connection_type == "sqlite":
            # SQLite connection
            connection_config["path"] = dbt_profile_config.get("path", "data/project.db")

        else:
            # Unknown type - preserve as much as possible
            if self.verbose:
                logger.warning(
                    f"Unknown connection type '{connection_type}', preserving all fields"
                )
            connection_config.update(dbt_profile_config)

        return connection_config
