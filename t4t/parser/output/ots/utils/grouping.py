"""Grouping utilities for models and functions by schema."""

import logging

from t4t.parser.shared.types import ParsedFunction, ParsedModel

logger = logging.getLogger(__name__)


def group_models_by_schema(
    parsed_models: dict[str, ParsedModel],
) -> dict[str, list[tuple[str, ParsedModel]]]:
    """
    Group models by their schema (first part of transformation_id).

    Args:
        parsed_models: Dictionary of parsed models

    Returns:
        Dictionary mapping schema to list of (model_id, model_data) tuples
    """
    grouped = {}
    for model_id, model_data in parsed_models.items():
        # Extract schema from model_id (e.g., "my_schema.table_name" → "my_schema")
        schema = model_id.split(".")[0] if "." in model_id else "default"

        if schema not in grouped:
            grouped[schema] = []
        grouped[schema].append((model_id, model_data))

    logger.debug(f"Grouped models into {len(grouped)} schemas: {list(grouped.keys())}")
    return grouped


def group_functions_by_schema(
    parsed_functions: dict[str, ParsedFunction],
) -> dict[str, list[tuple[str, ParsedFunction]]]:
    """
    Group functions by their schema (first part of function_id).

    Args:
        parsed_functions: Dictionary of parsed functions

    Returns:
        Dictionary mapping schema to list of (function_id, function_data) tuples
    """
    grouped = {}
    for function_id, function_data in parsed_functions.items():
        # Extract schema from function_id (e.g., "my_schema.function_name" → "my_schema")
        schema = function_id.split(".")[0] if "." in function_id else "default"

        if schema not in grouped:
            grouped[schema] = []
        grouped[schema].append((function_id, function_data))

    logger.debug(f"Grouped functions into {len(grouped)} schemas: {list(grouped.keys())}")
    return grouped
