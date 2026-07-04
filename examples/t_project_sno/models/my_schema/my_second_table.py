# Metadata for my_second_table.sql
from t4t.parser.processing.model_builder import SqlModelMetadata
from t4t.typing import ModelMetadata

metadata: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "number",
            "description": "Foreign key reference to my_first_table"
        },
        {
            "name": "name",
            "datatype": "string",
            "description": "Additional information",
            "tests": ["not_null"]
        }
    ],
    "materialization": "view",
    "tests": ["row_count_gt_0", "unique"],
    "description": "This is a description of the view"
}

# Automatically creates a model from metadata and companion SQL file
model = SqlModelMetadata(metadata)
