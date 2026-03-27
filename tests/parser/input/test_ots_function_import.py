"""
Tests for OTS function import functionality.
"""

from tee.parser.input import OTSConverter
from tee.typing.metadata import OTSModule


class TestOTSFunctionImport:
    """Tests for importing functions from OTS modules."""

    def test_convert_module_with_function(self):
        """Test converting an OTS module with a function (OTS 0.2.0)."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.2.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [],
            "functions": [
                {
                    "function_id": "test_schema.calculate_percentage",
                    "description": "Calculate percentage",
                    "function_type": "scalar",
                    "language": "sql",
                    "parameters": [
                        {"name": "numerator", "type": "FLOAT", "mode": "IN"},
                        {"name": "denominator", "type": "FLOAT", "mode": "IN"},
                    ],
                    "return_type": "FLOAT",
                    "code": {
                        "generic_sql": "CREATE OR REPLACE FUNCTION test_schema.calculate_percentage(numerator FLOAT, denominator FLOAT) RETURNS FLOAT AS $$ SELECT numerator / denominator * 100 $$ LANGUAGE sql;",
                        "database_specific": {},
                    },
                    "dependencies": {"tables": [], "functions": []},
                    "metadata": {
                        "file_path": "functions/test_schema/calculate_percentage.sql",
                        "tags": ["analytics", "math"],
                        "object_tags": {"classification": "public"},
                    },
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        assert len(parsed_models) == 0
        assert len(parsed_functions) == 1
        assert "test_schema.calculate_percentage" in parsed_functions

        parsed_function = parsed_functions["test_schema.calculate_percentage"]
        assert "code" in parsed_function
        assert "function_metadata" in parsed_function

        # Check function metadata
        func_metadata = parsed_function["function_metadata"]
        assert func_metadata["function_name"] == "calculate_percentage"
        assert func_metadata["schema"] == "test_schema"
        assert func_metadata["description"] == "Calculate percentage"
        assert func_metadata["function_type"] == "scalar"
        assert func_metadata["language"] == "sql"
        assert len(func_metadata["parameters"]) == 2
        assert func_metadata["return_type"] == "FLOAT"

        # Check code structure
        assert "sql" in parsed_function["code"]
        assert "original_sql" in parsed_function["code"]["sql"]

    def test_convert_module_0_1_0_no_functions(self):
        """Test that OTS 0.1.0 modules don't have functions."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.1.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [
                {
                    "transformation_id": "test_schema.table1",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 1",
                            "resolved_sql": "SELECT 1",
                            "source_tables": [],
                        }
                    },
                    "materialization": {"type": "table"},
                    "metadata": {},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        assert len(parsed_models) == 1
        assert len(parsed_functions) == 0

    def test_convert_function_with_dependencies(self):
        """Test converting a function with dependencies."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.2.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [],
            "functions": [
                {
                    "function_id": "test_schema.helper_func",
                    "function_type": "scalar",
                    "language": "sql",
                    "code": {
                        "generic_sql": "CREATE FUNCTION helper_func() AS $$ SELECT * FROM users $$",
                        "database_specific": {},
                    },
                    "dependencies": {
                        "tables": ["test_schema.users"],
                        "functions": ["test_schema.base_func"],
                    },
                    "metadata": {},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        parsed_function = parsed_functions["test_schema.helper_func"]

        # Dependencies are stored in code["sql"] (consistent with models)
        code_data = parsed_function.get("code", {})
        assert "sql" in code_data
        sql_code = code_data["sql"]
        assert "source_tables" in sql_code
        assert "source_functions" in sql_code
        assert sql_code["source_tables"] == ["test_schema.users"]
        assert sql_code["source_functions"] == ["test_schema.base_func"]

    def test_convert_function_with_tags(self):
        """Test converting a function with tags."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.2.0",
            "module_name": "test.module",
            "tags": ["module_tag1", "module_tag2"],
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [],
            "functions": [
                {
                    "function_id": "test_schema.calc",
                    "function_type": "scalar",
                    "language": "sql",
                    "code": {
                        "generic_sql": "CREATE FUNCTION calc() AS $$ SELECT 1 $$",
                        "database_specific": {},
                    },
                    "metadata": {
                        "tags": ["function_tag1"],
                        "object_tags": {"classification": "public"},
                    },
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        parsed_function = parsed_functions["test_schema.calc"]

        func_metadata = parsed_function["function_metadata"]
        # Tags should be merged (module + function) - stored in metadata dict
        tags = func_metadata["metadata"]["tags"]
        assert "module_tag1" in tags
        assert "module_tag2" in tags
        assert "function_tag1" in tags

        # Object tags should be preserved - stored in metadata dict
        assert func_metadata["metadata"]["object_tags"]["classification"] == "public"

    def test_convert_table_function(self):
        """Test converting a table function."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.2.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [],
            "functions": [
                {
                    "function_id": "test_schema.get_users",
                    "function_type": "table",
                    "language": "sql",
                    "return_table_schema": [
                        {"name": "id", "datatype": "INTEGER"},
                        {"name": "name", "datatype": "VARCHAR"},
                    ],
                    "code": {
                        "generic_sql": "CREATE FUNCTION get_users() RETURNS TABLE(id INTEGER, name VARCHAR) AS $$ SELECT * FROM users $$",
                        "database_specific": {},
                    },
                    "metadata": {},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        parsed_function = parsed_functions["test_schema.get_users"]

        func_metadata = parsed_function["function_metadata"]
        assert func_metadata["function_type"] == "table"
        # return_table_schema is stored in metadata dict
        assert "return_table_schema" in func_metadata["metadata"]
        assert len(func_metadata["metadata"]["return_table_schema"]) == 2

    def test_convert_module_with_functions_and_models(self):
        """Test converting a module with both functions and models."""
        converter = OTSConverter()

        module: OTSModule = {
            "ots_version": "0.2.0",
            "module_name": "test.module",
            "target": {
                "database": "test_db",
                "schema": "test_schema",
            },
            "transformations": [
                {
                    "transformation_id": "test_schema.table1",
                    "code": {
                        "sql": {
                            "original_sql": "SELECT 1",
                            "resolved_sql": "SELECT 1",
                            "source_tables": [],
                        }
                    },
                    "materialization": {"type": "table"},
                    "metadata": {},
                }
            ],
            "functions": [
                {
                    "function_id": "test_schema.func1",
                    "function_type": "scalar",
                    "language": "sql",
                    "code": {
                        "generic_sql": "CREATE FUNCTION func1() AS $$ SELECT 1 $$",
                        "database_specific": {},
                    },
                    "metadata": {},
                }
            ],
        }

        parsed_models, parsed_functions = converter.convert_module(module)
        assert len(parsed_models) == 1
        assert len(parsed_functions) == 1
        assert "test_schema.table1" in parsed_models
        assert "test_schema.func1" in parsed_functions
