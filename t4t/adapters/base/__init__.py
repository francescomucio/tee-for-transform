"""
Base adapter classes and configuration.

This module provides the core DatabaseAdapter class and related types.
All components are re-exported here for backward compatibility.
"""

# Import core components
from .config import AdapterConfig, MaterializationType
from .core import DatabaseAdapter

# Re-export everything for backward compatibility
# This allows: from ..base import DatabaseAdapter, AdapterConfig, MaterializationType
__all__ = [
    "DatabaseAdapter",
    "AdapterConfig",
    "MaterializationType",
]
