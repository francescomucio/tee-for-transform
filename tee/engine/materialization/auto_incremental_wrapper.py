"""
AutoIncremental query wrapper for dimension tables.

Supports two modes:
1. Explicit mode: User writes full query including ID column (e.g., ROW_NUMBER() OVER ... AS id)
   - For full refresh: execute as-is
   - For incremental: add MAX(id) to existing ROW_NUMBER() expression
2. Implicit mode: User writes simple query without ID column
   - System wraps query with full auto_incremental logic
"""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tee.adapters.base.core import DatabaseAdapter

import sqlglot
from sqlglot import expressions as exp

logger = logging.getLogger(__name__)


class AutoIncrementalWrapper:
    """Wraps SQL queries with auto_incremental ID calculation logic."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the auto_incremental wrapper.

        Args:
            adapter: Database adapter instance
        """
        self.adapter = adapter

    def _extract_query_columns(self, sql_query: str) -> list[str]:
        """
        Extract column names/aliases from a SELECT query.

        Args:
            sql_query: SQL SELECT query

        Returns:
            List of column names (aliases if present, otherwise column names)
        """
        try:
            parsed = sqlglot.parse_one(sql_query)
            if isinstance(parsed, exp.Select):
                return [self._get_column_name_from_expression(expr) for expr in parsed.expressions]
            return []
        except Exception as e:
            logger.warning(f"Failed to parse query columns: {e}")
            return self._extract_columns_with_regex(sql_query)

    def _get_column_name_from_expression(self, expr: Any) -> str:
        """
        Extract column name or alias from a SQL expression.

        Args:
            expr: SQL expression from sqlglot

        Returns:
            Column name or alias
        """
        # Direct alias
        if isinstance(expr, exp.Alias):
            return expr.alias

        # Direct column
        if isinstance(expr, exp.Column):
            return expr.name

        # Expression with alias attribute
        if hasattr(expr, "alias") and expr.alias:
            return expr.alias

        # Nested expression (e.g., ROW_NUMBER() OVER (...))
        if hasattr(expr, "this"):
            if hasattr(expr.this, "name"):
                return expr.this.name
            # Fallback: use string representation
            return str(expr).split(".")[-1]

        # Final fallback: use string representation
        col_str = str(expr).split(".")[-1]
        return col_str.split(" AS ")[-1].strip()

    def _extract_columns_with_regex(self, sql_query: str) -> list[str]:
        """
        Fallback method to extract columns using regex when sqlglot parsing fails.

        Args:
            sql_query: SQL SELECT query

        Returns:
            List of column names (aliases if present, otherwise column names)
        """
        match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_query, re.IGNORECASE | re.DOTALL)
        if not match:
            return []

        cols_str = match.group(1).strip()
        return [self._parse_column_string(col.strip()) for col in cols_str.split(",")]

    def _parse_column_string(self, col: str) -> str:
        """
        Parse a single column string to extract name or alias.

        Args:
            col: Column string from SQL (e.g., "table.col AS alias" or "col")

        Returns:
            Column name or alias
        """
        if " AS " in col.upper():
            alias = col.upper().split(" AS ")[1].strip()
            return alias
        else:
            # Use column name (last part if qualified)
            return col.split(".")[-1].strip()

    def _query_includes_auto_incremental_column(
        self, sql_query: str, auto_incremental_col: str
    ) -> bool:
        """
        Check if the query already includes the auto_incremental column.

        Args:
            sql_query: SQL query to check
            auto_incremental_col: Name of the auto_incremental column

        Returns:
            True if query includes the column, False otherwise
        """
        query_columns = self._extract_query_columns(sql_query)
        return auto_incremental_col in query_columns

    def _modify_explicit_id_expression(
        self,
        sql_query: str,
        auto_incremental_col: str,
        table_name: str,
        table_exists: bool = True,
    ) -> str:
        """
        Modify a query that already includes the auto_incremental column.

        For incremental runs, wraps the existing expression with MAX(id) + (...).
        Works with any expression method (ROW_NUMBER(), sequence, etc.).

        Args:
            sql_query: SQL query that already includes the auto_incremental column
            auto_incremental_col: Name of the auto_incremental column
            table_name: Target table name
            table_exists: Whether the target table exists

        Returns:
            Modified SQL query with MAX(id) added to the existing expression
        """
        # Build MAX(id) subquery
        max_id_expr = self._build_max_id_expression(table_name, auto_incremental_col, table_exists)

        # Try using sqlglot to find and replace the expression
        try:
            parsed = sqlglot.parse_one(sql_query)
            if isinstance(parsed, exp.Select):
                for expr in parsed.expressions:
                    # Check if this expression has the auto_incremental column as alias
                    if isinstance(expr, exp.Alias) and expr.alias == auto_incremental_col:
                        # Found the expression! Wrap it with MAX(id) +
                        original_expr = expr.this
                        # Create new expression: (MAX(id) + original_expr) AS column_name
                        new_expr = exp.Alias(
                            this=exp.Add(
                                this=sqlglot.parse_one(max_id_expr),
                                expression=original_expr,
                            ),
                            alias=auto_incremental_col,
                        )
                        # Replace in the SELECT
                        parsed.set(
                            "expressions",
                            [new_expr if e == expr else e for e in parsed.expressions],
                        )
                        # Preserve LIMIT clause if present
                        modified_query = parsed.sql()
                        logger.debug(
                            f"Modified explicit ID expression: added MAX({auto_incremental_col}) "
                            f"to existing expression for {auto_incremental_col}"
                        )
                        return modified_query
        except Exception as e:
            logger.debug(f"Could not use sqlglot to modify expression: {e}, falling back to regex")

        # Fallback to regex: find the expression that produces the auto_incremental column
        # Pattern: anything AS column_name (case-insensitive)
        # We need to match the entire expression before "AS column_name"
        # This is tricky because expressions can be complex, so we'll use a more flexible approach

        # Match: (expression) AS column_name or expression AS column_name
        # We'll look for the pattern: ... AS column_name (case-insensitive)
        # and capture everything before it (up to the previous comma or SELECT)

        # More robust: find the SELECT list and replace the specific column expression
        # Pattern: match from SELECT to FROM, find the expression for our column
        select_pattern = r"(SELECT\s+)(.*?)(\s+FROM)"

        def replace_column_expression(match):
            select_keyword = match.group(1)
            column_list = match.group(2)
            from_keyword = match.group(3)

            # Split columns by comma, but be careful with nested parentheses
            columns = []
            current_col = ""
            paren_depth = 0

            for char in column_list:
                if char == "(":
                    paren_depth += 1
                    current_col += char
                elif char == ")":
                    paren_depth -= 1
                    current_col += char
                elif char == "," and paren_depth == 0:
                    columns.append(current_col.strip())
                    current_col = ""
                else:
                    current_col += char

            if current_col.strip():
                columns.append(current_col.strip())

            # Find and replace the column that matches our auto_incremental column
            modified_columns = []
            for col in columns:
                # Check if this column has our alias
                # Pattern: ... AS column_name (case-insensitive)
                col_pattern = rf"(.+?)\s+AS\s+{re.escape(auto_incremental_col)}\s*$"
                col_match = re.match(col_pattern, col, re.IGNORECASE)
                if col_match:
                    # Found it! Wrap the expression with MAX(id) +
                    original_expr = col_match.group(1).strip()
                    # Remove outer parentheses if present (they'll be added back)
                    if original_expr.startswith("(") and original_expr.endswith(")"):
                        original_expr = original_expr[1:-1]
                    modified_col = f"({max_id_expr} + {original_expr}) AS {auto_incremental_col}"
                    modified_columns.append(modified_col)
                    logger.debug(
                        f"Modified explicit ID expression: added MAX({auto_incremental_col}) "
                        f"to existing expression for {auto_incremental_col}"
                    )
                else:
                    modified_columns.append(col)

            return f"{select_keyword}{', '.join(modified_columns)}{from_keyword}"

        modified_query = re.sub(
            select_pattern,
            replace_column_expression,
            sql_query,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if modified_query == sql_query:
            # No replacement happened - the column might not be found or pattern didn't match
            logger.debug(
                f"Could not find expression for {auto_incremental_col} in query. "
                "Using query as-is. For incremental runs with explicit mode, ensure the query "
                f"includes an expression that produces {auto_incremental_col}."
            )
            return sql_query

        return modified_query

    def _map_query_columns_to_schema(
        self, query_columns: list[str], schema_columns: list[str], auto_incremental_col: str
    ) -> dict[str, str]:
        """
        Map query columns to schema columns.

        Args:
            query_columns: Columns returned by the query
            schema_columns: Columns defined in schema
            auto_incremental_col: Name of auto_incremental column (to exclude from mapping)

        Returns:
            Dictionary mapping query column names to schema column names
        """
        # Remove auto_incremental column from schema columns for mapping
        schema_cols = [col for col in schema_columns if col != auto_incremental_col]

        # If query has auto_incremental column, remove it from query columns for mapping
        query_cols = [col for col in query_columns if col != auto_incremental_col]

        # If no query columns, return empty mapping
        if not query_cols:
            return {}

        # If query has fewer columns than schema (excluding auto_incremental), try positional mapping
        if len(query_cols) < len(schema_cols) and len(query_cols) == 1 and len(schema_cols) == 1:
            return {query_cols[0]: schema_cols[0]}

        # Try exact name matching
        mapping = {}
        for query_col in query_cols:
            if query_col in schema_cols:
                mapping[query_col] = query_col
                schema_cols.remove(query_col)

        # If all mapped, return
        if len(mapping) == len(query_cols):
            return mapping

        # If we have remaining columns, try positional mapping
        remaining_query = [q for q in query_cols if q not in mapping]
        if len(remaining_query) == len(schema_cols):
            for q_col, s_col in zip(remaining_query, schema_cols, strict=True):
                mapping[q_col] = s_col
            return mapping

        # Cannot determine mapping
        raise ValueError(
            f"Cannot map query columns {query_cols} to schema columns {schema_cols}. "
            f"Query must return columns that match schema (excluding auto_incremental column)."
        )

    def is_already_wrapped(self, sql_query: str) -> bool:
        """
        Check if a SQL query is already wrapped with auto_incremental logic.

        Args:
            sql_query: SQL query to check

        Returns:
            True if query appears to be already wrapped, False otherwise
        """
        # Check for telltale signs of wrapped query:
        # - Contains "max_id AS" CTE
        # - Contains "ROW_NUMBER() OVER" with max_id
        return "max_id AS" in sql_query and "ROW_NUMBER() OVER" in sql_query

    def _get_qualified_table_name(self, table_name: str) -> str:
        """
        Get qualified table name using adapter's qualification method.

        Args:
            table_name: Unqualified table name

        Returns:
            Qualified table name
        """
        try:
            if hasattr(self.adapter, "utils") and hasattr(
                self.adapter.utils, "qualify_object_name"
            ):
                return self.adapter.utils.qualify_object_name(table_name)
            else:
                return table_name
        except Exception:
            return table_name

    def _find_auto_incremental_column(self, metadata: dict[str, Any] | None) -> str | None:
        """
        Find the auto_incremental column from metadata.

        Args:
            metadata: Model metadata containing schema

        Returns:
            Name of the auto_incremental column, or None if not found
        """
        if not metadata:
            return None

        schema = metadata.get("schema", [])
        if not schema:
            return None

        for col in schema:
            if col.get("auto_incremental"):
                return col["name"]

        return None

    def _build_max_id_expression(
        self, table_name: str, auto_incremental_col: str, table_exists: bool
    ) -> str:
        """
        Build MAX(id) expression for auto_incremental ID calculation.

        Args:
            table_name: Target table name
            auto_incremental_col: Name of the auto_incremental column
            table_exists: Whether the target table exists

        Returns:
            SQL expression for MAX(id) (e.g., "(SELECT COALESCE(MAX(id), 0) FROM table)" or "0")
        """
        if not table_exists:
            return "0"

        qualified_table = self._get_qualified_table_name(table_name)
        return f"(SELECT COALESCE(MAX({auto_incremental_col}), 0) FROM {qualified_table})"

    def _build_max_id_cte(
        self, table_name: str, auto_incremental_col: str, table_exists: bool
    ) -> str:
        """
        Build max_id CTE for auto_incremental ID calculation.

        Args:
            table_name: Target table name
            auto_incremental_col: Name of the auto_incremental column
            table_exists: Whether the target table exists

        Returns:
            SQL CTE string (e.g., ",\\nmax_id AS (\\n    SELECT COALESCE(MAX(id), 0) AS max_id\\n    FROM table\\n)" or ",\\nmax_id AS (\\n    SELECT 0 AS max_id\\n)")
        """
        if not table_exists:
            return ",\nmax_id AS (\n    SELECT 0 AS max_id\n)"

        qualified_table = self._get_qualified_table_name(table_name)
        return (
            f",\nmax_id AS (\n    SELECT COALESCE(MAX({auto_incremental_col}), 0) AS max_id\n    "
            f"FROM {qualified_table}\n)"
        )

    def should_wrap(self, metadata: dict[str, Any] | None) -> bool:
        """
        Check if query should be wrapped based on metadata.

        Args:
            metadata: Model metadata dictionary

        Returns:
            True if wrapping is needed, False otherwise
        """
        auto_incremental_col = self._find_auto_incremental_column(metadata)
        if not auto_incremental_col:
            return False

        # Check for multiple auto_incremental columns (should not happen, but validate)
        schema = metadata.get("schema", []) if metadata else []
        auto_incremental_cols = [col for col in schema if col.get("auto_incremental", False)]

        if len(auto_incremental_cols) > 1:
            raise ValueError(
                "Multiple auto_incremental columns are not supported. "
                f"Found: {[col['name'] for col in auto_incremental_cols]}"
            )

        return True

    def wrap_query_for_merge(
        self,
        sql_query: str,
        table_name: str,
        metadata: dict[str, Any],
        unique_key: list[str],
        time_filter: str | None = None,
        table_exists: bool = True,
    ) -> str:
        """
        Wrap a SQL query with auto_incremental ID calculation for merge strategy.

        Supports two modes:
        1. Explicit: Query already includes auto_incremental column -> modify ROW_NUMBER() to add MAX(id)
        2. Implicit: Query doesn't include auto_incremental column -> full wrapping with CTEs

        Args:
            sql_query: User query (may or may not include auto_incremental column)
            table_name: Target table name (e.g., dim_dimension)
            metadata: Model metadata containing schema
            unique_key: Columns to match on for excluding existing records
            time_filter: Optional pre-computed time filter condition
            table_exists: Whether the target table exists

        Returns:
            Wrapped SQL query with ID calculation logic
        """
        # Find auto_incremental column
        auto_incremental_col = self._find_auto_incremental_column(metadata)
        if not auto_incremental_col:
            return sql_query

        # Validate unique_key for merge strategy
        if not unique_key:
            raise ValueError("unique_key is required for merge strategy with auto_incremental")

        # Check if query already includes the auto_incremental column (explicit mode)
        if self._query_includes_auto_incremental_column(sql_query, auto_incremental_col):
            # Explicit mode: query already includes ID column
            # For incremental runs with merge strategy:
            # 1. Exclude existing records first (based on unique_key)
            # 2. Then recalculate IDs only for new records using MAX(id) + ROW_NUMBER()
            # This ensures IDs are calculated correctly (not on all source rows)
            if table_exists:
                # Wrap to exclude existing records and recalculate IDs for new ones only
                return self._wrap_for_exclusion(
                    sql_query,
                    table_name,
                    unique_key,
                    auto_incremental_col,
                    time_filter,
                    table_exists,
                )
            else:
                # First run: use query as-is (no exclusion needed, no existing records)
                return sql_query

        # Implicit mode: query doesn't include ID column, use full wrapping
        return self._wrap_query_implicit(
            sql_query, table_name, metadata, unique_key, time_filter, table_exists, "merge"
        )

    def _wrap_for_exclusion(
        self,
        sql_query: str,
        table_name: str,
        unique_key: list[str],
        auto_incremental_col: str,
        time_filter: str | None = None,
        table_exists: bool = True,
    ) -> str:
        """
        Wrap a query to exclude existing records and recalculate IDs for new records only.

        Used when query already includes auto_incremental column (explicit mode).
        The key insight: we need to exclude existing records FIRST, then calculate IDs
        only for the new records, otherwise ROW_NUMBER() includes all source rows.

        Args:
            sql_query: Query that already includes auto_incremental column
            table_name: Target table name
            unique_key: Columns to match on for exclusion
            auto_incremental_col: Name of the auto_incremental column
            time_filter: Optional time filter
            table_exists: Whether the target table exists

        Returns:
            Wrapped query that excludes existing records and recalculates IDs for new ones only
        """
        qualified_table = self._get_qualified_table_name(table_name)

        # Extract the original query WITHOUT the auto_incremental column
        # We need to remove the ID column from the source query, then add it back
        # after exclusion, recalculated only for new records

        # Get all columns from the query
        query_columns = self._extract_query_columns(sql_query)

        # Separate the auto_incremental column from other columns
        data_columns = [col for col in query_columns if col != auto_incremental_col]

        # Build source_data CTE - we need to extract the query WITHOUT the ID column
        # This is tricky - we need to parse the SELECT and remove the ID column expression
        # For now, let's use a simpler approach: wrap the original query and then
        # rebuild the SELECT with the ID recalculated

        # Actually, better approach:
        # 1. Wrap original query (with ID) in source_data CTE
        # 2. Exclude existing records
        # 3. Recalculate ID for remaining new records using MAX(id) + ROW_NUMBER()

        # Build source_data CTE with original query (includes ID, but we'll recalculate it)
        source_cte = f"WITH source_data AS (\n    {sql_query}"
        if time_filter:
            source_cte += f"\n    AND {time_filter}"
        source_cte += "\n)"

        # Build existing_data CTE
        existing_cte = (
            f",\nexisting_data AS (\n    SELECT {', '.join(unique_key)} FROM {qualified_table}\n)"
        )

        # Build max_id CTE
        max_id_cte = self._build_max_id_cte(table_name, auto_incremental_col, table_exists)

        # Build final SELECT
        # Recalculate ID for new records only: MAX(id) + ROW_NUMBER() OVER (ORDER BY unique_key)
        # Use unique_key for ordering to ensure deterministic IDs
        select_cols = [
            f"m.max_id + ROW_NUMBER() OVER (ORDER BY {', '.join([f's.{key}' for key in unique_key])}) AS {auto_incremental_col}"
        ]

        # Add data columns from source (excluding the original ID column)
        for col in data_columns:
            select_cols.append(f"s.{col} AS {col}")

        select_clause = "SELECT DISTINCT\n    " + ",\n    ".join(select_cols)

        # Build FROM with LEFT JOIN to exclude existing
        from_clause = "\nFROM source_data s\nCROSS JOIN max_id m"
        join_conditions = " AND ".join([f"s.{key} = e.{key}" for key in unique_key])
        from_clause += f"\nLEFT JOIN existing_data e ON {join_conditions}"

        # WHERE clause to only get new records
        where_clause = "\nWHERE " + " AND ".join([f"e.{key} IS NULL" for key in unique_key])

        return f"{source_cte}{existing_cte}{max_id_cte}\n{select_clause}{from_clause}{where_clause}"

    def _wrap_query_implicit(
        self,
        sql_query: str,
        table_name: str,
        metadata: dict[str, Any],
        unique_key: list[str] | None,
        time_filter: str | None,
        table_exists: bool,
        strategy: str,
    ) -> str:
        """
        Wrap query using implicit mode (full wrapping with CTEs).

        This is the original wrapping logic for when the query doesn't include the auto_incremental column.

        Args:
            sql_query: Simple user query without auto_incremental column
            table_name: Target table name
            metadata: Model metadata
            unique_key: Columns for exclusion (None for append)
            time_filter: Optional time filter
            table_exists: Whether table exists
            strategy: Strategy name (merge, append, delete_insert)

        Returns:
            Fully wrapped query
        """
        # Find auto_incremental column
        auto_incremental_col = self._find_auto_incremental_column(metadata)
        if not auto_incremental_col:
            return sql_query

        # Get all column names from schema (excluding auto_incremental)
        schema = metadata.get("schema", [])
        all_columns = [col["name"] for col in schema]
        data_columns = [col for col in all_columns if col != auto_incremental_col]

        # Extract columns from user query and map to schema columns
        query_columns = self._extract_query_columns(sql_query)
        if not query_columns:
            # Fallback: assume query returns columns matching schema
            column_mapping = {col: col for col in data_columns}
        else:
            # Map query columns to schema columns
            column_mapping = self._map_query_columns_to_schema(
                query_columns, all_columns, auto_incremental_col
            )

        # Qualify table name if adapter supports it
        try:
            if hasattr(self.adapter, "utils") and hasattr(
                self.adapter.utils, "qualify_object_name"
            ):
                qualified_table = self.adapter.utils.qualify_object_name(table_name)
            else:
                qualified_table = table_name
        except Exception:
            qualified_table = table_name

        # Build source_data CTE with optional time filter
        source_cte = f"WITH source_data AS (\n    {sql_query}"
        if time_filter:
            # Add time filter to source query
            source_cte += f"\n    AND {time_filter}"
        source_cte += "\n)"

        # Build existing_data CTE (for LEFT JOIN exclusion)
        # Only needed if table exists and we have unique_key
        if table_exists and unique_key:
            existing_cte = f",\nexisting_data AS (\n    SELECT {', '.join(unique_key)} FROM {qualified_table}\n)"
        else:
            # Table doesn't exist, no need to exclude existing records
            existing_cte = ""

        # Build max_id CTE
        max_id_cte = self._build_max_id_cte(table_name, auto_incremental_col, table_exists)

        # Build final SELECT with ID calculation
        # Select columns: auto_incremental_col (calculated), then data columns
        if unique_key:
            # For merge/delete_insert: order by unique_key
            order_by_cols = unique_key
        else:
            # For append: order by mapped query columns
            mapped_query_cols = list(column_mapping.keys())
            order_by_cols = (
                mapped_query_cols if mapped_query_cols else data_columns if data_columns else ["1"]
            )

        select_cols = [
            f"m.max_id + ROW_NUMBER() OVER (ORDER BY {', '.join([f's.{col}' for col in order_by_cols])}) AS {auto_incremental_col}"
        ]

        # Add data columns from source
        for query_col, schema_col in column_mapping.items():
            select_cols.append(f"s.{query_col} AS {schema_col}")

        select_clause = "SELECT DISTINCT\n    " + ",\n    ".join(select_cols)

        # Build FROM with CROSS JOIN for max_id
        from_clause = "\nFROM source_data s\nCROSS JOIN max_id m"

        # LEFT JOIN to exclude existing records (only if unique_key provided)
        if unique_key and existing_cte:
            join_conditions = " AND ".join([f"s.{key} = e.{key}" for key in unique_key])
            from_clause += f"\nLEFT JOIN existing_data e ON {join_conditions}"

            # WHERE clause to only get new records
            where_clause = "\nWHERE " + " AND ".join([f"e.{key} IS NULL" for key in unique_key])
        else:
            # No exclusion needed (append strategy or first run)
            where_clause = ""

        wrapped_query = (
            f"{source_cte}{existing_cte}{max_id_cte}\n{select_clause}{from_clause}{where_clause}"
        )

        logger.debug(
            f"Wrapped query with auto_incremental logic for {auto_incremental_col} "
            f"({strategy} strategy, implicit mode)"
        )
        return wrapped_query

    def wrap_query_for_append(
        self,
        sql_query: str,
        table_name: str,
        metadata: dict[str, Any],
        time_filter: str | None = None,
        table_exists: bool = True,
    ) -> str:
        """
        Wrap a SQL query with auto_incremental ID calculation for append strategy.

        Supports explicit mode (query includes ID) and implicit mode (query doesn't include ID).

        Args:
            sql_query: User query (may or may not include auto_incremental column)
            table_name: Target table name
            metadata: Model metadata containing schema
            time_filter: Optional pre-computed time filter condition
            table_exists: Whether the target table exists

        Returns:
            Wrapped SQL query with ID calculation logic
        """
        # Find auto_incremental column
        auto_incremental_col = self._find_auto_incremental_column(metadata)
        if not auto_incremental_col:
            return sql_query

        # Check if query already includes the auto_incremental column (explicit mode)
        if self._query_includes_auto_incremental_column(sql_query, auto_incremental_col):
            # Explicit mode: query already includes ID column
            # For incremental runs, modify ROW_NUMBER() to add MAX(id)
            if table_exists:
                return self._modify_explicit_id_expression(
                    sql_query, auto_incremental_col, table_name, table_exists
                )
            else:
                # First run: use query as-is
                return sql_query

        # Implicit mode: query doesn't include ID column, use full wrapping
        return self._wrap_query_implicit(
            sql_query, table_name, metadata, None, time_filter, table_exists, "append"
        )

    def wrap_query_for_delete_insert(
        self,
        sql_query: str,
        table_name: str,
        metadata: dict[str, Any],
        unique_key: list[str],
        time_filter: str | None = None,
        table_exists: bool = True,
    ) -> str:
        """
        Wrap a SQL query with auto_incremental ID calculation for delete+insert strategy.

        Supports explicit mode (query includes ID) and implicit mode (query doesn't include ID).
        For delete_insert with unique_key, preserves existing IDs to maintain ID stability.

        Args:
            sql_query: User query (may or may not include auto_incremental column)
            table_name: Target table name
            metadata: Model metadata containing schema
            unique_key: Columns to match on (for ID preservation)
            time_filter: Optional pre-computed time filter condition
            table_exists: Whether the target table exists

        Returns:
            Wrapped SQL query with ID calculation logic
        """
        # Find auto_incremental column
        auto_incremental_col = self._find_auto_incremental_column(metadata)
        if not auto_incremental_col:
            return sql_query

        # Check if query already includes the auto_incremental column (explicit mode)
        if self._query_includes_auto_incremental_column(sql_query, auto_incremental_col):
            # Explicit mode: query already includes ID column
            # For delete_insert with unique_key, we need to preserve existing IDs
            # Use similar approach to merge: LEFT JOIN to existing records to preserve IDs
            if table_exists and unique_key:
                # Wrap query to preserve existing IDs for records that match unique_key
                # This ensures ID stability across delete+insert cycles
                return self._wrap_for_exclusion(
                    sql_query,
                    table_name,
                    unique_key,
                    auto_incremental_col,
                    time_filter,
                    table_exists,
                )
            elif table_exists:
                # No unique_key, just add MAX(id) to expression
                return self._modify_explicit_id_expression(
                    sql_query, auto_incremental_col, table_name, table_exists
                )
            else:
                # First run: use query as-is
                return sql_query

        # Implicit mode: query doesn't include ID column, use full wrapping
        return self._wrap_query_implicit(
            sql_query, table_name, metadata, unique_key, time_filter, table_exists, "delete_insert"
        )
