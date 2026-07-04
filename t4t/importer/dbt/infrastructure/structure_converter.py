"""
Structure converter for creating t4t project structure.
"""

import logging
from pathlib import Path

from t4t.importer.dbt.constants import (
    DATA_DIR,
    FUNCTIONS_DIR,
    MODELS_DIR,
    OTS_MODULES_DIR,
    OUTPUT_DIR,
    SEEDS_DIR,
    TESTS_DIR,
)

logger = logging.getLogger(__name__)


class StructureConverter:
    """Converts dbt project structure to t4t project structure."""

    def __init__(
        self,
        target_path: Path,
        output_format: str = "t4t",
        preserve_filenames: bool = False,
        verbose: bool = False,
    ) -> None:
        """
        Initialize structure converter.

        Args:
            target_path: Path where the t4t project will be created
            output_format: Output format - "t4t" or "ots"
            preserve_filenames: Keep original file names instead of using final table names
            verbose: Enable verbose logging
        """
        self.target_path = Path(target_path).resolve()
        self.output_format = output_format
        self.preserve_filenames = preserve_filenames
        self.verbose = verbose

    def create_structure(self) -> None:
        """Create the basic t4t project directory structure."""
        if self.verbose:
            logger.info(f"Creating t4t project structure at: {self.target_path}")

        # Create main directories
        directories = [MODELS_DIR, TESTS_DIR, SEEDS_DIR]

        if self.output_format == "t4t":
            # For t4t format, also create functions directory
            directories.append(FUNCTIONS_DIR)
        elif self.output_format == "ots":
            # For OTS format, create ots_modules directory
            directories.append(OTS_MODULES_DIR)

        for dir_name in directories:
            dir_path = self.target_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            if self.verbose:
                logger.info(f"Created directory: {dir_path}")

        # Create data directory (for DuckDB projects)
        data_dir = self.target_path / DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        if self.verbose:
            logger.info(f"Created directory: {data_dir}")

        # Create output directory for reports
        output_dir = self.target_path / OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.verbose:
            logger.info(f"Created directory: {output_dir}")
