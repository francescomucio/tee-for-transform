"""
Seed converter for dbt projects.

Copies seed files and converts seed configurations.
"""

import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SeedConverter:
    """Converts dbt seeds to t4t format."""

    def __init__(
        self,
        source_path: Path,
        target_path: Path,
        dbt_project: dict[str, Any],
        verbose: bool = False,
    ) -> None:
        """
        Initialize seed converter.

        Args:
            source_path: Path to dbt project root
            target_path: Path where t4t project will be created
            dbt_project: Parsed dbt project configuration
            verbose: Enable verbose logging
        """
        self.source_path = Path(source_path).resolve()
        self.target_path = Path(target_path).resolve()
        self.dbt_project = dbt_project
        self.verbose = verbose

    def convert_seeds(self) -> dict[str, Any]:
        """
        Convert dbt seeds to t4t format.

        Returns:
            Dictionary with conversion statistics
        """
        seed_paths = self.dbt_project.get("seed-paths", ["seeds"])
        copied_count = 0
        error_count = 0

        for seed_path_str in seed_paths:
            seed_path = self.source_path / seed_path_str

            if not seed_path.exists():
                if self.verbose:
                    logger.debug(f"Seed path does not exist: {seed_path}")
                continue

            # Find all seed files (CSV, TSV, JSON, etc.)
            seed_extensions = [".csv", ".tsv", ".json", ".parquet"]
            for ext in seed_extensions:
                for seed_file in seed_path.rglob(f"*{ext}"):
                    try:
                        # Get relative path from seed directory
                        rel_path = seed_file.relative_to(seed_path)

                        # Target file
                        target_file = self.target_path / "seeds" / rel_path

                        # Create directory if needed
                        target_file.parent.mkdir(parents=True, exist_ok=True)

                        # Copy file
                        shutil.copy2(seed_file, target_file)

                        copied_count += 1
                        if self.verbose:
                            logger.info(f"Copied seed file: {seed_file} -> {target_file}")

                    except Exception as e:
                        error_count += 1
                        logger.warning(f"Error copying seed file {seed_file}: {e}")

        return {
            "copied": copied_count,
            "errors": error_count,
        }
