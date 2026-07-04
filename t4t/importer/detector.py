"""
Project type detector.

Detects the type of project (dbt, etc.) based on project structure and files.
"""

from enum import Enum
from pathlib import Path


class ProjectType(Enum):
    """Supported project types for import."""

    DBT = "dbt"
    UNKNOWN = "unknown"


def detect_project_type(project_path: Path) -> ProjectType:
    """
    Detect the type of project based on project structure and files.

    Args:
        project_path: Path to the project directory

    Returns:
        ProjectType enum value indicating the detected project type
    """
    project_path = Path(project_path).resolve()

    if not project_path.exists() or not project_path.is_dir():
        return ProjectType.UNKNOWN

    # Check for dbt project
    dbt_project_file = project_path / "dbt_project.yml"
    if dbt_project_file.exists():
        # Additional validation: check for models directory (common in dbt projects)
        models_dir = project_path / "models"
        if models_dir.exists() or _is_valid_dbt_project(dbt_project_file):
            return ProjectType.DBT

    return ProjectType.UNKNOWN


def _is_valid_dbt_project(dbt_project_file: Path) -> bool:
    """
    Validate that a dbt_project.yml file is a valid dbt project file.

    Args:
        dbt_project_file: Path to dbt_project.yml file

    Returns:
        True if the file appears to be a valid dbt project file
    """
    try:
        import yaml

        with dbt_project_file.open("r", encoding="utf-8") as f:
            content = yaml.safe_load(f)

        # Check for required dbt project fields
        if not isinstance(content, dict):
            return False

        # dbt projects typically have a 'name' field
        return "name" in content
    except Exception:
        # If we can't parse it, assume it's not valid
        return False
