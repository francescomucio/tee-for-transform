"""
Test using SqlTestMetadata pattern (metadata-only Python + companion SQL file).

This test checks that the 'name' column has a reasonable length.
"""

from t4t.testing import SqlTestMetadata

metadata = {
    "name": "check_name_length",
    "severity": "error",
    "description": "Check that name column values are not too long",
    "tags": ["data-quality", "column-validation"],
}

# Automatically creates test from companion check_name_length.sql file
test = SqlTestMetadata(**metadata)
