"""
Custom exceptions for dbt importer.
"""


class DbtImporterError(Exception):
    """Base exception for dbt importer errors."""

    pass


class DbtProjectNotFoundError(DbtImporterError):
    """Raised when dbt project is not found or invalid."""

    pass


class ModelConversionError(DbtImporterError):
    """Raised when model conversion fails."""

    def __init__(self, model_name: str, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.model_name = model_name
        self.reason = reason

    def __str__(self) -> str:
        return f"Failed to convert model '{self.model_name}': {self.reason}"


class MacroConversionError(DbtImporterError):
    """Raised when macro conversion fails."""

    def __init__(self, macro_name: str, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.macro_name = macro_name
        self.reason = reason

    def __str__(self) -> str:
        return f"Failed to convert macro '{self.macro_name}': {self.reason}"


class TestConversionError(DbtImporterError):
    """Raised when test conversion fails."""

    def __init__(self, test_file: str, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.test_file = test_file
        self.reason = reason

    def __str__(self) -> str:
        return f"Failed to convert test '{self.test_file}': {self.reason}"


class SchemaParsingError(DbtImporterError):
    """Raised when schema.yml parsing fails."""

    def __init__(self, schema_file: str, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.schema_file = schema_file
        self.reason = reason

    def __str__(self) -> str:
        return f"Failed to parse schema file '{self.schema_file}': {self.reason}"


class SourceParsingError(DbtImporterError):
    """Raised when source file parsing fails."""

    def __init__(self, source_file: str, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.source_file = source_file
        self.reason = reason

    def __str__(self) -> str:
        return f"Failed to parse source file '{self.source_file}': {self.reason}"


class JinjaConversionError(DbtImporterError):
    """Raised when Jinja conversion fails."""

    def __init__(self, model_name: str, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.model_name = model_name
        self.reason = reason

    def __str__(self) -> str:
        return f"Failed to convert Jinja in model '{self.model_name}': {self.reason}"
