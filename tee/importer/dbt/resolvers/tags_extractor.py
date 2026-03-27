"""
Tags extractor for dbt models.

Extracts tags from schema.yml, config blocks, and dbt_project.yml for all models.
"""

import logging
from pathlib import Path
from typing import Any

from tee.importer.dbt.parsers import ConfigExtractor
from tee.importer.dbt.resolvers import SchemaResolver

logger = logging.getLogger(__name__)


def extract_model_tags(
    model_files: dict[str, Path],
    schema_metadata: dict[str, Any],
    dbt_project: dict[str, Any],  # noqa: ARG001
    schema_resolver: SchemaResolver | None = None,
    verbose: bool = False,
) -> dict[str, list[str]]:
    """
    Extract tags for all models from schema.yml, config blocks, and dbt_project.yml.

    Tags are collected additively from all sources (as dbt does):
    1. dbt_project.yml (models config) - lowest priority
    2. schema.yml (config block or root level)
    3. Model file config block ({{ config(tags=[...]) }}) - highest priority

    Args:
        model_files: Dictionary mapping relative paths to SQL model files
        schema_metadata: Parsed schema metadata from schema.yml files
        dbt_project: Parsed dbt project configuration
        schema_resolver: SchemaResolver instance (optional, for extracting project tags)
        verbose: Enable verbose logging

    Returns:
        Dictionary mapping model names to their tags
    """
    model_tags: dict[str, list[str]] = {}
    config_extractor = ConfigExtractor(verbose=verbose)

    for rel_path, sql_file in model_files.items():
        # Extract model name from file path (file name without extension)
        model_name = sql_file.stem

        tags: list[str] = []

        # 1. Tags from dbt_project.yml (lowest priority, added first)
        if schema_resolver:
            project_tags = schema_resolver.extract_tags_from_project_config(model_name, sql_file)
            if project_tags:
                tags.extend(project_tags)

        # 2. Tags from schema.yml (config block or root level)
        model_schema_metadata = schema_metadata.get(model_name)
        if model_schema_metadata:
            # Check config block first
            if "config" in model_schema_metadata and isinstance(
                model_schema_metadata["config"], dict
            ):
                config_tags = model_schema_metadata["config"].get("tags", [])
                if isinstance(config_tags, list):
                    tags.extend(config_tags)

            # Also check root level
            if "tags" in model_schema_metadata:
                root_tags = model_schema_metadata["tags"]
                if isinstance(root_tags, list):
                    tags.extend(root_tags)

        # 3. Tags from model file config block (highest priority, added last)
        try:
            sql_content = sql_file.read_text(encoding="utf-8")
            model_config = config_extractor.extract_config(sql_content)
            if model_config and "tags" in model_config:
                model_tags_list = model_config["tags"]
                if isinstance(model_tags_list, list):
                    tags.extend(model_tags_list)
        except Exception as e:
            if verbose:
                logger.debug(f"Could not read config from {sql_file}: {e}")

        # Remove duplicates while preserving order (first occurrence wins)
        from tee.importer.common.list_utils import deduplicate_preserve_order

        model_tags[model_name] = deduplicate_preserve_order(tags)

    if verbose:
        logger.info(f"Extracted tags for {len(model_tags)} models")

    return model_tags
