"""
Simplified ProjectParser class that delegates to the orchestrator.
"""

import logging
from pathlib import Path
from typing import Any

from tee.parser.core.orchestrator import ParserOrchestrator
from tee.parser.shared.exceptions import ParserError
from tee.parser.shared.types import ConnectionConfig, DependencyGraph, ParsedModel, Variables

# Configure logging
logger = logging.getLogger(__name__)


class ProjectParser:
    """
    A simplified module to parse SQL files in a project folder and extract parsed arguments.

    This class now delegates most of its work to the ParserOrchestrator for better
    separation of concerns and maintainability.

    For DuckDB connections, the full_table_name is constructed as:
    {first_parent_folder_in_models} + "." + {file_name_without_sql}
    """

    def __init__(
        self,
        project_folder: str,
        connection: ConnectionConfig,
        variables: Variables | None = None,
        project_config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the ProjectParser.

        Args:
            project_folder: Path to the project folder containing SQL files
            connection: Connection configuration dict with 'type' key
            variables: Optional dictionary of variables for SQL substitution
            project_config: Optional project configuration for OTS export
        """
        self.project_folder = Path(project_folder)
        self.connection = connection
        self.variables = variables or {}

        # Initialize the orchestrator
        self.orchestrator = ParserOrchestrator(
            project_folder, connection, variables, project_config
        )

        # Backward compatibility properties
        self.models_folder = self.project_folder / "models"
        self.parsed_models: dict[str, ParsedModel] | None = None
        self.graph: DependencyGraph | None = None

    def collect_models(self) -> dict[str, ParsedModel]:
        """
        Collect all .sql and .py files in the project folder, parse them,
        and return a JSON structure with parsed arguments.

        The result is cached in self.parsed_models for reuse.

        Returns:
            Dict mapping full_table_name to parsed SQL arguments
        """
        try:
            # Use orchestrator to discover and parse models
            self.parsed_models = self.orchestrator.discover_and_parse_models()
            return self.parsed_models
        except Exception as e:
            raise ParserError(f"Failed to collect models: {e}") from e

    def build_dependency_graph(self) -> DependencyGraph:
        """
        Build a dependency graph from the parsed SQL models and save all outputs.

        The result is cached in self.graph for reuse.
        Automatically saves:
        - Dependency graph as JSON
        - Mermaid diagram
        - Markdown report

        Returns:
            Dict containing dependency graph information
        """
        try:
            # Use orchestrator to build dependency graph
            self.graph = self.orchestrator.build_dependency_graph()

            # Save all outputs automatically
            self.save_dependency_graph()
            self.save_mermaid_diagram()
            self.save_markdown_report()

            return self.graph
        except Exception as e:
            raise ParserError(f"Failed to build dependency graph: {e}") from e

    def update_parsed_models(self, updated_models: dict[str, Any]) -> None:
        """
        Update the parser's cached models with updated model data.

        This method should be called by the executor after execution to ensure
        the parser's cached models are updated with the latest data.

        Args:
            updated_models: Models with updated data from execution
        """
        if self.parsed_models is None:
            return

        for table_name, model_data in updated_models.items():
            if table_name in self.parsed_models:
                self.parsed_models[table_name] = model_data
                logger.debug(f"Updated parser cache for {table_name}")

    def get_execution_order(self) -> list[str]:
        """Get the execution order for all tables based on dependencies."""
        return self.orchestrator.get_execution_order()

    def get_table_dependencies(self, table_name: str) -> list[str]:
        """Get direct dependencies for a specific table."""
        return self.orchestrator.get_table_dependencies(table_name)

    def get_table_dependents(self, table_name: str) -> list[str]:
        """Get tables that depend on a specific table."""
        return self.orchestrator.get_table_dependents(table_name)

    def save_to_json(self, output_file: str = None) -> None:
        """Collect models and save the result to a JSON file."""
        try:
            result = self.collect_models()

            # Use orchestrator's JSON exporter
            if output_file is None:
                self.orchestrator.json_exporter.export_parsed_models(result)
                self.orchestrator.json_exporter.export_dimension_registry(
                    self.orchestrator.dimension_registry
                )
                # Note: OTS modules and test library export is handled by the compiler
                # We don't export them here to avoid duplicate files
            else:
                self.orchestrator.json_exporter.export_parsed_models(result, output_file)
        except Exception as e:
            raise ParserError(f"Failed to save to JSON: {e}") from e

    def save_dependency_graph(self, output_file: str = None) -> None:
        """Save the dependency graph to JSON file."""
        try:
            if self.graph is None:
                self.build_dependency_graph()

            # Use orchestrator's JSON exporter
            if output_file is None:
                self.orchestrator.json_exporter.export_dependency_graph(self.graph)
            else:
                self.orchestrator.json_exporter.export_dependency_graph(self.graph, output_file)
        except Exception as e:
            raise ParserError(f"Failed to save dependency graph: {e}") from e

    def save_mermaid_diagram(self, output_file: str = None) -> None:
        """Save the dependency graph as a Mermaid diagram file."""
        try:
            if self.graph is None:
                self.build_dependency_graph()

            # Get parsed functions from orchestrator for function identification
            parsed_functions = self.orchestrator._parsed_functions or {}

            # Use orchestrator's report generator
            if output_file is None:
                self.orchestrator.report_generator.generate_mermaid_diagram(
                    self.graph, parsed_functions=parsed_functions
                )
            else:
                self.orchestrator.report_generator.generate_mermaid_diagram(
                    self.graph, output_file, parsed_functions=parsed_functions
                )
        except Exception as e:
            raise ParserError(f"Failed to save Mermaid diagram: {e}") from e

    def save_markdown_report(self, output_file: str = None) -> None:
        """Save a comprehensive markdown report with Mermaid diagram."""
        try:
            if self.graph is None:
                self.build_dependency_graph()

            # Get parsed functions from orchestrator for function identification
            parsed_functions = self.orchestrator._parsed_functions or {}

            # Use orchestrator's report generator
            if output_file is None:
                self.orchestrator.report_generator.generate_markdown_report(
                    self.graph, parsed_functions=parsed_functions
                )
            else:
                self.orchestrator.report_generator.generate_markdown_report(
                    self.graph, output_file, parsed_functions
                )
        except Exception as e:
            raise ParserError(f"Failed to save markdown report: {e}") from e
