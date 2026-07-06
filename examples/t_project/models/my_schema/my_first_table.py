# Metadata for my_first_table.sql
from t4t.parser.processing.model_builder import SqlModelMetadata
from t4t.typing.metadata import ModelMetadata

metadata: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "number",
            "description": "Unique identifier for the record",
            "tests": ["not_null", "unique"],
        },
        {
            "name": "name",
            "datatype": "string",
            "description": "Name of the record",
            "tests": ["not_null"],
        },
    ],
    "partitions": ["id"],
    "materialization": "table",
    "tests": [
        "row_count_gt_0",
        "test_my_first_table",  # Singular SQL test
        # Example: "example_custom_test" - Generic SQL test (requires table to have 5+ rows)
        # Example: {"name": "check_minimum_rows", "params": {"min_rows": 3}}
    ],
}

# Automatically creates a model from metadata and companion SQL file
model = SqlModelMetadata(metadata)
