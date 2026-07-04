"""
Schema.yml parser for dbt projects.

Parses dbt schema.yml files and extracts model metadata.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class SchemaParser:
    """Parser for dbt schema.yml files."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize schema parser.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def parse_schema_file(self, schema_file: Path) -> dict[str, Any]:
        """
        Parse a schema.yml file and extract model definitions.

        Args:
            schema_file: Path to the schema.yml file

        Returns:
            Dictionary mapping model names to their metadata
        """
        models = {}

        try:
            with schema_file.open("r", encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                logger.warning(f"Schema file {schema_file} is not a valid YAML dictionary")
                return models

            # Extract models from the YAML
            if "models" in content:
                for model_def in content["models"]:
                    if not isinstance(model_def, dict) or "name" not in model_def:
                        continue

                    model_name = model_def["name"]
                    models[model_name] = model_def

            if self.verbose:
                logger.info(f"Parsed {len(models)} models from {schema_file}")

        except Exception as e:
            logger.warning(f"Error parsing schema file {schema_file}: {e}")

        return models

    def parse_all_schema_files(self, schema_files: dict[str, Path]) -> dict[str, Any]:
        """
        Parse all schema files and combine model definitions.

        Args:
            schema_files: Dictionary mapping relative paths to schema file Path objects

        Returns:
            Dictionary mapping model names to their metadata
        """
        all_models = {}

        for rel_path, schema_file in schema_files.items():
            models = self.parse_schema_file(schema_file)
            # Merge models (later files override earlier ones if same model name)
            all_models.update(models)

        if self.verbose:
            logger.info(
                f"Parsed {len(all_models)} total models from {len(schema_files)} schema files"
            )

        return all_models
