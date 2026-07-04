"""
Unit tests for shared_helpers module.
"""

import pytest

from t4t.executor_helpers.shared_helpers import (
    create_empty_build_results,
    create_empty_execution_results,
    validate_compile_results,
)


class TestValidateCompileResults:
    """Test cases for validate_compile_results function."""

    def test_valid_compile_results(self):
        """Test validation with valid compile results."""
        compile_results = {
            "dependency_graph": {"nodes": ["model1", "model2"], "edges": []},
            "execution_order": ["model1", "model2"],
            "parsed_models": {"model1": {}, "model2": {}},
        }

        graph, execution_order, parsed_models = validate_compile_results(compile_results)

        assert graph == compile_results["dependency_graph"]
        assert execution_order == ["model1", "model2"]
        assert parsed_models == {"model1": {}, "model2": {}}

    def test_empty_execution_order(self):
        """Test validation with empty execution order (no models)."""
        compile_results = {
            "dependency_graph": {"nodes": [], "edges": []},
            "execution_order": [],
            "parsed_models": {},
        }

        graph, execution_order, parsed_models = validate_compile_results(compile_results)

        assert graph == compile_results["dependency_graph"]
        assert execution_order == []
        assert parsed_models == {}

    def test_missing_graph(self):
        """Test validation fails when graph is missing."""
        compile_results = {
            "execution_order": ["model1"],
            "parsed_models": {"model1": {}},
        }

        with pytest.raises(RuntimeError, match="Compilation did not return dependency graph"):
            validate_compile_results(compile_results)

    def test_none_execution_order(self):
        """Test validation fails when execution_order is None."""
        compile_results = {
            "dependency_graph": {"nodes": [], "edges": []},
            "execution_order": None,
            "parsed_models": {},
        }

        with pytest.raises(RuntimeError, match="Compilation did not return execution order"):
            validate_compile_results(compile_results)

    def test_missing_execution_order_key(self):
        """Test validation with missing execution_order key (defaults to empty list)."""
        compile_results = {
            "dependency_graph": {"nodes": [], "edges": []},
            "parsed_models": {},
        }

        graph, execution_order, parsed_models = validate_compile_results(compile_results)

        assert execution_order == []
        assert parsed_models == {}


class TestCreateEmptyExecutionResults:
    """Test cases for create_empty_execution_results function."""

    def test_create_empty_results(self):
        """Test creating empty execution results."""
        graph = {"nodes": [], "edges": []}

        results = create_empty_execution_results(graph)

        assert results["executed_tables"] == []
        assert results["failed_tables"] == []
        assert results["executed_functions"] == []
        assert results["failed_functions"] == []
        assert results["warnings"] == []
        assert results["table_info"] == {}
        assert results["analysis"]["total_models"] == 0
        assert results["analysis"]["dependency_graph"] == graph

    def test_create_empty_results_with_warnings(self):
        """Test creating empty execution results with warnings."""
        graph = {"nodes": [], "edges": []}
        warnings = ["No models matched the selection criteria"]

        results = create_empty_execution_results(graph, warnings=warnings)

        assert results["warnings"] == warnings
        assert results["analysis"]["dependency_graph"] == graph


class TestCreateEmptyBuildResults:
    """Test cases for create_empty_build_results function."""

    def test_create_empty_build_results(self):
        """Test creating empty build results."""
        graph = {"nodes": [], "edges": []}

        results = create_empty_build_results(graph)

        assert results["executed_tables"] == []
        assert results["failed_tables"] == []
        assert results["skipped_tables"] == []
        assert results["executed_functions"] == []
        assert results["failed_functions"] == []
        assert results["warnings"] == []
        assert results["table_info"] == {}
        assert results["test_results"]["total"] == 0
        assert results["test_results"]["passed"] == 0
        assert results["test_results"]["failed"] == 0
        assert results["test_results"]["warnings"] == 0
        assert results["test_results"]["test_results"] == []
        assert results["analysis"]["total_models"] == 0
        assert results["analysis"]["dependency_graph"] == graph
