"""
Custom exceptions for the parser module.
"""


class ParserError(Exception):
    """Base exception for all parser-related errors."""

    pass


class SQLParsingError(ParserError):
    """Raised when SQL parsing fails."""

    pass


class PythonParsingError(ParserError):
    """Raised when Python model parsing fails."""

    pass


class DependencyError(ParserError):
    """Raised when dependency analysis fails."""

    pass


class DimensionalGraphError(ParserError):
    """Raised when dimensional relationship graph analysis fails."""

    pass


class VariableSubstitutionError(ParserError):
    """Raised when variable substitution fails."""

    pass


class TableResolutionError(ParserError):
    """Raised when table name resolution fails."""

    pass


class FileDiscoveryError(ParserError):
    """Raised when file discovery fails."""

    pass


class OutputGenerationError(ParserError):
    """Raised when output generation fails."""

    pass


class FunctionParsingError(ParserError):
    """Raised when function parsing fails."""

    pass


class FunctionExecutionError(ParserError):
    """Raised when function execution/creation fails."""

    pass


class FunctionMetadataError(ParserError):
    """Raised when function metadata validation fails."""

    pass


class ModelConflictError(ParserError):
    """Raised when a model name conflict is detected during registration."""

    pass


class FunctionConflictError(ParserError):
    """Raised when a function name conflict is detected during registration."""

    pass
