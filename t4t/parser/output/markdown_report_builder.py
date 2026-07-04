"""
Helper functions for building markdown report sections.
"""

from t4t.parser.shared.types import DependencyGraph


def separate_nodes_by_type(
    all_nodes: list[str], function_names: set[str]
) -> tuple[list[str], list[str], list[str]]:
    """
    Separate nodes into test, function, and table nodes.

    Args:
        all_nodes: List of all node names
        function_names: Set of function names for identification

    Returns:
        Tuple of (test_nodes, function_nodes, table_nodes)
    """
    test_nodes = [node for node in all_nodes if node.startswith("test:")]
    function_nodes = [
        node for node in all_nodes if node in function_names and not node.startswith("test:")
    ]
    table_nodes = [
        node for node in all_nodes if node not in function_names and not node.startswith("test:")
    ]
    return test_nodes, function_nodes, table_nodes


def _filter_dependencies(deps: list[str]) -> tuple[list[str], list[str]]:
    """
    Filter dependencies into table dependencies and test dependencies.

    Args:
        deps: List of dependency node names

    Returns:
        Tuple of (table_deps, test_deps)
    """
    table_deps = [dep for dep in deps if not dep.startswith("test:")]
    test_deps = [dep for dep in deps if dep.startswith("test:")]
    return table_deps, test_deps


def _format_dependency_list(deps: list[str], prefix: str = "`", suffix: str = "`") -> str:
    """
    Format a list of dependencies as a comma-separated markdown string.

    Args:
        deps: List of dependency names
        prefix: Prefix for each dependency (default: backtick)
        suffix: Suffix for each dependency (default: backtick)

    Returns:
        Formatted string
    """
    return ", ".join([f"{prefix}{dep}{suffix}" for dep in deps])


def build_statistics_section(
    table_nodes: list[str], function_nodes: list[str], test_nodes: list[str], graph: DependencyGraph
) -> str:
    """
    Build the statistics section of the markdown report.

    Args:
        table_nodes: List of table node names
        function_nodes: List of function node names
        test_nodes: List of test node names
        graph: The dependency graph

    Returns:
        Markdown string for statistics section
    """
    return f"""## Statistics

- **Total Tables**: {len(table_nodes)}
- **Total Functions**: {len(function_nodes)}
- **Total Tests**: {len(test_nodes)}
- **Total Nodes**: {len(graph["nodes"])}
- **Total Dependencies**: {len(graph["edges"])}
- **Circular Dependencies**: {len(graph["cycles"])}
"""


def build_execution_order_section(execution_order: list[str]) -> str:
    """
    Build the execution order section of the markdown report.

    Args:
        execution_order: List of nodes in execution order

    Returns:
        Markdown string for execution order section
    """
    content = "## Execution Order\n\n"

    if execution_order:
        for i, node in enumerate(execution_order, 1):
            content += f"{i}. `{node}`\n"
    else:
        content += "No valid execution order (circular dependencies detected)\n"

    return content


def build_test_details_section(test_nodes: list[str], graph: DependencyGraph) -> str:
    """
    Build the tests details section of the markdown report.

    Args:
        test_nodes: List of test node names
        graph: The dependency graph

    Returns:
        Markdown string for tests details section
    """
    if not test_nodes:
        return ""

    content = "\n## Tests Details\n\n"
    content += "The following tests are defined and integrated into the dependency graph:\n\n"

    for test_node in sorted(test_nodes):
        # Parse test node: test:table.test_name or test:table.column.test_name
        test_parts = test_node.replace("test:", "").split(".")
        if len(test_parts) == 2:
            # Table-level test: test:table.test_name
            table_name, test_name = test_parts
            test_display = f"`{test_name}` on `{table_name}`"
            test_type = "Table-level"
        elif len(test_parts) == 3:
            # Column-level test: test:table.column.test_name
            table_name, column_name, test_name = test_parts
            test_display = f"`{test_name}` on `{table_name}.{column_name}`"
            test_type = "Column-level"
        else:
            # Fallback for unexpected format
            test_display = test_node.replace("test:", "")
            test_type = "Test"

        deps = graph.get("dependencies", {}).get(test_node, [])
        dependents = graph.get("dependents", {}).get(test_node, [])

        content += f"### {test_display}\n\n"
        content += f"**Type**: {test_type}\n\n"

        if deps:
            table_deps, test_deps = _filter_dependencies(deps)

            if table_deps:
                content += f"**Depends on tables**: {_format_dependency_list(table_deps)}\n\n"
            if test_deps:
                test_names = [dep.replace("test:", "") for dep in test_deps]
                content += f"**Depends on tests**: {_format_dependency_list(test_names)}\n\n"
        else:
            content += "**No dependencies**\n\n"

        if dependents:
            table_dependents, test_dependents = _filter_dependencies(dependents)

            if table_dependents:
                content += f"**Used by tables**: {_format_dependency_list(table_dependents)}\n\n"
            if test_dependents:
                test_names = [dep.replace("test:", "") for dep in test_dependents]
                content += f"**Used by tests**: {_format_dependency_list(test_names)}\n\n"
        else:
            content += "**No dependents**\n\n"

    return content


def build_transformation_details_section(
    function_nodes: list[str],
    table_nodes: list[str],
    function_names: set[str],
    graph: DependencyGraph,
) -> str:
    """
    Build the transformation details section of the markdown report.

    Args:
        function_nodes: List of function node names
        table_nodes: List of table node names
        function_names: Set of function names for identification
        graph: The dependency graph

    Returns:
        Markdown string for transformation details section
    """
    content = "\n## Transformation Details\n\n"

    # Include both function and table nodes in the transformation details section (exclude tests)
    all_transformations = sorted(function_nodes + table_nodes)
    for transformation in all_transformations:
        is_function = transformation in function_names
        node_type = "Function" if is_function else "Table"
        deps = graph.get("dependencies", {}).get(transformation, [])
        dependents = graph.get("dependents", {}).get(transformation, [])

        content += f"### `{transformation}`\n\n"
        content += f"**Type**: {node_type}\n\n"

        if deps:
            table_deps, test_deps = _filter_dependencies(deps)

            if table_deps:
                content += f"**Depends on**: {_format_dependency_list(table_deps)}\n\n"
            if test_deps:
                test_names = [dep.replace("test:", "") for dep in test_deps]
                content += f"**Has tests**: {_format_dependency_list(test_names)}\n\n"
        else:
            base_label = "base function" if is_function else "base table"
            content += f"**No dependencies** ({base_label})\n\n"

        if dependents:
            table_dependents, test_dependents = _filter_dependencies(dependents)

            if table_dependents:
                content += f"**Used by**: {_format_dependency_list(table_dependents)}\n\n"
            if test_dependents:
                test_names = [dep.replace("test:", "") for dep in test_dependents]
                content += f"**Tested by**: {_format_dependency_list(test_names)}\n\n"
        else:
            leaf_label = "leaf function" if is_function else "leaf table"
            content += f"**No dependents** ({leaf_label})\n\n"

    return content


def build_circular_dependencies_section(cycles: list[list[str]]) -> str:
    """
    Build the circular dependencies section of the markdown report.

    Args:
        cycles: List of circular dependency cycles

    Returns:
        Markdown string for circular dependencies section
    """
    if not cycles:
        return ""

    content = "## ⚠️ Circular Dependencies\n\n"
    for i, cycle in enumerate(cycles, 1):
        cycle_str = " → ".join([f"`{table}`" for table in cycle]) + f" → `{cycle[0]}`"
        content += f"{i}. {cycle_str}\n\n"

    return content
