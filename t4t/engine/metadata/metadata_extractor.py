"""Metadata extraction from model and function data."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extracts and transforms metadata from model and function data."""

    def extract_model_metadata(self, model_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract metadata from model data, prioritizing nested metadata over file metadata.

        Args:
            model_data: Dictionary containing model data

        Returns:
            Metadata dictionary with column descriptions, tags, and other info, or None if no metadata found
        """
        try:
            # First, try to get metadata from model_metadata
            model_metadata = model_data.get("model_metadata", {})
            if model_metadata and "metadata" in model_metadata:
                nested_metadata = model_metadata["metadata"]

                # Check if this is incremental materialization
                if (
                    "materialization" in nested_metadata
                    and nested_metadata["materialization"] == "incremental"
                ):
                    # Extract tags if present
                    self._extract_tags_to_metadata(nested_metadata, model_metadata)
                    return nested_metadata

                if nested_metadata and "schema" in nested_metadata:
                    # Prioritize file metadata description over nested description
                    if "description" in model_metadata and "description" not in nested_metadata:
                        nested_metadata["description"] = model_metadata["description"]
                    # Extract tags if present
                    self._extract_tags_to_metadata(nested_metadata, model_metadata)
                    return nested_metadata
                elif (
                    nested_metadata
                    and "metadata" in nested_metadata
                    and "schema" in nested_metadata["metadata"]
                ):
                    # Handle deeply nested metadata structure
                    deep_nested_metadata = nested_metadata["metadata"]
                    if "description" in model_metadata:
                        deep_nested_metadata["description"] = model_metadata["description"]
                    # Extract tags if present
                    self._extract_tags_to_metadata(deep_nested_metadata, model_metadata)
                    return deep_nested_metadata

            # Fallback to any other metadata in the model data
            if "metadata" in model_data:
                file_metadata = model_data["metadata"]
                if file_metadata and "schema" in file_metadata:
                    # Use file metadata description if available
                    if "description" in model_metadata:
                        file_metadata["description"] = model_metadata["description"]
                    # Extract tags if present
                    self._extract_tags_to_metadata(file_metadata, model_metadata)
                    # If no decorator description, file metadata description is already there
                    return file_metadata

            return None

        except Exception as e:
            logger.warning(f"Error extracting metadata: {e}")
            return None

    def extract_function_metadata(self, function_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract metadata from function data.

        Args:
            function_data: Dictionary containing function data

        Returns:
            Metadata dictionary with tags, object_tags, and other info, or None if no metadata found
        """
        try:
            function_metadata = function_data.get("function_metadata", {})
            if not function_metadata:
                return None

            # Extract tags and object_tags from function metadata
            metadata = {}
            if "tags" in function_metadata:
                metadata["tags"] = function_metadata["tags"]
            if "object_tags" in function_metadata:
                metadata["object_tags"] = function_metadata["object_tags"]
            if "description" in function_metadata:
                metadata["description"] = function_metadata["description"]

            return metadata if metadata else None

        except Exception as e:
            logger.warning(f"Error extracting function metadata: {e}")
            return None

    def load_schema_metadata(self, schema_name: str, project_folder: str) -> dict[str, Any] | None:
        """
        Load schema-level metadata (tags, object_tags) from project config.

        Supports:
        - Module-level tags: [module] tags = [...]
        - Per-schema tags: [schemas.schema_name] tags = [...]
        - Per-schema object_tags: [schemas.schema_name] object_tags = {...}

        Args:
            schema_name: Name of the schema
            project_folder: Project folder path

        Returns:
            Dictionary with tags and object_tags, or None if no schema metadata found
        """
        try:
            import tomllib
            from pathlib import Path

            project_toml = Path(project_folder) / "project.toml"
            if not project_toml.exists():
                return None

            with open(project_toml, "rb") as f:
                project_config = tomllib.load(f)

            schema_metadata = {}

            # Check for per-schema configuration
            schemas_config = project_config.get("schemas", {})
            if isinstance(schemas_config, dict) and schema_name in schemas_config:
                schema_config = schemas_config[schema_name]
                if isinstance(schema_config, dict):
                    if "tags" in schema_config:
                        schema_metadata["tags"] = schema_config["tags"]
                    if "object_tags" in schema_config:
                        schema_metadata["object_tags"] = schema_config["object_tags"]

            # Fall back to module-level tags if no per-schema tags
            if not schema_metadata.get("tags") and not schema_metadata.get("object_tags"):
                if "module" in project_config:
                    module_config = project_config.get("module", {})
                    if isinstance(module_config, dict):
                        if "tags" in module_config:
                            schema_metadata["tags"] = module_config["tags"]
                        if "object_tags" in module_config:
                            schema_metadata["object_tags"] = module_config["object_tags"]

                # Also check root-level tags (as fallback even if module exists but has no tags)
                if not schema_metadata.get("tags") and "tags" in project_config:
                    # Root-level tags
                    root_tags = project_config.get("tags", [])
                    if isinstance(root_tags, list):
                        schema_metadata["tags"] = root_tags

            return schema_metadata if schema_metadata else None

        except Exception as e:
            logger.debug(f"Could not load schema metadata for {schema_name}: {e}")
            return None

    def _extract_tags_to_metadata(
        self, metadata: dict[str, Any], model_metadata: dict[str, Any]
    ) -> None:
        """
        Extract tags and object_tags from model metadata and ensure they're in the metadata dict.

        Args:
            metadata: Metadata dictionary to populate with tags
            model_metadata: Model metadata containing tags
        """
        nested_metadata = model_metadata.get("metadata", {})

        # Extract tags (dbt-style, list of strings) from nested metadata structure
        if "tags" not in metadata or not metadata.get("tags"):
            nested_tags = nested_metadata.get("tags", [])
            if nested_tags:
                metadata["tags"] = nested_tags

        # Extract object_tags (database-style, key-value pairs) from nested metadata structure
        if "object_tags" not in metadata or not metadata.get("object_tags"):
            nested_object_tags = nested_metadata.get("object_tags", {})
            if nested_object_tags and isinstance(nested_object_tags, dict):
                metadata["object_tags"] = nested_object_tags
