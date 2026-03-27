"""
SQLFunctionMetadata class for creating functions from metadata and companion SQL files.

This class is used in metadata-only Python files to automatically create functions
by combining metadata with SQL from a companion .sql file.
"""

import logging
import os
from dataclasses import dataclass, field

from tee.parser.shared.exceptions import FunctionConflictError
from tee.parser.shared.function_builder import build_function_from_file
from tee.parser.shared.inspect_utils import get_caller_file_and_main
from tee.parser.shared.registry import FunctionRegistry
from tee.typing import Function, FunctionMetadata

logger = logging.getLogger(__name__)


@dataclass
class SQLFunctionMetadata:
    """
    A dataclass that automatically creates a function from metadata and associated SQL file.

    When instantiated, this class:
    1. Accepts FunctionMetadata as parameter
    2. Automatically finds the SQL file based on the Python file that invoked it
    3. Creates a function dictionary using the shared build_function_from_file utility
    4. If invoked from __main__, also prints the created function

    This is designed for metadata-only Python files that need to combine
    metadata with SQL from a companion .sql file.

    Example:
        from tee.parser.processing.function_builder import SQLFunctionMetadata
        from tee.typing import FunctionMetadata

        metadata: FunctionMetadata = {
            "function_name": "calculate_percentage",
            "parameters": [
                {"name": "numerator", "type": "FLOAT"},
                {"name": "denominator", "type": "FLOAT"}
            ],
            "return_type": "FLOAT"
        }

        # This will automatically find calculate_percentage.sql and create a function
        function = SQLFunctionMetadata(metadata)
    """

    metadata: FunctionMetadata
    function: Function | None = field(default=None, init=False)
    _caller_file: str | None = field(default=None, init=False, repr=False)
    _caller_main: bool = field(default=False, init=False, repr=False)

    def _print_function(self) -> None:
        """
        Print the function in a formatted, human-readable way.

        Displays the complete SQL definition from the companion .sql file and all function metadata
        including type, language, parameters (with types), return type, schema, deterministic flag,
        tests, tags, and description. The output is formatted with clear sections and visual
        separators for easy reading.
        """
        if not self.function:
            return

        output = []
        function_name = self.function["function_metadata"]["function_name"]
        output.append("\n" + "━" * 80)
        output.append(f"  🔧 FUNCTION: {function_name}")
        output.append("━" * 80)
        output.append("")

        # SQL Query Section - read original SQL file to preserve formatting
        output.append("  📝 SQL Definition:")
        sql_file_path = (
            os.path.splitext(self._caller_file)[0] + ".sql" if self._caller_file else None
        )
        if sql_file_path and os.path.exists(sql_file_path):
            with open(sql_file_path, encoding="utf-8") as f:
                sql_content = f.read().strip()
            sql_lines = sql_content.split("\n")
            for line in sql_lines:
                output.append(f"     {line}")
        else:
            # Fallback to parsed SQL if file not found
            sql = self.function["code"]["sql"]["original_sql"] if self.function.get("code") else ""
            sql_lines = sql.split("\n")
            for line in sql_lines:
                output.append(f"     {line}")
        output.append("")

        # Function Metadata Section - Key highlights
        output.append("  📋 Metadata:")
        func_metadata = self.function["function_metadata"]

        if func_metadata.get("function_type"):
            output.append(f"     Type: {func_metadata['function_type']}")

        if func_metadata.get("language"):
            output.append(f"     Language: {func_metadata['language']}")

        if func_metadata.get("parameters"):
            params = []
            for param in func_metadata["parameters"]:
                param_str = f"{param.get('name')} ({param.get('type')})"
                params.append(param_str)
            output.append(f"     Parameters: {', '.join(params)}")

        if func_metadata.get("return_type"):
            output.append(f"     Return Type: {func_metadata['return_type']}")

        if func_metadata.get("return_table_schema"):
            cols = [col.get("name", "?") for col in func_metadata["return_table_schema"]]
            output.append(f"     Return Schema: {', '.join(cols)}")

        if func_metadata.get("schema"):
            output.append(f"     Schema: {func_metadata['schema']}")

        if func_metadata.get("deterministic") is not None:
            output.append(f"     Deterministic: {func_metadata['deterministic']}")

        if func_metadata.get("tests"):
            test_strs = [
                str(t) if isinstance(t, str) else t.get("name", str(t))
                for t in func_metadata["tests"]
            ]
            output.append(f"     Tests: {', '.join(test_strs)}")

        if func_metadata.get("tags"):
            output.append(f"     Tags: {', '.join(func_metadata['tags'])}")

        if func_metadata.get("description"):
            output.append(f"     Description: {func_metadata['description']}")

        output.append("━" * 80)
        output.append("")

        print("\n".join(output))

    def __post_init__(self) -> None:
        """Post-initialization: find SQL file, read it, and create function."""
        # Get caller file path and whether it's being run as __main__
        self._caller_file, self._caller_main = get_caller_file_and_main()

        # Use build_function_from_file which handles SQL file discovery and function creation
        if self._caller_file:
            self.function = build_function_from_file(
                metadata=self.metadata,
                file_path=self._caller_file,
            )

            # Register the function with FunctionRegistry
            if self.function:
                function_name = self.function["function_metadata"]["function_name"]

                # Check for conflicts (only if from a different file)
                existing_function = FunctionRegistry.get(function_name)
                if existing_function:
                    existing_file = existing_function.get("function_metadata", {}).get("file_path")
                    if existing_file and existing_file != self._caller_file:
                        raise FunctionConflictError(
                            f"Function name conflict: '{function_name}' is already registered from another file. "
                            f"Use a different function name to avoid conflicts."
                        )

                FunctionRegistry.register(self.function)
                logger.debug(f"Registered function via SQLFunctionMetadata: {function_name}")

                # Print if called from __main__
                if self._caller_main:
                    self._print_function()
