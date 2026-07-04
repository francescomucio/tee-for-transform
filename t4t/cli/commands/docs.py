"""
Docs command implementation.
"""

import shutil
from pathlib import Path

import typer

from t4t.cli.context import CommandContext
from t4t.parser.core.project_parser import ProjectParser
from t4t.parser.output.docs_generator import DocsGenerator
from t4t.parser.output.lookup_generator import generate_lookups


def _is_lookup_model(model_name: str, model: dict) -> bool:
    """Return True when model should be treated as a lookup."""
    metadata = model.get("model_metadata", {}).get("metadata", {}) or {}
    explicit_type = metadata.get("table_type")
    if explicit_type == "lookup":
        return True
    short_name = model_name.split(".")[-1].lower()
    return short_name.startswith("lkp_")


def _filter_graph_to_models(graph: dict, allowed_nodes: set[str]) -> dict:
    """Keep only graph entries that reference allowed model nodes."""
    filtered_graph = dict(graph)

    nodes = graph.get("nodes", [])
    filtered_graph["nodes"] = [
        n for n in nodes if not isinstance(n, dict) or n.get("id") in allowed_nodes
    ]

    def _edge_in_scope(edge: dict) -> bool:
        src = edge.get("source")
        tgt = edge.get("target")
        src_ok = (not isinstance(src, str)) or (src in allowed_nodes)
        tgt_ok = (not isinstance(tgt, str)) or (tgt in allowed_nodes)
        return src_ok and tgt_ok

    edges = graph.get("edges", [])
    filtered_graph["edges"] = [e for e in edges if not isinstance(e, dict) or _edge_in_scope(e)]

    sql_edges = graph.get("sql_edges", [])
    filtered_graph["sql_edges"] = [
        e for e in sql_edges if not isinstance(e, dict) or _edge_in_scope(e)
    ]

    dependencies = graph.get("dependencies", {})
    filtered_graph["dependencies"] = {
        k: [d for d in v if not isinstance(d, str) or d in allowed_nodes]
        for k, v in dependencies.items()
        if k in allowed_nodes
    }

    dependents = graph.get("dependents", {})
    filtered_graph["dependents"] = {
        k: [d for d in v if not isinstance(d, str) or d in allowed_nodes]
        for k, v in dependents.items()
        if k in allowed_nodes
    }

    execution_order = graph.get("execution_order", [])
    filtered_graph["execution_order"] = [
        n for n in execution_order if not isinstance(n, str) or n in allowed_nodes
    ]

    return filtered_graph


def _clean_generated_lookup_dirs(project_path: Path) -> None:
    """Remove all generated lookup model folders before docs parsing."""
    models_root = project_path / "models"
    if not models_root.exists():
        return
    for gen_dir in models_root.rglob("_generated"):
        if gen_dir.is_dir():
            shutil.rmtree(gen_dir, ignore_errors=True)


def _filter_dimensional_graph_to_models(dimensional_graph: dict, allowed_nodes: set[str]) -> dict:
    """Keep only dimensional relationships that reference allowed models."""
    filtered = dict(dimensional_graph)
    relationships = dimensional_graph.get("relationships", [])
    filtered_relationships = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        src = rel.get("source_fact")
        tgt = rel.get("target_table")
        if isinstance(src, str) and src not in allowed_nodes:
            continue
        if isinstance(tgt, str) and tgt not in allowed_nodes:
            continue
        filtered_relationships.append(rel)

    filtered["relationships"] = filtered_relationships
    filtered["facts"] = [f for f in dimensional_graph.get("facts", []) if f in allowed_nodes]
    filtered["dimensions"] = [
        d for d in dimensional_graph.get("dimensions", []) if d in allowed_nodes
    ]
    filtered["grain"] = {
        k: v for k, v in (dimensional_graph.get("grain", {}) or {}).items() if k in allowed_nodes
    }
    return filtered


def cmd_docs(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    output_dir: str | None = None,
    auto_resolve_level_conflicts: bool = True,
    skip_lookups: bool = False,
    infer_dim_from_column_names: bool = False,
) -> None:
    """
    Generate static documentation site with dependency graph.

    This command:
    1. Parses SQL/Python models
    2. Builds dependency graph
    3. Generates static HTML documentation site with interactive graph

    Args:
        project_folder: Path to the project folder
        vars: Optional variables for SQL substitution (JSON format)
        verbose: Enable verbose output
        output_dir: Output directory for docs (default: output/docs)
    """
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
    )

    try:
        typer.echo(f"Generating documentation for project: {project_folder}")
        ctx.print_variables_info()

        if skip_lookups:
            typer.echo("Skipping generated lookup model refresh (--skip-lookups enabled)")
            typer.echo("Cleaning existing generated lookup models...")
            _clean_generated_lookup_dirs(ctx.project_path)
        else:
            typer.echo("Refreshing generated lookup models...")
            generate_lookups(
                project_path=ctx.project_path,
                vars_dict=ctx.vars,
                auto_resolve_level_conflicts=auto_resolve_level_conflicts,
            )

        # Determine output directory
        if output_dir:
            docs_output = Path(output_dir).resolve()
        else:
            docs_output = ctx.project_path / "output" / "docs"

        # Parse project
        parser = ProjectParser(
            project_folder=str(ctx.project_path),
            connection=ctx.config["connection"],
            variables=ctx.vars,
            project_config=ctx.config,
        )

        typer.echo("Parsing models...")
        parsed_models = parser.collect_models()
        if skip_lookups:
            parsed_models = {
                model_name: model
                for model_name, model in parsed_models.items()
                if not _is_lookup_model(model_name, model)
            }
        typer.echo(f"  Found {len(parsed_models)} model(s)")

        typer.echo("Building dependency graph...")
        graph = parser.build_dependency_graph()
        if skip_lookups:
            graph = _filter_graph_to_models(graph, set(parsed_models.keys()))
        typer.echo(f"  Graph has {len(graph['nodes'])} node(s) and {len(graph['edges'])} edge(s)")

        typer.echo("Building dimensional relationship graph...")
        dimensional_graph = parser.orchestrator.build_dimensional_graph(
            infer_from_column_names=infer_dim_from_column_names
        )
        if skip_lookups:
            dimensional_graph = _filter_dimensional_graph_to_models(
                dimensional_graph, set(parsed_models.keys())
            )

        # Get parsed functions if available
        parsed_functions = parser.orchestrator.discover_and_parse_functions()

        # Generate documentation
        typer.echo("Generating documentation site...")
        generator = DocsGenerator(
            project_path=ctx.project_path,
            output_path=docs_output,
            parsed_models=parsed_models,
            parsed_functions=parsed_functions,
            dependency_graph=graph,
            dimensional_graph=dimensional_graph,
            dimension_registry=parser.orchestrator.dimension_registry,
        )

        generator.generate()

        typer.echo("\n✅ Documentation generated successfully!")
        typer.echo(f"   Output: {docs_output}")
        typer.echo(f"   Open: {docs_output / 'index.html'}")

    except Exception as e:
        typer.echo(f"\n❌ Documentation generation failed: {e}", err=True)
        ctx.handle_error(e)
