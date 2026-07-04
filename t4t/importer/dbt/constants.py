"""
Constants for dbt importer.

Centralizes all magic strings, numbers, and configuration values.
"""

# Default values
DEFAULT_SCHEMA = "public"
DEFAULT_DBT_SCHEMA = "dev"  # dbt's default schema when no profile schema is specified
DEFAULT_DIALECT = "postgresql"
MAX_MODELS_IN_ERROR_MESSAGE = 10

# Directory names
MODELS_DIR = "models"
TESTS_DIR = "tests"
MACROS_DIR = "macros"
SEEDS_DIR = "seeds"
FUNCTIONS_DIR = "functions"
OTS_MODULES_DIR = "ots_modules"
OUTPUT_DIR = "output"
DATA_DIR = "data"

# File extensions
SQL_EXTENSION = ".sql"
PYTHON_EXTENSION = ".py"
YAML_EXTENSION = ".yml"
YAML_ALT_EXTENSION = ".yaml"

# Report file names
IMPORT_REPORT_FILE = "IMPORT_REPORT.md"
CONVERSION_LOG_FILE = "CONVERSION_LOG.json"

# dbt project files
DBT_PROJECT_FILE = "dbt_project.yml"
PROFILES_FILE = "profiles.yml"
PACKAGES_FILE = "packages.yml"
SOURCES_FILE = "__sources.yml"

# Schema file patterns
SCHEMA_FILE_PATTERNS = ["schema.yml", "schema.yaml", "*.yml", "*.yaml"]
