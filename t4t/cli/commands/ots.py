"""
OTS command implementations.
"""

from pathlib import Path

import typer

from t4t.cli.context import CommandContext
from t4t.parser import ProjectParser
from t4t.parser.input import OTSModuleReader, OTSModuleReaderError, load_ots_modules


def cmd_ots_run(
    ots_path: str,
    project_folder: str | None = None,
    vars: str | None = None,
    verbose: bool = False,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
) -> None:
    """
    Execute OTS modules.

    Args:
        ots_path: Path to OTS module file (.ots.json) or directory containing OTS modules
        project_folder: Optional project folder (for connection config and merging with existing models)
        vars: Optional variables for SQL substitution (JSON format)
        verbose: Enable verbose output
        select: Select models (can be used multiple times)
        exclude: Exclude models (can be used multiple times)
    """
    ots_path_obj = Path(ots_path)

    if not ots_path_obj.exists():
        typer.echo(f"❌ Error: OTS path not found: {ots_path}", err=True)
        raise typer.Exit(1)

    try:
        typer.echo(f"\n{'=' * 50}")
        typer.echo("t4t: EXECUTING OTS MODULES")
        typer.echo(f"{'=' * 50}")
        typer.echo(f"OTS path: {ots_path}")

        # Load OTS modules
        typer.echo("\nLoading OTS modules...")
        ots_parsed_models, ots_parsed_functions = load_ots_modules(ots_path_obj)
        loaded_msg = f"✅ Loaded {len(ots_parsed_models)} transformations"
        if ots_parsed_functions:
            loaded_msg += f" and {len(ots_parsed_functions)} functions from OTS modules"
        else:
            loaded_msg += " from OTS modules"
        typer.echo(loaded_msg)

        # Note: Functions from OTS modules are not yet integrated into execution
        # This will be handled in Phase 8 (Execution Engine Integration)
        if ots_parsed_functions:
            typer.echo(
                f"⚠️  Note: {len(ots_parsed_functions)} function(s) loaded but not yet executed (Phase 8)"
            )

        # Determine connection config and project folder
        if project_folder:
            ctx = CommandContext(
                project_folder=project_folder,
                vars=vars,
                verbose=verbose,
                select=select,
                exclude=exclude,
            )
            connection_config = ctx.config["connection"]
            project_path = ctx.project_path
            variables = ctx.vars
            select_patterns = ctx.select_patterns
            exclude_patterns = ctx.exclude_patterns

            typer.echo(f"\nMerging with project models from: {project_folder}")

            # Parse existing models
            parser = ProjectParser(
                str(project_path),
                connection_config,
                variables,
            )
            existing_models = parser.collect_models()
            typer.echo(f"Found {len(existing_models)} existing models in project")

            # Merge OTS models with existing models
            from t4t.parser.input import merge_ots_with_parsed_models

            all_models = merge_ots_with_parsed_models(existing_models, ots_parsed_models)
            typer.echo(f"Total models to execute: {len(all_models)}")

            # Inject merged models into parser
            parser.parsed_models = all_models

            # Build dependency graph with merged models
            typer.echo("\nBuilding dependency graph with merged models...")
            parser.build_dependency_graph()
            execution_order = parser.get_execution_order()
            typer.echo(f"Execution order: {' -> '.join(execution_order)}")

            # Apply selection filtering if specified
            if select_patterns or exclude_patterns:
                from t4t.cli.selection import ModelSelector

                selector = ModelSelector(
                    select_patterns=select_patterns, exclude_patterns=exclude_patterns
                )
                all_models, execution_order = selector.filter_models(all_models, execution_order)
                typer.echo(f"Filtered to {len(all_models)} models")

            # Execute models
            from t4t.engine import ModelExecutor

            model_executor = ModelExecutor(str(project_path), connection_config)
            results = model_executor.execute_models(
                parser=parser,
                variables=variables,
                parsed_models=all_models,
                execution_order=execution_order,
            )

            # Run tests
            from t4t.testing import TestExecutor

            test_executor = TestExecutor(model_executor.execution_engine)
            test_results = test_executor.run_tests(all_models, variables=variables)
            results["test_results"] = test_results

            # Disconnect
            model_executor.execution_engine.disconnect()

            # Print summary
            typer.echo("\n✅ Execution complete!")
            typer.echo(f"   Executed: {len(results['executed_tables'])} tables")
            if results.get("failed_tables"):
                typer.echo(f"   Failed: {len(results['failed_tables'])} tables")
            if results.get("test_results"):
                test_summary = results["test_results"]
                typer.echo(f"   Tests passed: {test_summary.get('passed', 0)}")
                typer.echo(f"   Tests failed: {test_summary.get('failed', 0)}")

        else:
            # Execute OTS modules standalone
            # We need connection config - try to infer from OTS module target
            if ots_path_obj.is_file():
                reader = OTSModuleReader()
                module = reader.read_module(ots_path_obj)
                target = module.get("target", {})

                # Create connection config from target
                sql_dialect = target.get("sql_dialect", "duckdb")
                connection_config = {
                    "type": sql_dialect,
                }
                # Add database-specific config if available
                if target.get("database"):
                    connection_config["database"] = target["database"]
                if target.get("schema"):
                    connection_config["schema"] = target["schema"]

                # Use current directory as project folder
                project_path = Path.cwd()
            else:
                typer.echo(
                    "❌ Error: Cannot determine connection config for directory of OTS modules",
                    err=True,
                )
                typer.echo(
                    "   Please provide --project-folder or ensure OTS modules have target config",
                    err=True,
                )
                raise typer.Exit(1)

            # In standalone mode there is no CommandContext, so use CLI vars directly.
            variables = vars or {}

            # Create a minimal parser for dependency graph building
            parser = ProjectParser(str(project_path), connection_config, variables)
            parser.parsed_models = ots_parsed_models

            # Build dependency graph
            typer.echo("\nBuilding dependency graph...")
            parser.build_dependency_graph()
            execution_order = parser.get_execution_order()
            typer.echo(f"Execution order: {' -> '.join(execution_order)}")

            # Execute models
            from t4t.engine import ModelExecutor

            model_executor = ModelExecutor(str(project_path), connection_config)
            results = model_executor.execute_models(
                parser=parser,
                variables=variables,
                parsed_models=ots_parsed_models,
                execution_order=execution_order,
            )

            # Run tests
            from t4t.testing import TestExecutor

            test_executor = TestExecutor(model_executor.execution_engine)
            test_results = test_executor.run_tests(ots_parsed_models, variables=variables)
            results["test_results"] = test_results

            # Disconnect
            model_executor.execution_engine.disconnect()

            # Print summary
            typer.echo("\n✅ Execution complete!")
            typer.echo(f"   Executed: {len(results['executed_tables'])} tables")
            if results.get("failed_tables"):
                typer.echo(f"   Failed: {len(results['failed_tables'])} tables")

    except OTSModuleReaderError as e:
        typer.echo(f"❌ Error reading OTS modules: {e}", err=True)
        raise typer.Exit(1) from None
    except Exception as e:
        typer.echo(f"❌ Error executing OTS modules: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1) from None


def cmd_ots_validate(
    ots_path: str,
    verbose: bool = False,
) -> None:
    """
    Validate OTS modules.

    Args:
        ots_path: Path to OTS module file (.ots.json) or directory containing OTS modules
        verbose: Enable verbose output
    """
    ots_path_obj = Path(ots_path)

    if not ots_path_obj.exists():
        typer.echo(f"❌ Error: OTS path not found: {ots_path}", err=True)
        raise typer.Exit(1)

    try:
        reader = OTSModuleReader()

        if ots_path_obj.is_file():
            typer.echo(f"\nValidating OTS module: {ots_path}")
            module = reader.read_module(ots_path_obj)
            info = reader.get_module_info(module)

            typer.echo("✅ OTS module is valid!")
            typer.echo("\nModule Information:")
            typer.echo(f"  Name: {info['module_name']}")
            typer.echo(f"  OTS Version: {info['ots_version']}")
            typer.echo(f"  Transformations: {info['transformation_count']}")
            typer.echo(f"  Target: {info['target'].get('database')}.{info['target'].get('schema')}")
            if info.get("module_tags"):
                typer.echo(f"  Tags: {', '.join(info['module_tags'])}")
            if info.get("has_test_library"):
                typer.echo("  Test Library: Yes")

        elif ots_path_obj.is_dir():
            typer.echo(f"\nValidating OTS modules in: {ots_path}")
            modules = reader.read_modules_from_directory(ots_path_obj)

            if not modules:
                typer.echo("⚠️  No OTS modules found")
                return

            typer.echo(f"✅ Found {len(modules)} OTS module(s)")

            for module_name, module in modules.items():
                info = reader.get_module_info(module)
                typer.echo(f"\n  {module_name}:")
                typer.echo(f"    Transformations: {info['transformation_count']}")
                typer.echo(
                    f"    Target: {info['target'].get('database')}.{info['target'].get('schema')}"
                )

        else:
            typer.echo(f"❌ Error: Path is neither a file nor a directory: {ots_path}", err=True)
            raise typer.Exit(1)

    except OTSModuleReaderError as e:
        typer.echo(f"❌ Validation failed: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1) from None
    except Exception as e:
        typer.echo(f"❌ Error: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1) from None
