"""
dbt project importer implementation.
"""

import logging
import shutil
import tempfile
from pathlib import Path

from t4t.importer.dbt.constants import DEFAULT_SCHEMA
from t4t.importer.dbt.infrastructure import StructureConverter
from t4t.importer.dbt.parsers import DbtProjectParser

logger = logging.getLogger(__name__)


def import_dbt_project(
    source_path: Path,
    target_path: Path,
    output_format: str = "t4t",
    preserve_filenames: bool = False,
    validate_execution: bool = False,
    verbose: bool = False,
    keep_jinja: bool = False,
    default_schema: str = DEFAULT_SCHEMA,
    target_dialect: str | None = None,
    dry_run: bool = False,
    select_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> None:
    """
    Import a dbt project into t4t format.

    Args:
        source_path: Path to the dbt project directory
        target_path: Path where the t4t project will be created
        output_format: Output format - "t4t" or "ots"
        preserve_filenames: Keep original file names instead of using final table names
        validate_execution: Run execution validation (requires database connection)
        verbose: Enable verbose output
        keep_jinja: Keep Jinja2 templates in models (only converts ref/source).
                    Note: Requires Jinja2 support in t4t (see issue #04-jinja2-support)
        default_schema: Default schema name for models and functions (default: DEFAULT_SCHEMA)
        target_dialect: Target database dialect for SQL conversion (e.g., "postgresql", "snowflake", "duckdb").
                       If not specified, defaults to PostgreSQL syntax. Used for macro-to-UDF conversion.
        dry_run: If True, perform validation without creating files
        select_patterns: List of patterns to select models (e.g., ["my_model", "tag:nightly"])
        exclude_patterns: List of patterns to exclude models (e.g., ["deprecated", "tag:test"])
    """
    source_path = Path(source_path).resolve()
    target_path = Path(target_path).resolve()

    # Parse dbt project
    parser = DbtProjectParser(source_path, verbose=verbose)
    dbt_project = parser.parse()

    # In dry-run mode, create a temporary directory for validation
    if dry_run:
        # Create temporary directory for dry-run validation
        temp_dir = tempfile.mkdtemp(prefix="t4t_dry_run_")
        validation_target = Path(temp_dir)
        if verbose:
            logger.info(f"🔍 DRY RUN MODE: Using temporary directory {temp_dir}")
    else:
        validation_target = target_path

    # Create target directory structure (or temp for dry-run)
    converter = StructureConverter(
        target_path=validation_target,
        output_format=output_format,
        preserve_filenames=preserve_filenames,
        verbose=verbose,
    )
    converter.create_structure()

    # Phase 1.5: Clone packages if needed
    from t4t.importer.dbt.infrastructure import PackagesHandler

    packages_handler = PackagesHandler(verbose=verbose)
    packages_info = packages_handler.discover_packages(source_path)
    cloned_packages: dict[str, Path] = {}
    if packages_info.get("has_packages"):
        if verbose:
            logger.info("Cloning dbt packages...")
        cloned_packages = packages_handler.clone_packages(source_path, packages_info)
        if verbose:
            logger.info(f"Cloned {len(cloned_packages)} package(s)")

    # Phase 2: Model conversion and seeds
    from t4t.importer.dbt.converters import ModelConverter, SeedConverter
    from t4t.importer.dbt.parsers import ModelFileDiscovery, SchemaParser

    # Discover model files
    model_discovery = ModelFileDiscovery(source_path, dbt_project.get("model-paths"))
    model_files = model_discovery.discover_models()

    # Discover and parse schema files
    schema_files = model_discovery.discover_schema_files()
    schema_parser = SchemaParser(verbose=verbose)
    schema_metadata = schema_parser.parse_all_schema_files(schema_files)

    # Discover and parse source files
    from t4t.importer.dbt.parsers import SourceParser

    source_files = model_discovery.discover_source_files()
    source_parser = SourceParser(verbose=verbose)
    source_map = source_parser.parse_all_source_files(source_files)

    # Get profile schema for schema resolution (needed before model conversion)
    profile_schema = None
    try:
        from t4t.importer.dbt.parsers import ProfilesParser

        profiles_parser = ProfilesParser(verbose=verbose)
        profiles_path = profiles_parser.find_profiles_file(source_path)
        if profiles_path:
            profiles_data = profiles_parser.parse_profiles(profiles_path)
            profile_name = dbt_project.get("profile")
            if profile_name:
                profile_config = profiles_parser.get_profile_config(profile_name, profiles_data)
                if profile_config:
                    profile_schema = profile_config.get("schema")
    except Exception as e:
        if verbose:
            logger.debug(f"Could not load profile schema: {e}")

    # Initialize schema resolver (needed for both filtering and conversion)
    from t4t.importer.dbt.resolvers import SchemaResolver

    schema_resolver = SchemaResolver(
        dbt_project=dbt_project,
        profile_schema=profile_schema,
        default_schema=default_schema,
        verbose=verbose,
    )

    # Filter models based on select/exclude patterns (if provided)
    if model_files and (select_patterns or exclude_patterns):
        from t4t.importer.dbt.infrastructure import DbtModelSelector
        from t4t.importer.dbt.resolvers import extract_model_tags

        # Extract tags for all models
        model_tags_map = extract_model_tags(
            model_files=model_files,
            schema_metadata=schema_metadata,
            dbt_project=dbt_project,
            schema_resolver=schema_resolver,
            verbose=verbose,
        )

        # Filter models
        selector = DbtModelSelector(
            select_patterns=select_patterns,
            exclude_patterns=exclude_patterns,
            verbose=verbose,
        )
        model_files = selector.filter_models(model_files, model_tags_map)

        if verbose:
            logger.info(f"After filtering: {len(model_files)} models selected for import")

    # Convert models
    if model_files:
        model_converter = ModelConverter(
            target_path=validation_target,
            dbt_project=dbt_project,
            preserve_filenames=preserve_filenames,
            verbose=verbose,
            keep_jinja=keep_jinja,
            default_schema=default_schema,
        )
        model_converter.schema_resolver = schema_resolver
        # Pass cloned packages and source path to model converter for Jinja2 rendering
        model_converter.cloned_packages = cloned_packages
        model_converter.source_path = source_path
        conversion_results = model_converter.convert_models(
            model_files, schema_metadata, source_map
        )

        if verbose:
            logger.info(f"Converted {conversion_results['converted']} models")
            logger.info(f"Python models: {conversion_results['python_models']}")
            logger.info(f"Errors: {conversion_results['errors']}")

    # Convert seeds
    seed_converter = SeedConverter(
        source_path=source_path,
        target_path=validation_target,
        dbt_project=dbt_project,
        verbose=verbose,
    )
    seed_results = seed_converter.convert_seeds()

    if verbose:
        logger.info(f"Copied {seed_results['copied']} seed files")

    # Phase 3: Advanced features (macros, variables, reporting)
    from t4t.importer.dbt.converters import MacroConverter
    from t4t.importer.dbt.generators import ReportGenerator
    from t4t.importer.dbt.parsers import MacroParser
    from t4t.importer.dbt.resolvers import VariablesExtractor

    macro_results = None
    variables_info = None

    # Discover and convert macros
    macro_parser = MacroParser(verbose=verbose)
    macro_files = macro_parser.discover_macros(source_path, dbt_project.get("macro-paths"))
    if macro_files:
        all_macros = macro_parser.parse_all_macros(macro_files)
        if all_macros:
            macro_converter = MacroConverter(
                target_path=validation_target,
                target_dialect=target_dialect,
                default_schema=default_schema,
                verbose=verbose,
            )
            macro_results = macro_converter.convert_macros(all_macros)
            if verbose:
                logger.info(f"Converted {macro_results['converted']} macros to UDFs")
                logger.info(f"Unconvertible macros: {macro_results['unconvertible']}")

    # Extract variables
    if model_files:
        variables_extractor = VariablesExtractor(verbose=verbose)
        conversion_log = conversion_results.get("conversion_log", []) if model_files else []
        variables_info = variables_extractor.extract_variables(
            model_files, dbt_project, conversion_log
        )
        if verbose:
            logger.info(f"Extracted {len(variables_info.get('variables', {}))} variables")

    # Phase 4: Convert tests
    test_results = None
    from t4t.importer.dbt.converters import TestConverter
    from t4t.importer.dbt.parsers import TestFileDiscovery

    test_discovery = TestFileDiscovery(source_path=source_path, verbose=verbose)
    test_files = test_discovery.discover_test_files()

    if test_files:
        # Identify freshness tests
        # Note: Actual dbt freshness tests are in __sources.yml, not SQL files.
        # SQL files that check freshness are regular singular tests.
        # We only skip tests with very specific freshness-related filenames.
        freshness_tests = set()
        for rel_path, test_file in test_files.items():
            if test_discovery.is_source_freshness_test(test_file):
                freshness_tests.add(rel_path)
                if verbose:
                    logger.info(
                        f"Detected potential freshness test: {rel_path}. "
                        "Note: Actual dbt freshness tests are in __sources.yml files."
                    )

        # Convert tests
        test_converter = TestConverter(
            target_path=validation_target,
            model_name_map=model_converter.model_name_map if model_files else {},
            verbose=verbose,
        )
        test_results = test_converter.convert_all_tests(test_files, freshness_tests)
        if verbose:
            logger.info(
                f"Converted {test_results['converted']} test(s), "
                f"skipped {test_results['skipped']} freshness test(s)"
            )

    # Phase 5: Configuration and Project Setup
    from t4t.importer.dbt.generators import ProjectConfigGenerator
    from t4t.importer.dbt.parsers import ProfilesParser

    # Packages already discovered and cloned in Phase 1.5

    # Generate project.toml
    config_generator = ProjectConfigGenerator(verbose=verbose)
    profiles_parser = ProfilesParser(verbose=verbose)

    # Try to get connection config from profiles.yml (only if not dry-run)
    connection_config = None
    if not dry_run:
        connection_config = config_generator.generate_project_toml_from_profiles(
            target_path, dbt_project, profiles_parser
        )

        # Generate project.toml
        config_generator.generate_project_toml(
            target_path=target_path,
            dbt_project=dbt_project,
            connection_config=connection_config,
            packages_info=packages_info,
        )

    # Phase 6: Validation
    validation_result = None
    if model_files:
        from t4t.importer.dbt.infrastructure import ProjectValidator

        # Use validation_target (temp dir for dry-run, actual target otherwise)
        validator = ProjectValidator(
            target_path=validation_target,
            model_name_map=model_converter.model_name_map if model_files else {},
            verbose=verbose,
        )

        # Get connection config for execution validation if needed
        connection_config = None
        if validate_execution:
            try:
                from t4t.importer.dbt.generators import ProjectConfigGenerator
                from t4t.importer.dbt.parsers import ProfilesParser

                profiles_parser = ProfilesParser(verbose=verbose)
                profiles_path = profiles_parser.find_profiles_file(source_path)
                if profiles_path:
                    profiles_data = profiles_parser.parse_profiles(profiles_path)
                    profile_name = dbt_project.get("profile")
                    if profile_name:
                        profile_config = profiles_parser.get_profile_config(
                            profile_name, profiles_data
                        )
                        if profile_config:
                            # Convert to t4t connection format
                            connection_config = ProjectConfigGenerator._convert_connection_config(
                                profile_config
                            )
            except Exception as e:
                if verbose:
                    logger.debug(f"Could not load connection config for validation: {e}")

        validation_result = validator.validate_all(
            validate_execution=validate_execution,
            connection_config=connection_config,
        )

        if verbose:
            if validation_result.is_valid:
                logger.info("✅ Validation passed: No errors found")
            else:
                logger.warning(f"⚠️  Validation found {validation_result.error_count} errors")

    # Phase 7: OTS Format Support (if requested)
    ots_compilation_result = None
    if not dry_run and output_format == "ots":
        from t4t.compiler import CompilationError, compile_project

        if verbose:
            logger.info("Compiling imported project to OTS modules...")

        try:
            # Get project config for compilation
            project_config = None
            project_toml_path = target_path / "project.toml"
            if project_toml_path.exists():
                import tomllib

                with project_toml_path.open("rb") as f:
                    project_config = tomllib.load(f)

            # Compile to OTS modules
            ots_result = compile_project(
                project_folder=str(target_path),
                connection_config=connection_config
                or {"type": "duckdb", "path": f"data/{target_path.name}.duckdb"},
                variables=None,  # Could extract from dbt vars in future
                project_config=project_config,
                format="json",  # Default to JSON, could add option later
            )

            ots_compilation_result = {
                "success": True,
                "ots_modules_count": ots_result.get("ots_modules_count", 0),
                "parsed_models_count": ots_result.get("parsed_models_count", 0),
                "parsed_functions_count": len(ots_result.get("parsed_functions", {})),
                "output_folder": str(ots_result.get("output_folder", "")),
            }

            if verbose:
                logger.info(
                    f"✅ OTS compilation complete: {ots_compilation_result['ots_modules_count']} module(s) generated"
                )

        except CompilationError as e:
            ots_compilation_result = {
                "success": False,
                "error": str(e),
            }
            logger.warning(f"⚠️  OTS compilation failed: {e}")
            if verbose:
                import traceback

                logger.debug(traceback.format_exc())
        except Exception as e:
            ots_compilation_result = {
                "success": False,
                "error": str(e),
            }
            logger.warning(f"⚠️  OTS compilation failed with unexpected error: {e}")
            if verbose:
                import traceback

                logger.debug(traceback.format_exc())

    # Generate import reports (only if not dry-run)
    if not dry_run:
        report_generator = ReportGenerator(target_path=target_path, verbose=verbose)
        report_generator.generate_reports(
            conversion_results=conversion_results
            if model_files
            else {
                "total": 0,
                "converted": 0,
                "python_models": 0,
                "errors": 0,
                "conversion_log": [],
            },
            macro_results=macro_results,
            variables_info=variables_info,
            seed_results=seed_results,
            test_results=test_results,
            packages_info=packages_info,
            validation_result=validation_result.to_dict() if validation_result else None,
            ots_compilation_result=ots_compilation_result,
        )

        if verbose:
            logger.info(
                "Import completed. See IMPORT_REPORT.md and CONVERSION_LOG.json for details."
            )
            if (
                output_format == "ots"
                and ots_compilation_result
                and ots_compilation_result.get("success")
            ):
                logger.info(
                    f"OTS modules available in: {ots_compilation_result.get('output_folder', 'output/ots_modules/')}"
                )
    else:
        # Dry-run: Print validation summary and clean up temp directory
        if validation_result:
            if validation_result.is_valid:
                logger.info("✅ DRY RUN: Validation passed - No errors found")
            else:
                logger.warning(
                    f"⚠️  DRY RUN: Validation found {validation_result.error_count} errors"
                )
                if verbose:
                    # Print detailed errors
                    for error in validation_result.syntax_errors:
                        logger.warning(
                            f"  Syntax: {error.get('file', 'unknown')} - {error.get('error', 'unknown')}"
                        )
                    for error in validation_result.dependency_errors:
                        logger.warning(
                            f"  Dependency: {error.get('file', 'unknown')} - {error.get('error', 'unknown')}"
                        )
                    for error in validation_result.metadata_errors:
                        logger.warning(
                            f"  Metadata: {error.get('file', 'unknown')} - {error.get('error', 'unknown')}"
                        )

        # Clean up temporary directory
        if dry_run and validation_target.exists():
            shutil.rmtree(validation_target)
            if verbose:
                logger.info(f"Cleaned up temporary directory: {validation_target}")
