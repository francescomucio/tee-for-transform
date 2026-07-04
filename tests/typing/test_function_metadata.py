"""
Tests for function metadata type definitions.
"""

from t4t.typing.metadata import (
    FunctionMetadata,
    FunctionParameter,
    FunctionType,
    OTSFunction,
    OTSModule,
)


class TestFunctionType:
    """Test FunctionType literal."""

    def test_function_type_values(self):
        """Test that FunctionType has correct values."""
        assert FunctionType.__args__ == ("scalar", "aggregate", "table")


class TestFunctionParameter:
    """Test FunctionParameter TypedDict."""

    def test_function_parameter_minimal(self):
        """Test minimal function parameter."""
        param: FunctionParameter = {
            "name": "input_value",
            "type": "FLOAT",
        }
        assert param["name"] == "input_value"
        assert param["type"] == "FLOAT"

    def test_function_parameter_full(self):
        """Test function parameter with all fields."""
        param: FunctionParameter = {
            "name": "input_value",
            "type": "FLOAT",
            "description": "Input value to process",
            "default": "1.0",
            "mode": "IN",
        }
        assert param["name"] == "input_value"
        assert param["type"] == "FLOAT"
        assert param["description"] == "Input value to process"
        assert param["default"] == "1.0"
        assert param["mode"] == "IN"

    def test_function_parameter_optional_fields(self):
        """Test function parameter with optional fields."""
        param: FunctionParameter = {
            "name": "x",
            "type": "INTEGER",
            "description": "Optional description",
        }
        assert "default" not in param or param.get("default") is None
        assert "mode" not in param or param.get("mode") is None


class TestFunctionMetadata:
    """Test FunctionMetadata TypedDict."""

    def test_function_metadata_minimal(self):
        """Test minimal function metadata."""
        metadata: FunctionMetadata = {
            "function_name": "calculate_metric",
        }
        assert metadata["function_name"] == "calculate_metric"

    def test_function_metadata_full(self):
        """Test function metadata with all fields."""
        metadata: FunctionMetadata = {
            "function_name": "calculate_metric",
            "description": "Calculates a custom metric",
            "function_type": "scalar",
            "language": "sql",
            "parameters": [
                {
                    "name": "input_value",
                    "type": "FLOAT",
                    "description": "Input value",
                }
            ],
            "return_type": "FLOAT",
            "schema": "my_schema",
            "deterministic": True,
            "tests": ["test_positive_result"],
            "tags": ["analytics", "production"],
            "object_tags": {"sensitivity_tag": "public"},
        }
        assert metadata["function_name"] == "calculate_metric"
        assert metadata["description"] == "Calculates a custom metric"
        assert metadata["function_type"] == "scalar"
        assert metadata["language"] == "sql"
        assert len(metadata["parameters"]) == 1
        assert metadata["return_type"] == "FLOAT"
        assert metadata["tags"] == ["analytics", "production"]
        assert metadata["object_tags"] == {"sensitivity_tag": "public"}

    def test_function_metadata_table_function(self):
        """Test function metadata for table-valued function."""
        metadata: FunctionMetadata = {
            "function_name": "get_users",
            "function_type": "table",
            "return_table_schema": [
                {
                    "name": "id",
                    "datatype": "integer",
                },
                {
                    "name": "name",
                    "datatype": "string",
                },
            ],
        }
        assert metadata["function_type"] == "table"
        assert metadata["return_table_schema"] is not None
        assert len(metadata["return_table_schema"]) == 2


class TestFunctionMetadataParsed:
    """Test FunctionMetadata with parsed/validated fields."""

    def test_function_metadata_parsed(self):
        """Test function metadata structure with parsed fields."""
        metadata: FunctionMetadata = {
            "function_name": "calculate_metric",
            "function_type": "scalar",  # Can be provided or defaulted
            "parameters": [],
            "deterministic": False,
            "tests": [],
            "tags": [],
            "object_tags": {},
        }
        assert metadata["function_name"] == "calculate_metric"
        assert metadata["function_type"] == "scalar"
        assert isinstance(metadata["parameters"], list)
        assert isinstance(metadata["tests"], list)
        assert isinstance(metadata["tags"], list)
        assert isinstance(metadata["object_tags"], dict)


class TestOTSFunction:
    """Test OTSFunction TypedDict."""

    def test_ots_function_minimal(self):
        """Test minimal OTS function."""
        ots_function: OTSFunction = {
            "function_id": "my_schema.calculate_metric",
            "function_type": "scalar",
            "language": "sql",
            "parameters": [],
            "code": {
                "generic_sql": "CREATE FUNCTION ...",
            },
            "metadata": {},
        }
        assert ots_function["function_id"] == "my_schema.calculate_metric"
        assert ots_function["function_type"] == "scalar"
        assert ots_function["language"] == "sql"

    def test_ots_function_full(self):
        """Test OTS function with all fields."""
        ots_function: OTSFunction = {
            "function_id": "my_schema.calculate_metric",
            "description": "Calculates a custom metric",
            "function_type": "scalar",
            "language": "sql",
            "parameters": [
                {
                    "name": "input_value",
                    "type": "FLOAT",
                }
            ],
            "return_type": "FLOAT",
            "code": {
                "generic_sql": "CREATE FUNCTION ...",
                "database_specific": {
                    "postgresql": "CREATE FUNCTION ...",
                    "snowflake": "CREATE FUNCTION ...",
                },
            },
            "dependencies": {
                "functions": [],
                "tables": ["my_schema.source_table"],
            },
            "metadata": {
                "file_path": "functions/my_schema/calculate_metric/function.sql",
                "tags": ["analytics"],
                "object_tags": {"sensitivity_tag": "public"},
            },
        }
        assert ots_function["function_id"] == "my_schema.calculate_metric"
        assert ots_function["dependencies"]["tables"] == ["my_schema.source_table"]
        assert "tags" in ots_function["metadata"]


class TestOTSModule:
    """Test OTSModule with functions support."""

    def test_ots_module_without_functions(self):
        """Test OTS module without functions (backward compatibility)."""
        module: OTSModule = {
            "ots_version": "0.1.0",
            "module_name": "my_project",
            "target": {
                "database": "duckdb",
                "schema": "my_schema",
            },
            "transformations": [],
        }
        assert module["ots_version"] == "0.1.0"
        assert "functions" not in module or module.get("functions") is None

    def test_ots_module_with_functions(self):
        """Test OTS module with functions (OTS 0.2.1)."""
        module: OTSModule = {
            "ots_version": "0.2.1",
            "module_name": "my_project",
            "target": {
                "database": "duckdb",
                "schema": "my_schema",
            },
            "transformations": [],
            "functions": [
                {
                    "function_id": "my_schema.calculate_metric",
                    "function_type": "scalar",
                    "language": "sql",
                    "parameters": [],
                    "code": {
                        "generic_sql": "CREATE FUNCTION ...",
                    },
                    "metadata": {},
                }
            ],
        }
        assert module["ots_version"] == "0.2.1"  # OTS 0.2.1 is used when functions are present
        assert module["functions"] is not None
        assert len(module["functions"]) == 1
        assert module["functions"][0]["function_id"] == "my_schema.calculate_metric"
