"""
Metadata schema definitions and validation for SQL models.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from t4t.typing.metadata import (
    ColumnTestName,
    DataType,
    FKReference,
    HierarchyDefinition,
    IncrementalConfig,
    MaterializationType,
    ModelMetadata,
    ModelTestName,
    TableType,
)

logger = logging.getLogger(__name__)


@dataclass
class ColumnSchema:
    """Schema definition for a table column."""

    name: str
    datatype: DataType
    description: str | None = None
    tests: list[ColumnTestName] | None = None
    fk_to: FKReference | None = None
    dimension: str | None = None

    def __post_init__(self):
        """Validate required fields after initialization."""
        if not self.name:
            raise ValueError("Column name is required")
        if not self.datatype:
            raise ValueError("Column datatype is required")
        if self.tests is None:
            self.tests = []

        if self.dimension is not None and not isinstance(self.dimension, str):
            raise ValueError("dimension must be a string")


@dataclass
class ValidatedModelMetadata:
    """Validated metadata definition for a SQL model (internal use)."""

    description: str | None = None
    schema: list[ColumnSchema] | None = None
    partitions: list[str] | None = None
    materialization: MaterializationType | None = None
    tests: list[ModelTestName] | None = None
    incremental: IncrementalConfig | None = None
    table_type: TableType | None = None
    data_model: bool | None = None
    hierarchy: HierarchyDefinition | None = None
    conformed_dimension: dict[str, str] | None = None
    disable_default_tests: bool | list[str] | None = None

    def __post_init__(self):
        """Validate metadata after initialization."""
        if self.materialization and self.materialization not in ["table", "view", "incremental"]:
            raise ValueError(
                f"Invalid materialization type: {self.materialization}. Must be one of: table, view, incremental"
            )
        if self.tests is None:
            self.tests = []
        if self.partitions is None:
            self.partitions = []

        if self.disable_default_tests is not None:
            if not isinstance(self.disable_default_tests, (bool, list)):
                raise ValueError("disable_default_tests must be a bool or list[str]")

        # Validate incremental configuration if present
        if self.incremental:
            self._validate_incremental_config()

    def _validate_incremental_config(self):
        """Validate incremental configuration."""
        if not self.incremental:
            return

        strategy = self.incremental.get("strategy")
        if not strategy:
            raise ValueError("Incremental strategy is required when incremental config is provided")

        if strategy not in ["append", "merge", "delete_insert"]:
            raise ValueError(
                f"Invalid incremental strategy: {strategy}. Must be one of: append, merge, delete_insert"
            )

        # Validate strategy-specific configuration
        if strategy == "append":
            if "append" not in self.incremental or not self.incremental["append"]:
                raise ValueError("Append strategy requires 'append' configuration")
            append_config = self.incremental["append"]
            if "filter_column" not in append_config:
                raise ValueError("Append strategy requires 'filter_column' in append configuration")

        elif strategy == "merge":
            if "merge" not in self.incremental or not self.incremental["merge"]:
                raise ValueError("Merge strategy requires 'merge' configuration")
            merge_config = self.incremental["merge"]
            if "unique_key" not in merge_config or not merge_config["unique_key"]:
                raise ValueError("Merge strategy requires 'unique_key' in merge configuration")
            if "filter_column" not in merge_config:
                raise ValueError("Merge strategy requires 'filter_column' in merge configuration")

        elif strategy == "delete_insert":
            if "delete_insert" not in self.incremental or not self.incremental["delete_insert"]:
                raise ValueError("Delete+insert strategy requires 'delete_insert' configuration")
            delete_insert_config = self.incremental["delete_insert"]
            if "where_condition" not in delete_insert_config:
                raise ValueError(
                    "Delete+insert strategy requires 'where_condition' in delete_insert configuration"
                )
            if "filter_column" not in delete_insert_config:
                raise ValueError(
                    "Delete+insert strategy requires 'filter_column' in delete_insert configuration"
                )


def validate_metadata_dict(metadata_dict: ModelMetadata) -> ValidatedModelMetadata:
    """
    Validate and convert a metadata dictionary to ValidatedModelMetadata object.

    Args:
        metadata_dict: Dictionary containing metadata (TypedDict ModelMetadata)

    Returns:
        Validated ValidatedModelMetadata object (dataclass)

    Raises:
        ValueError: If metadata is invalid
    """
    try:
        # Validate schema if present
        schema = None
        if "schema" in metadata_dict and metadata_dict["schema"]:
            if not isinstance(metadata_dict["schema"], list):
                raise ValueError("Schema must be a list of column definitions")

            schema = []
            for col_dict in metadata_dict["schema"]:
                if not isinstance(col_dict, dict):
                    raise ValueError("Each column in schema must be a dictionary")

                # Validate required fields
                if "name" not in col_dict:
                    raise ValueError("Column name is required")
                if "datatype" not in col_dict:
                    raise ValueError("Column datatype is required")

                schema.append(
                    ColumnSchema(
                        name=col_dict["name"],
                        datatype=col_dict["datatype"],
                        description=col_dict.get("description"),
                        tests=col_dict.get("tests", []),
                        fk_to=col_dict.get("fk_to"),
                        dimension=col_dict.get("dimension"),
                    )
                )

        # Validate other fields
        partitions = metadata_dict.get("partitions")
        if partitions is not None and not isinstance(partitions, list):
            raise ValueError("Partitions must be a list")

        materialization = metadata_dict.get("materialization")
        if materialization is not None and not isinstance(materialization, str):
            raise ValueError("Materialization must be a string")

        table_type = metadata_dict.get("table_type")
        if table_type is not None:
            if table_type not in ["fact", "dim", "lookup", "dimension"]:
                raise ValueError("Invalid table_type; must be one of: fact, dim, lookup, dimension")

        data_model = metadata_dict.get("data_model")
        if data_model is not None and not isinstance(data_model, bool):
            raise ValueError("data_model must be a boolean")

        hierarchy = metadata_dict.get("hierarchy")
        if hierarchy is not None and not isinstance(hierarchy, dict):
            raise ValueError("hierarchy must be a dict")

        conformed_dimension = metadata_dict.get("conformed_dimension")
        if conformed_dimension is not None:
            if not isinstance(conformed_dimension, dict):
                raise ValueError("conformed_dimension must be a dict")
            log = conformed_dimension.get("logical")
            lev = conformed_dimension.get("level")
            if not isinstance(log, str) or not isinstance(lev, str):
                raise ValueError("conformed_dimension requires string 'logical' and 'level'")

        disable_default_tests = metadata_dict.get("disable_default_tests")
        if disable_default_tests is not None and not isinstance(
            disable_default_tests, (bool, list)
        ):
            raise ValueError("disable_default_tests must be a bool or list[str]")

        tests = metadata_dict.get("tests")
        if tests is not None and not isinstance(tests, list):
            raise ValueError("Tests must be a list")

        # Validate incremental configuration if present
        incremental = metadata_dict.get("incremental")
        if incremental is not None and not isinstance(incremental, dict):
            raise ValueError("Incremental configuration must be a dictionary")

        return ValidatedModelMetadata(
            description=metadata_dict.get("description"),
            schema=schema,
            partitions=partitions,
            materialization=materialization,
            tests=tests,
            incremental=incremental,
            table_type=table_type,
            data_model=data_model,
            hierarchy=hierarchy,
            conformed_dimension=conformed_dimension,
            disable_default_tests=disable_default_tests,
        )

    except Exception as e:
        raise ValueError(f"Invalid metadata format: {str(e)}") from e


def parse_metadata_from_python_file(file_path: str) -> dict[str, Any] | None:
    """
    Parse metadata from a Python file containing a metadata object.
    Uses execution-based parsing (requires file to be executable).

    Args:
        file_path: Path to the Python file

    Returns:
        Dictionary containing metadata or None if not found

    Raises:
        ValueError: If file cannot be parsed or metadata is invalid
    """
    try:
        if not os.path.exists(file_path):
            return None

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # First, try to execute the file to get typed metadata
        # This will work if the file imports the typing classes
        try:
            # Create a safe namespace for execution
            namespace = {}
            # Add the typing classes to the namespace
            from t4t.typing.metadata import (
                ColumnDefinition,
                ColumnTestName,
                DataType,
                IncrementalAppendConfig,
                IncrementalConfig,
                IncrementalDeleteInsertConfig,
                IncrementalMergeConfig,
                IncrementalStrategy,
                MaterializationType,
                ModelMetadata,
                ModelTestName,
            )

            namespace.update(
                {
                    "ModelMetadata": ModelMetadata,
                    "ColumnDefinition": ColumnDefinition,
                    "DataType": DataType,
                    "MaterializationType": MaterializationType,
                    "ColumnTestName": ColumnTestName,
                    "ModelTestName": ModelTestName,
                    "IncrementalStrategy": IncrementalStrategy,
                    "IncrementalConfig": IncrementalConfig,
                    "IncrementalAppendConfig": IncrementalAppendConfig,
                    "IncrementalMergeConfig": IncrementalMergeConfig,
                    "IncrementalDeleteInsertConfig": IncrementalDeleteInsertConfig,
                }
            )

            # Set flag to skip registration during metadata parsing
            # This prevents decorators from re-registering models when we're just parsing metadata
            from t4t.parser.shared.registry import FunctionRegistry, ModelRegistry

            ModelRegistry.set_skip_registration(True)
            FunctionRegistry.set_skip_registration(True)

            try:
                # Execute the file
                exec(content, namespace)
            finally:
                # Always reset the flag, even if an error occurred
                ModelRegistry.set_skip_registration(False)
                FunctionRegistry.set_skip_registration(False)

            # Look for metadata in the namespace
            if "metadata" in namespace:
                metadata = namespace["metadata"]
                if isinstance(metadata, dict):
                    return metadata
                elif hasattr(metadata, "__dict__"):
                    # If it's a dataclass or similar, convert to dict
                    return metadata.__dict__

        except Exception as exec_error:
            logger.warning(
                f"Failed to execute metadata file {file_path}: {exec_error}. "
                f"Metadata files must be executable Python files."
            )
            # Return None if execution fails - let caller handle the error
            return None

        return None

    except Exception as e:
        logger.warning(f"Failed to parse metadata from {file_path}: {str(e)}")
        return None
