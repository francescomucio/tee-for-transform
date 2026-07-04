"""SQL dialect inference utilities."""

from typing import Any


def infer_sql_dialect(project_config: dict[str, Any]) -> str:
    """
    Infer SQL dialect from connection type in project configuration.

    Args:
        project_config: Project configuration dictionary

    Returns:
        SQL dialect string (e.g., "duckdb", "snowflake", "postgres")
    """
    conn_type = project_config.get("connection", {}).get("type", "duckdb")
    dialect_map = {
        "duckdb": "duckdb",
        "postgresql": "postgres",
        "postgres": "postgres",
        "snowflake": "snowflake",
        "mysql": "mysql",
        "bigquery": "bigquery",
        "spark": "spark",
    }
    return dialect_map.get(conn_type, "duckdb")
