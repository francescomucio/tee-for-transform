"""
Seed file discovery and loading functionality.

This module handles discovering and loading seed files (CSV, JSON, TSV) from the seeds folder
into database tables. Seeds are loaded before models are executed.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from t4t.adapters.base import DatabaseAdapter

# Configure logging
logger = logging.getLogger(__name__)

# Supported seed file extensions
SUPPORTED_SEED_EXTENSIONS = [".csv", ".json", ".tsv"]


class SeedDiscovery:
    """Handles discovery of seed files in the seeds folder."""

    def __init__(self, seeds_folder: Path) -> None:
        """
        Initialize the seed discovery.

        Args:
            seeds_folder: Path to the seeds folder
        """
        self.seeds_folder = seeds_folder
        self._file_cache: list[tuple[Path, str | None]] = []

    def discover_seed_files(self) -> list[tuple[Path, str | None]]:
        """
        Discover all seed files in the seeds folder.

        Returns:
            List of tuples (file_path, schema_name) where schema_name is None if file
            is directly in seeds folder, or the first subfolder name if in a subfolder.
        """
        if self._file_cache:
            return self._file_cache

        if not self.seeds_folder.exists():
            logger.debug(f"Seeds folder not found: {self.seeds_folder}")
            return []

        seed_files = []
        for ext in SUPPORTED_SEED_EXTENSIONS:
            # Find all files with this extension
            for file_path in self.seeds_folder.rglob(f"*{ext}"):
                # Determine schema name from path
                # If file is in a subfolder, use the first subfolder as schema name
                relative_path = file_path.relative_to(self.seeds_folder)
                parts = relative_path.parts

                # In a subfolder: first part is the schema name; directly in
                # the seeds folder: no schema
                schema_name = parts[0] if len(parts) > 1 else None

                seed_files.append((file_path, schema_name))

        # Sort for consistent ordering
        seed_files.sort(key=lambda x: (x[1] or "", x[0]))

        self._file_cache = seed_files
        logger.debug(f"Discovered {len(seed_files)} seed files")
        return seed_files

    def clear_cache(self) -> None:
        """Clear the seed discovery cache."""
        self._file_cache.clear()
        logger.debug("Seed discovery cache cleared")


class SeedLoader:
    """Handles loading seed files into database tables."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the seed loader.

        Args:
            adapter: Database adapter to use for loading seeds
        """
        self.adapter = adapter
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_seed_file(
        self, file_path: Path, table_name: str, schema_name: str | None = None
    ) -> None:
        """
        Load a seed file into a database table.

        Args:
            file_path: Path to the seed file
            table_name: Name of the table to create (without schema)
            schema_name: Optional schema name
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Seed file not found: {file_path}")

        # Construct full table name
        full_table_name = f"{schema_name}.{table_name}" if schema_name else table_name

        # Apply naming strategy (env-aware schema prefix)
        full_table_name = self.adapter.apply_naming(full_table_name)

        # Determine file type and load accordingly
        file_ext = file_path.suffix.lower()

        if file_ext == ".csv":
            self._load_csv(file_path, full_table_name)
        elif file_ext == ".tsv":
            self._load_tsv(file_path, full_table_name)
        elif file_ext == ".json":
            self._load_json(file_path, full_table_name)
        else:
            raise ValueError(f"Unsupported seed file type: {file_ext}")

        self.logger.info(f"Loaded seed file {file_path} into table {full_table_name}")

    def _load_csv(self, file_path: Path, table_name: str) -> None:
        """Load a CSV file into a table."""
        # Create schema if needed
        self._create_schema_if_needed(table_name)

        # Read CSV and determine column types
        with open(file_path, encoding="utf-8") as f:
            # CSV files use comma as delimiter
            reader = csv.DictReader(f, delimiter=",")

            # Get column names from header
            if not reader.fieldnames:
                raise ValueError(f"CSV file {file_path} has no header row")

            columns = list(reader.fieldnames)

            # Read all rows
            rows = list(reader)

        if not rows:
            # Create empty table with just column names
            self._create_empty_table(table_name, columns)
            return

        # Generate CREATE TABLE AS SELECT statement
        # For DuckDB, we can use read_csv_auto
        if self.adapter.config.type == "duckdb":
            self._load_csv_duckdb(file_path, table_name, columns)
        else:
            # For other databases, use INSERT statements
            self._load_csv_generic(file_path, table_name, columns, rows)

    def _load_tsv(self, file_path: Path, table_name: str) -> None:
        """Load a TSV file into a table."""
        # TSV is just CSV with tab delimiter
        # Create schema if needed
        self._create_schema_if_needed(table_name)

        # Read TSV
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")

            if not reader.fieldnames:
                raise ValueError(f"TSV file {file_path} has no header row")

            columns = list(reader.fieldnames)
            rows = list(reader)

        if not rows:
            self._create_empty_table(table_name, columns)
            return

        if self.adapter.config.type == "duckdb":
            self._load_tsv_duckdb(file_path, table_name, columns)
        else:
            self._load_tsv_generic(file_path, table_name, columns, rows)

    def _load_json(self, file_path: Path, table_name: str) -> None:
        """Load a JSON file into a table."""
        # Create schema if needed
        self._create_schema_if_needed(table_name)

        # Read JSON
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Handle empty data
        if not data:
            raise ValueError(f"JSON file {file_path} is empty or invalid")

        # Handle both array of objects and single object
        if isinstance(data, list):
            if len(data) == 0:
                raise ValueError(f"JSON file {file_path} contains empty array")
            # Array of objects
            columns = list(data[0].keys())
            rows = data
        elif isinstance(data, dict):
            # Single object - treat as single row
            columns = list(data.keys())
            rows = [data]
        else:
            raise ValueError(f"JSON file {file_path} must contain an array or object")

        if self.adapter.config.type == "duckdb":
            self._load_json_duckdb(file_path, table_name, columns)
        else:
            self._load_json_generic(table_name, columns, rows)

    def _load_csv_duckdb(self, file_path: Path, table_name: str, _columns: list[str]) -> None:
        """Load CSV using DuckDB's read_csv_auto function."""
        # Use DuckDB's read_csv_auto for efficient loading
        # Explicitly specify comma delimiter for CSV files
        # Escape single quotes in path and convert backslashes to forward slashes
        file_path_str = str(file_path.absolute()).replace("\\", "/").replace("'", "''")
        query = f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path_str}', delim=',')"

        try:
            self.adapter.execute_query(query)
        except Exception as e:
            self.logger.error(f"Error loading CSV with DuckDB: {e}")
            raise

    def _load_tsv_duckdb(self, file_path: Path, table_name: str, _columns: list[str]) -> None:
        """Load TSV using DuckDB's read_csv_auto function with delimiter option."""
        # Escape single quotes in path and convert backslashes to forward slashes
        file_path_str = str(file_path.absolute()).replace("\\", "/").replace("'", "''")
        query = f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path_str}', delim='\\t')"

        try:
            self.adapter.execute_query(query)
        except Exception as e:
            self.logger.error(f"Error loading TSV with DuckDB: {e}")
            raise

    def _load_json_duckdb(self, file_path: Path, table_name: str, _columns: list[str]) -> None:
        """Load JSON using DuckDB's read_json_auto function."""
        # Escape single quotes in path and convert backslashes to forward slashes
        file_path_str = str(file_path.absolute()).replace("\\", "/").replace("'", "''")
        query = f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_json_auto('{file_path_str}')"

        try:
            self.adapter.execute_query(query)
        except Exception as e:
            self.logger.error(f"Error loading JSON with DuckDB: {e}")
            raise

    def _load_csv_generic(
        self, _file_path: Path, table_name: str, columns: list[str], rows: list[dict[str, Any]]
    ) -> None:
        """Load CSV using generic INSERT statements."""
        # Create table first
        column_defs = ", ".join([f"{col} VARCHAR" for col in columns])
        create_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({column_defs})"

        try:
            self.adapter.execute_query(create_query)

            # Insert rows
            if rows:
                for row in rows:
                    values = [self._escape_value(row.get(col, "")) for col in columns]
                    values_str = ", ".join(values)
                    insert_query = (
                        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({values_str})"
                    )
                    self.adapter.execute_query(insert_query)
        except Exception as e:
            self.logger.error(f"Error loading CSV generically: {e}")
            raise

    def _load_tsv_generic(
        self, file_path: Path, table_name: str, columns: list[str], rows: list[dict[str, Any]]
    ) -> None:
        """Load TSV using generic INSERT statements."""
        self._load_csv_generic(file_path, table_name, columns, rows)

    def _load_json_generic(
        self, table_name: str, columns: list[str], rows: list[dict[str, Any]]
    ) -> None:
        """Load JSON using generic INSERT statements."""
        # Create table first
        column_defs = ", ".join([f"{col} VARCHAR" for col in columns])
        create_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({column_defs})"

        try:
            self.adapter.execute_query(create_query)

            # Insert rows
            if rows:
                for row in rows:
                    values = [self._escape_value(row.get(col, "")) for col in columns]
                    values_str = ", ".join(values)
                    insert_query = (
                        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({values_str})"
                    )
                    self.adapter.execute_query(insert_query)
        except Exception as e:
            self.logger.error(f"Error loading JSON generically: {e}")
            raise

    def _create_empty_table(self, table_name: str, columns: list[str]) -> None:
        """Create an empty table with the specified columns."""
        column_defs = ", ".join([f"{col} VARCHAR" for col in columns])
        create_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({column_defs})"

        try:
            self.adapter.execute_query(create_query)
        except Exception as e:
            self.logger.error(f"Error creating empty table: {e}")
            raise

    def _create_schema_if_needed(self, table_name: str) -> None:
        """Create schema if needed for the given table name."""
        if "." in table_name:
            schema_name, _ = table_name.split(".", 1)
            try:
                # Use adapter's method if available
                if hasattr(self.adapter, "_create_schema_if_needed"):
                    self.adapter._create_schema_if_needed(table_name)
                else:
                    # Fallback: execute CREATE SCHEMA directly
                    create_schema_query = f"CREATE SCHEMA IF NOT EXISTS {schema_name}"
                    self.adapter.execute_query(create_schema_query)
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema_name}: {e}")

    def _escape_value(self, value: Any) -> str:
        """Escape a value for SQL insertion."""
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        # Escape string values
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def load_all_seeds(self, seed_files: list[tuple[Path, str | None]]) -> dict[str, Any]:
        """
        Load all seed files into database tables.

        Args:
            seed_files: List of tuples (file_path, schema_name)

        Returns:
            Dictionary with loading results
        """
        results = {
            "loaded_tables": [],
            "failed_tables": [],
            "total_seeds": len(seed_files),
        }

        self.logger.info(f"Loading {len(seed_files)} seed files")

        for file_path, schema_name in seed_files:
            try:
                # Get table name from file name (without extension)
                table_name = file_path.stem

                # Load the seed file
                self.load_seed_file(file_path, table_name, schema_name)

                # Record success
                full_table_name = f"{schema_name}.{table_name}" if schema_name else table_name
                results["loaded_tables"].append(full_table_name)
                self.logger.info(f"Successfully loaded seed: {full_table_name}")

            except Exception as e:
                error_msg = f"Error loading seed file {file_path}: {e}"
                self.logger.error(error_msg)
                results["failed_tables"].append({"file": str(file_path), "error": str(e)})

        self.logger.info(
            f"Seed loading completed. {len(results['loaded_tables'])} successful, "
            f"{len(results['failed_tables'])} failed"
        )

        return results
