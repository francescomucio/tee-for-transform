"""
Metadata for calculate_percentage function.

This function calculates the percentage of a numerator over a denominator,
handling edge cases like division by zero.
"""

from t4t.parser.processing.function_builder import SQLFunctionMetadata
from t4t.typing import FunctionMetadata

metadata: FunctionMetadata = {
    "function_name": "calculate_percentage",
    "description": "Calculates the percentage of a numerator over a denominator. Returns NULL if denominator is zero or NULL.",
    "function_type": "scalar",
    "language": "sql",
    "parameters": [
        {"name": "numerator", "type": "DOUBLE", "description": "The numerator value"},
        {"name": "denominator", "type": "DOUBLE", "description": "The denominator value"},
    ],
    "return_type": "DOUBLE",
    "schema": "my_schema",
    "deterministic": True,
    "tags": ["math", "utility"],
    "object_tags": {"category": "calculation", "complexity": "simple"},
    "tests": [
        {
            "name": "test_calculate_percentage",
            "expected": 50.0,
            "params": {"numerator": 10.0, "denominator": 20.0},
        },
        {
            "name": "test_calculate_percentage_zero",
            "expected": None,
            "params": {"numerator": 10.0, "denominator": 0.0},
        },
    ],
}

# Automatically creates a function from metadata and companion SQL file
function = SQLFunctionMetadata(metadata)
