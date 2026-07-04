"""
JSON export functionality for parsed models and dependency graphs.
"""

import json
import logging
from pathlib import Path
from typing import Any, Literal

import yaml

from t4t.parser.shared.constants import OUTPUT_FILES
from t4t.parser.shared.exceptions import OutputGenerationError
from t4t.parser.shared.types import DependencyGraph, DimensionalGraph, ParsedFunction, ParsedModel

from .ots.transformer import OTSTransformer
from .test_library_exporter import TestLibraryExporter

# Configure logging
logger = logging.getLogger(__name__)


class JSONExporter:
    """Handles JSON export of parsed models and dependency graphs."""

    def __init__(
        self,
        output_folder: Path,
        project_config: dict[str, Any] | None = None,
        project_folder: Path | None = None,
    ):
        """
        Initialize the JSON exporter.

        Args:
            output_folder: Path to the output folder
            project_config: Optional project configuration for OTS transformer
            project_folder: Optional project folder path for test library export
        """
        self.output_folder = output_folder
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.project_config = project_config or {}
        self.project_folder = project_folder
        self.transformer = OTSTransformer(self.project_config) if self.project_config else None

    def export_parsed_models(
        self, parsed_models: dict[str, ParsedModel], output_file: str | None = None
    ) -> Path:
        """
        Export parsed models to JSON file.

        Args:
            parsed_models: Parsed models to export
            output_file: Optional custom output file path

        Returns:
            Path to the exported file

        Raises:
            OutputGenerationError: If export fails
        """
        try:
            if output_file is None:
                output_file = self.output_folder / OUTPUT_FILES["parsed_models"]
            else:
                output_file = Path(output_file)

            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(parsed_models, f, indent=2, ensure_ascii=False)

            print(f"Parsed models saved to {output_file}")
            print(f"Found {len(parsed_models)} models")

            return output_file

        except Exception as e:
            raise OutputGenerationError(f"Failed to export parsed models: {e}") from e

    def export_dependency_graph(
        self, graph: DependencyGraph, output_file: str | None = None
    ) -> Path:
        """
        Export dependency graph to JSON file.

        Args:
            graph: Dependency graph to export
            output_file: Optional custom output file path

        Returns:
            Path to the exported file

        Raises:
            OutputGenerationError: If export fails
        """
        try:
            if output_file is None:
                output_file = self.output_folder / OUTPUT_FILES["dependency_graph"]
            else:
                output_file = Path(output_file)

            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(graph, f, indent=2, ensure_ascii=False)

            logger.debug(f"Dependency graph saved to {output_file}")
            logger.debug(f"Found {len(graph['nodes'])} tables")
            logger.debug(f"Execution order: {' -> '.join(graph['execution_order'])}")
            if graph["cycles"]:
                print(f"Warning: Found {len(graph['cycles'])} circular dependencies!")
                for cycle in graph["cycles"]:
                    print(f"  Cycle: {' -> '.join(cycle)}")

            return output_file

        except Exception as e:
            raise OutputGenerationError(f"Failed to export dependency graph: {e}") from e

    def export_dimensional_graph(
        self, graph: DimensionalGraph, output_file: str | None = None
    ) -> Path:
        """
        Export dimensional relationship graph to JSON file.

        Args:
            graph: Dimensional graph to export
            output_file: Optional custom output file path

        Returns:
            Path to the exported file

        Raises:
            OutputGenerationError: If export fails
        """
        try:
            if output_file is None:
                output_file = self.output_folder / OUTPUT_FILES["dimensional_graph"]
            else:
                output_file = Path(output_file)

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(graph, f, indent=2, ensure_ascii=False)

            logger.debug(f"Dimensional graph saved to {output_file}")
            return output_file
        except Exception as e:
            raise OutputGenerationError(f"Failed to export dimensional graph: {e}") from e

    def export_dimension_registry(
        self,
        registry: dict[str, str],
        output_file: str | Path | None = None,
    ) -> Path:
        """
        Export auto-built logical dimension → table mapping for troubleshooting.

        Args:
            registry: Mapping from logical keys (e.g. ``date``, ``date.month``) to qualified table names
            output_file: Optional path; default uses OUTPUT_FILES under output_folder

        Returns:
            Path to the written JSON file
        """
        try:
            if output_file is None:
                output_file = self.output_folder / OUTPUT_FILES["dimension_registry"]
            else:
                output_file = Path(output_file)

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, ensure_ascii=False, sort_keys=True)

            logger.debug("Dimension registry saved to %s", output_file)
            return output_file
        except Exception as e:
            raise OutputGenerationError(f"Failed to export dimension registry: {e}") from e

    def export_all(
        self,
        parsed_models: dict[str, ParsedModel],
        graph: DependencyGraph,
        *,
        dimension_registry: dict[str, str] | None = None,
    ) -> dict[str, Path]:
        """
        Export both parsed models and dependency graph.

        Args:
            parsed_models: Parsed models to export
            graph: Dependency graph to export
            dimension_registry: Optional logical → table map (from parsed dimension models)

        Returns:
            Dict mapping export type to file path

        Raises:
            OutputGenerationError: If export fails
        """
        try:
            results = {}

            # Export parsed models
            results["parsed_models"] = self.export_parsed_models(parsed_models)

            # Export dependency graph
            results["dependency_graph"] = self.export_dependency_graph(graph)

            if dimension_registry is not None:
                results["dimension_registry"] = self.export_dimension_registry(dimension_registry)

            return results

        except Exception as e:
            raise OutputGenerationError(f"Failed to export all data: {e}") from e

    def export_ots_modules(
        self,
        parsed_models: dict[str, ParsedModel],
        parsed_functions: dict[str, ParsedFunction] | None = None,
        test_library_path: Path | None = None,
        format: Literal["json", "yaml"] = "json",
    ) -> dict[str, Path]:
        """
        Export parsed models and functions as OTS Modules.

        One file per schema module will be created.

        Args:
            parsed_models: Parsed models to export
            parsed_functions: Optional parsed functions to export
            test_library_path: Optional path to test library file
            format: Output format ("json" or "yaml")

        Returns:
            Dictionary mapping module names to output file paths

        Raises:
            OutputGenerationError: If export fails
        """
        if not self.transformer:
            raise OutputGenerationError(
                "OTS transformer not initialized. Provide project_config when creating JSONExporter."
            )

        try:
            logger.info("Transforming models and functions to OTS Modules")
            modules = self.transformer.transform_to_ots_modules(
                parsed_models,
                parsed_functions=parsed_functions,
                test_library_path=test_library_path,
            )

            results = {}
            for module_name, module_data in modules.items():
                # Create filename with double underscore between database and schema
                # e.g., "t_project.my_schema" -> "t_project__my_schema.ots.json" or ".ots.yaml"
                if format == "yaml":
                    filename = f"{module_name.replace('.', '__')}.ots.yaml"
                else:
                    filename = f"{module_name.replace('.', '__')}.ots.json"
                output_file = self.output_folder / filename

                # Ensure output directory exists
                output_file.parent.mkdir(parents=True, exist_ok=True)

                # Write module to file in the specified format
                with open(output_file, "w", encoding="utf-8") as f:
                    if format == "yaml":
                        yaml.dump(
                            module_data,
                            f,
                            default_flow_style=False,
                            sort_keys=False,
                            allow_unicode=True,
                        )
                    else:
                        json.dump(module_data, f, indent=2, ensure_ascii=False)

                results[module_name] = output_file
                logger.info(
                    f"Exported OTS module '{module_name}' to {output_file} ({format.upper()})"
                )
                logger.debug(
                    f"OTS module '{module_name}' saved to {output_file} ({format.upper()})"
                )

            logger.debug(f"Exported {len(results)} OTS module(s) ({format.upper()})")

            return results

        except Exception as e:
            raise OutputGenerationError(f"Failed to export OTS modules: {e}") from e

    def export_test_library(self, project_name: str) -> Path | None:
        """
        Export discovered SQL tests to OTS test library format.

        Args:
            project_name: Project name (for filename generation)

        Returns:
            Path to the exported test library file, or None if no tests found

        Raises:
            OutputGenerationError: If export fails
        """
        if not self.project_folder:
            logger.debug("No project folder provided, skipping test library export")
            return None

        try:
            exporter = TestLibraryExporter(self.project_folder, project_name)
            return exporter.export_test_library(self.output_folder, format="json")
        except Exception as e:
            logger.warning(f"Failed to export test library: {e}")
            return None
