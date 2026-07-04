"""
Dialect inference logic for function SQL parsing.
"""

from pathlib import Path
from typing import Any

from t4t.parser.shared.constants import KNOWN_DATABASE_NAMES


class DialectInferencer:
    """Handles SQL dialect inference from various sources."""

    @staticmethod
    def infer_from_connection(connection: dict[str, Any] | None = None) -> str:
        """
        Infer SQL dialect from connection type.

        Args:
            connection: Optional connection configuration dict

        Returns:
            SQL dialect string (e.g., 'postgres', 'snowflake', 'duckdb')
        """
        if not connection:
            return "postgres"  # Default to postgres for CREATE FUNCTION

        conn_type = connection.get("type", "duckdb")
        dialect_map = {
            "duckdb": "duckdb",
            "postgresql": "postgres",
            "postgres": "postgres",
            "snowflake": "snowflake",
            "mysql": "mysql",
            "bigquery": "bigquery",
            "spark": "spark",
        }
        return dialect_map.get(conn_type.lower(), "postgres")

    @staticmethod
    def infer_from_filename(file_path: Path) -> str | None:
        """
        Infer dialect from database-specific override filename.

        Args:
            file_path: Path to the SQL file

        Returns:
            Dialect string if detected from filename, None otherwise
        """
        stem = file_path.stem  # filename without extension
        if "." in stem:
            parts = stem.split(".")
            if len(parts) >= 2:
                # Check if last part before extension is a known database name
                potential_db = parts[-1].lower()

                if potential_db in KNOWN_DATABASE_NAMES:
                    # Map database name to dialect
                    dialect_map = {
                        "duckdb": "duckdb",
                        "postgresql": "postgres",
                        "snowflake": "snowflake",
                        "bigquery": "bigquery",
                    }
                    return dialect_map.get(potential_db, "postgres")

        return None
