"""
Schema resolver for dbt models.

Resolves final schema names based on dbt_project.yml configuration, profiles.yml,
and folder structure, following dbt's schema resolution logic.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.importer.common.path_utils import extract_schema_from_path
from t4t.importer.dbt.constants import DEFAULT_DBT_SCHEMA, MODELS_DIR

logger = logging.getLogger(__name__)


class SchemaResolver:
    """Resolves schema names for dbt models following dbt's logic."""

    def __init__(
        self,
        dbt_project: dict[str, Any],
        profile_schema: str | None = None,
        default_schema: str = "public",
        verbose: bool = False,
    ) -> None:
        """
        Initialize schema resolver.

        Args:
            dbt_project: Parsed dbt project configuration
            profile_schema: Schema from profiles.yml target (optional)
            default_schema: Default schema if none found (default: "public")
            verbose: Enable verbose logging
        """
        self.dbt_project = dbt_project
        self.profile_schema = profile_schema
        self.default_schema = default_schema
        self.verbose = verbose

        # Extract models configuration from dbt_project.yml
        self.models_config = self._extract_models_config()

    def _extract_models_config(self) -> dict[str, Any]:
        """
        Extract models configuration from dbt_project.yml.

        Returns:
            Dictionary with model configurations organized by folder/model path
        """
        raw_config = self.dbt_project.get("raw_config", {})
        models_section = raw_config.get("models", {})

        # models_section can be:
        # - A dict with project name as key: { "my_project": { "staging": { "+schema": "staging" } } }
        # - A dict directly: { "staging": { "+schema": "staging" } }
        # - None/empty

        if not models_section:
            return {}

        # If it's a dict with project name, extract the inner config
        project_name = self.dbt_project.get("name")
        if project_name and project_name in models_section:
            models_config = models_section[project_name]
        elif isinstance(models_section, dict):
            models_config = models_section
        else:
            return {}

        return models_config

    def resolve_schema(
        self,
        model_name: str,
        model_path: Path,
        schema_metadata: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> str:
        """
        Resolve final schema name for a model.

        Priority (like dbt, most specific wins):
        1. Config block in model file ({{ config(schema='custom') }})
        2. Model YAML (schema.yml) - config block or root level
        3. dbt_project.yml - most specific match (model > nested folder > folder)
        4. Profile/Default schema

        dbt does NOT concatenate multiple folder-level schemas.
        It uses the MOST SPECIFIC match and combines only with target.schema.

        Args:
            model_name: Name of the dbt model
            model_path: Path to the model file
            schema_metadata: Metadata from schema.yml (optional)
            model_config: Config block from model file ({{ config(...) }}) (optional)

        Returns:
            Final schema name
        """
        # Start with profile schema (if available) - this is dbt's target.schema
        # Default in dbt is "dev" if no profile schema is specified
        # Note: Profile schema support is not yet implemented in t4t, but we use it for schema resolution
        # In t4t, schema configuration should be done via project.toml
        base_schema = self.profile_schema or DEFAULT_DBT_SCHEMA

        # Priority 1: Config block in model file (highest priority)
        model_file_schema = None
        if model_config:
            # Check for schema or +schema in model config
            model_file_schema = self._extract_schema_from_config(model_config)

        # Priority 2: Get schema from model YAML (schema.yml)
        # Note: schema and +schema are aliases in dbt, both combine with target.schema
        yaml_schema = self._extract_schema_from_yaml_metadata(schema_metadata)

        # Priority 3: Get MOST SPECIFIC schema from project config (dbt_project.yml)
        # This finds the most specific match (model > nested folder > folder)
        # and does NOT concatenate multiple folder schemas
        project_schema = self._get_most_specific_schema_from_project_config(model_name, model_path)

        # Determine final schema: most specific wins (Model Config > YAML > Project Config)
        # Both schema and +schema combine with base schema (they are aliases)
        custom_schema = None

        if model_file_schema:
            # Model file config has highest priority
            custom_schema = model_file_schema
        elif yaml_schema:
            # YAML is next priority
            custom_schema = yaml_schema
        elif project_schema:
            # Project config is next priority
            custom_schema = project_schema

        # Apply schema: always combine with base schema (schema and +schema are aliases)
        # Both schema and +schema combine with base (like generate_schema_name)
        final_schema = f"{base_schema}_{custom_schema}" if custom_schema else base_schema

        # Fallback to folder structure if nothing found and using default
        if final_schema == "dev" or final_schema == self.default_schema:
            folder_schema = self._get_schema_from_folder_structure(model_path)
            if folder_schema:
                final_schema = folder_schema

        if self.verbose:
            logger.debug(f"Resolved schema for {model_name}: {final_schema}")

        return final_schema

    def _get_most_specific_schema_from_project_config(
        self, model_name: str, model_path: Path
    ) -> str | None:
        """
        Get the MOST SPECIFIC schema from dbt_project.yml models configuration.

        dbt does NOT concatenate multiple folder-level schemas.
        It uses the most specific match:
        - Model-level: models.my_project.staging.my_model.schema (most specific)
        - Nested folder: models.my_project.staging.intermediate.schema
        - Folder-level: models.my_project.staging.schema (least specific)

        Note: schema and +schema are aliases in dbt, both combine with target.schema.

        Args:
            model_name: Name of the model
            model_path: Path to the model file

        Returns:
            Schema name if found, None otherwise.
        """
        if not self.models_config:
            return None

        # Build path from model file to match dbt_project.yml structure
        # e.g., models/staging/intermediate/my_model.sql -> ["staging", "intermediate"]
        rel_path = self._get_model_relative_path(model_path)
        path_parts = self._get_path_parts_from_file(rel_path)

        # Check model-specific schema first (most specific)
        model_schema = self._get_model_specific_schema(model_name, path_parts)
        if model_schema:
            return model_schema

        # If no model-specific schema, check nested folders (more specific than root folder)
        return self._get_folder_schema(path_parts)

    def _get_model_specific_schema(self, model_name: str, path_parts: list[str]) -> str | None:
        """
        Get model-specific schema configuration.

        Args:
            model_name: Name of the model
            path_parts: Folder path parts from model file

        Returns:
            Schema value if found, None otherwise
        """
        # Navigate to the model's folder first
        current_config = self.models_config
        for part in path_parts:
            if isinstance(current_config, dict) and part in current_config:
                folder_config = current_config[part]
                if isinstance(folder_config, dict):
                    current_config = folder_config
                else:
                    return None
            else:
                return None

        # Check for model-specific schema (most specific - level 2)
        if isinstance(current_config, dict) and model_name in current_config:
            model_config = current_config[model_name]
            if isinstance(model_config, dict):
                return self._extract_schema_from_config(model_config)

        return None

    def _get_folder_schema(self, path_parts: list[str]) -> str | None:
        """
        Get schema from folder configuration (most specific folder wins).

        Args:
            path_parts: Folder path parts from model file

        Returns:
            Most specific schema value if found, None otherwise
        """
        most_specific_schema = None
        most_specific_level = -1  # Track specificity (higher = more specific)

        current_config = self.models_config
        for i, part in enumerate(path_parts):
            if isinstance(current_config, dict) and part in current_config:
                folder_config = current_config[part]
                if isinstance(folder_config, dict):
                    # Check for schema in this folder level
                    # Deeper folders are more specific (higher index = more specific)
                    schema = self._extract_schema_from_config(folder_config)
                    if schema and i > most_specific_level:
                        most_specific_schema = schema
                        most_specific_level = i
                    # Continue to next level
                    current_config = folder_config
                else:
                    break
            else:
                break

        return most_specific_schema

    def extract_tags_from_project_config(self, model_name: str, model_path: Path) -> list[str]:
        """
        Extract tags from dbt_project.yml models configuration (most specific match).

        Args:
            model_name: Name of the model
            model_path: Path to the model file

        Returns:
            List of tags if found, empty list otherwise
        """
        if not self.models_config:
            return []

        # Build path from model file to match dbt_project.yml structure
        rel_path = self._get_model_relative_path(model_path)
        path_parts = self._get_path_parts_from_file(rel_path)

        # Navigate to model's location in config
        current_config = self.models_config
        for part in path_parts:
            if isinstance(current_config, dict) and part in current_config:
                folder_config = current_config[part]
                if isinstance(folder_config, dict):
                    current_config = folder_config
                else:
                    break
            else:
                break

        # Check for model-specific tags first (most specific)
        if isinstance(current_config, dict) and model_name in current_config:
            model_config = current_config[model_name]
            if isinstance(model_config, dict) and "tags" in model_config:
                tags = model_config["tags"]
                if isinstance(tags, list):
                    return tags

        # Check folder-level tags (less specific)
        all_tags = self._collect_folder_tags(path_parts)

        # Remove duplicates while preserving order
        from t4t.importer.common.list_utils import deduplicate_preserve_order

        return deduplicate_preserve_order(all_tags)

    def _collect_folder_tags(self, path_parts: list[str]) -> list[str]:
        """
        Collect tags from folder-level configuration.

        Args:
            path_parts: Folder path parts from model file

        Returns:
            List of tags from folder configurations
        """
        all_tags: list[str] = []
        current_config = self.models_config
        for part in path_parts:
            if isinstance(current_config, dict) and part in current_config:
                folder_config = current_config[part]
                if isinstance(folder_config, dict):
                    if "tags" in folder_config:
                        folder_tags = folder_config["tags"]
                        if isinstance(folder_tags, list):
                            all_tags.extend(folder_tags)
                    current_config = folder_config
                else:
                    break
            else:
                break

        return all_tags

    def _extract_schema_from_config(self, config: dict[str, Any]) -> str | None:
        """
        Extract schema value from config dict (checks +schema and schema).

        Args:
            config: Configuration dictionary

        Returns:
            Schema value if found, None otherwise
        """
        # schema and +schema are aliases in dbt
        if "+schema" in config:
            return config["+schema"]
        if "schema" in config:
            return config["schema"]
        return None

    def _extract_schema_from_yaml_metadata(
        self, schema_metadata: dict[str, Any] | None
    ) -> str | None:
        """
        Extract schema from schema.yml metadata.

        Checks config block first (most specific), then root level.

        Args:
            schema_metadata: Metadata from schema.yml

        Returns:
            Schema value if found, None otherwise
        """
        if not schema_metadata:
            return None

        # Check for schema in config block first (most specific in YAML)
        config = schema_metadata.get("config", {})
        schema = self._extract_schema_from_config(config)
        if schema:
            return schema

        # Also check root level (some dbt projects put it there)
        return self._extract_schema_from_config(schema_metadata)

    def _get_model_relative_path(self, model_path: Path) -> Path:
        """
        Get model path relative to models directory.

        Args:
            model_path: Absolute path to model file

        Returns:
            Relative path from models/ directory
        """
        parts = model_path.parts
        if MODELS_DIR in parts:
            models_idx = parts.index(MODELS_DIR)
            # Get everything after models/
            rel_parts = parts[models_idx + 1 :]
            # Reconstruct path (but we only need the directory parts, not the filename)
            return Path(*rel_parts[:-1])  # Remove filename, keep only folder path
        return Path()

    def _get_path_parts_from_file(self, rel_path: Path) -> list[str]:
        """
        Extract folder path parts from relative path.

        Args:
            rel_path: Relative path from models/ directory

        Returns:
            List of folder names
        """
        if not rel_path or rel_path == Path("."):
            return []
        return [part for part in rel_path.parts if part]

    def _get_schema_from_folder_structure(self, model_path: Path) -> str | None:
        """
        Extract schema from folder structure as fallback.

        Args:
            model_path: Path to model file

        Returns:
            Schema name if found in folder structure, None otherwise
        """
        # Use common path utility to avoid code duplication
        return extract_schema_from_path(model_path, MODELS_DIR)
