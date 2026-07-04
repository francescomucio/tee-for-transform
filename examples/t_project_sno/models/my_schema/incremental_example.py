# Metadata for incremental_example.sql
from t4t.typing.metadata import ModelMetadata

# Example 1: Append-only incremental
metadata_append: ModelMetadata = {
    "description": "Incremental table using append strategy",
    "materialization": "incremental",
    "incremental": {
        "strategy": "append",
        "append": {
            "filter_column": "created_at",
            "start_value": "@start_date",  # Use variable from CLI
            "lookback": "7 days"
        }
    }
}

# Example 2: Merge incremental
metadata_merge: ModelMetadata = {
    "description": "Incremental table using merge strategy",
    "materialization": "incremental", 
    "incremental": {
        "strategy": "merge",
        "merge": {
            "unique_key": ["id"],
            "filter_column": "updated_at",
            "start_value": "auto",  # Will use max(filter_column) from target table
            "lookback": "3 hours"
        }
    }
}

# Example 3: Delete+insert incremental
metadata_delete_insert: ModelMetadata = {
    "description": "Incremental table using delete+insert strategy",
    "materialization": "incremental",
    "incremental": {
        "strategy": "delete_insert",
        "delete_insert": {
            "where_condition": "updated_at >= '@start_date'",
            "filter_column": "updated_at",
            "start_value": "@start_date",
        }
    }
}

# Choose which strategy to use by assigning to 'metadata'
# Simply change the assignment below to test different strategies:
# metadata = metadata_append  # Uncomment to use append strategy
# metadata = metadata_merge  # Uncomment to use merge strategy
metadata = metadata_delete_insert  # Currently using delete+insert strategy
