"""
Standard test implementations for common data quality checks.
"""

from typing import Any

from .base import StandardTest, TestRegistry, TestSeverity


class NotNullTest(StandardTest):
    """Test that verifies a column contains no NULL values."""

    def __init__(self):
        super().__init__("not_null", severity=TestSeverity.ERROR)

    def validate_params(
        self,
        params: dict[str, Any] | None = None,
        column_name: str | None = None,  # noqa: ARG002
    ) -> None:
        """Validate not_null test parameters (none required currently)."""
        # Future: could support `allow_nulls` parameter
        self._validate_unknown_params(params, set())

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        _params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate SQL query to find NULL values using adapter.

        Returns rows where column is NULL (test fails if any rows returned).
        """
        if not column_name:
            raise ValueError("not_null test requires a column name")

        # Delegate SQL generation to adapter for database-specific syntax
        return adapter.generate_not_null_test_query(table_name, column_name)


class UniqueTest(StandardTest):
    """
    Test that verifies values are unique.

    Can be used in two ways:
    1. Column-level: Applied to a column, checks if that single column has duplicates
    2. Table-level: Applied at model level with params, checks composite uniqueness
        on multiple columns specified in params={"columns": ["col1", "col2"]}
    """

    def __init__(self):
        super().__init__("unique", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        """
        Validate unique test parameters.

        Args:
            params: Test parameters
            column_name: Column name if this is a column-level test

        Raises:
            ValueError: If parameters are invalid
        """
        if params and "columns" in params:
            # Table-level test with composite columns
            if column_name:
                raise ValueError(
                    "unique test cannot use 'columns' param when applied to a column. "
                    "Use 'columns' param only for table-level tests."
                )
            columns = params["columns"]
            if not isinstance(columns, list) or len(columns) == 0:
                raise ValueError("columns parameter must be a non-empty list")
        elif params:
            # Unknown params
            unknown_params = set(params.keys())
            raise ValueError(f"Unknown parameters for unique test: {unknown_params}")
        # If no params and no column_name at table level, that's valid (checks all columns)

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate SQL query to find duplicate values using adapter.

        Args:
            adapter: Database adapter instance
            table_name: Fully qualified table name
            column_name: Column name (for column-level tests)
            params: Parameters dict. For table-level tests, should contain
                   {"columns": ["col1", "col2", ...]}

        Returns:
            SQL query string

        Raises:
            ValueError: If test configuration is invalid
        """
        # Validate params first
        self.validate_params(params, column_name)

        # Determine columns to check
        if column_name:
            # Case 1: Column-level test
            columns = [column_name]
        elif params and "columns" in params:
            # Case 2: Table-level test with composite columns
            columns = params["columns"]
        else:
            # Case 3: Table-level test without columns specified - check all columns (entire row uniqueness)
            # Try to get columns from adapter if available
            columns = None
            try:
                if hasattr(adapter, "get_table_columns") and adapter.connection:
                    columns = adapter.get_table_columns(table_name)
            except Exception:
                # If getting columns fails, adapter will handle None
                pass

        # Delegate SQL generation to adapter for database-specific syntax
        return adapter.generate_unique_test_query(table_name, columns)


# NoDuplicatesTest has been removed - use UniqueTest at table level without columns
# to check entire row uniqueness (equivalent to no_duplicates)


class RowCountGreaterThanZeroTest(StandardTest):
    """
    Test that verifies a table has at least one row.

    This is a model-level test that checks if the table contains any data.
    """

    def __init__(self):
        super().__init__("row_count_gt_0", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        """
        Validate row_count_gt_0 test parameters.

        Args:
            params: Test parameters (none required currently)
            column_name: Should be None for model-level tests

        Raises:
            ValueError: If parameters are invalid
        """
        self._validate_model_level_only(column_name)
        self._validate_unknown_params(params, set())

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        _params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate SQL query to count rows using adapter.

        Args:
            adapter: Database adapter instance
            table_name: Fully qualified table name
            column_name: Should be None (this is a model-level test)
            params: Optional parameters (not used currently)

        Returns:
            SQL query string that returns row count
        """
        self._validate_model_level_only(column_name)

        # Delegate SQL generation to adapter for database-specific syntax
        return adapter.generate_row_count_gt_0_test_query(table_name)

    def check_passed(self, count: int) -> bool:
        """
        Check if test passed - row_count_gt_0 has inverted logic.

        Passes if count > 0 (table has data), fails if count == 0 (table is empty).
        """
        return count > 0

    def format_message(self, passed: bool, count: int) -> str:
        """
        Format message for row_count_gt_0 test.
        """
        if passed:
            return f"Test passed: {self.name} (table has {count} row(s))"
        else:
            return f"Test failed: {self.name} (table is empty, 0 rows)"


class AcceptedValuesTest(StandardTest):
    """
    Test that verifies column values are in an accepted list.

    This is a column-level test that checks if all values in a column
    are within a specified list of allowed values.
    """

    def __init__(self):
        super().__init__("accepted_values", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        """
        Validate accepted_values test parameters.

        Args:
            params: Test parameters - must contain "values" key with a list
            column_name: Column name (required for this test)

        Raises:
            ValueError: If parameters are invalid
        """
        if not column_name:
            raise ValueError("accepted_values test requires a column name")

        if not params or "values" not in params:
            raise ValueError(
                "accepted_values test requires 'values' parameter with a list of accepted values"
            )

        values = params["values"]
        if not isinstance(values, list):
            raise ValueError("accepted_values test 'values' parameter must be a list")

        if len(values) == 0:
            raise ValueError(
                "accepted_values test 'values' parameter must contain at least one value"
            )

        # Check for unknown parameters
        self._validate_unknown_params(params, {"values"})

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate SQL query to find values not in accepted list using adapter.

        Args:
            adapter: Database adapter instance
            table_name: Fully qualified table name
            column_name: Column name to test
            params: Parameters dict containing {"values": [...]}

        Returns:
            SQL query string
        """
        if not column_name:
            raise ValueError("accepted_values test requires a column name")

        if not params or "values" not in params:
            raise ValueError("accepted_values test requires 'values' parameter")

        values = params["values"]

        # Delegate SQL generation to adapter for database-specific syntax
        return adapter.generate_accepted_values_test_query(table_name, column_name, values)


class RelationshipsTest(StandardTest):
    """
    Test that verifies referential integrity between tables.

    This is a column-level test that checks if values in source column(s)
    exist in a target table's column(s) (foreign key relationship).

    Supports both single-column and composite key relationships.
    """

    def __init__(self):
        super().__init__("relationships", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        """
        Validate relationships test parameters.

        Args:
            params: Test parameters - must contain "to" and "field" keys
            column_name: Column name in source table (required for this test)

        Raises:
            ValueError: If parameters are invalid
        """
        if not column_name:
            raise ValueError("relationships test requires a column name")

        if not params:
            raise ValueError("relationships test requires 'to' parameter")

        if "to" not in params:
            raise ValueError("relationships test requires 'to' parameter (target table name)")

        # Support both single-column (field) and multi-column (fields) syntax
        has_field = "field" in params
        has_fields = "fields" in params

        if not has_field and not has_fields:
            raise ValueError(
                "relationships test requires 'field' or 'fields' parameter (target column name(s))"
            )

        if has_field and has_fields:
            raise ValueError("relationships test cannot use both 'field' and 'fields' parameters")

        target_table = params["to"]

        if not isinstance(target_table, str) or not target_table.strip():
            raise ValueError("relationships test 'to' parameter must be a non-empty string")

        # Handle single column or multiple columns
        if has_field:
            target_field = params["field"]
            if not isinstance(target_field, str) or not target_field.strip():
                raise ValueError("relationships test 'field' parameter must be a non-empty string")
        else:  # has_fields
            target_fields = params["fields"]
            if not isinstance(target_fields, list) or len(target_fields) == 0:
                raise ValueError("relationships test 'fields' parameter must be a non-empty list")
            for field in target_fields:
                if not isinstance(field, str) or not field.strip():
                    raise ValueError(
                        "relationships test 'fields' parameter must contain non-empty strings"
                    )

        # Check for source_fields parameter (optional, defaults to column_name)
        if "source_fields" in params:
            source_fields = params["source_fields"]
            if not isinstance(source_fields, list) or len(source_fields) == 0:
                raise ValueError(
                    "relationships test 'source_fields' parameter must be a non-empty list"
                )
            # Validate that source_fields matches target fields length
            target_fields_count = 1 if has_field else len(params["fields"])
            if len(source_fields) != target_fields_count:
                raise ValueError(
                    f"relationships test: source_fields ({len(source_fields)}) and "
                    f"target fields ({target_fields_count}) must have the same length"
                )

        # Check for unknown parameters
        self._validate_unknown_params(params, {"to", "field", "fields", "source_fields"})

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate SQL query to find orphaned rows using adapter.

        Args:
            adapter: Database adapter instance
            table_name: Fully qualified source table name
            column_name: Column name in source table
            params: Parameters dict containing {"to": "target_table", "field": "target_column"}

        Returns:
            SQL query string
        """
        if not column_name:
            raise ValueError("relationships test requires a column name")

        if not params or "to" not in params:
            raise ValueError("relationships test requires 'to' parameter")

        if "field" not in params and "fields" not in params:
            raise ValueError("relationships test requires 'field' or 'fields' parameter")

        target_table = params["to"]

        # Determine source and target columns
        if "source_fields" in params:
            source_columns = params["source_fields"]
        else:
            # Default: use column_name for single column, or wrap in list
            source_columns = [column_name]

        # Get target columns
        if "field" in params:
            target_columns = [params["field"]]
        else:  # "fields" in params
            target_columns = params["fields"]

        # Validate lengths match
        if len(source_columns) != len(target_columns):
            raise ValueError(
                f"relationships test: source columns ({len(source_columns)}) and "
                f"target columns ({len(target_columns)}) must have the same length"
            )

        # Delegate SQL generation to adapter for database-specific syntax
        return adapter.generate_relationships_test_query(
            table_name, source_columns, target_table, target_columns
        )


class PrimaryKeyTest(StandardTest):
    """
    Test that verifies a column is a valid primary key.

    The test is a combined check:
    - NOT NULL
    - UNIQUE
    """

    def __init__(self):
        super().__init__("primary_key", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        self._validate_unknown_params(params, set())

        # This is a column-level test: column_name is required.
        if not column_name:
            raise ValueError("primary_key test requires a column name")

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        _params: dict[str, Any] | None = None,
    ) -> str:
        if not column_name:
            raise ValueError("primary_key test requires a column name")
        return adapter.generate_primary_key_test_query(table_name, column_name)


class HierarchyNoSplitTest(StandardTest):
    """
    Model-level test ensuring each child PK maps to exactly one parent value.

    This prevents split/diamond-shaped hierarchies.
    """

    def __init__(self):
        super().__init__("hierarchy_no_split", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        self._validate_model_level_only(column_name)

        if not params:
            raise ValueError("hierarchy_no_split test requires params")
        if "child_col" not in params or "parent_col" not in params:
            raise ValueError("hierarchy_no_split requires 'child_col' and 'parent_col' params")

        if not isinstance(params["child_col"], str) or not params["child_col"].strip():
            raise ValueError("hierarchy_no_split: 'child_col' must be a non-empty string")
        if not isinstance(params["parent_col"], str) or not params["parent_col"].strip():
            raise ValueError("hierarchy_no_split: 'parent_col' must be a non-empty string")

        self._validate_unknown_params(params, {"child_col", "parent_col"})

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        self.validate_params(params=params, column_name=column_name)
        return adapter.generate_hierarchy_no_split_test_query(
            table_name=table_name,
            child_col=params["child_col"],
            parent_col=params["parent_col"],
        )


class LevelUniquenessTest(StandardTest):
    """
    Model-level test ensuring each PK at a hierarchy level has a single consistent attribute tuple.
    """

    def __init__(self):
        super().__init__("level_uniqueness", severity=TestSeverity.ERROR)

    def validate_params(
        self, params: dict[str, Any] | None = None, column_name: str | None = None
    ) -> None:
        self._validate_model_level_only(column_name)

        if not params:
            raise ValueError("level_uniqueness test requires params")
        if "pk_col" not in params or "attribute_cols" not in params:
            raise ValueError("level_uniqueness requires 'pk_col' and 'attribute_cols' params")

        if not isinstance(params["pk_col"], str) or not params["pk_col"].strip():
            raise ValueError("level_uniqueness: 'pk_col' must be a non-empty string")
        if not isinstance(params["attribute_cols"], list):
            raise ValueError("level_uniqueness: 'attribute_cols' must be a list")
        if any(not isinstance(c, str) or not c.strip() for c in params["attribute_cols"]):
            raise ValueError("level_uniqueness: 'attribute_cols' must contain non-empty strings")

        self._validate_unknown_params(params, {"pk_col", "attribute_cols"})

    def get_test_query(
        self,
        adapter,
        table_name: str | None = None,
        column_name: str | None = None,
        _function_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        self.validate_params(params=params, column_name=column_name)
        return adapter.generate_level_uniqueness_test_query(
            table_name=table_name,
            pk_col=params["pk_col"],
            attribute_cols=params["attribute_cols"],
        )


# Register standard tests
NOT_NULL = NotNullTest()
UNIQUE = UniqueTest()
# NO_DUPLICATES removed - use UNIQUE at table level without columns instead
ROW_COUNT_GT_0 = RowCountGreaterThanZeroTest()
ACCEPTED_VALUES = AcceptedValuesTest()
RELATIONSHIPS = RelationshipsTest()
PRIMARY_KEY = PrimaryKeyTest()
HIERARCHY_NO_SPLIT = HierarchyNoSplitTest()
LEVEL_UNIQUENESS = LevelUniquenessTest()

TestRegistry.register(NOT_NULL)
TestRegistry.register(UNIQUE)
TestRegistry.register(ROW_COUNT_GT_0)
TestRegistry.register(ACCEPTED_VALUES)
TestRegistry.register(RELATIONSHIPS)
TestRegistry.register(PRIMARY_KEY)
TestRegistry.register(HIERARCHY_NO_SPLIT)
TestRegistry.register(LEVEL_UNIQUENESS)
