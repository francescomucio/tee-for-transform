"""
Shared helper functions for executor modules.

This module contains helper functions used by both execute_models and build_models
to avoid code duplication.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_compile_results(
    compile_results: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """
    Validate and extract results from compilation.

    Args:
        compile_results: Dictionary returned from compile_project

    Returns:
        Tuple of (graph, execution_order, parsed_models)

    Raises:
        RuntimeError: If compilation results are invalid
    """
    graph = compile_results.get("dependency_graph")
    execution_order = compile_results.get("execution_order", [])
    parsed_models = compile_results.get("parsed_models", {})

    if not graph:
        raise RuntimeError("Compilation did not return dependency graph")

    # Allow empty execution_order when there are no models, but not None
    if execution_order is None:
        raise RuntimeError("Compilation did not return execution order")

    logger.debug(f"Using dependency graph from compilation: {len(graph['nodes'])} nodes")
    if execution_order:
        logger.debug(f"Execution order: {' -> '.join(execution_order)}")
    else:
        logger.debug("Execution order: (empty - no models to execute)")

    return graph, execution_order, parsed_models


def create_empty_execution_results(
    graph: dict[str, Any], warnings: list[str] | None = None
) -> dict[str, Any]:
    """
    Create an empty execution results dictionary for when there are no models.

    Args:
        graph: Dependency graph from compilation
        warnings: Optional list of warning messages to include

    Returns:
        Dictionary with empty execution results structure
    """
    return {
        "executed_tables": [],
        "failed_tables": [],
        "executed_functions": [],
        "failed_functions": [],
        "warnings": warnings or [],
        "table_info": {},
        "analysis": {
            "total_models": 0,
            "total_tables": 0,
            "execution_order": [],
            "dependency_graph": graph,
        },
    }


def create_empty_build_results(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Create an empty build results dictionary for when there are no models.

    Args:
        graph: Dependency graph from compilation

    Returns:
        Dictionary with empty build results structure (includes test_results)
    """
    return {
        "executed_tables": [],
        "failed_tables": [],
        "skipped_tables": [],
        "executed_functions": [],
        "failed_functions": [],
        "test_results": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "test_results": [],
        },
        "seed_results": {
            "loaded_tables": [],
            "failed_tables": [],
            "total_seeds": 0,
        },
        "warnings": [],
        "table_info": {},
        "analysis": {
            "total_models": 0,
            "total_tables": 0,
            "execution_order": [],
            "dependency_graph": graph,
        },
    }
