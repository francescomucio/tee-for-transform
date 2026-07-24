@model(table_name="leaf_changed", tags=["nightly"])  # noqa: F821
def leaf_changed():
    return "SELECT 1 AS id"
