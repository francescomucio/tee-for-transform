"""
Unit tests for DependencyGraphBuilder with test nodes.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from tee.parser.analysis import TableResolver
from tee.parser.analysis.dependency_graph import DependencyGraphBuilder


class TestDependencyGraphWithTests:
    """Test cases for DependencyGraphBuilder with test nodes."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def table_resolver(self):
        """Create a TableResolver instance."""
        return TableResolver({"type": "duckdb"})

    @pytest.fixture
    def builder(self):
        """Create a DependencyGraphBuilder instance."""
        return DependencyGraphBuilder()

    @pytest.fixture
    def parsed_models_basic(self):
        """Create basic parsed models for testing."""
        return {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "schema": [
                            {
                                "name": "id",
                                "type": "integer",
                                "tests": ["not_null"],
                            }
                        ],
                        "tests": ["check_minimum_rows"],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
            "schema1.table2": {
                "model_metadata": {
                    "metadata": {
                        "schema": [
                            {
                                "name": "name",
                                "type": "varchar",
                                "tests": ["unique"],
                            }
                        ]
                    }
                },
                "code": {"sql": {"source_tables": ["schema1.table1"]}},
            },
        }

    def test_parse_test_dependencies_standard_tests(
        self, builder, temp_dir, table_resolver, parsed_models_basic
    ):
        """Test parsing dependencies for standard tests (not_null, unique)."""
        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models_basic,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should have test nodes for:
        # - schema1.table1.id.not_null (column-level)
        # - schema1.table1.check_minimum_rows (table-level)
        # - schema1.table2.name.unique (column-level)

        assert "test:schema1.table1.id.not_null" in test_deps
        assert "test:schema1.table1.check_minimum_rows" in test_deps
        assert "test:schema1.table2.name.unique" in test_deps

        # Standard tests should only depend on the table being tested
        assert test_deps["test:schema1.table1.id.not_null"] == ["schema1.table1"]
        assert test_deps["test:schema1.table1.check_minimum_rows"] == ["schema1.table1"]
        assert test_deps["test:schema1.table2.name.unique"] == ["schema1.table2"]

    def test_parse_test_dependencies_generic_sql_test(self, builder, temp_dir, table_resolver):
        """Test parsing dependencies for generic SQL tests with @table_name."""
        # Create a generic SQL test
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "check_minimum_rows.sql"
        test_file.write_text("SELECT COUNT(*) FROM @table_name HAVING COUNT(*) < 10")

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "tests": ["check_minimum_rows"],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
        }

        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should create test node
        assert "test:schema1.table1.check_minimum_rows" in test_deps
        # Generic SQL test should depend on the table it's testing
        assert "schema1.table1" in test_deps["test:schema1.table1.check_minimum_rows"]

    def test_parse_test_dependencies_singular_sql_test(self, builder, temp_dir, table_resolver):
        """Test parsing dependencies for singular SQL tests with hardcoded table."""
        # Create a singular SQL test
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "test_table1.sql"
        test_file.write_text("SELECT * FROM schema1.table1 WHERE id < 0")

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "tests": ["test_table1"],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
        }

        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should create test node
        assert "test:schema1.table1.test_table1" in test_deps
        # Singular SQL test should depend on the table it references
        assert "schema1.table1" in test_deps["test:schema1.table1.test_table1"]

    def test_parse_test_dependencies_sql_test_with_multiple_tables(
        self, builder, temp_dir, table_resolver
    ):
        """Test parsing dependencies for SQL tests that reference multiple tables."""
        # Create a SQL test that references multiple tables
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "relationship_test.sql"
        test_file.write_text(
            "SELECT t1.id FROM @table_name t1 "
            "LEFT JOIN schema1.other_table t2 ON t1.id = t2.id "
            "WHERE t2.id IS NULL"
        )

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "tests": ["relationship_test"],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
            "schema1.other_table": {
                "model_metadata": {},
                "code": {"sql": {"source_tables": []}},
            },
        }

        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should create test node
        assert "test:schema1.table1.relationship_test" in test_deps
        # Should depend on both tables
        deps = test_deps["test:schema1.table1.relationship_test"]
        assert "schema1.table1" in deps
        assert "schema1.other_table" in deps

    def test_parse_test_dependencies_column_level_sql_test(self, builder, temp_dir, table_resolver):
        """Test parsing dependencies for column-level SQL tests."""
        # Create a column-level SQL test
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "column_not_negative.sql"
        test_file.write_text("SELECT @column_name FROM @table_name WHERE @column_name < 0")

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "schema": [
                            {
                                "name": "amount",
                                "type": "decimal",
                                "tests": ["column_not_negative"],
                            }
                        ]
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
        }

        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should create column-level test node
        assert "test:schema1.table1.amount.column_not_negative" in test_deps
        # Should depend on the table
        assert "schema1.table1" in test_deps["test:schema1.table1.amount.column_not_negative"]

    def test_parse_test_instance_dependencies_standard_test(self, builder, table_resolver):
        """Test _parse_test_instance_dependencies for standard tests."""
        parsed_models = {
            "schema1.table1": {
                "model_metadata": {},
                "code": {"sql": {"source_tables": []}},
            },
        }

        deps = builder._parse_test_instance_dependencies(
            test_name="not_null",
            table_name="schema1.table1",
            column_name="id",
            discovered_tests={},
            sql_parser=Mock(),
            table_resolver=table_resolver,
            parsed_models=parsed_models,
        )

        # Standard test should only depend on the table
        assert deps == ["schema1.table1"]

    def test_parse_test_instance_dependencies_sql_test(self, builder, temp_dir, table_resolver):
        """Test _parse_test_instance_dependencies for SQL tests."""
        # Create a SQL test
        tests_folder = temp_dir / "tests"
        tests_folder.mkdir()
        test_file = tests_folder / "my_test.sql"
        test_file.write_text("SELECT * FROM @table_name WHERE id = 1")

        from tee.parser.parsers.sql_parser import SQLParser
        from tee.testing.test_discovery import TestDiscovery

        discovery = TestDiscovery(temp_dir)
        discovered_tests = discovery.discover_tests()
        sql_parser = SQLParser()

        parsed_models = {
            "schema1.table1": {
                "model_metadata": {},
                "code": {"sql": {"source_tables": []}},
            },
        }

        deps = builder._parse_test_instance_dependencies(
            test_name="my_test",
            table_name="schema1.table1",
            column_name=None,
            discovered_tests=discovered_tests,
            sql_parser=sql_parser,
            table_resolver=table_resolver,
            parsed_models=parsed_models,
        )

        # SQL test should depend on the table
        assert "schema1.table1" in deps

    def test_build_graph_includes_test_nodes(
        self, builder, temp_dir, table_resolver, parsed_models_basic
    ):
        """Test that build_graph includes test nodes in the graph."""
        graph = builder.build_graph(
            parsed_models=parsed_models_basic,
            table_resolver=table_resolver,
            project_folder=temp_dir,
        )

        # Check that test nodes are in nodes
        assert "test:schema1.table1.id.not_null" in graph["nodes"]
        assert "test:schema1.table1.check_minimum_rows" in graph["nodes"]
        assert "test:schema1.table2.name.unique" in graph["nodes"]

        # Check that test nodes have dependencies
        assert "test:schema1.table1.id.not_null" in graph["dependencies"]
        assert "test:schema1.table1.check_minimum_rows" in graph["dependencies"]

    def test_build_graph_test_nodes_in_execution_order(
        self, builder, temp_dir, table_resolver, parsed_models_basic
    ):
        """Test that test nodes appear in execution order after their tables."""
        graph = builder.build_graph(
            parsed_models=parsed_models_basic,
            table_resolver=table_resolver,
            project_folder=temp_dir,
        )

        execution_order = graph["execution_order"]

        # Find positions
        table1_pos = execution_order.index("schema1.table1")
        table2_pos = execution_order.index("schema1.table2")
        test1_pos = execution_order.index("test:schema1.table1.id.not_null")
        test2_pos = execution_order.index("test:schema1.table1.check_minimum_rows")
        test3_pos = execution_order.index("test:schema1.table2.name.unique")

        # Tests should come after their tables
        assert test1_pos > table1_pos
        assert test2_pos > table1_pos
        assert test3_pos > table2_pos

    def test_build_graph_no_metadata(self, builder, temp_dir, table_resolver):
        """Test that models without metadata don't create test nodes."""
        parsed_models = {
            "schema1.table1": {
                "model_metadata": {},
                "code": {"sql": {"source_tables": []}},
            },
        }

        graph = builder.build_graph(
            parsed_models=parsed_models,
            table_resolver=table_resolver,
            project_folder=temp_dir,
        )

        # Should not have any test nodes
        test_nodes = [n for n in graph["nodes"] if n.startswith("test:")]
        assert len(test_nodes) == 0

    def test_build_graph_empty_tests(self, builder, temp_dir, table_resolver):
        """Test that models with empty test lists don't create test nodes."""
        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "tests": [],
                        "schema": [{"name": "id", "type": "integer", "tests": []}],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
        }

        graph = builder.build_graph(
            parsed_models=parsed_models,
            table_resolver=table_resolver,
            project_folder=temp_dir,
        )

        # Should not have any test nodes
        test_nodes = [n for n in graph["nodes"] if n.startswith("test:")]
        assert len(test_nodes) == 0

    def test_parse_test_dependencies_handles_missing_test_file(
        self, builder, temp_dir, table_resolver
    ):
        """Test that missing test files are handled gracefully."""
        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "tests": ["nonexistent_test"],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
        }

        # Should not raise an error
        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should still create a test node (treated as standard test)
        assert "test:schema1.table1.nonexistent_test" in test_deps
        assert test_deps["test:schema1.table1.nonexistent_test"] == ["schema1.table1"]

    def test_parse_test_dependencies_table_level_vs_column_level(
        self, builder, temp_dir, table_resolver
    ):
        """Test that table-level and column-level tests create different nodes."""
        parsed_models = {
            "schema1.table1": {
                "model_metadata": {
                    "metadata": {
                        "schema": [
                            {
                                "name": "id",
                                "type": "integer",
                                "tests": ["not_null"],
                            }
                        ],
                        "tests": ["check_minimum_rows"],
                    }
                },
                "code": {"sql": {"source_tables": []}},
            },
        }

        test_deps = builder._parse_test_dependencies(
            parsed_models=parsed_models,
            project_folder=temp_dir,
            table_resolver=table_resolver,
        )

        # Should have both column-level and table-level test nodes
        assert "test:schema1.table1.id.not_null" in test_deps  # Column-level
        assert "test:schema1.table1.check_minimum_rows" in test_deps  # Table-level

        # They should be different nodes
        assert "test:schema1.table1.id.not_null" != "test:schema1.table1.check_minimum_rows"
