"""
Processing layer for variable substitution, file discovery, and model decorators.
"""

from .file_discovery import FileDiscovery
from .function_builder import SQLFunctionMetadata
from .function_decorator import FunctionDecoratorError, functions
from .model import create_model, model
from .model_builder import SqlModelMetadata
from .variable_substitution import substitute_sql_variables, validate_sql_variables

__all__ = [
    "substitute_sql_variables",
    "validate_sql_variables",
    "model",
    "create_model",
    "FileDiscovery",
    "functions",
    "FunctionDecoratorError",
    "SqlModelMetadata",
    "SQLFunctionMetadata",
]
