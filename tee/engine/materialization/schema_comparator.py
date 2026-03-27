"""
Schema comparison and change detection for incremental materialization.

This module compares transformation output schema with existing table schema
to detect differences for on_schema_change handling (OTS 0.2.1).
"""

import logging
from typing import Any

from tee.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class SchemaComparator:
    """Compares transformation output schema with existing table schema."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the schema comparator.

        Args:
            adapter: Database adapter instance
        """
        self.adapter = adapter

    def infer_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """
        Infer schema from SQL query output using database-specific methods.

        Uses adapter.describe_query_schema() if available, otherwise falls back
        to executing the query with LIMIT 0 and extracting metadata.

        Args:
            sql_query: SQL query to analyze

        Returns:
            List of column definitions: [{"name": "col1", "type": "VARCHAR"}, ...]
        """
        # Use adapter's describe_query_schema method if available
        if hasattr(self.adapter, "describe_query_schema") and callable(
            self.adapter.describe_query_schema
        ):
            try:
                return self.adapter.describe_query_schema(sql_query)
            except Exception as e:
                # Check if the error is due to a missing table reference (common with auto_incremental wrapped queries)
                error_str = str(e).lower()
                if (
                    "does not exist" in error_str
                    or "not found" in error_str
                    or "not authorized" in error_str
                ):
                    # This is likely a wrapped query referencing a table that doesn't exist yet
                    # Log at debug level instead of warning since this is expected behavior
                    logger.debug(
                        f"describe_query_schema failed (likely due to missing table reference in wrapped query): {e}"
                    )
                else:
                    logger.warning(f"describe_query_schema failed, falling back to LIMIT 0: {e}")
                # Fall through to LIMIT 0 approach

        # Fallback: Execute query with LIMIT 0 and extract schema from result
        try:
            # Wrap query in a subquery and add LIMIT 0
            # This executes the query structure without returning data
            limit_query = f"SELECT * FROM ({sql_query}) LIMIT 0"
            result = self.adapter.execute_query(limit_query)

            # Extract schema from result metadata
            # This is database-specific, so we need to handle different result types
            schema = []
            if hasattr(result, "description"):  # Python DB-API cursor
                for col in result.description:
                    schema.append({"name": col[0], "type": col[1]})
            elif hasattr(result, "columns"):  # Pandas-like
                for col_name, col_type in zip(result.columns, result.dtypes, strict=True):
                    schema.append({"name": col_name, "type": str(col_type)})
            else:
                # Try to get schema from cursor if available
                cursor = getattr(self.adapter, "connection", None)
                if cursor and hasattr(cursor, "description"):
                    for col in cursor.description:
                        schema.append({"name": col[0], "type": col[1]})

            if schema:
                return schema

            # Check if the error in the outer try block was due to missing table reference
            # If so, this is expected and we should log at debug level
            logger.debug("Could not extract schema from query result, using empty schema")
            return []
        except Exception as e:
            logger.error(f"Failed to infer query schema: {e}")
            raise

    def get_table_schema(self, table_name: str) -> list[dict[str, Any]]:
        """
        Get schema from existing table.

        Args:
            table_name: Name of the table

        Returns:
            List of column definitions: [{"name": "col1", "type": "VARCHAR"}, ...]
        """
        try:
            table_info = self.adapter.get_table_info(table_name)
            schema = table_info.get("schema", [])

            # Normalize schema format - adapters return {"column": ..., "type": ...}
            # but we want {"name": ..., "type": ...}
            normalized_schema = []
            for col in schema:
                normalized_schema.append(
                    {
                        "name": col.get("column") or col.get("name"),
                        "type": col.get("type"),
                    }
                )

            return normalized_schema
        except Exception as e:
            logger.error(f"Failed to get table schema for {table_name}: {e}")
            raise

    def compare_schemas(
        self,
        query_schema: list[dict[str, Any]],
        table_schema: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Compare two schemas and identify differences.

        Args:
            query_schema: Schema from transformation output
            table_schema: Schema from existing table

        Returns:
            Dictionary with:
            - "new_columns": List of columns in query but not in table
            - "missing_columns": List of columns in table but not in query
            - "type_mismatches": List of columns with same name but different type
            - "has_changes": Boolean indicating if any differences exist
        """
        # Normalize column names to lowercase for comparison (case-insensitive)
        query_cols = {col["name"].lower(): col for col in query_schema}
        table_cols = {col["name"].lower(): col for col in table_schema}

        new_columns = []
        missing_columns = []
        type_mismatches = []

        # Find new columns (in query, not in table)
        for col_name, col_info in query_cols.items():
            if col_name not in table_cols:
                new_columns.append(col_info)
            else:
                # Check for type mismatch
                query_type = self._normalize_type(col_info.get("type", ""))
                table_type = self._normalize_type(table_cols[col_name].get("type", ""))
                if query_type != table_type:
                    type_mismatches.append(
                        {
                            "name": col_info["name"],
                            "query_type": col_info.get("type", ""),
                            "table_type": table_cols[col_name].get("type", ""),
                        }
                    )

        # Find missing columns (in table, not in query)
        for col_name, col_info in table_cols.items():
            if col_name not in query_cols:
                missing_columns.append(col_info)

        has_changes = len(new_columns) > 0 or len(missing_columns) > 0 or len(type_mismatches) > 0

        return {
            "new_columns": new_columns,
            "missing_columns": missing_columns,
            "type_mismatches": type_mismatches,
            "has_changes": has_changes,
        }

    def _normalize_type(self, type_str: str) -> str:
        """
        Normalize database type strings for comparison.

        This handles variations like VARCHAR(255) vs VARCHAR vs TEXT,
        INTEGER vs INT, etc. The goal is to identify truly different types
        vs just variations of the same type.

        Args:
            type_str: Database type string

        Returns:
            Normalized type string for comparison
        """
        if not type_str:
            return ""

        # Convert to uppercase and remove whitespace
        normalized = type_str.upper().strip()

        # Remove length/precision specifications for comparison
        # e.g., VARCHAR(255) -> VARCHAR, DECIMAL(10,2) -> DECIMAL
        import re

        # Remove parentheses and contents: VARCHAR(255) -> VARCHAR
        normalized = re.sub(r"\([^)]*\)", "", normalized)

        # Map common type aliases to canonical forms
        # Order matters: longer/more specific aliases first to avoid partial matches
        type_aliases = [
            ("INT8", "BIGINT"),
            ("INT4", "INTEGER"),
            ("INT", "INTEGER"),
            ("FLOAT8", "DOUBLE"),
            ("FLOAT4", "REAL"),
            ("FLOAT", "DOUBLE"),
            ("TIMESTAMP_TZ", "TIMESTAMP"),
            ("TIMESTAMP_LTZ", "TIMESTAMP"),
            ("TIMESTAMP_NTZ", "TIMESTAMP"),
            ("CHAR", "VARCHAR"),
            ("TEXT", "VARCHAR"),  # Many databases treat TEXT and VARCHAR similarly
            ("STRING", "VARCHAR"),
            ("BOOL", "BOOLEAN"),
        ]

        # Check for aliases (longer ones first to avoid partial matches)
        for alias, canonical in type_aliases:
            if normalized.startswith(alias):
                return canonical

        return normalized
