"""
File discovery functionality for finding SQL and Python model files.
"""

import logging
from pathlib import Path

from t4t.parser.shared.constants import (
    KNOWN_DATABASE_NAMES,
    SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS,
    SUPPORTED_PYTHON_EXTENSIONS,
    SUPPORTED_SQL_EXTENSIONS,
)
from t4t.parser.shared.exceptions import FileDiscoveryError

# Configure logging
logger = logging.getLogger(__name__)


class FileDiscovery:
    """Handles discovery of SQL and Python model files, and function files."""

    def __init__(self, models_folder: Path, functions_folder: Path | None = None):
        """
        Initialize the file discovery.

        Args:
            models_folder: Path to the models folder
            functions_folder: Optional path to the functions folder
        """
        self.models_folder = models_folder
        self.functions_folder = functions_folder
        self._file_cache: dict[str, list[Path]] = {}

    def discover_sql_files(self) -> list[Path]:
        """
        Discover all SQL files in the models folder.

        Returns:
            List of SQL file paths

        Raises:
            FileDiscoveryError: If file discovery fails
        """
        try:
            cache_key = "sql_files"
            if cache_key in self._file_cache:
                return self._file_cache[cache_key]

            if not self.models_folder.exists():
                raise FileDiscoveryError(f"Models folder not found: {self.models_folder}")

            sql_files = []
            for ext in SUPPORTED_SQL_EXTENSIONS:
                sql_files.extend(self.models_folder.rglob(f"*{ext}"))

            # Sort for consistent ordering
            sql_files.sort()

            # Cache the result
            self._file_cache[cache_key] = sql_files

            logger.debug(f"Discovered {len(sql_files)} SQL files")
            return sql_files

        except Exception as e:
            if isinstance(e, FileDiscoveryError):
                raise
            raise FileDiscoveryError(f"Failed to discover SQL files: {e}") from e

    def discover_python_files(self) -> list[Path]:
        """
        Discover all Python files in the models folder.

        Returns:
            List of Python file paths

        Raises:
            FileDiscoveryError: If file discovery fails
        """
        try:
            cache_key = "python_files"
            if cache_key in self._file_cache:
                return self._file_cache[cache_key]

            if not self.models_folder.exists():
                raise FileDiscoveryError(f"Models folder not found: {self.models_folder}")

            python_files = []
            for ext in SUPPORTED_PYTHON_EXTENSIONS:
                python_files.extend(self.models_folder.rglob(f"*{ext}"))

            # Sort for consistent ordering
            python_files.sort()

            # Cache the result
            self._file_cache[cache_key] = python_files

            logger.debug(f"Discovered {len(python_files)} Python files")
            return python_files

        except Exception as e:
            if isinstance(e, FileDiscoveryError):
                raise
            raise FileDiscoveryError(f"Failed to discover Python files: {e}") from e

    def discover_ots_modules(self) -> list[Path]:
        """
        Discover all OTS module files in the models folder.

        Returns:
            List of OTS module file paths (.ots.json, .ots.yaml, .ots.yml)

        Raises:
            FileDiscoveryError: If file discovery fails
        """
        try:
            cache_key = "ots_modules"
            if cache_key in self._file_cache:
                return self._file_cache[cache_key]

            if not self.models_folder.exists():
                # Return empty list if models folder doesn't exist (not an error for OTS)
                return []

            ots_files = []
            # Discover JSON and YAML OTS modules
            ots_files.extend(self.models_folder.rglob("*.ots.json"))
            ots_files.extend(self.models_folder.rglob("*.ots.yaml"))
            ots_files.extend(self.models_folder.rglob("*.ots.yml"))

            # Sort for consistent ordering
            ots_files.sort()

            # Cache the result
            self._file_cache[cache_key] = ots_files

            logger.debug(f"Discovered {len(ots_files)} OTS module files")
            return ots_files

        except Exception as e:
            if isinstance(e, FileDiscoveryError):
                raise
            raise FileDiscoveryError(f"Failed to discover OTS module files: {e}") from e

    def discover_all_files(self) -> dict[str, list[Path]]:
        """
        Discover all supported files in the models folder.

        Returns:
            Dict with 'sql', 'python', and 'ots' keys containing lists of file paths

        Raises:
            FileDiscoveryError: If file discovery fails
        """
        try:
            return {
                "sql": self.discover_sql_files(),
                "python": self.discover_python_files(),
                "ots": self.discover_ots_modules(),
            }
        except Exception as e:
            if isinstance(e, FileDiscoveryError):
                raise
            raise FileDiscoveryError(f"Failed to discover files: {e}") from e

    def discover_function_files(self) -> dict[str, list[Path]]:
        """
        Discover all function files in the functions folder.

        Supports both flat and folder-based structures:
        - Flat: functions/{schema}/{function_name}.sql or .py
        - Folder: functions/{schema}/{function_name}/{function_name}.sql or .py
        - Database overrides: {function_name}.{database}.sql or .js

        Returns:
            Dict with 'sql', 'python', and 'database_overrides' keys containing lists of file paths

        Raises:
            FileDiscoveryError: If file discovery fails
        """
        try:
            cache_key = "function_files"
            if cache_key in self._file_cache:
                return self._file_cache[cache_key]

            # Handle missing or unconfigured folder (cache empty result)
            empty_result = {
                "sql": [],
                "python": [],
                "database_overrides": [],
            }

            if not self.functions_folder:
                logger.debug("Functions folder not configured")
                self._file_cache[cache_key] = empty_result
                return empty_result

            if not self.functions_folder.exists():
                logger.debug(f"Functions folder not found: {self.functions_folder}")
                self._file_cache[cache_key] = empty_result
                return empty_result

            # Single-pass discovery: collect all relevant files at once
            sql_files = []
            python_files = []
            database_overrides = []

            # Collect all files with supported extensions in a single pass
            # This is more efficient than multiple rglob() calls
            all_extensions = (
                set(SUPPORTED_SQL_EXTENSIONS)
                | set(SUPPORTED_PYTHON_EXTENSIONS)
                | set(SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS)
            )

            for ext in all_extensions:
                for file_path in self.functions_folder.rglob(f"*{ext}"):
                    # Check if this is a database override file
                    # Pattern: {function_name}.{database}.{ext}
                    # e.g., calculate_metric.postgresql.sql
                    stem = file_path.stem  # filename without extension

                    if "." in stem:
                        # Split by dots - last part before extension should be a database name
                        parts = stem.split(".")
                        if len(parts) >= 2:
                            # Check if the last part is a known database name
                            potential_db = parts[-1].lower()
                            if potential_db in KNOWN_DATABASE_NAMES:
                                # This is a database override file
                                database_overrides.append(file_path)
                                continue

                    # Not a database override - categorize by extension
                    if ext in SUPPORTED_SQL_EXTENSIONS:
                        sql_files.append(file_path)
                    elif ext in SUPPORTED_PYTHON_EXTENSIONS:
                        python_files.append(file_path)

            # Sort for consistent ordering
            sql_files.sort()
            python_files.sort()
            database_overrides.sort()

            result = {
                "sql": sql_files,
                "python": python_files,
                "database_overrides": database_overrides,
            }

            # Cache the result
            self._file_cache[cache_key] = result

            logger.debug(
                f"Discovered {len(sql_files)} SQL function files, "
                f"{len(python_files)} Python function files, "
                f"and {len(database_overrides)} database override files"
            )
            return result

        except Exception as e:
            if isinstance(e, FileDiscoveryError):
                raise
            raise FileDiscoveryError(f"Failed to discover function files: {e}") from e

    def clear_cache(self) -> None:
        """Clear the file discovery cache."""
        self._file_cache.clear()
        logger.debug("File discovery cache cleared")
