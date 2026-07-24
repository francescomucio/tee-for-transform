"""
t4t Compiler - Compiles t4t projects to OTS modules.

This module handles the compilation workflow:
1. Parse SQL/Python models
2. Load and validate imported OTS modules
3. Detect conflicts
4. Merge and convert to OTS format
5. Validate compiled modules
6. Export to output/ots_modules/
"""

import logging
from pathlib import Path
from typing import Any

from t4t.parser import ProjectParser
from t4t.parser.input import (
    OTSConverter,
    OTSConverterError,
    OTSModuleReader,
    OTSModuleReaderError,
    OTSValidationError,
    validate_ots_module_location,
)
from t4t.parser.shared.exceptions import ParserError

logger = logging.getLogger(__name__)


class CompilationError(Exception):
    """Exception raised when compilation fails."""

    pass


def compile_project(
    project_folder: str,
    connection_config: dict[str, Any],
    variables: dict[str, Any] | None = None,
    project_config: dict[str, Any] | None = None,
    format: str = "json",
) -> dict[str, Any]:
    """
    Compile a t4t project to OTS modules.

    This function:
    1. Parses SQL/Python models
    2. Loads and validates imported OTS modules
    3. Detects conflicts (duplicate transformation_id)
    4. Merges all models (SQL, Python, and imported OTS)
    5. Builds dependency graph and saves analysis files
    6. Converts to OTS format
    7. Validates compiled modules
    8. Exports to output/ots_modules/

    Args:
        project_folder: Path to the project folder
        connection_config: Database connection configuration
        variables: Optional variables for SQL substitution
        project_config: Optional project configuration
        format: Output format for OTS modules ("json" or "yaml")

    Returns:
        Dictionary with compilation results including:
        - parsed_models: Merged parsed models
        - dependency_graph: Built dependency graph
        - execution_order: Execution order list
        - ots_modules_count: Number of OTS modules created
        - exported_paths: Paths to exported OTS modules

    Raises:
        CompilationError: If compilation fails
    """
    project_path = Path(project_folder)
    models_folder = project_path / "models"
    tests_folder = project_path / "tests"
    output_folder = project_path / "output" / "ots_modules"

    try:
        logger.info("Starting project compilation to OTS modules")
        parser, parsed_models, parsed_functions = _parse_project_models_and_functions(
            project_folder, connection_config, variables, project_config
        )
        ots_files, imported_ots_models = _load_imported_ots_models(models_folder)

        _detect_transformation_conflicts(parsed_models, imported_ots_models)
        all_models = _merge_models(parsed_models, imported_ots_models)
        graph, execution_order = _build_dependency_artifacts(parser, all_models)

        _print_step("STEP 5: Building OTS modules")
        imported_ots_modules = _load_imported_ots_modules(ots_files)
        exported_paths, ots_modules_count = _build_validate_and_export_ots_modules(
            project_path=project_path,
            tests_folder=tests_folder,
            output_folder=output_folder,
            project_config=project_config,
            all_models=all_models,
            parsed_functions=parsed_functions,
            imported_ots_modules=imported_ots_modules,
            format=format,
        )
        logger.info(
            f"✅ Built and exported {ots_modules_count} OTS module(s)",
            extra={"cli_output": True},
        )

        return {
            "success": True,
            "parsed_models_count": len(parsed_models),
            "imported_ots_count": len(imported_ots_models),
            "total_transformations": len(all_models),
            "ots_modules_count": ots_modules_count,
            "exported_paths": exported_paths,
            "output_folder": str(output_folder),
            "dependency_graph": graph,
            "execution_order": execution_order,
            "parsed_models": all_models,
            "parsed_functions": parsed_functions,
        }

    except (CompilationError, ParserError):
        raise
    except Exception as e:
        raise CompilationError(f"Compilation failed: {e}") from e


def _print_step(title: str) -> None:
    marker = {"cli_output": True}
    logger.info("\n" + "=" * 50, extra=marker)
    logger.info(title, extra=marker)
    logger.info("=" * 50, extra=marker)


def _parse_project_models_and_functions(
    project_folder: str,
    connection_config: dict[str, Any],
    variables: dict[str, Any] | None,
    project_config: dict[str, Any] | None,
) -> tuple[ProjectParser, dict[str, Any], dict[str, Any]]:
    _print_step("STEP 1: Parsing SQL and Python models and functions")
    parser = ProjectParser(project_folder, connection_config, variables, project_config)
    parsed_models = parser.collect_models()
    logger.info(
        f"✅ Parsed {len(parsed_models)} models from SQL/Python files",
        extra={"cli_output": True},
    )

    parsed_functions = parser.orchestrator.discover_and_parse_functions()
    if parsed_functions:
        logger.info(f"✅ Parsed {len(parsed_functions)} functions", extra={"cli_output": True})
    else:
        logger.info("✅ No functions found", extra={"cli_output": True})

    return parser, parsed_models, parsed_functions


def _load_imported_ots_models(models_folder: Path) -> tuple[list[Path], dict[str, Any]]:
    _print_step("STEP 2: Loading imported OTS modules")

    from t4t.parser.processing import FileDiscovery

    ots_files = FileDiscovery(models_folder).discover_ots_modules()
    imported_ots_models: dict[str, Any] = {}

    if not ots_files:
        logger.info("No imported OTS modules found", extra={"cli_output": True})
        return ots_files, imported_ots_models

    logger.info(f"Found {len(ots_files)} imported OTS module(s)", extra={"cli_output": True})
    reader = OTSModuleReader()
    converter = OTSConverter()

    for ots_file in ots_files:
        try:
            validate_ots_module_location(ots_file, models_folder)
            module = reader.read_module(ots_file)
            module_models, module_functions = converter.convert_module(module)

            for transformation_id, parsed_model in module_models.items():
                if transformation_id in imported_ots_models:
                    raise CompilationError(
                        f"Duplicate transformation_id '{transformation_id}' found in imported OTS modules. "
                        f"Found in both {ots_file} and another imported module."
                    )
                imported_ots_models[transformation_id] = parsed_model

            if module_functions:
                logger.debug(
                    f"Loaded {len(module_functions)} functions from OTS module {ots_file.name} (not yet integrated)"
                )

            line = f"  ✅ Loaded {ots_file.name}: {len(module_models)} transformations"
            if module_functions:
                line += f" and {len(module_functions)} functions"
            logger.info(line, extra={"cli_output": True})
        except (OTSValidationError, OTSModuleReaderError, OTSConverterError) as e:
            raise CompilationError(f"Failed to load imported OTS module {ots_file}: {e}") from e
        except Exception as e:
            raise CompilationError(f"Unexpected error loading OTS module {ots_file}: {e}") from e

    return ots_files, imported_ots_models


def _detect_transformation_conflicts(
    parsed_models: dict[str, Any], imported_ots_models: dict[str, Any]
) -> None:
    _print_step("STEP 3: Detecting conflicts")

    conflicts = [
        transformation_id
        for transformation_id in parsed_models
        if transformation_id in imported_ots_models
    ]
    if conflicts:
        error_msg = (
            f"Found {len(conflicts)} conflict(s): duplicate transformation_id found in both "
            f"SQL/Python models and imported OTS modules:\n"
        )
        for conflict in conflicts:
            error_msg += f"  - {conflict}\n"
        raise CompilationError(error_msg)

    logger.info("✅ No conflicts detected", extra={"cli_output": True})


def _merge_models(
    parsed_models: dict[str, Any], imported_ots_models: dict[str, Any]
) -> dict[str, Any]:
    _print_step("STEP 4: Merging models")
    all_models = parsed_models.copy()
    all_models.update(imported_ots_models)

    logger.info(
        f"✅ Merged {len(parsed_models)} SQL/Python models with {len(imported_ots_models)} imported OTS transformations",
        extra={"cli_output": True},
    )
    logger.info(f"   Total: {len(all_models)} transformations", extra={"cli_output": True})
    return all_models


def _build_dependency_artifacts(
    parser: ProjectParser, all_models: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    parser.parsed_models = all_models
    graph = parser.build_dependency_graph()
    execution_order = parser.get_execution_order()

    parser.save_dependency_graph()
    parser.save_markdown_report()
    parser.save_to_json()

    logger.debug(f"Built dependency graph with {len(graph['nodes'])} nodes")
    logger.debug(f"Execution order: {' -> '.join(execution_order)}")
    return graph, execution_order


def _load_imported_ots_modules(ots_files: list[Path]) -> list[tuple[dict[str, Any], Path]]:
    imported_ots_modules: list[tuple[dict[str, Any], Path]] = []
    if not ots_files:
        return imported_ots_modules

    reader = OTSModuleReader()
    for ots_file in ots_files:
        try:
            module = reader.read_module(ots_file)
            imported_ots_modules.append((module, ots_file))
        except Exception:
            # Already validated above, but keep compilation robust.
            continue

    return imported_ots_modules


def _build_validate_and_export_ots_modules(
    project_path: Path,
    tests_folder: Path,
    output_folder: Path,
    project_config: dict[str, Any] | None,
    all_models: dict[str, Any],
    parsed_functions: dict[str, Any],
    imported_ots_modules: list[tuple[dict[str, Any], Path]],
    format: str,
) -> tuple[list[Path], int]:
    import json
    import tempfile

    from t4t.parser.output import JSONExporter, OTSTransformer

    transformer = OTSTransformer(project_config or {})
    test_library_path = _merge_test_libraries(
        project_path,
        tests_folder,
        output_folder,
        project_config,
        imported_ots_modules,
        format,
    )
    ots_modules = transformer.transform_to_ots_modules(
        all_models,
        parsed_functions=parsed_functions,
        test_library_path=test_library_path,
    )

    reader = OTSModuleReader()
    for module_name, module in ots_modules.items():
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".ots.json", delete=False) as tmp:
                json.dump(module, tmp, indent=2)
                tmp_path = Path(tmp.name)
            reader.read_module(tmp_path)
            tmp_path.unlink()
        except Exception as e:
            raise CompilationError(f"Validation failed for module {module_name}: {e}") from e

    output_folder.mkdir(parents=True, exist_ok=True)
    exporter = JSONExporter(output_folder, project_config, project_path)
    exported_paths = exporter.export_ots_modules(
        all_models,
        parsed_functions=parsed_functions,
        test_library_path=test_library_path,
        format=format,
    )

    return exported_paths, len(ots_modules)


def _merge_test_libraries(
    project_path: Path,
    _tests_folder: Path,
    output_folder: Path,
    project_config: dict[str, Any] | None,
    imported_ots_modules: list[tuple],
    format: str = "json",
) -> Path | None:
    """
    Merge test libraries from project and imported OTS modules.

    Args:
        project_path: Project root path
        tests_folder: Path to tests folder
        output_folder: Output folder for compiled test library
        project_config: Project configuration
        imported_ots_modules: List of tuples (module_dict, module_file_path) from imported OTS modules

    Returns:
        Path to merged test library file, or None if no tests found
    """
    import json

    from t4t.parser.output import TestLibraryExporter

    # Get project name from config or folder name
    # project.toml has "project_folder" not "name", so use that or fall back to folder name
    if project_config:
        project_name = (
            project_config.get("name") or project_config.get("project_folder") or project_path.name
        )
    else:
        project_name = project_path.name

    # Step 1: Export project's test library (or create empty structure)
    # This creates the base test library that will be merged with imported ones
    test_exporter = TestLibraryExporter(project_path, project_name)
    project_test_library_path = test_exporter.export_test_library(output_folder, format=format)
    # Note: This file will be overwritten by the merged version below

    # Load project's test library if it exists
    project_test_library = {}
    if project_test_library_path and project_test_library_path.exists():
        try:
            with open(project_test_library_path, encoding="utf-8") as f:
                # Try JSON first, then YAML
                try:
                    project_test_library = json.load(f)
                except json.JSONDecodeError:
                    # Try YAML
                    import yaml

                    f.seek(0)
                    project_test_library = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load project test library: {e}")
            project_test_library = {}

    # If no project test library was created, create empty structure
    if not project_test_library:
        project_test_library = {
            "ots_version": "0.2.1",  # Test libraries are part of OTS 0.2.1
            "test_library_version": "1.0",
            "description": f"Test library for {project_name} project",
        }

    # Step 2: Collect and load test libraries from imported OTS modules
    imported_test_libraries = []
    test_library_paths_found = set()

    for module, module_file in imported_ots_modules:
        test_library_path_str = module.get("test_library_path")
        if not test_library_path_str:
            continue

        # Resolve test library path relative to the OTS module file location
        module_dir = module_file.parent
        test_lib_path = module_dir / test_library_path_str

        # Also try relative to project root (in case path is absolute or relative to project)
        if not test_lib_path.exists():
            test_lib_path = project_path / test_library_path_str

        # Skip if we've already loaded this test library (avoid duplicates)
        test_lib_key = str(test_lib_path.resolve())
        if test_lib_key in test_library_paths_found:
            continue

        if test_lib_path.exists():
            try:
                with open(test_lib_path, encoding="utf-8") as f:
                    # Try JSON first, then YAML
                    try:
                        imported_lib = json.load(f)
                    except json.JSONDecodeError:
                        # Try YAML
                        import yaml

                        f.seek(0)
                        imported_lib = yaml.safe_load(f)

                    imported_test_libraries.append((imported_lib, test_lib_path))
                    test_library_paths_found.add(test_lib_key)
                    logger.info(f"Loaded test library from imported OTS module: {test_lib_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to load test library from {test_lib_path} (referenced by {module_file}): {e}"
                )
        else:
            logger.warning(
                f"Test library path '{test_library_path_str}' referenced by {module_file} not found at {test_lib_path}"
            )

    # Step 3: Merge test libraries
    merged_generic_tests = project_test_library.get("generic_tests", {}).copy()
    merged_singular_tests = project_test_library.get("singular_tests", {}).copy()
    conflicts = []

    for imported_lib, lib_path in imported_test_libraries:
        # Merge generic tests
        imported_generic = imported_lib.get("generic_tests", {})
        for test_name, test_def in imported_generic.items():
            if test_name in merged_generic_tests:
                conflicts.append(f"generic_tests.{test_name} (from {lib_path.name})")
                # Project test library takes precedence
                logger.warning(
                    f"Test conflict: generic test '{test_name}' already exists in project test library. "
                    f"Project version will be used (imported from {lib_path.name} will be ignored)."
                )
            else:
                merged_generic_tests[test_name] = test_def

        # Merge singular tests
        imported_singular = imported_lib.get("singular_tests", {})
        for test_name, test_def in imported_singular.items():
            if test_name in merged_singular_tests:
                conflicts.append(f"singular_tests.{test_name} (from {lib_path.name})")
                # Project test library takes precedence
                logger.warning(
                    f"Test conflict: singular test '{test_name}' already exists in project test library. "
                    f"Project version will be used (imported from {lib_path.name} will be ignored)."
                )
            else:
                merged_singular_tests[test_name] = test_def

    # Step 4: Build merged test library
    merged_test_library = {
        "ots_version": "0.2.1",  # Test libraries are part of OTS 0.2.1
        "test_library_version": project_test_library.get("test_library_version", "1.0"),
        "description": project_test_library.get(
            "description", f"Test library for {project_name} project"
        ),
    }

    if merged_generic_tests:
        merged_test_library["generic_tests"] = merged_generic_tests
    if merged_singular_tests:
        merged_test_library["singular_tests"] = merged_singular_tests

    # Step 5: Write merged test library
    if not merged_generic_tests and not merged_singular_tests:
        logger.info("No tests found in project or imported libraries")
        return None

    # Use appropriate extension based on format
    if format == "yaml":
        filename = f"{project_name}_test_library.ots.yaml"
    else:
        filename = f"{project_name}_test_library.ots.json"
    output_file = output_folder / filename
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        if format == "yaml":
            import yaml

            yaml.dump(
                merged_test_library,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        else:
            json.dump(merged_test_library, f, indent=2, ensure_ascii=False)

    logger.debug(f"Exported merged test library to {output_file}")
    if conflicts:
        logger.debug(f"{len(conflicts)} test conflict(s) resolved (project version used)")

    return output_file
