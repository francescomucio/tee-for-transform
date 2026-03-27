"""
SqlTestMetadata class for creating tests from metadata and companion SQL files.

This class is used in metadata-only Python files to automatically create tests
by combining metadata with SQL from a companion .sql file.
"""

import inspect
import logging
import os
from dataclasses import dataclass, field

from tee.parser.shared.inspect_utils import get_caller_file_info

from .base import TestRegistry, TestSeverity
from .python_test import PythonTest

logger = logging.getLogger(__name__)


class TestBuilderError(Exception):
    """Raised when test builder operations fail."""

    __test__ = False  # Tell pytest this is not a test class

    pass


@dataclass
class SqlTestMetadata:
    """
    A dataclass that automatically creates a test from metadata and associated SQL file.

    When instantiated, this class:
    1. Accepts test metadata (name, severity, description, tags)
    2. Automatically finds the SQL file based on the Python file that invoked it
    3. Creates a PythonTest instance and registers it with TestRegistry
    4. If invoked from __main__, also prints the created test

    This is designed for metadata-only Python files that need to combine
    metadata with SQL from a companion .sql file.

    Example:
        from tee.testing import SqlTestMetadata

        metadata = {
            "name": "check_minimum_rows",
            "severity": "error",
            "description": "Check that table has at least N rows",
            "tags": ["data-quality", "row-count"]
        }

        # This will automatically find check_minimum_rows.sql and create a test
        test = SqlTestMetadata(**metadata)
    """

    name: str
    severity: str | TestSeverity = "error"
    description: str | None = None
    tags: list[str] | None = None
    test: PythonTest | None = field(default=None, init=False)
    _caller_file: str | None = field(default=None, init=False, repr=False)
    _caller_main: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Post-initialization: find SQL file, read it, and create test."""
        # Get caller file path and whether it's being run as __main__
        # When executed in isolated module, we need to check module globals first
        frame = inspect.currentframe()
        caller_file = None
        caller_main = False

        # Walk up frames to find the module's __file__
        # We're looking for the frame where the module was executed (not test_builder.py itself)
        current_frame = frame
        for _ in range(10):  # Walk up to 10 frames
            if current_frame and current_frame.f_back:
                current_frame = current_frame.f_back
                frame_globals = current_frame.f_globals
                # Check if this frame has __file__ and it's not from test_builder.py
                if "__file__" in frame_globals:
                    potential_file = frame_globals.get("__file__")
                    # Skip if it's from test_builder.py itself
                    if potential_file and "test_builder.py" not in potential_file:
                        caller_file = potential_file
                        caller_main = frame_globals.get("__name__") == "__main__"
                        # Make sure it's an absolute path
                        if caller_file:
                            caller_file = os.path.abspath(caller_file)
                        break
            else:
                break

        # Fallback to get_caller_file_info if we didn't find it
        if not caller_file:
            caller_file, caller_main = get_caller_file_info(frames_up=2)

        self._caller_file = caller_file
        self._caller_main = caller_main

        if not self._caller_file:
            raise TestBuilderError(
                "Could not determine caller file path. SqlTestMetadata must be instantiated "
                "at module level in a Python test file."
            )

        # Find companion SQL file
        sql_file_path = os.path.splitext(self._caller_file)[0] + ".sql"
        if not os.path.exists(sql_file_path):
            raise TestBuilderError(
                f"Companion SQL file not found: {sql_file_path}. "
                f"SqlTestMetadata requires a companion .sql file with the same name."
            )

        # Read SQL content
        try:
            with open(sql_file_path, encoding="utf-8") as f:
                sql_content = f.read().strip()
        except Exception as e:
            raise TestBuilderError(f"Failed to read SQL file {sql_file_path}: {e}") from e

        if not sql_content:
            raise TestBuilderError(f"SQL file {sql_file_path} is empty")

        # Convert severity string to enum if needed
        if isinstance(self.severity, str):
            severity_enum = (
                TestSeverity.ERROR if self.severity.lower() == "error" else TestSeverity.WARNING
            )
        else:
            severity_enum = self.severity

        # Validate test name
        if not self.name or not self.name.replace("_", "").replace(".", "").isalnum():
            raise TestBuilderError(f"Invalid test name: {self.name}")

        # Check for conflicts
        existing_test = TestRegistry.get(self.name)
        if existing_test:
            raise TestBuilderError(
                f"Test name conflict: '{self.name}' is already registered from another file. "
                f"Use a different name to avoid conflicts."
            )

        # Create and register test
        self.test = PythonTest(
            name=self.name,
            sql=sql_content,
            severity=severity_enum,
            description=self.description,
            tags=self.tags or [],
        )

        TestRegistry.register(self.test)
        logger.debug(f"Registered test via SqlTestMetadata: {self.name} from {self._caller_file}")

        # Print if called from __main__
        if self._caller_main:
            self._print_test()

    def _print_test(self) -> None:
        """Print the test in a formatted, readable way."""
        if not self.test:
            return

        output = []
        output.append("\n" + "━" * 80)
        output.append(f"  🧪 TEST: {self.test.name}")
        output.append("━" * 80)
        output.append("")

        # SQL Query Section - read original SQL file to preserve formatting
        output.append("  📝 SQL Query:")
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
            # Fallback to test SQL if file not found
            sql_lines = self.test.sql.split("\n")
            for line in sql_lines:
                output.append(f"     {line}")
        output.append("")

        # Test Metadata Section - Key highlights
        output.append("  📋 Metadata:")
        if self.test.severity:
            output.append(f"     Severity: {self.test.severity.value}")

        if self.test.tags:
            output.append(f"     Tags: {', '.join(self.test.tags)}")

        if self.test.description:
            output.append(f"     Description: {self.test.description}")

        output.append("━" * 80)
        output.append("")

        print("\n".join(output))
