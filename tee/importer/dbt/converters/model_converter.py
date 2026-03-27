"""
Model converter for dbt models.

Converts dbt SQL models to t4t format, handling Jinja conversion, metadata, and file generation.
"""

import logging
from pathlib import Path
from typing import Any

from tee.importer.common.path_utils import (
    ensure_directory_exists,
    extract_schema_from_path,
    get_target_file_path,
)
from tee.importer.dbt.constants import (
    DEFAULT_SCHEMA,
    MODELS_DIR,
    PYTHON_EXTENSION,
    SQL_EXTENSION,
    YAML_ALT_EXTENSION,
    YAML_EXTENSION,
)

logger = logging.getLogger(__name__)


class ModelConverter:
    """Converts dbt models to t4t format."""

    def __init__(
        self,
        target_path: Path,
        dbt_project: dict[str, Any],
        preserve_filenames: bool = False,
        verbose: bool = False,
        keep_jinja: bool = False,
        default_schema: str = DEFAULT_SCHEMA,
    ) -> None:
        """
        Initialize model converter.

        Args:
            target_path: Path where t4t project will be created
            dbt_project: Parsed dbt project configuration
            preserve_filenames: Keep original file names instead of using final table names
            verbose: Enable verbose logging
            keep_jinja: Keep Jinja2 templates (only converts ref/source)
            default_schema: Default schema name for models (default: DEFAULT_SCHEMA)
        """
        self.target_path = Path(target_path).resolve()
        self.dbt_project = dbt_project
        self.preserve_filenames = preserve_filenames
        self.verbose = verbose
        self.keep_jinja = keep_jinja
        self.default_schema = default_schema

        # Will be populated during conversion
        self.model_name_map: dict[str, str] = {}  # dbt model name -> final table name
        self.conversion_log: list[dict[str, Any]] = []

        # Schema resolver (will be initialized with profile schema if available)
        self.schema_resolver: Any | None = None

        # Cloned packages for Jinja2 rendering (set by importer)
        self.cloned_packages: dict[str, Path] = {}
        # Source path for loading macros (set by importer)
        self.source_path: Path | None = None

    def convert_models(
        self,
        model_files: dict[str, Path],
        schema_metadata: dict[str, Any],
        source_map: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Convert all dbt models to t4t format.

        Args:
            model_files: Dictionary mapping relative paths to SQL model files
            schema_metadata: Parsed schema metadata from schema.yml files
            source_map: Mapping of source names to schema.table format

        Returns:
            Dictionary with conversion statistics and logs
        """
        # First pass: Build model_name_map by determining all table names
        self._build_model_name_map(model_files, schema_metadata)

        # Second pass: Convert models with complete model_name_map
        return self._convert_all_models(model_files, schema_metadata, source_map)

    def _build_model_name_map(
        self, model_files: dict[str, Path], schema_metadata: dict[str, Any]
    ) -> None:
        """
        Build mapping of dbt model names to final table names.

        Args:
            model_files: Dictionary mapping relative paths to SQL model files
            schema_metadata: Parsed schema metadata from schema.yml files
        """
        from tee.importer.dbt.parsers import ConfigExtractor

        config_extractor = ConfigExtractor(verbose=self.verbose)

        for rel_path, sql_file in model_files.items():
            try:
                dbt_model_name = self._extract_model_name(sql_file, rel_path)
                model_schema_metadata = schema_metadata.get(dbt_model_name)

                # Extract config block from model file
                sql_content = sql_file.read_text(encoding="utf-8")
                model_config = config_extractor.extract_config(sql_content)

                final_table_name = self._determine_table_name(
                    dbt_model_name, model_schema_metadata, sql_file, model_config
                )
                self.model_name_map[dbt_model_name] = final_table_name
            except FileNotFoundError:
                # File doesn't exist - will be caught in conversion phase
                dbt_model_name = self._extract_model_name(sql_file, rel_path)
                # Use fallback table name without config
                model_schema_metadata = schema_metadata.get(dbt_model_name)
                final_table_name = self._determine_table_name(
                    dbt_model_name, model_schema_metadata, sql_file, None
                )
                self.model_name_map[dbt_model_name] = final_table_name

    def _convert_all_models(
        self,
        model_files: dict[str, Path],
        schema_metadata: dict[str, Any],
        source_map: dict[str, dict[str, str]] | None,
    ) -> dict[str, Any]:
        """
        Convert all models using the complete model_name_map.

        Args:
            model_files: Dictionary mapping relative paths to SQL model files
            schema_metadata: Parsed schema metadata from schema.yml files
            source_map: Mapping of source names to schema.table format

        Returns:
            Dictionary with conversion statistics and logs
        """
        from tee.importer.dbt.converters import JinjaConverter
        from tee.importer.dbt.renderers import JinjaRenderer

        # Check if we should use Jinja2 rendering (when packages are present or keep_jinja is True)
        use_jinja2_rendering = (
            self.keep_jinja or bool(self.cloned_packages) or self._has_package_macros()
        )

        if use_jinja2_rendering and self.source_path:
            # Use Jinja2 renderer for full macro support
            jinja_renderer = JinjaRenderer(
                project_path=self.source_path,
                macro_paths=self.dbt_project.get("macro-paths"),
                package_paths=self.cloned_packages,
                model_name_map=self.model_name_map,
                source_map=source_map or {},
                variables=self.dbt_project.get("vars", {}),
                verbose=self.verbose,
            )
            # Create a wrapper that uses Jinja2 renderer
            jinja_converter = JinjaConverter(
                dbt_project=self.dbt_project,
                model_name_map=self.model_name_map,
                source_map=source_map or {},
                verbose=self.verbose,
                keep_jinja=self.keep_jinja,
                jinja_renderer=jinja_renderer,
            )
        else:
            # Use regular converter
            jinja_converter = JinjaConverter(
                dbt_project=self.dbt_project,
                model_name_map=self.model_name_map,
                source_map=source_map or {},
                verbose=self.verbose,
                keep_jinja=self.keep_jinja,
            )

        converted_count = 0
        python_model_count = 0
        error_count = 0

        for rel_path, sql_file in model_files.items():
            try:
                result = self._convert_single_model(
                    sql_file, rel_path, schema_metadata, jinja_converter
                )
                if result["is_python_model"]:
                    python_model_count += 1
                else:
                    converted_count += 1
            except (ValueError, KeyError, FileNotFoundError) as e:
                error_count += 1
                model_name = self._extract_model_name(sql_file, rel_path)
                error_msg = f"Error converting model {rel_path}: {e}"
                logger.error(error_msg)
                self.conversion_log.append(
                    {
                        "model": model_name,
                        "status": "error",
                        "error": str(e),
                    }
                )
            except Exception as e:
                error_count += 1
                model_name = self._extract_model_name(sql_file, rel_path)
                error_msg = f"Unexpected error converting model {rel_path}: {e}"
                logger.exception(error_msg)
                self.conversion_log.append(
                    {
                        "model": model_name,
                        "status": "error",
                        "error": f"Unexpected error: {str(e)}",
                    }
                )

        return {
            "converted": converted_count,
            "python_models": python_model_count,
            "errors": error_count,
            "total": len(model_files),
            "conversion_log": self.conversion_log,
        }

    def _convert_single_model(
        self,
        sql_file: Path,
        rel_path: str,
        schema_metadata: dict[str, Any],
        jinja_converter: Any,
    ) -> dict[str, Any]:
        """
        Convert a single dbt model to t4t format.

        Args:
            sql_file: Path to the SQL model file
            rel_path: Relative path from dbt project root
            schema_metadata: Parsed schema metadata from schema.yml files
            jinja_converter: JinjaConverter instance

        Returns:
            Dictionary with conversion result
        """
        from tee.importer.dbt.converters import MetadataConverter, PythonModelGenerator

        metadata_converter = MetadataConverter(verbose=self.verbose)

        # Extract model name from file path
        dbt_model_name = self._extract_model_name(sql_file, rel_path)

        # Read SQL content
        sql_content = sql_file.read_text(encoding="utf-8")

        # Extract config block from model file ({{ config(...) }})
        from tee.importer.dbt.parsers import ConfigExtractor

        config_extractor = ConfigExtractor(verbose=self.verbose)
        model_config = config_extractor.extract_config(sql_content)

        # Convert Jinja (now with complete model_name_map)
        jinja_result = jinja_converter.convert(sql_content, dbt_model_name)

        # Get metadata for this model - look in same folder as model file
        model_schema_metadata = self._get_model_metadata_from_folder(
            sql_file, dbt_model_name, schema_metadata
        )

        # Extract tags from dbt_project.yml (most specific match)
        project_tags = None
        if self.schema_resolver:
            project_tags = self.schema_resolver.extract_tags_from_project_config(
                dbt_model_name, sql_file
            )

        # Convert metadata
        t4t_metadata = metadata_converter.convert_model_metadata(
            schema_metadata=model_schema_metadata,
            model_config=model_config if model_config else None,
            project_tags=project_tags,
        )

        # Log if no description found
        if not t4t_metadata.get("description"):
            logger.warning(
                f"No description found for model {dbt_model_name} "
                f"(checked schema.yml files in {sql_file.parent})"
            )

        # Get final table name (already determined in first pass)
        final_table_name = self.model_name_map[dbt_model_name]

        # Write model files
        if jinja_result["is_python_model"]:
            # Generate Python model
            generator = PythonModelGenerator(verbose=self.verbose)
            # Use SQL with refs/sources already converted
            sql_for_python = jinja_result.get("sql_with_refs_converted", sql_content)
            python_code = generator.generate(
                sql_content=sql_for_python,
                model_name=dbt_model_name,
                table_name=final_table_name,
                metadata=t4t_metadata,
                variables=jinja_result.get("variables", []),
                conversion_warnings=jinja_result["conversion_warnings"],
            )

            # Write Python model file
            self._write_python_model(final_table_name, python_code, sql_file, rel_path)

            self.conversion_log.append(
                {
                    "model": dbt_model_name,
                    "status": "python_model",
                    "table_name": final_table_name,
                    "warnings": jinja_result["conversion_warnings"],
                }
            )
            return {"is_python_model": True}
        else:
            # Write SQL file
            self._write_sql_model(final_table_name, jinja_result["sql"], sql_file, rel_path)

            # Always write metadata file (even if empty, will include table_name and TODO)
            self._write_metadata_file(final_table_name, t4t_metadata or {}, rel_path)

            self.conversion_log.append(
                {
                    "model": dbt_model_name,
                    "status": "converted",
                    "table_name": final_table_name,
                    "warnings": jinja_result["conversion_warnings"],
                }
            )
            return {"is_python_model": False}

    def _extract_model_name(self, sql_file: Path, _rel_path: str) -> str:
        """Extract model name from file path."""
        # Model name is the file name without extension
        return sql_file.stem

    def _determine_table_name(
        self,
        dbt_model_name: str,
        schema_metadata: dict[str, Any] | None,
        sql_file: Path,
        model_config: dict[str, Any] | None = None,
    ) -> str:
        """
        Determine the final table name for a model.

        Args:
            dbt_model_name: Original dbt model name
            schema_metadata: Metadata from schema.yml
            sql_file: Path to the SQL file
            model_config: Config block from model file ({{ config(...) }})

        Returns:
            Final table name (schema.table format)
        """
        # Check for alias in model config (highest priority), then metadata
        if model_config and "alias" in model_config:
            table_name = model_config["alias"]
        elif schema_metadata and "alias" in schema_metadata:
            table_name = schema_metadata["alias"]
        else:
            table_name = dbt_model_name

        # Determine schema using schema resolver (follows dbt's priority)
        # Priority: model config > schema.yml > dbt_project.yml > profile/default
        if self.schema_resolver:
            schema = self.schema_resolver.resolve_schema(
                dbt_model_name, sql_file, schema_metadata, model_config
            )
        else:
            # Fallback if resolver not initialized
            schema = extract_schema_from_path(sql_file, MODELS_DIR) or self.default_schema

        return f"{schema}.{table_name}"

    def _write_sql_model(
        self, table_name: str, sql_content: str, _original_file: Path, rel_path: str
    ) -> None:
        """
        Write converted SQL model to target directory.

        Args:
            table_name: Final table name (schema.table)
            sql_content: Converted SQL content
            _original_file: Original SQL file path (reserved)
            rel_path: Relative path from dbt project root
        """
        target_file = get_target_file_path(
            self.target_path, table_name, rel_path, SQL_EXTENSION, self.preserve_filenames
        )

        # Create directory if needed
        ensure_directory_exists(target_file)

        # Write SQL file
        target_file.write_text(sql_content, encoding="utf-8")

        if self.verbose:
            logger.info(f"Wrote SQL model: {target_file}")

    def _write_metadata_file(
        self, table_name: str, metadata: dict[str, Any], rel_path: str
    ) -> None:
        """
        Write Python metadata file for a model.

        Args:
            table_name: Final table name (schema.table)
            metadata: t4t metadata dictionary
            rel_path: Relative path from dbt project root (for determining target path)
        """
        from tee.importer.dbt.generators import write_metadata_file

        target_file = get_target_file_path(
            self.target_path, table_name, rel_path, PYTHON_EXTENSION, self.preserve_filenames
        )

        # Create directory if needed
        ensure_directory_exists(target_file)

        # Write metadata file (include table_name in metadata)
        write_metadata_file(target_file, metadata, table_name=table_name)

        if self.verbose:
            logger.info(f"Wrote metadata file: {target_file}")

    def _write_python_model(
        self, table_name: str, python_code: str, _original_file: Path, rel_path: str
    ) -> None:
        """
        Write Python model file to target directory.

        Args:
            table_name: Final table name (schema.table)
            python_code: Generated Python code
            _original_file: Original SQL file path (reserved)
            rel_path: Relative path from dbt project root
        """
        target_file = get_target_file_path(
            self.target_path, table_name, rel_path, PYTHON_EXTENSION, self.preserve_filenames
        )

        # Create directory if needed
        ensure_directory_exists(target_file)

        # Write Python file with newline at end
        if not python_code.endswith("\n"):
            python_code += "\n"
        target_file.write_text(python_code, encoding="utf-8")

        if self.verbose:
            logger.info(f"Wrote Python model: {target_file}")

    def _get_model_metadata_from_folder(
        self,
        sql_file: Path,
        dbt_model_name: str,
        all_schema_metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Get metadata for a model from schema.yml files in the same folder.

        Args:
            sql_file: Path to the SQL model file
            dbt_model_name: Name of the dbt model
            all_schema_metadata: All parsed schema metadata

        Returns:
            Model metadata from schema.yml in the same folder, or None
        """
        # First try direct lookup
        if dbt_model_name in all_schema_metadata:
            return all_schema_metadata[dbt_model_name]

        # Look for schema.yml files in the same folder as the model
        model_folder = sql_file.parent
        schema_files = list(model_folder.glob(f"*{YAML_EXTENSION}")) + list(
            model_folder.glob(f"*{YAML_ALT_EXTENSION}")
        )

        if schema_files:
            # Parse schema files in the same folder
            from tee.importer.dbt.parsers import SchemaParser

            parser = SchemaParser(verbose=self.verbose)
            for schema_file in schema_files:
                models = parser.parse_schema_file(schema_file)
                if dbt_model_name in models:
                    return models[dbt_model_name]

        return None

    def _has_package_macros(self) -> bool:
        """Check if any cloned packages have macros."""
        if not self.cloned_packages:
            return False
        from tee.importer.dbt.parsers import MacroParser

        macro_parser = MacroParser(verbose=self.verbose)
        for pkg_path in self.cloned_packages.values():
            macros_dir = pkg_path / "macros"
            if macros_dir.exists():
                macro_files = macro_parser.discover_macros(pkg_path, ["macros"])
                if macro_files:
                    return True
        return False
