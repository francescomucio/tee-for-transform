"""
OTS Module Reader - Reads and validates OTS module files.

This module handles loading and basic validation of OTS (Open Transformation Specification)
module files in JSON and YAML formats.
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from tee.typing.metadata import OTSModule

logger = logging.getLogger(__name__)


class OTSModuleReaderError(Exception):
    """Exception raised when reading or validating OTS modules fails."""

    pass


class OTSModuleReader:
    """Reads and validates OTS module files."""

    def __init__(self):
        """Initialize the OTS module reader."""
        # Support 0.1.0, 0.2.0, 0.2.1, and 0.2.2 (semantic versioning comparison)
        self.max_supported_version = "0.2.2"
        self.supported_ots_versions = [
            "0.1.0",
            "0.2.0",
            "0.2.1",
            "0.2.2",
        ]  # Explicitly supported versions

    def read_module(self, file_path: Path) -> OTSModule:
        """
        Read and validate an OTS module from a file.

        Supports both JSON (.ots.json) and YAML (.ots.yaml, .ots.yml) formats.

        Args:
            file_path: Path to the OTS module file

        Returns:
            Validated OTS module dictionary

        Raises:
            OTSModuleReaderError: If file cannot be read or is invalid
        """
        if not file_path.exists():
            raise OTSModuleReaderError(f"OTS module file not found: {file_path}")

        # Determine file format
        is_json = file_path.suffixes == [".ots", ".json"] or file_path.name.endswith(".ots.json")
        is_yaml = file_path.suffixes in [
            [".ots", ".yaml"],
            [".ots", ".yml"],
        ] or file_path.name.endswith((".ots.yaml", ".ots.yml"))

        if not (is_json or is_yaml):
            logger.warning(
                f"File {file_path} does not have .ots.json or .ots.yaml extension, "
                f"but attempting to read anyway"
            )
            # Try to infer from content
            is_json = file_path.suffix == ".json"
            is_yaml = file_path.suffix in [".yaml", ".yml"]

        try:
            with open(file_path, encoding="utf-8") as f:
                if is_json or (not is_yaml and file_path.suffix == ".json"):
                    module_data = json.load(f)
                else:
                    module_data = yaml.safe_load(f)
                    if module_data is None:
                        raise OTSModuleReaderError(f"Empty YAML file: {file_path}")
        except json.JSONDecodeError as e:
            raise OTSModuleReaderError(f"Invalid JSON in OTS module file {file_path}: {e}") from e
        except yaml.YAMLError as e:
            raise OTSModuleReaderError(f"Invalid YAML in OTS module file {file_path}: {e}") from e
        except Exception as e:
            raise OTSModuleReaderError(f"Error reading OTS module file {file_path}: {e}") from e

        # Validate the module structure
        self._validate_module(module_data, file_path)

        return module_data

    def read_modules_from_directory(self, directory: Path) -> dict[str, OTSModule]:
        """
        Read all OTS modules from a directory.

        Args:
            directory: Directory containing OTS module files

        Returns:
            Dictionary mapping module names to OTS modules

        Raises:
            OTSModuleReaderError: If directory doesn't exist or contains invalid modules
        """
        if not directory.exists():
            raise OTSModuleReaderError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise OTSModuleReaderError(f"Path is not a directory: {directory}")

        modules = {}
        # Discover both JSON and YAML OTS modules
        ots_files = (
            list(directory.glob("*.ots.json"))
            + list(directory.glob("*.ots.yaml"))
            + list(directory.glob("*.ots.yml"))
        )

        if not ots_files:
            logger.warning(
                f"No OTS module files (.ots.json, .ots.yaml, .ots.yml) found in {directory}"
            )
            return modules

        for ots_file in ots_files:
            try:
                module = self.read_module(ots_file)
                module_name = module.get("module_name", ots_file.stem)
                modules[module_name] = module
                logger.info(f"Loaded OTS module: {module_name} from {ots_file}")
            except OTSModuleReaderError as e:
                logger.error(f"Failed to load OTS module {ots_file}: {e}")
                # Continue loading other modules
                continue

        return modules

    def _validate_module(self, module_data: dict[str, Any], file_path: Path) -> None:
        """
        Validate an OTS module structure.

        Args:
            module_data: Module data dictionary
            file_path: Path to the module file (for error messages)

        Raises:
            OTSModuleReaderError: If module is invalid
        """
        # Check required top-level fields
        # For OTS 0.2.0+, transformations is optional if functions are present
        ots_version = module_data.get("ots_version", "0.1.0")
        required_fields = ["ots_version", "module_name", "target"]

        # Transformations is required for 0.1.0, optional for 0.2.0+ if functions exist
        if ots_version == "0.1.0":
            required_fields.append("transformations")
        elif ots_version >= "0.2.0":
            # For 0.2.0+, must have either transformations or functions
            if "transformations" not in module_data and "functions" not in module_data:
                raise OTSModuleReaderError(
                    f"OTS module {file_path} (version {ots_version}) must have either 'transformations' or 'functions'"
                )
        else:
            required_fields.append("transformations")

        for field in required_fields:
            if field not in module_data:
                raise OTSModuleReaderError(
                    f"Missing required field '{field}' in OTS module {file_path}"
                )

        # Validate OTS version (support 0.1.0, 0.2.0, and 0.2.1, error for above)
        # Note: ots_version was already extracted above for field validation
        if not self._is_version_supported(ots_version):
            raise OTSModuleReaderError(
                f"OTS module {file_path} uses version {ots_version}, "
                f"which is not supported. Maximum supported version: {self.max_supported_version}. "
                f"Please use version 0.1.0, 0.2.0, or 0.2.1."
            )

        # Validate target structure
        target = module_data.get("target", {})
        if not isinstance(target, dict):
            raise OTSModuleReaderError(
                f"Invalid 'target' field in OTS module {file_path}: must be a dictionary"
            )

        required_target_fields = ["database", "schema"]
        for field in required_target_fields:
            if field not in target:
                raise OTSModuleReaderError(
                    f"Missing required field 'target.{field}' in OTS module {file_path}"
                )

        # Validate transformations
        transformations = module_data.get("transformations", [])
        if not isinstance(transformations, list):
            raise OTSModuleReaderError(
                f"Invalid 'transformations' field in OTS module {file_path}: must be a list"
            )

        if len(transformations) == 0:
            logger.warning(f"OTS module {file_path} contains no transformations")

        # Validate each transformation
        for i, transformation in enumerate(transformations):
            self._validate_transformation(transformation, file_path, i)

    def _validate_transformation(
        self, transformation: dict[str, Any], file_path: Path, index: int
    ) -> None:
        """
        Validate a single transformation.

        Args:
            transformation: Transformation data dictionary
            file_path: Path to the module file (for error messages)
            index: Index of the transformation in the list

        Raises:
            OTSModuleReaderError: If transformation is invalid
        """
        # Check required fields
        required_fields = ["transformation_id", "code"]
        for field in required_fields:
            if field not in transformation:
                raise OTSModuleReaderError(
                    f"Missing required field 'transformations[{index}].{field}' in OTS module {file_path}"
                )

        # Validate code structure
        code = transformation.get("code", {})
        if not isinstance(code, dict):
            raise OTSModuleReaderError(
                f"Invalid 'code' field in transformation {index} of OTS module {file_path}: must be a dictionary"
            )

        # For SQL transformations, validate SQL structure
        transformation_type = transformation.get("transformation_type", "sql")
        if transformation_type == "sql":
            if "sql" not in code:
                raise OTSModuleReaderError(
                    f"Missing 'code.sql' field in SQL transformation {index} of OTS module {file_path}"
                )

            sql_code = code.get("sql", {})
            if not isinstance(sql_code, dict):
                raise OTSModuleReaderError(
                    f"Invalid 'code.sql' field in transformation {index} of OTS module {file_path}: must be a dictionary"
                )

            # Check for at least one SQL field
            sql_fields = ["original_sql", "resolved_sql"]
            if not any(field in sql_code for field in sql_fields):
                raise OTSModuleReaderError(
                    f"Missing SQL content in transformation {index} of OTS module {file_path}. "
                    f"Must have at least one of: {sql_fields}"
                )

        # Validate transformation_id format (should be schema.table)
        transformation_id = transformation.get("transformation_id", "")
        if "." not in transformation_id:
            logger.warning(
                f"Transformation ID '{transformation_id}' in transformation {index} of OTS module {file_path} "
                f"does not follow schema.table format"
            )

    def _is_version_supported(self, version: str) -> bool:
        """
        Check if OTS version is supported (0.1.0, 0.2.0, 0.2.1, and 0.2.2).

        Args:
            version: OTS version string (e.g., "0.1.0", "0.2.0", "0.2.1", "0.2.2")

        Returns:
            True if version is supported, False otherwise
        """
        try:
            # Check if version is in explicitly supported list
            if version in self.supported_ots_versions:
                return True

            # Simple semantic version comparison
            # Split version into parts
            parts = version.split(".")
            if len(parts) < 2:
                return False

            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2]) if len(parts) > 2 else 0

            # Support versions <= 0.2.2
            max_parts = self.max_supported_version.split(".")
            max_major = int(max_parts[0])
            max_minor = int(max_parts[1])
            max_patch = int(max_parts[2]) if len(max_parts) > 2 else 0

            if major < max_major:
                return True
            elif major == max_major:
                if minor < max_minor:
                    return True
                elif minor == max_minor:
                    return patch <= max_patch
            return False
        except (ValueError, IndexError):
            # If version format is invalid, don't support it
            return False

    def get_module_info(self, module: OTSModule) -> dict[str, Any]:
        """
        Extract summary information from an OTS module.

        Args:
            module: OTS module dictionary

        Returns:
            Dictionary with module information
        """
        return {
            "module_name": module.get("module_name"),
            "ots_version": module.get("ots_version"),
            "module_description": module.get("module_description"),
            "version": module.get("version"),
            "target": module.get("target", {}),
            "transformation_count": len(module.get("transformations", [])),
            "has_test_library": "test_library_path" in module,
            "module_tags": module.get("tags", []),
        }
