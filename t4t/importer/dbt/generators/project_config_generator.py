"""
Project configuration generator for dbt importer.

Converts dbt_project.yml to t4t project.toml format.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ProjectConfigGenerator:
    """Generates t4t project.toml from dbt project configuration."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize project config generator.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def generate_project_toml(
        self,
        target_path: Path,
        dbt_project: dict[str, Any],  # noqa: ARG002
        connection_config: dict[str, Any] | None = None,
        packages_info: dict[str, Any] | None = None,
    ) -> None:
        """
        Generate project.toml file for t4t project.

        Args:
            target_path: Path where t4t project is created
            dbt_project: Parsed dbt project configuration
            connection_config: Connection configuration from profiles.yml (optional)
            packages_info: Information about dbt packages (optional)
        """
        project_folder = target_path.name

        # Build TOML content
        lines = [f'project_folder = "{project_folder}"', ""]

        # Connection section
        if connection_config:
            lines.append("[connection]")
            for key, value in sorted(connection_config.items()):
                if isinstance(value, str):
                    # Escape quotes in strings
                    escaped_value = value.replace('"', '\\"')
                    lines.append(f'{key} = "{escaped_value}"')
                elif isinstance(value, (int, float)):
                    lines.append(f"{key} = {value}")
                elif isinstance(value, bool):
                    lines.append(f"{key} = {str(value).lower()}")
                else:
                    # For other types, convert to string
                    lines.append(f'{key} = "{str(value)}"')
            lines.append("")
        else:
            # No connection config - use DuckDB default
            if self.verbose:
                logger.warning(
                    "No connection configuration found. Using DuckDB default. "
                    "Please update project.toml with your database connection."
                )
            lines.append("[connection]")
            lines.append('type = "duckdb"')
            lines.append(f'path = "data/{project_folder}.duckdb"')
            lines.append("")

        # Flags section
        lines.append("[flags]")
        lines.append(
            'materialization_change_behavior = "warn"  # Options: "warn", "error", "ignore"'
        )
        lines.append("")

        # Add comment about packages if present
        if packages_info and packages_info.get("packages"):
            lines.append("# Note: This project uses dbt packages:")
            for pkg in packages_info.get("packages", []):
                pkg_name = pkg.get("package", "unknown")
                pkg_version = pkg.get("version", "unknown")
                lines.append(f"#   - {pkg_name} (version: {pkg_version})")
            lines.append("# Package dependencies may need to be handled separately.")
            lines.append("")

        # Write project.toml
        project_toml_path = target_path / "project.toml"
        project_toml_path.write_text("\n".join(lines), encoding="utf-8")

        if self.verbose:
            logger.info(f"Generated project.toml at: {project_toml_path}")

    def generate_project_toml_from_profiles(
        self,
        target_path: Path,
        dbt_project: dict[str, Any],
        profiles_parser: Any,  # ProfilesParser
        target: str = "dev",
    ) -> dict[str, Any] | None:
        """
        Generate project.toml using profiles.yml.

        Args:
            target_path: Path where t4t project is created
            dbt_project: Parsed dbt project configuration
            profiles_parser: ProfilesParser instance
            target: Target name to use (default: "dev")

        Returns:
            Connection configuration dictionary if found, None otherwise
        """
        profile_name = dbt_project.get("profile")
        if not profile_name:
            if self.verbose:
                logger.warning("No profile name in dbt_project.yml, cannot load connection config")
            return None

        # Find and parse profiles.yml
        profiles_path = profiles_parser.find_profiles_file(target_path.parent)
        if not profiles_path:
            if self.verbose:
                logger.warning(
                    f"profiles.yml not found. Cannot extract connection configuration. "
                    f"Please configure connection manually in project.toml"
                )
            return None

        try:
            profiles_data = profiles_parser.parse_profiles(profiles_path)
            profile_config = profiles_parser.get_profile_config(profile_name, profiles_data, target)

            if not profile_config:
                if self.verbose:
                    logger.warning(
                        f"Profile '{profile_name}' not found in profiles.yml. "
                        f"Please configure connection manually in project.toml"
                    )
                return None

            # Convert to t4t format
            connection_config = profiles_parser.convert_to_t4t_connection(profile_config)

            return connection_config

        except Exception as e:
            if self.verbose:
                logger.warning(f"Error loading connection from profiles.yml: {e}")
            return None
