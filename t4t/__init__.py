"""
Tee Module

A SQL model execution framework with parsing and execution capabilities.
"""

# Import new adapter system
from .adapters import BigQueryAdapter, DuckDBAdapter, PostgreSQLAdapter, SnowflakeAdapter

# Import CLI
from .cli import main as cli_main
from .compiler import compile_project
from .engine import ExecutionEngine, ModelExecutor
from .executor import build_models, execute_models
from .parser import ProjectParser

__all__ = [
    "ProjectParser",
    "ModelExecutor",
    "ExecutionEngine",
    "DuckDBAdapter",
    "SnowflakeAdapter",
    "PostgreSQLAdapter",
    "BigQueryAdapter",
    "execute_models",
    "build_models",
    "compile_project",
    "cli_main",
]
