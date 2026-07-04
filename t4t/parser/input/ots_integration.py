"""
OTS Integration - Integrates OTS modules with t4t's execution flow.

This module provides functions to load OTS modules and merge them with
existing ParsedModel dictionaries for execution.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.parser.input.ots_converter import OTSConverter, OTSConverterError
from t4t.parser.input.ots_reader import OTSModuleReader, OTSModuleReaderError
from t4t.parser.shared.types import ParsedFunction, ParsedModel

logger = logging.getLogger(__name__)


def load_ots_modules(
    ots_path: Path,
    connection_config: dict[str, Any] | None = None,
) -> tuple[dict[str, ParsedModel], dict[str, ParsedFunction]]:
    """
    Load OTS modules from a file or directory and convert them to ParsedModel and ParsedFunction format.

    Args:
        ots_path: Path to OTS module file (.ots.json) or directory containing OTS modules
        connection_config: Optional connection configuration to override OTS target config

    Returns:
        Tuple of (parsed_models, parsed_functions) dictionaries

    Raises:
        OTSModuleReaderError: If OTS modules cannot be read
        OTSConverterError: If OTS modules cannot be converted
    """
    reader = OTSModuleReader()
    converter = OTSConverter(module_path=ots_path if ots_path.is_file() else None)

    # Load OTS modules
    if ots_path.is_file():
        modules = {ots_path.stem: reader.read_module(ots_path)}
    elif ots_path.is_dir():
        modules = reader.read_modules_from_directory(ots_path)
    else:
        raise OTSModuleReaderError(f"Path is neither a file nor a directory: {ots_path}")

    # Convert all modules to ParsedModel and ParsedFunction format
    all_parsed_models = {}
    all_parsed_functions = {}
    for module_name, module in modules.items():
        try:
            # Override target config if connection_config is provided
            if connection_config:
                module = _override_target_config(module, connection_config)

            parsed_models, parsed_functions = converter.convert_module(module)
            all_parsed_models.update(parsed_models)
            all_parsed_functions.update(parsed_functions)
            logger.info(
                f"Loaded {len(parsed_models)} transformations and {len(parsed_functions)} functions from OTS module: {module_name}"
            )
        except OTSConverterError as e:
            logger.error(f"Failed to convert OTS module {module_name}: {e}")
            raise

    return all_parsed_models, all_parsed_functions


def merge_ots_with_parsed_models(
    parsed_models: dict[str, ParsedModel],
    ots_parsed_models: dict[str, ParsedModel],
) -> dict[str, ParsedModel]:
    """
    Merge OTS-converted ParsedModels with existing ParsedModels.

    If there are conflicts (same transformation_id), OTS models take precedence.

    Args:
        parsed_models: Existing ParsedModels from SQL/Python files
        ots_parsed_models: ParsedModels converted from OTS modules

    Returns:
        Merged dictionary of ParsedModels
    """
    merged = parsed_models.copy()

    # Add OTS models (will overwrite any conflicts)
    conflicts = []
    for transformation_id, ots_model in ots_parsed_models.items():
        if transformation_id in merged:
            conflicts.append(transformation_id)
            logger.warning(
                f"OTS transformation '{transformation_id}' conflicts with existing model. "
                f"OTS version will be used."
            )
        merged[transformation_id] = ots_model

    if conflicts:
        logger.info(f"Resolved {len(conflicts)} conflicts by using OTS versions")

    return merged


def merge_ots_with_parsed_functions(
    parsed_functions: dict[str, ParsedFunction],
    ots_parsed_functions: dict[str, ParsedFunction],
) -> dict[str, ParsedFunction]:
    """
    Merge OTS-converted ParsedFunctions with existing ParsedFunctions.

    If there are conflicts (same function_id), OTS functions take precedence.

    Args:
        parsed_functions: Existing ParsedFunctions from SQL/Python files
        ots_parsed_functions: ParsedFunctions converted from OTS modules

    Returns:
        Merged dictionary of ParsedFunctions
    """
    merged = parsed_functions.copy()

    # Add OTS functions (will overwrite any conflicts)
    conflicts = []
    for function_id, ots_function in ots_parsed_functions.items():
        if function_id in merged:
            conflicts.append(function_id)
            logger.warning(
                f"OTS function '{function_id}' conflicts with existing function. "
                f"OTS version will be used."
            )
        merged[function_id] = ots_function

    if conflicts:
        logger.info(f"Resolved {len(conflicts)} conflicts by using OTS versions")

    return merged


def _override_target_config(
    module: dict[str, Any], connection_config: dict[str, Any]
) -> dict[str, Any]:
    """
    Override OTS module target config with provided connection config.

    Args:
        module: OTS module dictionary
        connection_config: Connection configuration to use

    Returns:
        Modified OTS module with overridden target config
    """
    # Create a copy to avoid modifying the original
    modified_module = module.copy()

    # Update target config
    target = modified_module.get("target", {})
    target["database"] = connection_config.get("database", target.get("database"))
    target["schema"] = connection_config.get("schema", target.get("schema"))
    target["sql_dialect"] = connection_config.get("sql_dialect", target.get("sql_dialect"))

    modified_module["target"] = target
    return modified_module
