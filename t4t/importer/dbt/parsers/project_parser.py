"""
dbt project parser.

Parses dbt_project.yml and validates dbt project structure.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from t4t.importer.dbt.constants import (
    DBT_PROJECT_FILE,
    MACROS_DIR,
    MODELS_DIR,
    SEEDS_DIR,
    TESTS_DIR,
)
from t4t.importer.dbt.exceptions import DbtProjectNotFoundError

logger = logging.getLogger(__name__)


class DbtProjectParser:
    """Parser for dbt project configuration and structure."""

    def __init__(self, project_path: Path, verbose: bool = False) -> None:
        """
        Initialize dbt project parser.

        Args:
            project_path: Path to the dbt project directory
            verbose: Enable verbose logging
        """
        self.project_path = Path(project_path).resolve()
        self.verbose = verbose
        self.dbt_project_file = self.project_path / DBT_PROJECT_FILE

        if not self.dbt_project_file.exists():
            raise DbtProjectNotFoundError(f"{DBT_PROJECT_FILE} not found in {self.project_path}")

    def parse(self) -> dict[str, Any]:
        """
        Parse dbt project configuration.

        Returns:
            Dictionary containing parsed dbt project configuration
        """
        if self.verbose:
            logger.info(f"Parsing dbt project: {self.project_path}")

        # Parse dbt_project.yml
        with self.dbt_project_file.open("r", encoding="utf-8") as f:
            dbt_config = yaml.safe_load(f)

        if not isinstance(dbt_config, dict):
            raise DbtProjectNotFoundError(f"{DBT_PROJECT_FILE} is not a valid YAML dictionary")

        if "name" not in dbt_config:
            raise DbtProjectNotFoundError(f"{DBT_PROJECT_FILE} missing required 'name' field")

        # Validate project structure
        self._validate_structure()

        return {
            "name": dbt_config.get("name"),
            "version": dbt_config.get("version"),
            "profile": dbt_config.get("profile-name"),
            "model-paths": dbt_config.get("model-paths", [MODELS_DIR]),
            "test-paths": dbt_config.get("test-paths", [TESTS_DIR]),
            "seed-paths": dbt_config.get("seed-paths", [SEEDS_DIR]),
            "macro-paths": dbt_config.get("macro-paths", [MACROS_DIR]),
            "analysis-paths": dbt_config.get("analysis-paths", ["analyses"]),
            "snapshot-paths": dbt_config.get("snapshot-paths", ["snapshots"]),
            "target-path": dbt_config.get("target-path", "target"),
            "clean-targets": dbt_config.get("clean-targets", ["target", "dbt_packages"]),
            "config-version": dbt_config.get("config-version", 2),
            "vars": dbt_config.get("vars", {}),
            "raw_config": dbt_config,
        }

    def _validate_structure(self) -> None:
        """Validate that the dbt project has the expected structure."""
        # Check for common dbt directories (at least one should exist)
        common_dirs = [MODELS_DIR, TESTS_DIR, MACROS_DIR, SEEDS_DIR, "snapshots", "analyses"]
        found_dirs = [d for d in common_dirs if (self.project_path / d).exists()]

        if not found_dirs:
            logger.warning(
                f"No common dbt directories found in {self.project_path}. "
                "This might not be a valid dbt project."
            )

        if self.verbose:
            logger.info(f"Found dbt directories: {', '.join(found_dirs)}")
