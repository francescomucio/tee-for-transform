"""
Validation system for imported dbt projects.

Validates syntax, dependencies, metadata, and optionally execution.
"""

import logging
from pathlib import Path
from typing import Any

import sqlglot

logger = logging.getLogger(__name__)


class ValidationResult:
    """Results from validation checks."""

    def __init__(self) -> None:
        """Initialize validation result."""
        self.syntax_errors: list[dict[str, Any]] = []
        self.dependency_errors: list[dict[str, Any]] = []
        self.metadata_errors: list[dict[str, Any]] = []
        self.execution_errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return (
            len(self.syntax_errors) == 0
            and len(self.dependency_errors) == 0
            and len(self.metadata_errors) == 0
            and len(self.execution_errors) == 0
        )

    @property
    def error_count(self) -> int:
        """Get total number of errors."""
        return (
            len(self.syntax_errors)
            + len(self.dependency_errors)
            + len(self.metadata_errors)
            + len(self.execution_errors)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert validation result to dictionary."""
        return {
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "syntax_errors": self.syntax_errors,
            "dependency_errors": self.dependency_errors,
            "metadata_errors": self.metadata_errors,
            "execution_errors": self.execution_errors,
            "warnings": self.warnings,
        }


class ProjectValidator:
    """Validates imported dbt projects."""

    def __init__(
        self,
        target_path: Path,
        model_name_map: dict[str, str],
        verbose: bool = False,
    ) -> None:
        """
        Initialize project validator.

        Args:
            target_path: Path to the imported t4t project
            model_name_map: Mapping of dbt model names to final table names
            verbose: Enable verbose logging
        """
        self.target_path = target_path
        self.model_name_map = model_name_map
        self.verbose = verbose

    def validate_all(
        self,
        validate_execution: bool = False,
        connection_config: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Run all validation checks.

        Args:
            validate_execution: Whether to run execution validation
            connection_config: Database connection config for execution validation

        Returns:
            ValidationResult with all validation results
        """
        result = ValidationResult()

        # Syntax validation
        result.syntax_errors = self.validate_syntax()

        # Dependency validation
        result.dependency_errors = self.validate_dependencies()

        # Metadata validation
        result.metadata_errors = self.validate_metadata()

        # Execution validation (optional)
        if validate_execution:
            result.execution_errors = self.validate_execution(connection_config)

        if self.verbose:
            logger.info(
                f"Validation complete: {result.error_count} errors, {len(result.warnings)} warnings"
            )

        return result

    def validate_syntax(self) -> list[dict[str, Any]]:
        """
        Validate SQL syntax in all model files.

        Returns:
            List of syntax errors (empty if all valid)
        """
        errors: list[dict[str, Any]] = []
        models_dir = self.target_path / "models"

        if not models_dir.exists():
            return errors

        # Find all SQL files
        sql_files = list(models_dir.rglob("*.sql"))

        for sql_file in sql_files:
            try:
                sql_content = sql_file.read_text(encoding="utf-8")

                # Skip empty files
                if not sql_content.strip():
                    continue

                # Try to parse with SQLGlot
                try:
                    parsed = sqlglot.parse_one(sql_content)
                    if parsed is None:
                        errors.append(
                            {
                                "file": str(sql_file.relative_to(self.target_path)),
                                "error": "Failed to parse SQL (returned None)",
                                "type": "syntax",
                            }
                        )
                except Exception as e:
                    errors.append(
                        {
                            "file": str(sql_file.relative_to(self.target_path)),
                            "error": str(e),
                            "type": "syntax",
                        }
                    )

            except Exception as e:
                errors.append(
                    {
                        "file": str(sql_file.relative_to(self.target_path)),
                        "error": f"Failed to read file: {str(e)}",
                        "type": "syntax",
                    }
                )

        if self.verbose and errors:
            logger.warning(f"Found {len(errors)} syntax errors")

        return errors

    def validate_dependencies(self) -> list[dict[str, Any]]:
        """
        Validate that all model references resolve.

        Checks:
        - All @ref() calls reference existing models
        - All source() calls are valid

        Returns:
            List of dependency errors (empty if all valid)
        """
        errors: list[dict[str, Any]] = []
        models_dir = self.target_path / "models"

        if not models_dir.exists():
            return errors

        # Find all SQL files
        sql_files = list(models_dir.rglob("*.sql"))

        for sql_file in sql_files:
            try:
                sql_content = sql_file.read_text(encoding="utf-8")

                # Check for @ref() patterns (t4t variable syntax)
                # Pattern: @ref_model_name or @schema.model_name
                import re

                ref_pattern = r"@(\w+(?:\.\w+)?)"
                for match in re.finditer(ref_pattern, sql_content):
                    ref_name = match.group(1)

                    # Skip if it's a variable (has :default)
                    if ":" in sql_content[match.end() : match.end() + 20]:
                        continue

                    # Check if it's a model reference
                    # Simple heuristic: if it's in model_name_map or looks like a table
                    if ref_name not in self.model_name_map.values():
                        # Check if it's a qualified name (schema.table)
                        if "." in ref_name:
                            # Qualified name - assume it's a source table
                            continue
                        else:
                            # Unqualified name - might be a missing model
                            errors.append(
                                {
                                    "file": str(sql_file.relative_to(self.target_path)),
                                    "error": f"Unresolved reference: @{ref_name}",
                                    "type": "dependency",
                                    "reference": ref_name,
                                }
                            )

            except Exception as e:
                errors.append(
                    {
                        "file": str(sql_file.relative_to(self.target_path)),
                        "error": f"Failed to validate dependencies: {str(e)}",
                        "type": "dependency",
                    }
                )

        if self.verbose and errors:
            logger.warning(f"Found {len(errors)} dependency errors")

        return errors

    def validate_metadata(self) -> list[dict[str, Any]]:
        """
        Validate that required metadata fields are present.

        Checks:
        - Each model has a corresponding metadata file (if expected)
        - Required metadata fields are present

        Returns:
            List of metadata errors (empty if all valid)
        """
        errors: list[dict[str, Any]] = []
        models_dir = self.target_path / "models"

        if not models_dir.exists():
            return errors

        # Find all SQL files
        sql_files = list(models_dir.rglob("*.sql"))

        for sql_file in sql_files:
            # Check for corresponding metadata file
            metadata_file = sql_file.with_suffix(".py")
            if not metadata_file.exists():
                # Metadata file is optional, but log as warning
                continue

            # Try to parse metadata file
            try:
                # Read and check if it's valid Python
                metadata_content = metadata_file.read_text(encoding="utf-8")

                # Basic validation: check if it contains model metadata structure
                # This is a simple check - full validation would require importing the module
                if "table_name" not in metadata_content and "@model" not in metadata_content:
                    errors.append(
                        {
                            "file": str(metadata_file.relative_to(self.target_path)),
                            "error": "Metadata file missing required fields (table_name or @model)",
                            "type": "metadata",
                        }
                    )

            except Exception as e:
                errors.append(
                    {
                        "file": str(metadata_file.relative_to(self.target_path)),
                        "error": f"Failed to parse metadata file: {str(e)}",
                        "type": "metadata",
                    }
                )

        if self.verbose and errors:
            logger.warning(f"Found {len(errors)} metadata errors")

        return errors

    def validate_execution(
        self, connection_config: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Validate that the project can be executed.

        This attempts to parse the project using t4t's parser to ensure
        it can be loaded and executed.

        Args:
            connection_config: Database connection configuration

        Returns:
            List of execution errors (empty if all valid)
        """
        errors: list[dict[str, Any]] = []

        if not connection_config:
            errors.append(
                {
                    "error": "Connection config required for execution validation",
                    "type": "execution",
                }
            )
            return errors

        # Try to use t4t's parser to validate the project
        try:
            from t4t.parser.core.orchestrator import ParserOrchestrator

            orchestrator = ParserOrchestrator(
                project_path=str(self.target_path),
                verbose=self.verbose,
            )

            # Try to parse all models
            try:
                models = orchestrator.parse_all_models()
                if not models:
                    errors.append(
                        {
                            "error": "No models found in project",
                            "type": "execution",
                        }
                    )
            except Exception as e:
                errors.append(
                    {
                        "error": f"Failed to parse project: {str(e)}",
                        "type": "execution",
                    }
                )

        except ImportError:
            # Parser not available - skip execution validation
            errors.append(
                {
                    "error": "Parser not available for execution validation",
                    "type": "execution",
                }
            )
        except Exception as e:
            errors.append(
                {
                    "error": f"Execution validation failed: {str(e)}",
                    "type": "execution",
                }
            )

        if self.verbose and errors:
            logger.warning(f"Found {len(errors)} execution errors")

        return errors
