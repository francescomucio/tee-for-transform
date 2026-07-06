"""
Adapter registry for managing database adapters.

This module provides a registry system for discovering and managing
database adapters with automatic registration and factory methods.
"""

import logging
from typing import Any

from .base import AdapterConfig, DatabaseAdapter


class AdapterRegistry:
    """Registry for managing database adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[DatabaseAdapter]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def register(self, adapter_type: str, adapter_class: type[DatabaseAdapter]) -> None:
        """
        Register a database adapter.

        Args:
            adapter_type: Database type identifier (e.g., 'duckdb', 'snowflake')
            adapter_class: Adapter class that implements DatabaseAdapter
        """
        self._adapters[adapter_type.lower()] = adapter_class
        self.logger.debug(f"Registered adapter: {adapter_type} -> {adapter_class.__name__}")

    def get_adapter_class(self, adapter_type: str) -> type[DatabaseAdapter] | None:
        """
        Get adapter class for a database type.

        Args:
            adapter_type: Database type identifier

        Returns:
            Adapter class or None if not found
        """
        return self._adapters.get(adapter_type.lower())

    def create_adapter(self, config: AdapterConfig | dict[str, Any]) -> DatabaseAdapter:
        """
        Create an adapter instance from configuration.

        Args:
            config: Adapter configuration (AdapterConfig or dict)

        Returns:
            Configured adapter instance

        Raises:
            ValueError: If adapter type is not supported
        """
        # Extract adapter type
        adapter_type = config.type if isinstance(config, AdapterConfig) else config.get("type")

        if not adapter_type:
            raise ValueError("Database type is required")

        adapter_class = self.get_adapter_class(adapter_type)
        if not adapter_class:
            supported_types = list(self._adapters.keys())
            raise ValueError(
                f"Unsupported database type: {adapter_type}. Supported types: {supported_types}"
            )

        # Convert AdapterConfig to dict if needed
        if isinstance(config, AdapterConfig):
            config_dict = {
                "type": config.type,
                "host": config.host,
                "port": config.port,
                "database": config.database,
                "user": config.user,
                "password": config.password,
                "path": config.path,
                "source_dialect": config.source_dialect,
                "target_dialect": config.target_dialect,
                "connection_timeout": config.connection_timeout,
                "query_timeout": config.query_timeout,
                "schema": config.schema,
                "warehouse": config.warehouse,
                "role": config.role,
                "project": config.project,
                "extra": config.extra,
                "_naming_config": config.naming,
            }
        else:
            config_dict = config

        return adapter_class(config_dict)

    def list_adapters(self) -> list[str]:
        """Get list of registered adapter types."""
        return list(self._adapters.keys())

    def is_supported(self, adapter_type: str) -> bool:
        """Check if an adapter type is supported."""
        return adapter_type.lower() in self._adapters


# Global registry instance
_registry = AdapterRegistry()


def register_adapter(adapter_type: str, adapter_class: type[DatabaseAdapter]) -> None:
    """Register an adapter with the global registry."""
    _registry.register(adapter_type, adapter_class)


def get_adapter(config: AdapterConfig | dict[str, Any]) -> DatabaseAdapter:
    """
    Get an adapter instance from configuration.

    Args:
        config: Adapter configuration (AdapterConfig or dict)

    Returns:
        Configured adapter instance
    """
    return _registry.create_adapter(config)


def list_available_adapters() -> list[str]:
    """Get list of available adapter types."""
    return _registry.list_adapters()


def is_adapter_supported(adapter_type: str) -> bool:
    """Check if an adapter type is supported."""
    return _registry.is_supported(adapter_type)
