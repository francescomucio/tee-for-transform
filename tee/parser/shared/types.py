"""
Common type definitions for the parser module.
"""

from pathlib import Path
from typing import Any

from tee.typing.function import Function
from tee.typing.model import Model

# Core data structures
# Note: Model and Function are now proper TypedDicts from tee.typing
# ParsedModel and ParsedFunction are kept as aliases for backward compatibility
ParsedModel = Model
ParsedFunction = Function
DependencyGraph = dict[str, Any]
DimensionalGraph = dict[str, Any]
TableReference = str
FunctionReference = str

# File paths
FilePath = str | Path

# Connection configuration
ConnectionConfig = dict[str, Any]

# Variable substitution
Variables = dict[str, Any]


# Dependency information
DependencyInfo = dict[str, list[str]]

# Execution order
ExecutionOrder = list[str]

GraphCycles = list[list[str]]
