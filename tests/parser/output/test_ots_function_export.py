"""
Unit tests for OTS function export functionality.
"""

import pytest

from t4t.parser.output.ots.transformer import OTSTransformer
from t4t.typing import Function, Model


class TestOTSFunctionExport:
    """Test cases for function export in OTSTransformer."""

    @pytest.fixture
    def project_config(self):
        """Create sample project config."""
        return {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
        }

    @pytest.fixture
    def sample_function(self) -> Function:
        """Create sample parsed function for testing."""
        return {
            "function_metadata": {
                "function_name": "calculate_percentage",
                "description": "Calculate percentage",
                "function_type": "scalar",
                "language": "sql",
                "parameters": [
                    {"name": "numerator", "type": "FLOAT", "mode": "IN"},
                    {"name": "denominator", "type": "FLOAT", "mode": "IN"},
                ],
                "return_type": "FLOAT",
                "schema": "my_schema",
                "tags": ["analytics", "math"],
                "object_tags": {"classification": "public"},
                "dependencies": {"tables": [], "functions": []},
                "file_path": "functions/my_schema/calculate_percentage.sql",
            },
            "code": {
                "sql": {
                    "original_sql": "CREATE OR REPLACE FUNCTION my_schema.calculate_percentage(numerator FLOAT, denominator FLOAT) RETURNS FLOAT AS $$ SELECT numerator / denominator * 100 $$ LANGUAGE sql;",
                }
            },
            "function_hash": "abc123",
        }

    def test_export_function_to_ots(self, project_config, sample_function):
        """Test exporting a function to OTS format."""
        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.calculate_percentage": sample_function,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)

        assert len(modules) == 1
        module = modules["test_project.my_schema"]
        assert module["ots_version"] == "0.2.2"  # Latest OTS version
        assert "functions" in module
        assert len(module["functions"]) == 1

        ots_function = module["functions"][0]
        assert ots_function["function_id"] == "my_schema.calculate_percentage"
        assert ots_function["description"] == "Calculate percentage"
        assert ots_function["function_type"] == "scalar"
        assert ots_function["language"] == "sql"
        assert len(ots_function["parameters"]) == 2
        assert ots_function["return_type"] == "FLOAT"

    def test_ots_version_without_functions(self, project_config):
        """Test that OTS version is 0.1.0 when no functions are present."""
        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "my_schema.table1": {
                "model_metadata": {"metadata": {}, "file_path": "models/table1.sql"},
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1",
                        "resolved_sql": "SELECT 1",
                        "source_tables": [],
                    }
                },
            }
        }

        modules = transformer.transform_to_ots_modules(parsed_models)

        assert len(modules) == 1
        module = modules["test_project.my_schema"]
        assert module["ots_version"] == "0.2.2"
        assert "functions" not in module

    def test_ots_version_with_functions(self, project_config, sample_function):
        """Test that OTS version is 0.2.1 when functions are present."""
        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.calculate_percentage": sample_function,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)

        assert len(modules) == 1
        module = modules["test_project.my_schema"]
        assert module["ots_version"] == "0.2.2"

    def test_function_tags_export(self, project_config, sample_function):
        """Test that function tags are exported to OTS."""
        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.calculate_percentage": sample_function,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)
        ots_function = modules["test_project.my_schema"]["functions"][0]

        assert "metadata" in ots_function
        assert "tags" in ots_function["metadata"]
        assert ots_function["metadata"]["tags"] == ["analytics", "math"]

    def test_function_object_tags_export(self, project_config, sample_function):
        """Test that function object_tags are exported to OTS."""
        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.calculate_percentage": sample_function,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)
        ots_function = modules["test_project.my_schema"]["functions"][0]

        assert "metadata" in ots_function
        assert "object_tags" in ots_function["metadata"]
        assert ots_function["metadata"]["object_tags"]["classification"] == "public"

    def test_function_code_structure(self, project_config, sample_function):
        """Test that function code is structured correctly in OTS."""
        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.calculate_percentage": sample_function,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)
        ots_function = modules["test_project.my_schema"]["functions"][0]

        assert "code" in ots_function
        assert "generic_sql" in ots_function["code"]
        assert "database_specific" in ots_function["code"]
        assert isinstance(ots_function["code"]["database_specific"], dict)

    def test_function_dependencies_export(self, project_config):
        """Test that function dependencies are exported."""
        function_with_deps: Function = {
            "function_metadata": {
                "function_name": "helper_func",
                "function_type": "scalar",
                "language": "sql",
                "file_path": "functions/my_schema/helper_func.sql",
            },
            "code": {
                "sql": {
                    "original_sql": "CREATE FUNCTION helper_func() AS $$ SELECT * FROM my_schema.users $$",
                    "source_tables": [
                        "my_schema.users"
                    ],  # Dependencies in code["sql"] (consistent with models)
                    "source_functions": ["my_schema.base_func"],
                }
            },
        }

        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.helper_func": function_with_deps,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)
        ots_function = modules["test_project.my_schema"]["functions"][0]

        assert "dependencies" in ots_function
        assert ots_function["dependencies"]["tables"] == ["my_schema.users"]
        assert ots_function["dependencies"]["functions"] == ["my_schema.base_func"]

    def test_function_grouping_by_schema(self, project_config):
        """Test that functions are grouped by schema."""
        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "schema1.func1": {
                "function_metadata": {
                    "function_name": "func1",
                    "function_type": "scalar",
                    "language": "sql",
                    "file_path": "functions/schema1/func1.sql",
                },
                "code": {"sql": {"original_sql": "CREATE FUNCTION func1() AS $$ SELECT 1 $$"}},
            },
            "schema2.func2": {
                "function_metadata": {
                    "function_name": "func2",
                    "function_type": "scalar",
                    "language": "sql",
                    "file_path": "functions/schema2/func2.sql",
                },
                "code": {"sql": {"original_sql": "CREATE FUNCTION func2() AS $$ SELECT 2 $$"}},
            },
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)

        assert len(modules) == 2
        assert "test_project.schema1" in modules
        assert "test_project.schema2" in modules
        assert len(modules["test_project.schema1"]["functions"]) == 1
        assert len(modules["test_project.schema2"]["functions"]) == 1

    def test_functions_and_models_in_same_module(self, project_config, sample_function):
        """Test that functions and models can be in the same OTS module."""
        transformer = OTSTransformer(project_config)
        parsed_models: dict[str, Model] = {
            "my_schema.table1": {
                "model_metadata": {"metadata": {}, "file_path": "models/table1.sql"},
                "code": {
                    "sql": {
                        "original_sql": "SELECT 1",
                        "resolved_sql": "SELECT 1",
                        "source_tables": [],
                    }
                },
            }
        }
        parsed_functions: dict[str, Function] = {
            "my_schema.calculate_percentage": sample_function,
        }

        modules = transformer.transform_to_ots_modules(
            parsed_models, parsed_functions=parsed_functions
        )

        assert len(modules) == 1
        module = modules["test_project.my_schema"]
        assert module["ots_version"] == "0.2.2"
        assert len(module["transformations"]) == 1
        assert len(module["functions"]) == 1

    def test_function_with_table_return_type(self, project_config):
        """Test exporting a table function."""
        table_function: Function = {
            "function_metadata": {
                "function_name": "get_users",
                "function_type": "table",
                "language": "sql",
                "return_table_schema": [
                    {"name": "id", "datatype": "INTEGER"},
                    {"name": "name", "datatype": "VARCHAR"},
                ],
                "file_path": "functions/my_schema/get_users.sql",
            },
            "code": {
                "sql": {
                    "original_sql": "CREATE FUNCTION get_users() RETURNS TABLE(id INTEGER, name VARCHAR) AS $$ SELECT * FROM users $$",
                }
            },
        }

        transformer = OTSTransformer(project_config)
        parsed_functions: dict[str, Function] = {
            "my_schema.get_users": table_function,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)
        ots_function = modules["test_project.my_schema"]["functions"][0]

        assert ots_function["function_type"] == "table"
        assert "return_table_schema" in ots_function
        assert len(ots_function["return_table_schema"]) == 2

    def test_function_merge_module_tags(self, project_config):
        """Test that module tags are merged with function tags."""
        project_config_with_tags = {
            "project_folder": "test_project",
            "connection": {"type": "duckdb", "path": ":memory:"},
            "module": {"tags": ["analytics", "production"]},
        }

        function_with_tags: Function = {
            "function_metadata": {
                "function_name": "calc",
                "function_type": "scalar",
                "language": "sql",
                "tags": ["math", "helper"],
                "file_path": "functions/my_schema/calc.sql",
            },
            "code": {"sql": {"original_sql": "CREATE FUNCTION calc() AS $$ SELECT 1 $$"}},
        }

        transformer = OTSTransformer(project_config_with_tags)
        parsed_functions: dict[str, Function] = {
            "my_schema.calc": function_with_tags,
        }

        modules = transformer.transform_to_ots_modules({}, parsed_functions=parsed_functions)
        ots_function = modules["test_project.my_schema"]["functions"][0]

        # Should have merged tags: module tags + function tags
        tags = ots_function["metadata"]["tags"]
        assert "analytics" in tags
        assert "production" in tags
        assert "math" in tags
        assert "helper" in tags
