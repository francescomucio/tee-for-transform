"""
Parser Module

A comprehensive tool for parsing SQL files and building dependency graphs.
Reorganized with clear layer separation for better maintainability.
"""

# Re-export key components for advanced usage
from .analysis import DependencyGraphBuilder, TableResolver
from .core import ProjectParser
from .output import JSONExporter, ReportGenerator
from .parsers import ParserFactory, PythonParser, SQLParser
from .processing import model, substitute_sql_variables, validate_sql_variables
from .shared import (
    DependencyError,
    DimensionalGraphError,
    FileDiscoveryError,
    OutputGenerationError,
    ParserError,
    PythonParsingError,
    SQLParsingError,
    TableResolutionError,
    VariableSubstitutionError,
)

__all__ = [
    "ProjectParser",
    "DependencyGraphBuilder",
    "TableResolver",
    "JSONExporter",
    "ReportGenerator",
    "ParserFactory",
    "PythonParser",
    "SQLParser",
    "model",
    "substitute_sql_variables",
    "validate_sql_variables",
    "DependencyError",
    "DimensionalGraphError",
    "FileDiscoveryError",
    "OutputGenerationError",
    "ParserError",
    "PythonParsingError",
    "SQLParsingError",
    "TableResolutionError",
    "VariableSubstitutionError",
]
