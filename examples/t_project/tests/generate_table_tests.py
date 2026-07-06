"""
Test using create_test() function pattern.

This demonstrates dynamic test creation for multiple tables.
"""

from t4t.testing import create_test

# Dynamically create tests for common validations
TABLES_TO_TEST = ["my_first_table"]

for table in TABLES_TO_TEST:
    # Test: Check table is not empty
    create_test(
        name=f"check_{table}_not_empty",
        sql=f"""
        SELECT 1 as violation
        FROM my_schema.{table}
        GROUP BY 1
        HAVING COUNT(*) = 0
        """,
        severity="error",
        description=f"Check that {table} is not empty",
    )

    # Test: Check id column is positive
    create_test(
        name=f"check_{table}_id_positive",
        sql=f"""
        SELECT id
        FROM my_schema.{table}
        WHERE id <= 0
        """,
        severity="error",
        description=f"Check that {table}.id contains only positive values",
    )
