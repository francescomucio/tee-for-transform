"""
Metadata for calculate_percentage function (Snowflake version).

This function calculates the percentage of a numerator over a denominator,
handling edge cases like division by zero.
"""

metadata = {
    "function_name": "calculate_percentage",
    "description": "Calculates the percentage of a numerator over a denominator. Returns NULL if denominator is zero or NULL.",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "FLOAT", "description": "The numerator value"},
        {"name": "denominator", "type": "FLOAT", "description": "The denominator value"},
    ],
    "return_type": "FLOAT",
    "schema": "my_schema",
    "deterministic": True,
    "tags": ["math", "utility"],
    "object_tags": {"category": "calculation", "complexity": "simple"},
    "tests": [
        {
            "name": "test_calculate_percentage",
            "expected": 50.0,
            "params": {"numerator": 10.0, "denominator": 20.0},
        }
    ],
}
