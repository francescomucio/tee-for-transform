"""
Type definitions for the TEE project.
"""

from .function import Function, ParsedFunction
from .metadata import (
    ColumnDefinition,
    DataType,
    FunctionMetadata,
    MaterializationType,
    ModelMetadata,
)
from .model import Model, ParsedModel

__all__ = [
    "ColumnDefinition",
    "ModelMetadata",
    "Model",
    "FunctionMetadata",
    "Function",
    "MaterializationType",
    "DataType",
    # Backward compatibility
    "ParsedModel",
    "ParsedFunction",
]
