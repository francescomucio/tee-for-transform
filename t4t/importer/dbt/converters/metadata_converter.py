"""
Metadata converter from dbt format to t4t format.

Converts dbt model metadata (from schema.yml and model config) to t4t Python metadata format.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MetadataConverter:
    """Converts dbt metadata to t4t metadata format."""

    # Mapping from dbt data types to t4t data types
    DBT_TO_T4T_DATATYPE = {
        "text": "string",
        "varchar": "string",
        "char": "string",
        "string": "string",
        "integer": "integer",
        "int": "integer",
        "bigint": "integer",
        "smallint": "integer",
        "tinyint": "integer",
        "numeric": "number",
        "decimal": "number",
        "float": "float",
        "double": "float",
        "real": "float",
        "boolean": "boolean",
        "bool": "boolean",
        "timestamp": "timestamp",
        "timestamptz": "timestamp",
        "datetime": "timestamp",
        "date": "date",
        "time": "time",
        "json": "json",
        "jsonb": "json",
        "array": "array",
        "object": "object",
    }

    # Mapping from dbt materialization to t4t materialization
    DBT_TO_T4T_MATERIALIZATION = {
        "table": "table",
        "view": "view",
        "incremental": "incremental",
        "ephemeral": "view",  # Ephemeral models become views in t4t
        "materialized_view": "table",  # Materialized views become tables
    }

    # Mapping from dbt test names to t4t test names
    DBT_TO_T4T_TEST = {
        "not_null": "not_null",
        "unique": "unique",
        "accepted_values": "accepted_values",
        "relationships": "relationships",
        "expression": "expression",
        "dbt_utils.unique_combination_of_columns": "unique",  # Map to unique test
    }

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize metadata converter.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def convert_model_metadata(
        self,
        schema_metadata: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
        project_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Convert dbt model metadata to t4t format.

        Args:
            schema_metadata: Metadata from schema.yml file
            model_config: Model config from dbt_project.yml or model file
            project_tags: Tags from dbt_project.yml

        Returns:
            t4t metadata dictionary
        """
        metadata: dict[str, Any] = {}

        # Merge schema metadata and model config
        # Note: For most fields, model config takes precedence
        # But tags are ALWAYS additive in dbt (combine all sources)
        combined = {}
        if schema_metadata:
            combined.update(schema_metadata)
        if model_config:
            # For non-tag fields, model config takes precedence
            for key, value in model_config.items():
                if key != "tags":
                    combined[key] = value

        # Convert description
        if "description" in combined:
            metadata["description"] = combined["description"]

        # Convert materialization
        materialization = self._convert_materialization(combined)
        if materialization:
            metadata["materialization"] = materialization

        # Convert schema (columns)
        if "columns" in combined:
            metadata["schema"] = self._convert_columns(combined["columns"])

        # Convert tests (model-level tests)
        # dbt uses "data_tests" or "tests" for model-level tests
        model_tests = combined.get("data_tests") or combined.get("tests")
        if model_tests:
            metadata["tests"] = self._convert_tests(model_tests)

        # Convert tags - ALWAYS additive in dbt (combine all sources)
        all_tags = self._collect_tags_additively(schema_metadata, model_config, project_tags)
        if all_tags:
            metadata["tags"] = all_tags

        # Extract meta field from config (dbt's meta field for custom metadata)
        if (
            "config" in combined
            and isinstance(combined["config"], dict)
            and "meta" in combined["config"]
        ):
            # Store meta in metadata dict
            if "meta" not in metadata:
                metadata["meta"] = {}
            metadata["meta"].update(combined["config"]["meta"])

        # Also check for meta at root level
        if "meta" in combined:
            if "meta" not in metadata:
                metadata["meta"] = {}
            if isinstance(combined["meta"], dict):
                metadata["meta"].update(combined["meta"])

        # Convert incremental config if present
        warnings: list[str] = []
        if materialization == "incremental" and "config" in combined:
            incremental_config, config_warnings = self._convert_incremental_config(
                combined["config"]
            )
            if incremental_config:
                metadata["incremental"] = incremental_config
            warnings.extend(config_warnings)

        # Store warnings in metadata for reporting
        if warnings:
            if "warnings" not in metadata:
                metadata["warnings"] = []
            metadata["warnings"].extend(warnings)

        return metadata

    def _convert_materialization(self, combined: dict[str, Any]) -> str | None:
        """Convert dbt materialization to t4t materialization."""
        # Check in config first (from model file or dbt_project.yml)
        if "config" in combined and isinstance(combined["config"], dict):
            materialized = combined["config"].get("materialized")
        else:
            materialized = combined.get("materialized")

        if materialized:
            return self.DBT_TO_T4T_MATERIALIZATION.get(materialized, "table")
        return None

    def _convert_columns(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert dbt column definitions to t4t format."""
        converted = []

        for col in columns:
            if not isinstance(col, dict) or "name" not in col:
                continue

            col_def: dict[str, Any] = {
                "name": col["name"],
            }

            # Convert data type
            if "data_type" in col:
                col_def["datatype"] = self._convert_datatype(col["data_type"])
            elif "type" in col:
                col_def["datatype"] = self._convert_datatype(col["type"])
            else:
                # Default to string if no type specified
                col_def["datatype"] = "string"

            # Convert description
            if "description" in col:
                col_def["description"] = col["description"]

            # Convert tests (column-level tests)
            # dbt uses "data_tests" or "tests" for column-level tests
            col_tests = col.get("data_tests") or col.get("tests")
            if col_tests:
                col_def["tests"] = self._convert_tests(col_tests)

            converted.append(col_def)

        return converted

    def _convert_datatype(self, dbt_type: str) -> str:
        """Convert dbt data type to t4t data type."""
        # Normalize dbt type (lowercase, remove size/precision)
        normalized = dbt_type.lower().split("(")[0].strip()

        return self.DBT_TO_T4T_DATATYPE.get(normalized, "string")

    def _convert_tests(self, tests: list[Any]) -> list[Any]:
        """Convert dbt tests to t4t tests."""
        converted = []

        for test in tests:
            if isinstance(test, str):
                # Simple test name
                t4t_test = self.DBT_TO_T4T_TEST.get(test, test)
                converted.append(t4t_test)
            elif isinstance(test, dict):
                # Test with parameters
                test_name = test.get("test") or test.get("name")
                if test_name:
                    t4t_test_name = self.DBT_TO_T4T_TEST.get(test_name, test_name)
                    test_dict = {"name": t4t_test_name}
                    if "params" in test:
                        test_dict["params"] = test["params"]
                    if "severity" in test:
                        test_dict["severity"] = test["severity"]
                    converted.append(test_dict)
            else:
                # Unknown format, keep as-is
                converted.append(test)

        return converted

    def _convert_incremental_config(
        self, config: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """
        Convert dbt incremental config to t4t incremental config.

        Args:
            config: dbt incremental config dictionary

        Returns:
            Tuple of (converted config, list of warnings)
        """
        if not isinstance(config, dict):
            return None, []

        warnings: list[str] = []
        incremental_strategy = config.get("incremental_strategy", "append")
        unique_key = config.get("unique_key")
        on_schema_change = config.get("on_schema_change")

        # Map dbt incremental strategies to t4t
        strategy_map = {
            "append": "append",
            "merge": "merge",
            "delete+insert": "delete_insert",
        }

        # Check if strategy is supported
        if incremental_strategy not in strategy_map:
            # Check if it's a Spark-specific strategy
            if incremental_strategy == "insert_overwrite":
                warnings.append(
                    f"Unsupported incremental strategy: {incremental_strategy}. "
                    f"This is a Spark-specific strategy. Using 'append' as fallback. "
                    f"Search for the issue associated with Spark support or please create one."
                )
            else:
                warnings.append(
                    f"Unsupported incremental strategy: {incremental_strategy}. "
                    f"Using 'append' as fallback. "
                    f"Search for the issue associated with this missing feature or please create one."
                )
            t4t_strategy = "append"
        else:
            t4t_strategy = strategy_map[incremental_strategy]

        result: dict[str, Any] = {"strategy": t4t_strategy}

        if t4t_strategy == "merge" and unique_key:
            result["merge"] = {
                "unique_key": unique_key if isinstance(unique_key, list) else [unique_key],
                "filter_column": config.get("incremental_key", "updated_at"),
            }
        elif t4t_strategy == "append":
            result["append"] = {
                "filter_column": config.get("incremental_key", "updated_at"),
            }

        # Convert on_schema_change (OTS 0.2.1)
        if on_schema_change:
            # dbt uses same values as OTS 0.2.1, so we can pass through directly
            result["on_schema_change"] = on_schema_change

        return result, warnings

    def _collect_tags_additively(
        self,
        schema_metadata: dict[str, Any] | None,
        model_config: dict[str, Any] | None,
        project_tags: list[str] | None = None,
    ) -> list[str]:
        """
        Collect tags from all sources additively (as dbt does).

        Tags are always additive in dbt - they combine from:
        1. dbt_project.yml (models config) - lowest priority
        2. schema.yml (config block or root level)
        3. Model file config block ({{ config(tags=[...]) }}) - highest priority

        Args:
            schema_metadata: Metadata from schema.yml
            model_config: Config from model file
            project_tags: Tags from dbt_project.yml

        Returns:
            Combined list of unique tags (order: project -> schema -> model)
        """
        tags: list[str] = []

        # 1. Tags from dbt_project.yml (lowest priority, added first)
        if project_tags:
            tags.extend(project_tags)

        # 2. Tags from schema.yml (config block or root level)
        if schema_metadata:
            # Check config block first
            if "config" in schema_metadata and isinstance(schema_metadata["config"], dict):
                config_tags = schema_metadata["config"].get("tags", [])
                if isinstance(config_tags, list):
                    tags.extend(config_tags)

            # Also check root level
            if "tags" in schema_metadata:
                root_tags = schema_metadata["tags"]
                if isinstance(root_tags, list):
                    tags.extend(root_tags)

        # 3. Tags from model file config block (highest priority, added last)
        if model_config and "tags" in model_config:
            model_tags = model_config["tags"]
            if isinstance(model_tags, list):
                tags.extend(model_tags)

        # Remove duplicates while preserving order (first occurrence wins)
        from t4t.importer.common.list_utils import deduplicate_preserve_order

        return deduplicate_preserve_order(tags)
