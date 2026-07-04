"""
Registry classes for models and functions.

These registries allow Python files to auto-register models and functions
when executed, similar to how tests work with TestRegistry.
"""

from typing import Any


class ModelRegistry:
    """Registry for models discovered from Python files."""

    _models: dict[str, dict[str, Any]] = {}
    _skip_registration: bool = False  # Flag to skip registration during evaluation

    @classmethod
    def set_skip_registration(cls, skip: bool) -> None:
        """
        Set flag to skip model registration.

        Used during evaluation phase to prevent re-registration of models.

        Args:
            skip: If True, skip registration; if False, allow registration
        """
        cls._skip_registration = skip

    @classmethod
    def should_skip_registration(cls) -> bool:
        """
        Check if registration should be skipped.

        Returns:
            True if registration should be skipped, False otherwise
        """
        return cls._skip_registration

    @classmethod
    def register(cls, model_data: dict[str, Any]) -> None:
        """
        Register a model.

        Args:
            model_data: Model data dictionary (with model_metadata, code, etc.)
        """
        table_name = model_data["model_metadata"]["table_name"]
        cls._models[table_name] = model_data

    @classmethod
    def get(cls, table_name: str) -> dict[str, Any] | None:
        """
        Get a registered model by table name.

        Args:
            table_name: Table name

        Returns:
            Model data dictionary or None if not found
        """
        return cls._models.get(table_name)

    @classmethod
    def list_all(cls) -> list[str]:
        """
        List all registered model table names.

        Returns:
            List of table names
        """
        return list(cls._models.keys())

    @classmethod
    def get_all(cls) -> dict[str, dict[str, Any]]:
        """
        Get all registered models.

        Returns:
            Dictionary mapping table_name to model data
        """
        return cls._models.copy()

    @classmethod
    def get_models_by_file_path(cls, file_path: str) -> list[dict[str, Any]]:
        """
        Get all models registered from a specific file path.

        Args:
            file_path: Absolute file path to search for

        Returns:
            List of model data dictionaries registered from the given file
        """
        return [
            model_data
            for model_data in cls._models.values()
            if model_data.get("model_metadata", {}).get("file_path") == file_path
        ]

    @classmethod
    def has_models_from_file(cls, file_path: str) -> bool:
        """
        Check if any models are registered from a specific file path.

        This is more efficient than get_models_by_file_path() when you only need
        to check existence, as it uses a generator and stops at the first match.

        Args:
            file_path: Absolute file path to check

        Returns:
            True if any models are registered from the file, False otherwise
        """
        return any(
            model_data.get("model_metadata", {}).get("file_path") == file_path
            for model_data in cls._models.values()
        )

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered models (mainly for testing).
        """
        cls._models.clear()


class FunctionRegistry:
    """Registry for functions discovered from Python files."""

    _functions: dict[str, dict[str, Any]] = {}
    _skip_registration: bool = False  # Flag to skip registration during evaluation

    @classmethod
    def set_skip_registration(cls, skip: bool) -> None:
        """
        Set flag to skip function registration.

        Used during evaluation phase to prevent re-registration of functions.

        Args:
            skip: If True, skip registration; if False, allow registration
        """
        cls._skip_registration = skip

    @classmethod
    def should_skip_registration(cls) -> bool:
        """
        Check if registration should be skipped.

        Returns:
            True if registration should be skipped, False otherwise
        """
        return cls._skip_registration

    @classmethod
    def register(cls, function_data: dict[str, Any]) -> None:
        """
        Register a function.

        Args:
            function_data: Function data dictionary (with function_metadata, code, etc.)
        """
        function_name = function_data["function_metadata"]["function_name"]
        cls._functions[function_name] = function_data

    @classmethod
    def get(cls, function_name: str) -> dict[str, Any] | None:
        """
        Get a registered function by function name.

        Args:
            function_name: Function name

        Returns:
            Function data dictionary or None if not found
        """
        return cls._functions.get(function_name)

    @classmethod
    def list_all(cls) -> list[str]:
        """
        List all registered function names.

        Returns:
            List of function names
        """
        return list(cls._functions.keys())

    @classmethod
    def get_all(cls) -> dict[str, dict[str, Any]]:
        """
        Get all registered functions.

        Returns:
            Dictionary mapping function_name to function data
        """
        return cls._functions.copy()

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered functions (mainly for testing).
        """
        cls._functions.clear()
