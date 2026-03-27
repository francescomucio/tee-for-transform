"""
Source parser for dbt projects.

Parses dbt source definitions from __sources.yml files.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class SourceParser:
    """Parser for dbt source definitions."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize source parser.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def parse_source_file(self, source_file: Path) -> dict[str, dict[str, str]]:
        """
        Parse a __sources.yml file and extract source definitions.

        Args:
            source_file: Path to the __sources.yml file

        Returns:
            Dictionary mapping source names to table mappings
            Format: {source_name: {table_name: "schema.table"}}
        """
        sources = {}

        try:
            with source_file.open("r", encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                logger.warning(f"Source file {source_file} is not a valid YAML dictionary")
                return sources

            # Extract sources from the YAML
            if "sources" in content:
                for source_def in content["sources"]:
                    if not isinstance(source_def, dict) or "name" not in source_def:
                        continue

                    source_name = source_def["name"]
                    source_schema = source_def.get("schema", source_name)  # Default to source name

                    # Extract tables
                    if "tables" in source_def:
                        table_map = {}
                        for table_def in source_def["tables"]:
                            if isinstance(table_def, dict) and "name" in table_def:
                                table_name = table_def["name"]
                                # Convert to schema.table format
                                table_map[table_name] = f"{source_schema}.{table_name}"

                        if table_map:
                            sources[source_name] = table_map

            if self.verbose:
                logger.info(f"Parsed {len(sources)} sources from {source_file}")

        except Exception as e:
            logger.warning(f"Error parsing source file {source_file}: {e}")

        return sources

    def parse_all_source_files(self, source_files: list[Path]) -> dict[str, dict[str, str]]:
        """
        Parse all source files and combine source definitions.

        Args:
            source_files: List of source file Path objects

        Returns:
            Dictionary mapping source names to table mappings
        """
        all_sources = {}

        for source_file in source_files:
            sources = self.parse_source_file(source_file)
            # Merge sources (later files override earlier ones if same source name)
            for source_name, table_map in sources.items():
                if source_name in all_sources:
                    all_sources[source_name].update(table_map)
                else:
                    all_sources[source_name] = table_map

        if self.verbose:
            logger.info(f"Parsed {len(all_sources)} total sources from {len(source_files)} files")

        return all_sources
