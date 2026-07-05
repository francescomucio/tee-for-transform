# See dim_shop.py: the "Region" level name here intentionally conflicts
# with the one declared by dim_shop.
from t4t.typing.metadata import ModelMetadata

metadata: ModelMetadata = {
    "materialization": "table",
    "table_type": "dim",
    "data_model": True,
    "hierarchy": {
        "type": "Fixed-Depth Hierarchy",
        "levels": [
            {
                "level_number": 1,
                "name": "Region",
                "column": "region_name",
                "primary_key": "region_id",
            },
            {
                "level_number": 2,
                "name": "Customer",
                "column": "customer_name",
                "primary_key": "customer_id",
            },
        ],
    },
    "schema": [
        {"name": "customer_id", "datatype": "integer", "description": "Customer surrogate key."},
        {"name": "customer_name", "datatype": "string", "description": "Customer display name."},
        {"name": "region_id", "datatype": "integer", "description": "Customer region key."},
        {"name": "region_name", "datatype": "string", "description": "Customer region name."},
    ],
}
