"""
Constants for the parser module.
"""

# Default folder names
DEFAULT_MODELS_FOLDER = "models"
DEFAULT_FUNCTIONS_FOLDER = "functions"

# Supported file extensions
SUPPORTED_SQL_EXTENSIONS = [".sql"]
SUPPORTED_PYTHON_EXTENSIONS = [".py"]
# Database-specific function file extensions (for overrides)
SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS = [
    ".sql",
    ".js",
]  # .sql for SQL, .js for JavaScript (Snowflake)

# Known database adapter names (lowercase) for override detection
# These should match the adapters available in tee.adapters
# See tee.adapters.__init__ for the list of registered adapters
KNOWN_DATABASE_NAMES = {"duckdb", "snowflake", "postgresql", "bigquery"}

# Common SQL built-in functions that should be filtered out when extracting user-defined functions
SQL_BUILT_IN_FUNCTIONS = {
    "count",
    "sum",
    "avg",
    "max",
    "min",
    "coalesce",
    "case",
    "when",
    "then",
    "else",
    "end",
    "select",
    "from",
    "where",
    "group",
    "order",
    "by",
    "having",
    "limit",
    "offset",
    "null",
    "is",
    "not",
}

# SQL variable patterns
SQL_VARIABLE_PATTERNS = {
    "at_variable": r"@(\w+)",
    "jinja_variable": r"\{\{\s*(\w+(?:\.\w+)*)\s*\}\}",
    "jinja_with_default": r"\{\{\s*(\w+(?:\.\w+)*)\s*\|\s*default\s*\(\s*([^)]+)\s*\)\s*\}\}",
}


# Output file names
OUTPUT_FILES = {
    "parsed_models": "parsed_models.json",
    "dependency_graph": "dependency_graph.json",
    "dimensional_graph": "dimensional_graph.json",
    "dimension_registry": "dimension_registry.json",
    "markdown_report": "dependency_report.md",
    "last_run": "last_run.json",
    "runs_db": "runs.sqlite",
}
