"""
OTS Module Validator - Validates OTS module location and schema consistency.

This module validates that imported OTS modules are in the correct folder
based on their target schema.
"""

import logging
from pathlib import Path

from t4t.parser.input import OTSModuleReader, OTSModuleReaderError

logger = logging.getLogger(__name__)


class OTSValidationError(Exception):
    """Exception raised when OTS module validation fails."""

    pass


def validate_ots_module_location(module_path: Path, models_folder: Path) -> None:
    """
    Validate that an OTS module is in the correct folder based on its target schema.

    Args:
        module_path: Path to the OTS module file
        models_folder: Path to the models folder

    Raises:
        OTSValidationError: If module is in wrong location
        OTSModuleReaderError: If module cannot be read
    """
    try:
        reader = OTSModuleReader()
        module = reader.read_module(module_path)

        # Get target schema from module
        target = module.get("target", {})
        target_schema = target.get("schema")

        if not target_schema:
            raise OTSValidationError(
                f"OTS module {module_path} does not specify a target schema. "
                f"Cannot validate location."
            )

        # Get expected folder path
        expected_folder = models_folder / target_schema

        # Check if module is in the correct folder
        module_folder = module_path.parent

        # Resolve paths to handle symlinks and relative paths
        expected_folder = expected_folder.resolve()
        module_folder = module_folder.resolve()
        models_folder = models_folder.resolve()

        # Check if module is in the expected schema folder
        if module_folder != expected_folder:
            # Also check if it's in a subfolder of the expected folder
            try:
                module_folder.relative_to(expected_folder)
                # It's in a subfolder, which is acceptable
                return
            except ValueError as e:
                # Not in expected folder or subfolder
                raise OTSValidationError(
                    f"OTS module {module_path} targets schema '{target_schema}' "
                    f"but is located in '{module_folder.relative_to(models_folder)}'. "
                    f"Expected location: '{expected_folder.relative_to(models_folder)}/'"
                ) from e

    except OTSModuleReaderError:
        # Re-raise OTS reading errors
        raise
    except Exception as e:
        if isinstance(e, OTSValidationError):
            raise
        raise OTSValidationError(f"Error validating OTS module location: {e}") from e
