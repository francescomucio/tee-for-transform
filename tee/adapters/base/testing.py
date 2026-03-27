"""
Test SQL generation methods for database adapters.

These methods are mixed into DatabaseAdapter via multiple inheritance.
"""

from typing import Any


class TestQueryGenerator:
    """Mixin class for generating test SQL queries."""

    def generate_not_null_test_query(self, table_name: str, column_name: str) -> str:
        """
        Generate SQL query for not_null test.

        Returns count of rows where column is NULL (test fails if count > 0).
        Query should return 0 if test passes.

        Uses COUNT(*) for better performance instead of returning all rows.
        Adapters can override this method for database-specific optimizations or syntax.

        Args:
            table_name: Fully qualified table name (e.g., "my_schema.my_table")
            column_name: Column name to test (e.g., "user_id")

        Returns:
            SQL query string
        """
        # Default implementation - adapters can override for optimizations
        # Note: table_name and column_name are expected to be simple identifiers
        # (no spaces, no special chars) from validated metadata
        # Using COUNT(*) for better performance on large tables
        return f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL"

    def generate_unique_test_query(self, table_name: str, columns: list[str] | None = None) -> str:
        """
        Generate SQL query for unique test.

        Returns count of duplicate groups (test fails if count > 0).
        Query should return 0 if test passes (no duplicates).

        Uses COUNT(*) for better performance instead of returning all duplicate rows.
        Adapters can override this method for database-specific optimizations or syntax.

        Args:
            table_name: Fully qualified table name (e.g., "my_schema.my_table")
            columns: List of column names to check for uniqueness (e.g., ["col1", "col2"]).
                    If None, checks all columns (entire row uniqueness).

        Returns:
            SQL query string
        """
        # Default implementation - adapters can override for optimizations
        # Note: table_name and columns are expected to be simple identifiers
        # (no spaces, no special chars) from validated metadata
        # Using COUNT(*) for better performance on large tables

        if columns is None or len(columns) == 0:
            # Check all columns (entire row uniqueness)
            # Use SELECT * to group by all columns
            return f"""
                SELECT COUNT(*)
                FROM (
                    SELECT *, COUNT(*) as duplicate_count
                    FROM {table_name}
                    GROUP BY *
                    HAVING COUNT(*) > 1
                ) AS duplicate_groups
            """
        else:
            column_list = ", ".join(columns)
            return f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {column_list}, COUNT(*) as duplicate_count
                    FROM {table_name}
                    GROUP BY {column_list}
                    HAVING COUNT(*) > 1
                ) AS duplicate_groups
            """

    def generate_no_duplicates_test_query(
        self, table_name: str, columns: list[str] | None = None
    ) -> str:
        """
        DEPRECATED: Use generate_unique_test_query instead.

        This method is kept for backward compatibility but delegates to generate_unique_test_query.
        """
        return self.generate_unique_test_query(table_name, columns)

    def generate_row_count_gt_0_test_query(self, table_name: str) -> str:
        """
        Generate SQL query for row_count_gt_0 test.

        Returns count of rows in table (test passes if count > 0).
        Query returns the row count, not violations.

        This is a default implementation using standard SQL.
        Adapters can override this method for database-specific optimizations or syntax.

        Args:
            table_name: Fully qualified table name (e.g., "my_schema.my_table")

        Returns:
            SQL query string
        """
        # Simple COUNT(*) query - returns the number of rows
        return f"SELECT COUNT(*) FROM {table_name}"

    def generate_accepted_values_test_query(
        self, table_name: str, column_name: str, values: list[Any]
    ) -> str:
        """
        Generate SQL query for accepted_values test.

        Returns count of rows where column value is not in the accepted values list.
        Query should return 0 if test passes (all values are accepted).

        Uses COUNT(*) for better performance instead of returning all rows.
        Adapters can override this method for database-specific optimizations or syntax.

        Args:
            table_name: Fully qualified table name (e.g., "my_schema.my_table")
            column_name: Column name to test (e.g., "status")
            values: List of accepted values (e.g., ["active", "inactive", "pending"])

        Returns:
            SQL query string
        """
        if not values:
            raise ValueError(
                "accepted_values test requires at least one value in 'values' parameter"
            )

        # Format values for SQL - handle strings, numbers, and other types
        formatted_values = []
        for val in values:
            if isinstance(val, str):
                # Escape single quotes in strings
                escaped_val = val.replace("'", "''")
                formatted_values.append(f"'{escaped_val}'")
            elif isinstance(val, (int, float)):
                formatted_values.append(str(val))
            elif val is None:
                formatted_values.append("NULL")
            else:
                # Convert other types to string and quote
                escaped_val = str(val).replace("'", "''")
                formatted_values.append(f"'{escaped_val}'")

        values_list = ", ".join(formatted_values)
        return f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} NOT IN ({values_list})"

    def generate_relationships_test_query(
        self,
        source_table: str,
        source_columns: list[str],
        target_table: str,
        target_columns: list[str],
    ) -> str:
        """
        Generate SQL query for relationships test.

        Returns count of rows where source column(s) value(s) don't exist in target table.
        Query should return 0 if test passes (all source values exist in target).
        Supports both single-column and composite key relationships.

        Uses COUNT(*) for better performance instead of returning all rows.
        Adapters can override this method for database-specific optimizations or syntax.

        Args:
            source_table: Fully qualified source table name (e.g., "my_schema.source_table")
            source_columns: List of column names in source table (e.g., ["user_id"] or ["region_id", "country_id"])
            target_table: Fully qualified target table name (e.g., "my_schema.users")
            target_columns: List of column names in target table (e.g., ["id"] or ["region_id", "country_id"])

        Returns:
            SQL query string
        """
        if len(source_columns) != len(target_columns):
            raise ValueError(
                f"relationships test: source_columns ({len(source_columns)}) and "
                f"target_columns ({len(target_columns)}) must have the same length"
            )

        # Build JOIN conditions for all columns
        join_conditions = []
        for source_col, target_col in zip(source_columns, target_columns, strict=True):
            join_conditions.append(f"source.{source_col} = target.{target_col}")

        join_clause = " AND ".join(join_conditions)

        # For WHERE clause, check if ANY of the target columns is NULL (indicating no match)
        # This handles composite keys correctly
        null_conditions = [f"target.{col} IS NULL" for col in target_columns]
        where_clause = " OR ".join(null_conditions)

        # LEFT JOIN to find orphaned rows (rows in source that don't exist in target)
        return f"""
            SELECT COUNT(*)
            FROM {source_table} AS source
            LEFT JOIN {target_table} AS target
                ON {join_clause}
            WHERE {where_clause}
        """

    def generate_primary_key_test_query(self, table_name: str, column_name: str) -> str:
        """
        Generate SQL query for a combined primary_key test.

        The test fails if there are:
        - NULL values in the PK column
        - duplicate values in the PK column (ignoring NULL handling; NULLs are already covered)
        """
        return f"""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM {table_name}
                    WHERE {column_name} IS NULL
                )
                +
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT {column_name}
                        FROM {table_name}
                        GROUP BY {column_name}
                        HAVING COUNT(*) > 1
                    ) AS dup_groups
                ) AS violation_count
        """

    def generate_hierarchy_no_split_test_query(
        self,
        table_name: str,
        child_col: str,
        parent_col: str,
    ) -> str:
        """
        Generate SQL query to ensure each child PK maps to exactly one parent value.

        Fails if any child_col value is associated with more than one distinct parent_col value.
        """
        return f"""
            SELECT COUNT(*)
            FROM (
                SELECT {child_col}
                FROM {table_name}
                GROUP BY {child_col}
                HAVING COUNT(DISTINCT {parent_col}) > 1
            ) AS violations
        """

    def generate_level_uniqueness_test_query(
        self,
        table_name: str,
        pk_col: str,
        attribute_cols: list[str],
    ) -> str:
        """
        Generate SQL query to ensure attribute values for each PK are consistent.

        Fails if the same pk_col is associated with more than one distinct attribute tuple.
        """
        if not attribute_cols:
            # Trivially unique: no attributes to vary.
            return "SELECT 0"

        attrs = ", ".join(attribute_cols)

        return f"""
            SELECT COUNT(*)
            FROM (
                SELECT {pk_col}
                FROM (
                    SELECT {pk_col}, {attrs}
                    FROM {table_name}
                    GROUP BY {pk_col}, {attrs}
                ) AS tuples
                GROUP BY {pk_col}
                HAVING COUNT(*) > 1
            ) AS violations
        """
