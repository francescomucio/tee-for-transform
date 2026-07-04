"""OTS module building and assembly."""

import logging
from pathlib import Path
from typing import Any

from t4t.parser.shared.types import ParsedFunction, ParsedModel
from t4t.typing.metadata import OTSModule, OTSTarget

from ..transformers.function_transformer import FunctionTransformer
from ..transformers.model_transformer import ModelTransformer

logger = logging.getLogger(__name__)


class ModuleBuilder:
    """Builds OTS modules from transformations and functions."""

    def __init__(self, project_config: dict[str, Any], database: str, sql_dialect: str):
        """
        Initialize the module builder.

        Args:
            project_config: Project configuration dictionary
            database: Database name
            sql_dialect: SQL dialect string
        """
        self.project_config = project_config
        self.database = database
        self.sql_dialect = sql_dialect

    def build_modules(
        self,
        models_by_schema: dict[str, list[tuple[str, ParsedModel]]],
        functions_by_schema: dict[str, list[tuple[str, ParsedFunction]]],
        test_library_path: Path | None,
        model_transformer: ModelTransformer,
        function_transformer: FunctionTransformer,
    ) -> dict[str, OTSModule]:
        """
        Build OTS modules for all schemas.

        Args:
            models_by_schema: Dictionary mapping schema to list of (model_id, model_data) tuples
            functions_by_schema: Dictionary mapping schema to list of (function_id, function_data) tuples
            test_library_path: Optional path to test library
            model_transformer: Model transformer instance
            function_transformer: Function transformer instance

        Returns:
            Dictionary mapping module_name to OTS Module
        """
        # Collect all schemas (from both models and functions)
        all_schemas = set(models_by_schema.keys()) | set(functions_by_schema.keys())

        modules = {}
        for schema in all_schemas:
            module_name = f"{self.database}.{schema}"
            models = models_by_schema.get(schema, [])
            functions = functions_by_schema.get(schema, [])
            logger.info(
                f"Creating OTS module: {module_name} with {len(models)} transformations and {len(functions)} functions"
            )
            module = self.build_module(
                module_name,
                schema,
                models,
                functions,
                test_library_path,
                model_transformer,
                function_transformer,
            )
            modules[module_name] = module

        return modules

    def build_module(
        self,
        module_name: str,
        schema: str,
        models: list[tuple[str, ParsedModel]],
        functions: list[tuple[str, ParsedFunction]],
        test_library_path: Path | None,
        model_transformer: ModelTransformer,
        function_transformer: FunctionTransformer,
    ) -> OTSModule:
        """
        Build a single OTS module.

        Args:
            module_name: Full module name (database.schema)
            schema: Schema name
            models: List of (model_id, model_data) tuples for this schema
            functions: List of (function_id, function_data) tuples for this schema
            test_library_path: Optional path to test library
            model_transformer: Model transformer instance
            function_transformer: Function transformer instance

        Returns:
            Complete OTS Module structure
        """
        # Extract transformations
        transformations = []
        for model_id, model_data in models:
            transformation = model_transformer.transform(model_id, model_data, schema)
            transformations.append(transformation)

        # Extract functions
        ots_functions = []
        for function_id, function_data in functions:
            ots_function = function_transformer.transform(function_id, function_data, schema)
            ots_functions.append(ots_function)

        # Build target configuration
        target: OTSTarget = {
            "database": self.database,
            "schema": schema,
            "sql_dialect": self.sql_dialect,
        }

        # Extract module-level tags from project config
        module_tags = []
        if "module" in self.project_config:
            module_config = self.project_config.get("module", {})
            if isinstance(module_config, dict):
                module_tags = module_config.get("tags", [])
        elif "tags" in self.project_config:
            root_tags = self.project_config.get("tags", [])
            if isinstance(root_tags, list):
                module_tags = root_tags

        # Ensure module_tags is a list
        if not isinstance(module_tags, list):
            module_tags = []

        # Always use the latest OTS version (0.2.2)
        # This ensures our exports are aligned with the latest standard
        ots_version = "0.2.2"

        # Build module
        module: OTSModule = {
            "ots_version": ots_version,
            "module_name": module_name,
            "module_description": f"Transformations for {schema} schema",
            "target": target,
            "transformations": transformations,
        }

        # Add functions if present (OTS 0.2.1)
        if ots_functions:
            module["functions"] = ots_functions

        # Add test_library_path if test library was exported
        if test_library_path:
            # Calculate relative path from output folder to test library
            # test_library_path is already in output folder, so use just the filename
            module["test_library_path"] = test_library_path.name

        # Add module-level tags if present
        if module_tags:
            module["tags"] = module_tags

        return module
