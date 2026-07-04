"""
Test discovery for finding SQL and Python test files in project's tests/ folder.
"""

import importlib.util
import logging
import sys
import types
from pathlib import Path

from .base import StandardTest, TestRegistry, TestSeverity
from .sql_test import SqlTest
from .test_builder import SqlTestMetadata
from .test_decorator import TestDecoratorError, create_test, test

logger = logging.getLogger(__name__)


class TestDiscoveryError(Exception):
    """Raised when test discovery fails."""

    __test__ = False  # Tell pytest this is not a test class

    pass


class TestDiscovery:
    """Discovers SQL and Python test files in the project's tests/ folder."""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(self, project_folder: Path):
        """
        Initialize test discovery.

        Args:
            project_folder: Path to the project folder (should contain tests/ subfolder)
        """
        self.project_folder = Path(project_folder)
        self.tests_folder = self.project_folder / "tests"
        self.functions_tests_folder = self.project_folder / "tests" / "functions"
        self._discovered_tests: dict[str, StandardTest] = {}
        self._discovered_function_tests: dict[str, SqlTest] = {}
        self._python_test_files: set[Path] = set()

    def discover_tests(self) -> dict[str, StandardTest]:
        """
        Discover all test files (Python + SQL) in the tests/ folder (excluding tests/functions/).

        Returns:
            Dictionary mapping test names to StandardTest instances (PythonTest or SqlTest)

        Discovery flow:
        1. Clear TestRegistry
        2. Execute Python test files (they auto-register)
        3. Discover remaining SQL files (those without companion .py or with SqlTestMetadata .py)
        4. If companion .py exists, assume it's SqlTestMetadata and skip SQL file
        """
        if self._discovered_tests:
            return self._discovered_tests

        if not self.tests_folder.exists():
            logger.debug(f"Tests folder not found: {self.tests_folder}")
            return {}

        # Clear TestRegistry before discovery
        TestRegistry.clear()

        # Step 1: Discover and execute Python test files
        python_files = self._discover_python_test_files()
        python_file_bases = {f.stem for f in python_files}
        self._python_test_files = python_files

        for py_file in python_files:
            try:
                self._execute_python_test_file(py_file)
            except Exception as e:
                error_msg = f"Failed to execute Python test file {py_file}: {e}"
                logger.error(error_msg)
                raise TestDiscoveryError(error_msg) from e

        # Step 2: Get all registered tests from TestRegistry (from Python files)
        discovered = {}
        registered_test_names = TestRegistry.list_all()
        for test_name in registered_test_names:
            registered_test = TestRegistry.get(test_name)
            if registered_test:
                discovered[test_name] = registered_test
                logger.debug(f"Registered test from Python file: {test_name}")

        # Step 3: Discover remaining SQL files (those without companion .py or with SqlTestMetadata .py)
        sql_files = [
            f
            for f in self.tests_folder.rglob("*.sql")
            if not str(f).startswith(str(self.functions_tests_folder))
        ]

        for sql_file in sql_files:
            sql_file_stem = sql_file.stem

            # Check if companion .py file exists
            if sql_file_stem in python_file_bases:
                # If companion .py exists, assume it's SqlTestMetadata and skip SQL file
                # The Python file should have already registered the test during execution
                companion_py = None
                for py_file in python_files:
                    if py_file.stem == sql_file_stem:
                        companion_py = py_file
                        break

                # Check if .py file registered a test with the same name (via SqlTestMetadata)
                # If yes, skip SQL file (already registered)
                # If no, process SQL file (Python file didn't register anything)
                if companion_py and sql_file_stem in discovered:
                    logger.debug(
                        f"Skipping {sql_file} - companion Python file {companion_py} already registered test '{sql_file_stem}'"
                    )
                    continue

            # No companion .py or .py is metadata-only: create SqlTest
            try:
                test_name = sql_file_stem

                if test_name in discovered:
                    logger.warning(
                        f"Duplicate test name '{test_name}' found. "
                        f"Using {sql_file} (previous: {discovered[test_name]})"
                    )

                # Create SqlTest instance
                sql_test = SqlTest(
                    name=test_name,
                    sql_file_path=sql_file,
                    project_folder=self.project_folder,
                    severity=TestSeverity.ERROR,
                )

                discovered[test_name] = sql_test
                TestRegistry.register(sql_test)
                logger.debug(f"Discovered SQL test: {test_name} from {sql_file}")

            except Exception as e:
                logger.error(f"Failed to load SQL test from {sql_file}: {e}")
                continue

        logger.info(
            f"Discovered {len(discovered)} test(s) from {self.tests_folder} "
            f"({len(python_files)} Python, {len(sql_files)} SQL)"
        )
        self._discovered_tests = discovered
        return discovered

    def _discover_python_test_files(self) -> list[Path]:
        """Discover all Python test files in tests/ folder (excluding tests/functions/)."""
        if not self.tests_folder.exists():
            return []

        python_files = []
        for ext in [".py"]:
            python_files.extend(
                [
                    f
                    for f in self.tests_folder.rglob(f"*{ext}")
                    if not str(f).startswith(str(self.functions_tests_folder))
                ]
            )

        python_files.sort()
        return python_files

    def _execute_python_test_file(self, py_file: Path) -> None:
        """
        Execute a Python test file in an isolated module namespace.

        The file will have access to: test, create_test, SqlTestMetadata
        Tests will auto-register themselves when executed.

        Args:
            py_file: Path to the Python test file

        Raises:
            TestDiscoveryError: If execution fails
        """
        module_name = f"temp_test_module_{hash(py_file)}"

        try:
            # Read file content
            with open(py_file, encoding="utf-8") as f:
                content = f.read()

            # Create a module spec and execute the file
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            if spec is None:
                raise TestDiscoveryError(f"Could not create module spec for {py_file}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            # Inject test decorator, create_test, and SqlTestMetadata into the module
            # Mark test as not a pytest test function (it's a decorator)
            test_func = test
            test_func.__test__ = False
            module.test = test_func
            module.create_test = create_test
            module.SqlTestMetadata = SqlTestMetadata

            # Also inject into tee.testing structure for imports
            if "tee" not in sys.modules:
                tee_module = types.ModuleType("tee")
                sys.modules["tee"] = tee_module
            if "tee.testing" not in sys.modules:
                testing_module = types.ModuleType("testing")
                sys.modules["tee.testing"] = testing_module
            # Mark test as not a pytest test function (it's a decorator)
            test_func = test
            test_func.__test__ = False
            sys.modules["tee.testing"].test = test_func
            sys.modules["tee.testing"].create_test = create_test
            sys.modules["tee.testing"].SqlTestMetadata = SqlTestMetadata

            # Set __file__ so SqlTestMetadata can find the companion SQL file
            module.__file__ = str(py_file.absolute())

            # Execute the file content
            exec(content, module.__dict__)

            logger.debug(f"Executed Python test file: {py_file}")

        except TestDecoratorError as e:
            # Re-raise test decorator errors as discovery errors
            raise TestDiscoveryError(f"Test registration error in {py_file}: {e}") from e
        except Exception as e:
            raise TestDiscoveryError(f"Failed to execute Python test file {py_file}: {e}") from e
        finally:
            # Clean up
            if module_name in sys.modules:
                del sys.modules[module_name]

    def discover_function_tests(self) -> dict[str, SqlTest]:
        """
        Discover all SQL test files in the tests/functions/ folder.

        Returns:
            Dictionary mapping test names to SqlTest instances

        Test names are derived from file names (without .sql extension).
        Example: tests/functions/calculate_percentage_test.sql -> test name "calculate_percentage_test"
        """
        if self._discovered_function_tests:
            return self._discovered_function_tests

        if not self.functions_tests_folder.exists():
            logger.debug(f"Function tests folder not found: {self.functions_tests_folder}")
            return {}

        discovered = {}

        # Find all .sql files in tests/functions/ folder
        sql_files = list(self.functions_tests_folder.rglob("*.sql"))

        for sql_file in sql_files:
            try:
                # Test name is the file name without extension
                test_name = sql_file.stem  # filename without extension

                if test_name in discovered:
                    logger.warning(
                        f"Duplicate function test name '{test_name}' found. "
                        f"Using {sql_file} (previous: {discovered[test_name].sql_file_path})"
                    )

                # Create SqlTest instance (same class, but for functions)
                sql_test = SqlTest(
                    name=test_name,
                    sql_file_path=sql_file,
                    project_folder=self.project_folder,
                    severity=TestSeverity.ERROR,
                )

                discovered[test_name] = sql_test
                logger.debug(f"Discovered function SQL test: {test_name} from {sql_file}")

            except Exception as e:
                logger.error(f"Failed to load function SQL test from {sql_file}: {e}")
                continue

        logger.info(
            f"Discovered {len(discovered)} function SQL test(s) from {self.functions_tests_folder}"
        )
        self._discovered_function_tests = discovered
        return discovered

    def register_discovered_tests(self) -> None:
        """
        Discover and register all tests (Python + SQL, both model and function tests) with the TestRegistry.

        This should be called before test execution to ensure all tests
        are available in the registry.

        Note: Python tests are already registered during discovery (they auto-register),
        but this method ensures SQL tests are also registered.
        """
        # Discover tests (Python tests auto-register, SQL tests are registered here)
        tests = self.discover_tests()
        # Python tests are already registered, but ensure SQL tests are registered
        for test_name, test_instance in tests.items():
            if test_name not in TestRegistry.list_all():
                TestRegistry.register(test_instance)
                logger.debug(f"Registered test: {test_name}")

        # Register function tests
        function_tests = self.discover_function_tests()
        for test_name, sql_test in function_tests.items():
            TestRegistry.register(sql_test)
            logger.debug(f"Registered function SQL test: {test_name}")
