"""
Tee Testing Framework

Provides automated testing capabilities for data quality validation.
"""

# Import standard tests to trigger registration
from . import standard_tests  # noqa: F401
from .base import StandardTest, TestRegistry, TestResult, TestSeverity
from .executor import TestExecutor
from .python_test import PythonTest
from .sql_test import SqlTest
from .test_builder import SqlTestMetadata
from .test_decorator import TestDecoratorError, create_test, test
from .test_discovery import TestDiscovery, TestDiscoveryError

__all__ = [
    "StandardTest",
    "TestSeverity",
    "TestResult",
    "TestRegistry",
    "TestExecutor",
    "SqlTest",
    "PythonTest",
    "TestDiscovery",
    "TestDiscoveryError",
    "test",
    "create_test",
    "SqlTestMetadata",
    "TestDecoratorError",
]
