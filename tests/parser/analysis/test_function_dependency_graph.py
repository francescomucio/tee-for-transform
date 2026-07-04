"""
Unit tests for function dependency graph integration.
"""

from t4t.parser.analysis.dependency_graph import DependencyGraphBuilder
from t4t.parser.analysis.table_resolver import TableResolver


class TestFunctionDependencyGraph:
    """Test function integration in dependency graph."""

    def test_build_graph_with_functions(self):
        """Test building dependency graph with functions."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_models = {
            "my_schema.table1": {
                "code": {
                    "sql": {"source_tables": [], "resolved_sql": "SELECT * FROM my_schema.table2"}
                },
                "model_metadata": {},
            }
        }

        parsed_functions = {
            "my_schema.func1": {
                "function_metadata": {
                    "function_name": "func1",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": ["my_schema.table1"],
                        "source_functions": [],
                    }
                },
            }
        }

        graph = builder.build_graph(parsed_models, resolver, parsed_functions=parsed_functions)

        assert "my_schema.func1" in graph["nodes"]
        assert "my_schema.table1" in graph["nodes"]
        assert len(graph["nodes"]) >= 2

    def test_function_to_table_dependency(self):
        """Test function depending on a table."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_models = {
            "my_schema.users": {
                "code": {"sql": {"source_tables": [], "resolved_sql": "SELECT * FROM users"}},
                "model_metadata": {},
            }
        }

        parsed_functions = {
            "my_schema.get_users": {
                "function_metadata": {
                    "function_name": "get_users",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": ["users"],
                        "source_functions": [],
                    }
                },
            }
        }

        graph = builder.build_graph(parsed_models, resolver, parsed_functions=parsed_functions)

        # Function should depend on table
        assert "my_schema.users" in graph["dependencies"]["my_schema.get_users"]

    def test_function_to_function_dependency(self):
        """Test function depending on another function."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_functions = {
            "my_schema.helper_func": {
                "function_metadata": {
                    "function_name": "helper_func",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
            },
            "my_schema.main_func": {
                "function_metadata": {
                    "function_name": "main_func",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": ["helper_func"],
                    }
                },
            },
        }

        graph = builder.build_graph({}, resolver, parsed_functions=parsed_functions)

        # Main function should depend on helper function
        assert "my_schema.helper_func" in graph["dependencies"]["my_schema.main_func"]

    def test_model_to_function_dependency(self):
        """Test model depending on a function."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_models = {
            "my_schema.result": {
                "code": {
                    "sql": {
                        "source_tables": [],
                        "source_functions": [
                            "my_schema.calculate_metric"
                        ],  # Pre-extracted during parsing
                        "resolved_sql": "SELECT my_schema.calculate_metric(value) FROM data",
                    }
                },
                "model_metadata": {},
            }
        }

        parsed_functions = {
            "my_schema.calculate_metric": {
                "function_metadata": {
                    "function_name": "calculate_metric",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
            }
        }

        graph = builder.build_graph(parsed_models, resolver, parsed_functions=parsed_functions)

        # Model should depend on function
        assert "my_schema.calculate_metric" in graph["dependencies"]["my_schema.result"]

    def test_execution_order_functions_first(self):
        """Test that functions come before models in execution order."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_models = {
            "my_schema.table1": {
                "code": {"sql": {"source_tables": [], "resolved_sql": "SELECT 1"}},
                "model_metadata": {},
            }
        }

        parsed_functions = {
            "my_schema.func1": {
                "function_metadata": {
                    "function_name": "func1",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
            }
        }

        graph = builder.build_graph(parsed_models, resolver, parsed_functions=parsed_functions)

        execution_order = graph["execution_order"]

        # Find positions
        func_pos = execution_order.index("my_schema.func1")
        model_pos = execution_order.index("my_schema.table1")

        # Function should come before model
        assert func_pos < model_pos

    def test_function_dependency_chain(self):
        """Test chain of function dependencies."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_functions = {
            "my_schema.base_func": {
                "function_metadata": {
                    "function_name": "base_func",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
            },
            "my_schema.mid_func": {
                "function_metadata": {
                    "function_name": "mid_func",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": ["base_func"],
                    }
                },
            },
            "my_schema.top_func": {
                "function_metadata": {
                    "function_name": "top_func",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": ["mid_func"],
                    }
                },
            },
        }

        graph = builder.build_graph({}, resolver, parsed_functions=parsed_functions)

        # Check dependency chain
        assert "my_schema.base_func" in graph["dependencies"]["my_schema.mid_func"]
        assert "my_schema.mid_func" in graph["dependencies"]["my_schema.top_func"]

        # Check execution order respects dependencies
        execution_order = graph["execution_order"]
        base_pos = execution_order.index("my_schema.base_func")
        mid_pos = execution_order.index("my_schema.mid_func")
        top_pos = execution_order.index("my_schema.top_func")

        assert base_pos < mid_pos < top_pos

    def test_function_and_model_dependencies(self):
        """Test function depending on table, model depending on function."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_models = {
            "my_schema.users": {
                "code": {"sql": {"source_tables": [], "resolved_sql": "SELECT * FROM users"}},
                "model_metadata": {},
            },
            "my_schema.result": {
                "code": {
                    "sql": {
                        "source_tables": ["my_schema.users"],  # Table dependency from SQL
                        "source_functions": [
                            "my_schema.process_users"
                        ],  # Pre-extracted during parsing
                        "resolved_sql": "SELECT my_schema.process_users(id) FROM my_schema.users",
                    }
                },
                "model_metadata": {},
            },
        }

        parsed_functions = {
            "my_schema.process_users": {
                "function_metadata": {
                    "function_name": "process_users",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": ["users"],
                        "source_functions": [],
                    }
                },
            }
        }

        graph = builder.build_graph(parsed_models, resolver, parsed_functions=parsed_functions)

        # Function depends on table
        assert "my_schema.users" in graph["dependencies"]["my_schema.process_users"]
        # Model depends on function and table
        assert "my_schema.process_users" in graph["dependencies"]["my_schema.result"]
        assert "my_schema.users" in graph["dependencies"]["my_schema.result"]

        # Execution order: users -> process_users -> result
        execution_order = graph["execution_order"]
        users_pos = execution_order.index("my_schema.users")
        func_pos = execution_order.index("my_schema.process_users")
        result_pos = execution_order.index("my_schema.result")

        assert users_pos < func_pos < result_pos

    def test_cycle_detection_functions(self):
        """Test cycle detection in function dependencies."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_functions = {
            "my_schema.func1": {
                "function_metadata": {
                    "function_name": "func1",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": ["func2"],
                    }
                },
            },
            "my_schema.func2": {
                "function_metadata": {
                    "function_name": "func2",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": ["func1"],
                    }
                },
            },
        }

        graph = builder.build_graph({}, resolver, parsed_functions=parsed_functions)

        # Should detect cycle
        assert len(graph["cycles"]) > 0
        # Execution order should be empty when cycles exist
        assert len(graph["execution_order"]) == 0

    def test_no_functions_empty_graph(self):
        """Test that graph works when no functions are provided."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_models = {
            "my_schema.table1": {
                "code": {"sql": {"source_tables": [], "resolved_sql": "SELECT 1"}},
                "model_metadata": {},
            }
        }

        graph = builder.build_graph(parsed_models, resolver, parsed_functions=None)

        assert "my_schema.table1" in graph["nodes"]
        assert len(graph["execution_order"]) > 0

    def test_qualified_function_name_resolution(self):
        """Test resolving qualified function names in dependencies."""
        builder = DependencyGraphBuilder()
        resolver = TableResolver({"type": "duckdb"})

        parsed_functions = {
            "my_schema.helper": {
                "function_metadata": {
                    "function_name": "helper",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": [],
                    }
                },
            },
            "my_schema.main": {
                "function_metadata": {
                    "function_name": "main",
                },
                "code": {
                    "sql": {
                        "original_sql": "CREATE FUNCTION...",
                        "source_tables": [],
                        "source_functions": ["my_schema.helper"],
                    }
                },
            },
        }

        graph = builder.build_graph({}, resolver, parsed_functions=parsed_functions)

        # Should resolve qualified function name
        assert "my_schema.helper" in graph["dependencies"]["my_schema.main"]
