"""
Core database adapter base class.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from .config import AdapterConfig, MaterializationType
from .metadata import MetadataHandler
from .sql import SQLProcessor
from .testing import TestQueryGenerator


class DatabaseAdapter(ABC, SQLProcessor, MetadataHandler, TestQueryGenerator):
    """
    Abstract base class for database adapters.

    This class defines the interface that all database adapters must implement,
    including SQL dialect conversion, connection management, and database-specific features.
    """

    # Override in subclasses to define required fields
    REQUIRED_FIELDS = ["type"]

    def __init__(self, config_dict: dict[str, Any]) -> None:
        self.connection: Any | None = None
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

        # Validate configuration first
        self._validate_config(config_dict)

        # Create adapter config
        self.config: AdapterConfig = self._create_adapter_config(config_dict)

        # Initialize SQLglot dialect objects (needed for SQL processing)
        # We need to do this after config is created but before we can use SQL methods
        # The dialect objects will be set up in _init_dialects
        self._init_dialects()

    def _init_dialects(self) -> None:
        """Initialize SQLglot dialect objects."""

        self.source_dialect = self._get_dialect(self.config.source_dialect)
        self.target_dialect = self._get_dialect(
            self.config.target_dialect or self.get_default_dialect()
        )

    def _validate_config(self, config_dict: dict[str, Any]) -> None:
        """Validate configuration against adapter requirements."""
        # Check required fields
        missing = set(self.REQUIRED_FIELDS) - set(config_dict.keys())
        if missing:
            raise ValueError(f"Missing required fields for {self.__class__.__name__}: {missing}")

        # Validate field types
        self._validate_field_types(config_dict)

        # Validate field values
        self._validate_field_values(config_dict)

    def _validate_field_types(self, config_dict: dict[str, Any]) -> None:
        """Validate field types."""
        if (
            "port" in config_dict
            and config_dict["port"] is not None
            and not isinstance(config_dict["port"], int)
        ):
            raise ValueError("Port must be an integer")

        if (
            "connection_timeout" in config_dict
            and config_dict["connection_timeout"] is not None
            and not isinstance(config_dict["connection_timeout"], int)
        ):
            raise ValueError("Connection timeout must be an integer")

        if (
            "query_timeout" in config_dict
            and config_dict["query_timeout"] is not None
            and not isinstance(config_dict["query_timeout"], int)
        ):
            raise ValueError("Query timeout must be an integer")

    def _validate_field_values(self, config_dict: dict[str, Any]) -> None:
        """Validate field values."""
        if (
            "port" in config_dict
            and config_dict["port"] is not None
            and not (1 <= config_dict["port"] <= 65535)
        ):
            raise ValueError("Port must be between 1 and 65535")

        if (
            "connection_timeout" in config_dict
            and config_dict["connection_timeout"] is not None
            and config_dict["connection_timeout"] <= 0
        ):
            raise ValueError("Connection timeout must be positive")

        if (
            "query_timeout" in config_dict
            and config_dict["query_timeout"] is not None
            and config_dict["query_timeout"] <= 0
        ):
            raise ValueError("Query timeout must be positive")

    def _create_adapter_config(self, config_dict: dict[str, Any]) -> AdapterConfig:
        """Create AdapterConfig from validated dictionary."""
        # Map source_sql_dialect to source_dialect (source_sql_dialect is the preferred name in project.toml)
        source_dialect = config_dict.get("source_dialect") or config_dict.get("source_sql_dialect")

        return AdapterConfig(
            type=config_dict["type"],
            host=config_dict.get("host"),
            port=config_dict.get("port"),
            database=config_dict.get("database"),
            user=config_dict.get("user"),
            password=config_dict.get("password"),
            path=config_dict.get("path"),
            source_dialect=source_dialect,
            target_dialect=config_dict.get("target_dialect"),
            connection_timeout=config_dict.get("connection_timeout", 30),
            query_timeout=config_dict.get("query_timeout", 300),
            schema=config_dict.get("schema"),
            warehouse=config_dict.get("warehouse"),
            role=config_dict.get("role"),
            project=config_dict.get("project"),
            naming=config_dict.get("_naming_config"),
            extra=config_dict.get("extra"),
        )

    @abstractmethod
    def get_default_dialect(self) -> str:
        """Get the default SQL dialect for this database."""
        pass

    @abstractmethod
    def get_supported_materializations(self) -> list[MaterializationType]:
        """Get list of supported materialization types for this database."""
        pass

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""
        pass

    @abstractmethod
    def execute_query(self, query: str) -> Any:
        """Execute a SQL query and return results."""
        pass

    @abstractmethod
    def create_table(
        self, table_name: str, query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Create a table from a qualified SQL query with optional column metadata.

        Args:
            table_name: Name of the table to create
            query: SQL query to execute
            metadata: Optional metadata containing column descriptions and other info
        """
        pass

    @abstractmethod
    def create_view(
        self, view_name: str, query: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Create a view from a qualified SQL query."""
        pass

    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        pass

    @abstractmethod
    def drop_table(self, table_name: str) -> None:
        """Drop a table from the database."""
        pass

    @abstractmethod
    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table."""
        pass

    # Schema change handling methods (OTS 0.2.1)
    @abstractmethod
    def describe_query_schema(self, sql_query: str) -> list[dict[str, Any]]:
        """Infer schema from SQL query output using database-specific methods.

        This method should use database-specific DESCRIBE or similar commands
        to get the schema without executing the full query.

        Args:
            sql_query: SQL query to analyze

        Returns:
            List of column definitions: [{"name": "col1", "type": "VARCHAR"}, ...]
        """
        pass

    @abstractmethod
    def add_column(self, table_name: str, column: dict[str, Any]) -> None:
        """Add a column to an existing table.

        Args:
            table_name: Name of the table
            column: Column definition with "name" and "type" keys
        """
        pass

    @abstractmethod
    def drop_column(self, table_name: str, column_name: str) -> None:
        """Drop a column from an existing table.

        Args:
            table_name: Name of the table
            column_name: Name of the column to drop
        """
        pass

    # Function management methods
    @abstractmethod
    def create_function(
        self,
        function_name: str,
        function_sql: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create or replace a user-defined function in the database.

        This method should use CREATE OR REPLACE FUNCTION syntax to ensure
        functions are always overwritten (no versioning).

        Args:
            function_name: Fully qualified function name (schema.function_name)
            function_sql: SQL statement to create the function (CREATE OR REPLACE FUNCTION ...)
            metadata: Optional metadata containing function description, tags, etc.

        Raises:
            FunctionExecutionError: If function creation fails
        """
        pass

    @abstractmethod
    def function_exists(self, function_name: str, signature: str | None = None) -> bool:
        """
        Check if a function exists in the database.

        Args:
            function_name: Name of the function (can be qualified: schema.function_name)
            signature: Optional function signature (e.g., "FLOAT, FLOAT" for parameters)
                      If provided, checks for exact signature match (handles overloading)

        Returns:
            True if function exists (and matches signature if provided), False otherwise
        """
        pass

    @abstractmethod
    def drop_function(self, function_name: str) -> None:
        """Drop a function from the database.

        Args:
            function_name: Fully qualified function name (schema.function_name)

        Raises:
            FunctionExecutionError: If function drop fails
        """
        pass

    def get_function_info(self, function_name: str) -> dict[str, Any]:
        """Get information about a function.

        This is an optional method that adapters can override if they support
        querying function metadata. By default, it returns a basic structure.

        Args:
            function_name: Fully qualified function name (schema.function_name)

        Returns:
            Dictionary containing function information (name, parameters, return_type, etc.)
        """
        self.logger.debug(
            f"Adapter {self.__class__.__name__} does not support querying function info. "
            f"Requested info for function: {function_name}"
        )
        return {
            "function_name": function_name,
            "exists": self.function_exists(function_name),
        }

    # Incremental materialization methods
    def execute_incremental_append(self, table_name: str, source_sql: str) -> None:
        """Execute incremental append operation.

        This method can be overridden by adapters that support incremental append.
        By default, it falls back to regular table creation.
        """
        self.logger.warning(
            f"Adapter {self.__class__.__name__} does not support incremental append, falling back to regular table creation"
        )
        self.create_table(table_name, source_sql)

    def execute_incremental_merge(
        self, _table_name: str, source_sql: str, _config: dict[str, Any]
    ) -> None:
        """Execute incremental merge operation.

        This method can be overridden by adapters that support incremental merge.
        By default, it falls back to regular query execution.
        """
        self.logger.warning(
            f"Adapter {self.__class__.__name__} does not support incremental merge, falling back to regular execution"
        )
        self.execute_query(source_sql)

    def execute_incremental_delete_insert(
        self, _table_name: str, delete_sql: str, insert_sql: str
    ) -> None:
        """Execute incremental delete+insert operation.

        This method can be overridden by adapters that support incremental delete+insert.
        By default, it falls back to regular query execution.
        """
        self.logger.warning(
            f"Adapter {self.__class__.__name__} does not support incremental delete+insert, falling back to regular execution"
        )
        self.execute_query(delete_sql)
        self.execute_query(insert_sql)

    def get_database_info(self) -> dict[str, Any]:
        """Get information about the current database connection."""
        return {
            "adapter_type": self.__class__.__name__,
            "database_type": self.config.type,
            "source_dialect": self.config.source_dialect,
            "target_dialect": self.get_default_dialect(),
            "is_connected": self.connection is not None,
            "supported_materializations": [m.value for m in self.get_supported_materializations()],
        }

    def attach_tags(self, object_type: str, object_name: str, tags: list[str]) -> None:
        """
        Attach tags (dbt-style, list of strings) to a database object.

        This is an optional method that adapters can override if they support tagging.
        By default, it logs a debug message that tagging is not supported.

        Args:
            object_type: Type of object ('TABLE', 'VIEW', 'FUNCTION', etc.)
            object_name: Fully qualified object name
            tags: List of tag strings to attach (dbt-style)
        """
        self.logger.debug(
            f"Adapter {self.__class__.__name__} does not support tagging. "
            f"Tags would be attached to {object_type} {object_name}: {tags}"
        )

    def attach_object_tags(
        self, object_type: str, object_name: str, object_tags: dict[str, str]
    ) -> None:
        """
        Attach object tags (database-style, key-value pairs) to a database object.

        This is an optional method that adapters can override if they support object tagging.
        By default, it logs a debug message that object tagging is not supported.

        Args:
            object_type: Type of object ('TABLE', 'VIEW', 'FUNCTION', etc.)
            object_name: Fully qualified object name
            object_tags: Dictionary of tag key-value pairs (database-style)
        """
        self.logger.debug(
            f"Adapter {self.__class__.__name__} does not support object tagging. "
            f"Object tags would be attached to {object_type} {object_name}: {object_tags}"
        )

    def _get_dialect(self, dialect_name: str | None) -> Any:
        """Get SQLglot dialect object from name."""
        import sqlglot

        if not dialect_name:
            return None

        try:
            return sqlglot.dialects.Dialect.get(dialect_name)
        except Exception:
            self.logger.warning(f"Unknown dialect: {dialect_name}")
            return None

    # ── Naming strategy (env-aware) ──────────────────────────────────────

    def apply_naming(self, name: str) -> str:
        """Apply the environment-aware naming strategy to a database object name.

        When a ``naming.schema_prefix`` is configured on the adapter, this
        method prepends the prefix to the schema portion of a qualified name
        (e.g. ``my_schema.my_table`` → ``dev_my_schema.my_table``).

        For three-part names (``db.schema.table``), the schema (second-to-last
        part) is prefixed, not the database (first part).

        For unqualified names, the adapter's default schema is used as the
        schema portion before applying the prefix.

        Args:
            name: A database object name, optionally qualified (``schema.object``).

        Returns:
            The mapped name with naming strategy applied, or the original
            name unchanged if no naming config is set.
        """
        naming = self.config.naming
        if naming is None or naming.schema_prefix is None:
            return name

        parts = name.split(".")
        if len(parts) >= 3:
            # Three-or-more-part name: prefix the second-to-last part (schema)
            # e.g. my_db.my_schema.my_table -> my_db.dev_my_schema.my_table
            parts[-2] = f"{naming.schema_prefix}{parts[-2]}"
            return ".".join(parts)
        elif len(parts) == 2:
            # Two-part name: prefix the first part (schema)
            # e.g. my_schema.my_table -> dev_my_schema.my_table
            return f"{naming.schema_prefix}{parts[0]}.{parts[1]}"
        else:
            # Unqualified name — use the adapter's default schema
            schema = self.config.schema or self._get_default_schema()
            return f"{naming.schema_prefix}{schema}.{name}"

    def _get_default_schema(self) -> str:
        """Return the default schema name for this database type.

        Override in subclasses to provide the correct default for each
        database (e.g. DuckDB → ``main``, Snowflake → ``PUBLIC``).
        """
        return "public"
