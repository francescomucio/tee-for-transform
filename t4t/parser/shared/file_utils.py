"""
Shared file utilities for parsers.
"""

from pathlib import Path


def find_metadata_file(sql_file_path: str) -> str | None:
    """
    Find companion Python metadata file for a SQL file.

    This utility is shared between SQLParser and FunctionSQLParser
    to avoid code duplication.

    Args:
        sql_file_path: Path to the SQL file

    Returns:
        Path to the Python metadata file if found, None otherwise
    """
    if not sql_file_path:
        return None

    sql_path = Path(sql_file_path)
    if not sql_path.exists():
        return None

    # Look for Python file with same name in same directory
    python_file = sql_path.with_suffix(".py")
    if python_file.exists():
        return str(python_file)

    return None
