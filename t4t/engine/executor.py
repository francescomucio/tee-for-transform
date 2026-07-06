"""
Enhanced Model Executor with pluggable database adapters.

This module provides the high-level executor that uses the new adapter system
for database-agnostic SQL model execution.
"""

import logging
from pathlib import Path
from typing import Any

from t4t.adapters import AdapterConfig

from .config import load_database_config
from .execution_engine import ExecutionEngine
from .seeds import SeedDiscovery, SeedLoader


class ModelExecutor:
    """Enhanced executor that uses the new adapter system for database-agnostic execution."""

    def __init__(
        self,
        project_folder: str,
        config: AdapterConfig | dict[str, Any] | None = None,
        config_name: str = "default",
        env_name: str | None = None,
    ) -> None:
        """
        Initialize the ModelExecutor.

        Args:
            project_folder: Path to the project folder containing SQL models
            config: Database adapter configuration (AdapterConfig or dict, if None, loads from config files)
            config_name: Configuration name to load (if config is None)
            env_name: Environment name for scoping state
        """
        self.project_folder = project_folder
        self.env_name = env_name

        # Handle configuration
        if config is None:
            self.config = load_database_config(config_name, project_folder)
        elif isinstance(config, dict):
            # Convert dict to AdapterConfig, handling adapter-specific fields
            from pathlib import Path

            from ..adapters.base import AdapterConfig

            # Resolve relative paths relative to project folder
            if "path" in config and config["path"] and not Path(config["path"]).is_absolute():
                config["path"] = str(Path(project_folder) / config["path"])

            # Handle adapter-specific fields by moving them to 'extra'
            extra_fields = {}
            adapter_specific_fields = ["account"]  # Add more as needed

            for field in adapter_specific_fields:
                if field in config:
                    extra_fields[field] = config.pop(field)

            # Add existing extra fields
            if "extra" in config and config["extra"]:
                extra_fields.update(config["extra"])

            # Set extra field if we have any
            if extra_fields:
                config["extra"] = extra_fields

            # Map source_sql_dialect to source_dialect (source_sql_dialect is the preferred name in project.toml)
            if "source_sql_dialect" in config and "source_dialect" not in config:
                config["source_dialect"] = config.pop("source_sql_dialect")

            self.config = AdapterConfig(**config)
        else:
            self.config = config

        self.execution_engine = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def execute_models(
        self,
        parser: Any,
        variables: dict[str, Any] | None = None,
        parsed_models: dict[str, Any] | None = None,
        execution_order: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the parsed SQL models using the enhanced execution engine.

        Args:
            parser: Parser instance that has collected models and execution order
            variables: Optional dictionary of variables to inject into Python model functions
            parsed_models: Optional pre-filtered models dict (overrides parser.collect_models())
            execution_order: Optional pre-filtered execution order (overrides parser.get_execution_order())

        Returns:
            Dictionary containing execution results
        """
        self.logger.info("Starting model execution with enhanced adapter system")

        # Create execution engine
        self.execution_engine = ExecutionEngine(
            self.config, project_folder=self.project_folder, variables=variables, env_name=self.env_name
        )

        try:
            # Connect to database
            self.execution_engine.connect()
            self.logger.info("Connected to database successfully")

            # Get parsed models and execution order from parser (or use provided filtered versions)
            if parsed_models is None:
                parsed_models = parser.collect_models()
            if execution_order is None:
                execution_order = parser.get_execution_order()

            # Evaluate Python models before SQL execution
            # This ensures all Python models have their SQLGlot expressions ready
            parsed_models = parser.orchestrator.evaluate_python_models(parsed_models, variables)

            # Get parsed functions and execute them before models
            # Functions must be created before models that depend on them
            parsed_functions = parser.orchestrator.discover_and_parse_functions()
            function_results = {}
            if parsed_functions:
                self.logger.info(f"Executing {len(parsed_functions)} functions before models")
                function_results = self.execution_engine.execute_functions(
                    parsed_functions, execution_order
                )
                if function_results.get("failed_functions"):
                    self.logger.warning(
                        f"Some functions failed: {len(function_results['failed_functions'])} failed"
                    )
                else:
                    self.logger.info(
                        f"Successfully executed {len(function_results.get('executed_functions', []))} functions"
                    )

            # Filter out functions from execution order before executing models
            # Functions are already executed above, so we only need models here
            model_execution_order = [
                name
                for name in execution_order
                if name not in (parsed_functions or {}) and not name.startswith("test:")
            ]

            self.logger.info(f"Executing {len(model_execution_order)} models in dependency order")
            self.logger.debug(f"Execution order: {' -> '.join(model_execution_order)}")

            # Log database and dialect information (debug level for details)
            db_info = self.execution_engine.get_database_info()
            self.logger.debug(f"Using adapter: {db_info['adapter_type']}")
            self.logger.debug(f"Database type: {db_info['database_type']}")
            if db_info.get("source_dialect") and db_info.get("target_dialect"):
                self.logger.debug(
                    f"SQL dialect conversion: {db_info['source_dialect']} -> {db_info['target_dialect']}"
                )

            # Execute all models (excluding functions which were already executed)
            results = self.execution_engine.execute_models(parsed_models, model_execution_order)

            # Merge function results into main results
            if function_results:
                results["executed_functions"] = function_results.get("executed_functions", [])
                results["failed_functions"] = function_results.get("failed_functions", [])
                if "execution_log" not in results:
                    results["execution_log"] = []
                results["execution_log"].extend(function_results.get("execution_log", []))

            # Update Python parser's cached models with resolved SQL from execution
            # This ensures the resolved_sql is saved back to the Python parser
            parser.orchestrator.update_python_models_with_resolved_sql(parsed_models)

            # Update the main parser's cached models with resolved SQL from execution
            # This ensures the resolved_sql is saved back to the main parser for JSON output
            parser.update_parsed_models(parsed_models)

            # Log results
            self.logger.info(f"Successfully executed: {len(results['executed_tables'])} tables")
            self.logger.info(f"Failed: {len(results['failed_tables'])} tables")
            if results.get("executed_functions"):
                self.logger.info(
                    f"Successfully executed: {len(results['executed_functions'])} functions"
                )
            if results.get("failed_functions"):
                self.logger.info(f"Failed: {len(results['failed_functions'])} functions")
            if results.get("warnings"):
                self.logger.info(f"Warnings: {len(results['warnings'])} warnings")

            # Log dialect conversion summary
            if results.get("dialect_conversions"):
                self.logger.info(
                    f"Performed {len(results['dialect_conversions'])} SQL dialect conversions"
                )

            if results["executed_tables"]:
                self.logger.info("Successfully executed tables:")
                for table in results["executed_tables"]:
                    table_info = results["table_info"].get(table, {})
                    row_count = table_info.get("row_count", 0)
                    execution_log = next(
                        (log for log in results["execution_log"] if log["table"] == table), {}
                    )
                    materialization = execution_log.get("materialization", "table")
                    self.logger.info(f"  - {table}: {row_count} rows ({materialization})")

            if results["failed_tables"]:
                self.logger.error("Failed tables:")
                for failure in results["failed_tables"]:
                    self.logger.error(f"  - {failure['table']}: {failure['error']}")

            return results

        except Exception as e:
            self.logger.error(f"Error during execution: {e}")
            raise
        finally:
            # Always disconnect
            if self.execution_engine:
                self.execution_engine.disconnect()
                self.logger.info("Disconnected from database")

    def get_database_info(self) -> dict[str, Any] | None:
        """Get database connection information."""
        if self.execution_engine:
            return self.execution_engine.get_database_info()
        return None

    def test_connection(self) -> bool:
        """
        Test the database connection.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            self.execution_engine = ExecutionEngine(self.config, project_folder=self.project_folder)
            self.execution_engine.connect()
            self.logger.info("Database connection test successful")
            return True
        except Exception as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False
        finally:
            if self.execution_engine:
                self.execution_engine.disconnect()

    def list_supported_materializations(self) -> list[str]:
        """Get list of supported materialization types for the current adapter."""
        try:
            self.execution_engine = ExecutionEngine(self.config, project_folder=self.project_folder)
            return [m.value for m in self.execution_engine.adapter.get_supported_materializations()]
        except Exception as e:
            self.logger.error(f"Could not get supported materializations: {e}")
            return []
        finally:
            if self.execution_engine:
                self.execution_engine.disconnect()

    def _load_seeds(self) -> None:
        """Load seed files from the seeds folder into database tables."""
        seeds_folder = Path(self.project_folder) / "seeds"

        # Discover seed files
        seed_discovery = SeedDiscovery(seeds_folder)
        seed_files = seed_discovery.discover_seed_files()

        if not seed_files:
            self.logger.debug("No seed files found")
            return

        self.logger.info(f"Found {len(seed_files)} seed file(s) to load")

        # Load seeds using the adapter
        seed_loader = SeedLoader(self.execution_engine.adapter)
        seed_results = seed_loader.load_all_seeds(seed_files)

        # Log results
        if seed_results["loaded_tables"]:
            self.logger.info(f"Successfully loaded {len(seed_results['loaded_tables'])} seed(s)")
            for table in seed_results["loaded_tables"]:
                self.logger.info(f"  - {table}")

        if seed_results["failed_tables"]:
            self.logger.warning(f"Failed to load {len(seed_results['failed_tables'])} seed(s)")
            for failure in seed_results["failed_tables"]:
                self.logger.warning(f"  - {failure['file']}: {failure['error']}")
