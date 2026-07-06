from t4t.parser.processing import create_model, model


@model(table_name="users_summary", description="Summary of user data")
def create_users_summary():
    """Create a summary table of users with aggregated data."""
    return "SELECT * FROM my_first_table"


@model(table_name="recent_users")
def get_recent_users():
    """Get users created recently."""
    return "SELECT * FROM my_schema.my_first_table"


@model(table_name="complex_join")
def create_complex_join():
    """Create a complex join between multiple tables."""
    return "SELECT * FROM my_schema.my_first_table"


# OPTION 2: Dynamic model creation using create_model()
# Just update this list to add/remove models - zero code repetition!
STAGING_TABLES = ["my_first_table", "my_second_table", "my_third_table"]
STAGING_SCHEMA = "staging"

# Dynamically create models for each staging table
for table_name in STAGING_TABLES:
    create_model(
        table_name=table_name + "_from_loop",
        sql=f"SELECT * FROM {table_name}",
        description=f"Select from  my_schema.{table_name}",
    )
