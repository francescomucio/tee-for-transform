"""
Test discovery for dbt projects.

Discovers test files in the tests/ directory and identifies test types.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TestFileDiscovery:
    """Discovers test files in dbt projects."""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(self, source_path: Path, verbose: bool = False) -> None:
        """
        Initialize test discovery.

        Args:
            source_path: Path to dbt project root
            verbose: Enable verbose logging
        """
        self.source_path = Path(source_path).resolve()
        self.verbose = verbose
        self.tests_dir = self.source_path / "tests"

    def discover_test_files(self) -> dict[str, Path]:
        """
        Discover all test files in the tests/ directory.

        Returns:
            Dictionary mapping test file paths (relative to project root) to absolute Path objects
        """
        test_files: dict[str, Path] = {}

        if not self.tests_dir.exists():
            if self.verbose:
                logger.debug(f"Tests directory not found: {self.tests_dir}")
            return test_files

        # Find all .sql files in tests/ directory
        for sql_file in self.tests_dir.rglob("*.sql"):
            # Get relative path from project root
            rel_path = sql_file.relative_to(self.source_path)
            test_files[str(rel_path)] = sql_file

        if self.verbose:
            logger.info(f"Discovered {len(test_files)} test file(s) in {self.tests_dir}")

        return test_files

    def is_source_freshness_test(self, test_file: Path) -> bool:
        """
        Check if a test file is a source freshness test.

        Note: In dbt, source freshness tests are actually defined in __sources.yml
        files with a `freshness` block, not as SQL test files. SQL test files that
        check freshness are regular singular tests and should be converted normally.

        However, we may want to detect tests that are clearly meant to be freshness
        tests (e.g., tests that check source freshness but are written as SQL files).
        For now, we only check filename patterns to be conservative.

        Args:
            test_file: Path to test file

        Returns:
            True if this appears to be a source freshness test
        """
        try:
            # Only check filename patterns to be conservative
            # Actual dbt freshness tests are in __sources.yml, not SQL files
            filename_lower = test_file.name.lower()

            # Very specific patterns that indicate this is a freshness test
            # (though in dbt, these would typically be in __sources.yml)
            freshness_filename_patterns = [
                "source_freshness",
                "check_source_freshness",
                "test_source_freshness",
            ]

            # Only flag if filename explicitly indicates freshness test
            return bool(any(pattern in filename_lower for pattern in freshness_filename_patterns))
        except Exception as e:
            logger.warning(f"Error checking if {test_file} is a freshness test: {e}")
            return False
