"""
Test fixtures for metadata propagation tests.

This module contains test data and helper functions for metadata testing.
Note: TestMetadataModels is not a test class - it's a collection of helper functions.
"""

from tee.typing import ModelMetadata

# Metadata fixtures for testing
USERS_METADATA: ModelMetadata = {
    "schema": [
        {"name": "id", "datatype": "integer", "description": "Unique identifier for the user"},
        {
            "name": "username",
            "datatype": "string",
            "description": "User's login username, must be unique",
        },
        {
            "name": "email",
            "datatype": "string",
            "description": "User's email address for notifications",
        },
        {
            "name": "created_at",
            "datatype": "timestamp",
            "description": "Timestamp when the user account was created",
        },
        {
            "name": "is_active",
            "datatype": "boolean",
            "description": "Whether the user account is currently active",
        },
    ]
}

PRODUCTS_METADATA: ModelMetadata = {
    "schema": [
        {"name": "product_id", "datatype": "integer", "description": "Primary key for the product"},
        {
            "name": "product_name",
            "datatype": "string",
            "description": "Display name of the product",
        },
        {
            "name": "price",
            "datatype": "number",
            "description": "Product price in USD, stored as decimal",
        },
        {
            "name": "category",
            "datatype": "string",
            "description": "Product category for grouping and filtering",
        },
        {
            "name": "in_stock",
            "datatype": "boolean",
            "description": "Whether the product is currently available for purchase",
        },
    ]
}

ORDERS_METADATA: ModelMetadata = {
    "schema": [
        {"name": "order_id", "datatype": "integer", "description": "Unique order identifier"},
        {
            "name": "user_id",
            "datatype": "integer",
            "description": "Foreign key reference to users table",
        },
        {
            "name": "total_amount",
            "datatype": "number",
            "description": "Total order value including tax and shipping",
        },
        {
            "name": "order_date",
            "datatype": "timestamp",
            "description": "Date and time when the order was placed",
        },
        {
            "name": "status",
            "datatype": "string",
            "description": "Current order status: pending, shipped, delivered, cancelled",
        },
    ]
}

PRIORITY_TEST_METADATA: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "integer",
            "description": "DECORATOR: This description should take priority",
        },
        {
            "name": "name",
            "datatype": "string",
            "description": "DECORATOR: This description should take priority over file metadata",
        },
    ]
}

MALFORMED_METADATA: ModelMetadata = {
    "schema": [
        {"name": "id", "datatype": "integer", "description": "Valid description"},
        {
            # Missing 'name' field - should cause error
            "datatype": "string",
            "description": "This should cause an error",
        },
    ]
}

LONG_DESCRIPTION_METADATA: ModelMetadata = {
    "schema": [
        {
            "name": "id",
            "datatype": "integer",
            "description": "A" * 5000,  # This should exceed the 4000 character limit
        }
    ]
}

INVALID_SCHEMA_TYPE_METADATA: ModelMetadata = {
    "schema": "not_a_list"  # Should be a list, not a string
}


# Helper functions for creating test models (not actual test classes)
class MetadataModelHelpers:
    """Helper functions for creating test models with metadata."""

    @staticmethod
    def create_users_with_descriptions():
        """Create a users table with detailed column descriptions."""
        return "SELECT * FROM my_first_table"

    @staticmethod
    def create_products_with_descriptions():
        """Create a products table with column descriptions."""
        return "SELECT * FROM my_first_table"

    @staticmethod
    def create_orders_with_descriptions():
        """Create an orders table with column descriptions."""
        return "SELECT * FROM my_first_table"

    @staticmethod
    def create_priority_test_table():
        """Create a table to test metadata priority."""
        return "SELECT * FROM my_first_table"

    @staticmethod
    def create_malformed_metadata_table():
        """Create a table with malformed metadata."""
        return "SELECT * FROM my_first_table"

    @staticmethod
    def create_long_description_table():
        """Create a table with description that's too long."""
        return "SELECT * FROM my_first_table"

    @staticmethod
    def create_invalid_schema_type_table():
        """Create a table with invalid schema type."""
        return "SELECT * FROM my_first_table"
