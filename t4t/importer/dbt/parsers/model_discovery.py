"""
Model file discovery for dbt projects.

Discovers and organizes SQL model files from dbt project structure.
"""

import logging
from pathlib import Path

from t4t.importer.dbt.constants import MODELS_DIR, SOURCES_FILE, YAML_ALT_EXTENSION, YAML_EXTENSION

logger = logging.getLogger(__name__)


class ModelFileDiscovery:
    """Discovers model files in a dbt project."""

    def __init__(self, project_path: Path, model_paths: list[str] | None = None) -> None:
        """
        Initialize model file discovery.

        Args:
            project_path: Path to the dbt project root
            model_paths: List of model paths from dbt_project.yml (default: [MODELS_DIR])
        """
        self.project_path = Path(project_path).resolve()
        self.model_paths = model_paths or [MODELS_DIR]

    def discover_models(self) -> dict[str, Path]:
        """
        Discover all SQL model files in the dbt project.

        Returns:
            Dictionary mapping model file paths (relative to project) to full Path objects
        """
        models = {}

        for model_path_str in self.model_paths:
            model_path = self.project_path / model_path_str

            if not model_path.exists():
                logger.debug(f"Model path does not exist: {model_path}")
                continue

            # Recursively find all .sql files
            for sql_file in model_path.rglob("*.sql"):
                # Skip files in test directories or other special directories
                if self._should_skip_file(sql_file):
                    continue

                # Get relative path from project root
                rel_path = sql_file.relative_to(self.project_path)
                models[str(rel_path)] = sql_file

        logger.info(f"Discovered {len(models)} SQL model files")
        return models

    def _should_skip_file(self, file_path: Path) -> bool:
        """
        Determine if a file should be skipped.

        Args:
            file_path: Path to the file

        Returns:
            True if file should be skipped
        """
        # Skip files in common test/exclude directories
        skip_dirs = {"__pycache__", ".git", "target", "dbt_packages", ".dbt"}
        parts = file_path.parts

        for part in parts:
            if part in skip_dirs:
                return True

        return False

    def discover_schema_files(self) -> dict[str, Path]:
        """
        Discover all schema.yml files in the dbt project.

        Returns:
            Dictionary mapping schema file paths (relative to project) to full Path objects
        """
        schema_files = {}

        for model_path_str in self.model_paths:
            model_path = self.project_path / model_path_str

            if not model_path.exists():
                continue

            # Find all YAML files (schema.yml, _schema.yml, etc.)
            for yaml_file in model_path.rglob(f"*{YAML_EXTENSION}"):
                if self._should_skip_file(yaml_file):
                    continue

                rel_path = yaml_file.relative_to(self.project_path)
                schema_files[str(rel_path)] = yaml_file

            # Also check for .yaml files
            for yaml_file in model_path.rglob(f"*{YAML_ALT_EXTENSION}"):
                if self._should_skip_file(yaml_file):
                    continue

                rel_path = yaml_file.relative_to(self.project_path)
                schema_files[str(rel_path)] = yaml_file

        logger.info(f"Discovered {len(schema_files)} schema YAML files")
        return schema_files

    def discover_source_files(self) -> list[Path]:
        """
        Discover all __sources.yml files in the dbt project.

        Returns:
            List of source file Path objects
        """
        source_files = []

        for model_path_str in self.model_paths:
            model_path = self.project_path / model_path_str

            if not model_path.exists():
                continue

            # Find __sources.yml files
            for source_file in model_path.rglob(SOURCES_FILE):
                if not self._should_skip_file(source_file):
                    source_files.append(source_file)

            # Also check for __sources.yaml
            for source_file in model_path.rglob(
                SOURCES_FILE.replace(YAML_EXTENSION, YAML_ALT_EXTENSION)
            ):
                if not self._should_skip_file(source_file):
                    source_files.append(source_file)

        logger.info(f"Discovered {len(source_files)} source YAML files")
        return source_files
