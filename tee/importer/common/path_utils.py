"""
Path utilities for dbt importer.

Provides common functions for file path construction and manipulation.
"""

from pathlib import Path

from tee.importer.dbt.constants import MODELS_DIR


def parse_table_name(table_name: str) -> tuple[str, str]:
    """
    Parse table name into schema and name components.

    Args:
        table_name: Table name in format "schema.table"

    Returns:
        Tuple of (schema, name)
    """
    return table_name.split(".", 1)


def get_target_file_path(
    target_path: Path,
    table_name: str,
    rel_path: str,
    extension: str,
    preserve_filenames: bool,
    base_dir: str = MODELS_DIR,
) -> Path:
    """
    Get target file path for converted model/test/function.

    Args:
        target_path: Base target path for t4t project
        table_name: Final table name (schema.table format)
        rel_path: Relative path from dbt project root
        extension: File extension (e.g., ".sql", ".py")
        preserve_filenames: If True, keep original file structure; if False, use table name
        base_dir: Base directory name (default: "models")

    Returns:
        Path to target file
    """
    if preserve_filenames:
        # Keep original file structure
        # rel_path is relative to dbt project root (e.g., "models/staging/customers.sql")
        # Replace extension if needed
        if extension == ".py" and rel_path.endswith(".sql"):
            target_file = target_path / rel_path.replace(".sql", ".py")
        else:
            target_file = target_path / rel_path
    else:
        # Use table name for file name, organized by schema folder
        # This matches t4t's convention: models/{schema}/{table_name}.sql
        schema, name = parse_table_name(table_name)
        target_file = target_path / base_dir / schema / f"{name}{extension}"

    return target_file


def extract_schema_from_path(file_path: Path, base_dir: str = MODELS_DIR) -> str | None:
    """
    Extract schema name from file path structure.

    Args:
        file_path: Path to the file
        base_dir: Base directory name (e.g., "models", "macros")

    Returns:
        Schema name if found, None otherwise
    """
    parts = file_path.parts
    if base_dir in parts:
        base_idx = parts.index(base_dir)
        if base_idx + 1 < len(parts) - 1:  # There's a folder after base_dir/
            return parts[base_idx + 1]
    return None


def ensure_directory_exists(file_path: Path) -> None:
    """
    Ensure parent directory exists for file path.

    Args:
        file_path: Path to file
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
