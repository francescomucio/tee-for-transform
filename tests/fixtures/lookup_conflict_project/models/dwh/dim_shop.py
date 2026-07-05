# Two dimensions in this fixture declare a hierarchy level named "Region".
# The lookup generator must either raise (default) or auto-resolve the
# conflict by prefixing the dimension name.
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
                "name": "Shop",
                "column": "shop_name",
                "primary_key": "shop_id",
            },
        ],
    },
    "schema": [
        {"name": "shop_id", "datatype": "integer", "description": "Shop surrogate key."},
        {"name": "shop_name", "datatype": "string", "description": "Shop name."},
        {"name": "region_id", "datatype": "integer", "description": "Region key for shop."},
        {"name": "region_name", "datatype": "string", "description": "Region name for shop."},
    ],
}
