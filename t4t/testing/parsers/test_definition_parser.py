"""
Test definition parsing utilities.

Extracts test definition parsing logic from TestExecutor to eliminate duplication.
"""

import logging
from dataclasses import dataclass
from typing import Any

from t4t.testing.base import TestSeverity
from t4t.typing.metadata import TestDefinition

logger = logging.getLogger(__name__)


@dataclass
class ParsedTestDefinition:
    """Parsed test definition with extracted components."""

    test_name: str
    params: dict[str, Any] | None = None
    expected: Any | None = None
    severity_override: TestSeverity | None = None


class TestDefinitionParser:
    """Parses test definitions from various formats."""

    @staticmethod
    def parse(
        test_def: TestDefinition,
        severity_overrides: dict[str, TestSeverity],
        context: str,
    ) -> ParsedTestDefinition | None:
        """
        Parse a test definition into its components.

        Args:
            test_def: Test definition (string name or dict with name/params/severity/expected)
            severity_overrides: Dict of severity overrides
            context: Context string for override key (e.g., "table_name.test_name" or "function_name.test_name")

        Returns:
            ParsedTestDefinition or None if parsing fails
        """
        if isinstance(test_def, str):
            return ParsedTestDefinition(
                test_name=test_def,
                params=None,
                expected=None,
                severity_override=severity_overrides.get(test_def),
            )

        if isinstance(test_def, dict):
            test_name = test_def.get("name") or test_def.get("test")
            if not test_name:
                logger.warning(f"Test definition missing name: {test_def}")
                return None

            # Extract params (everything except name/test, severity, and expected)
            params = {
                k: v
                for k, v in test_def.items()
                if k not in ["name", "test", "severity", "expected"]
            }
            if not params:
                params = None

            # Extract expected value (for expected value pattern)
            expected = test_def.get("expected")

            # Get severity override from test definition or overrides dict
            severity_override = TestDefinitionParser._extract_severity_override(
                test_def, severity_overrides, context, test_name
            )

            return ParsedTestDefinition(
                test_name=test_name,
                params=params,
                expected=expected,
                severity_override=severity_override,
            )

        logger.warning(f"Invalid test definition type: {type(test_def)}")
        return None

    @staticmethod
    def _extract_severity_override(
        test_def: dict[str, Any],
        severity_overrides: dict[str, TestSeverity],
        context: str,
        test_name: str,
    ) -> TestSeverity | None:
        """
        Extract severity override from test definition or overrides dict.

        Args:
            test_def: Test definition dict
            severity_overrides: Dict of severity overrides
            context: Context string for override key
            test_name: Test name

        Returns:
            TestSeverity or None
        """
        severity_str = test_def.get("severity")
        if severity_str:
            try:
                return TestSeverity(severity_str.lower())
            except ValueError:
                logger.warning(f"Invalid severity '{severity_str}', using default")
                return None

        # Check severity_overrides dict (key format: "context.test_name" or just "test_name")
        override_key = f"{context}.{test_name}"
        return severity_overrides.get(override_key) or severity_overrides.get(test_name)
