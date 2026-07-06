"""
Init command implementation.
"""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import typer

# Type alias for database type
DatabaseType = Literal["duckdb", "snowflake", "postgresql", "bigquery", "motherduck"]


def _get_default_connection_config(db_type: str, project_name: str) -> dict[str, Any]:
    """
    Get default connection configuration for a database type.

    Args:
        db_type: Database type identifier
        project_name: Name of the project

    Returns:
        Dictionary with default connection configuration
    """
    db_type_lower = db_type.lower()

    # Database type configuration factory functions
    config_factories: dict[str, Callable[[str], dict[str, Any]]] = {
        "duckdb": lambda name: {
            "type": "duckdb",
            "path": f"data/{name}.duckdb",
        },
        "snowflake": lambda _: {
            "type": "snowflake",
            "host": "YOUR_ACCOUNT.snowflakecomputing.com",
            "user": "YOUR_USERNAME",
            "password": "YOUR_PASSWORD",
            "role": "YOUR_ROLE",
            "warehouse": "YOUR_WAREHOUSE",
            "database": "YOUR_DATABASE",
        },
        "postgresql": lambda name: {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": name,
            "user": "postgres",
            "password": "postgres",
        },
        "bigquery": lambda name: {
            "type": "bigquery",
            "project": "YOUR_PROJECT_ID",
            "database": name,  # dataset name
        },
        "motherduck": lambda name: {
            "type": "duckdb",
            "path": f"md:{name}",
            "database": name,
            "schema": "main",
        },
    }

    factory = config_factories.get(db_type_lower)
    if factory:
        return factory(project_name)

    # Generic fallback
    return {
        "type": db_type_lower,
    }


def _generate_project_toml(project_name: str, db_type: str) -> str:
    """
    Generate project.toml content.

    Args:
        project_name: Name of the project
        db_type: Database type identifier

    Returns:
        String content for project.toml
    """
    connection_config = _get_default_connection_config(db_type, project_name)

    # Build connection section
    connection_lines = []
    for key, value in connection_config.items():
        if isinstance(value, str):
            connection_lines.append(f'{key} = "{value}"')
        else:
            connection_lines.append(f"{key} = {value}")

    connection_section = "\n".join(connection_lines)

    # Build the TOML content
    toml_content = f'''project_folder = "{project_name}"

[environments.dev.connection]
{connection_section}'''

    # Add extra section for motherduck token
    if db_type.lower() == "motherduck":
        toml_content += """
[environments.dev.connection.extra]
# MotherDuck access token (recommended: use MOTHERDUCK_TOKEN environment variable instead)
# motherduck_token = "your_motherduck_access_token_here"
"""

    toml_content += """

[flags]
materialization_change_behavior = "warn"  # Options: "warn", "error", "ignore"
"""

    return toml_content


def cmd_init(
    project_name: str,
    database_type: DatabaseType = "duckdb",
) -> None:
    """Execute the init command to initialize a new project."""
    # database_type is already validated by Typer callback
    db_type = database_type.lower()

    # Validate project name (basic validation)
    if not project_name or project_name.strip() != project_name:
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + "Project name cannot be empty or contain leading/trailing whitespace"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1)

    # Create project directory (resolve to absolute path for creation)
    project_path = Path(project_name).resolve()

    if project_path.exists():
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Directory '{project_name}' already exists"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1) from None

    # Create project directory (with race condition handling)
    try:
        project_path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # Directory was created between check and mkdir (race condition)
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Directory '{project_name}' already exists"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1) from None

    try:
        typer.echo(f"Created project directory: {project_name}/")

        # Create default directories
        directories = ["models", "tests", "seeds"]
        if db_type == "duckdb":
            directories.append("data")

        for dir_name in directories:
            dir_path = project_path / dir_name
            dir_path.mkdir()
            typer.echo(f"Created directory: {project_name}/{dir_name}/")

        # Generate and write project.toml
        toml_content = _generate_project_toml(project_name, db_type)
        toml_path = project_path / "project.toml"
        toml_path.write_text(toml_content, encoding="utf-8")
        typer.echo(f"Created configuration file: {project_name}/project.toml")

        typer.echo(f"\n✅ Project '{project_name}' initialized successfully!")
        typer.echo("\nNext steps:")
        typer.echo(f"  1. Edit {project_name}/project.toml to configure your database connection")
        typer.echo(f"  2. Add SQL models to {project_name}/models/")
        typer.echo(f"  3. Add seed files to {project_name}/seeds/")
        typer.echo(f"  4. Run: t4t run {project_name}")

    except OSError as e:
        # Handle filesystem errors (permissions, disk full, etc.)
        if project_path.exists():
            shutil.rmtree(project_path)
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Failed to create project directory: {e}"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1) from None
    except Exception as e:
        # Cleanup on error
        if project_path.exists():
            shutil.rmtree(project_path)
        error_msg = (
            typer.style("Error: ", fg=typer.colors.RED, bold=True)
            + f"Failed to initialize project: {e}"
        )
        typer.echo(error_msg, err=True)
        raise typer.Exit(1) from None
