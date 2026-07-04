"""
SQL processing methods for database adapters.

These methods are mixed into DatabaseAdapter via multiple inheritance.
"""

import sqlglot


class SQLProcessor:
    """Mixin class for SQL dialect conversion and processing."""

    def convert_sql_dialect(self, sql: str, source_dialect: str | None = None) -> str:
        """
        Convert SQL from source dialect to target dialect.

        Uses auto-detection (read=None) by default, which allows SQLGlot to parse
        SQL from various dialects more flexibly. If source_dialect is explicitly provided,
        it will be used instead.

        Args:
            sql: SQL query to convert
            source_dialect: Source dialect (uses None/auto-detect if None, which is more flexible)

        Returns:
            Converted SQL query
        """
        if not sql or not sql.strip():
            return sql

        try:
            # Parse with source dialect (None = auto-detect, more flexible)
            # If source_dialect is provided, use it; otherwise let SQLGlot auto-detect
            read_dialect = self._get_dialect(source_dialect) if source_dialect else None
            parsed = sqlglot.parse_one(sql, read=read_dialect)

            # Convert to target dialect
            converted = parsed.sql(dialect=self.target_dialect)

            # Log info if conversion happened
            source_name = source_dialect or "auto-detect"
            if source_name != self.get_default_dialect():
                self.logger.debug(
                    f"Converted SQL from {source_name} to {self.get_default_dialect()}. "
                    f"Please review the converted query for correctness."
                )

            return converted

        except Exception as e:
            source_name = source_dialect or "auto-detect"
            self.logger.error(
                f"Failed to convert SQL from {source_name} to {self.get_default_dialect()}: {e}"
            )
            raise ValueError(f"SQL dialect conversion failed: {e}") from e

    def qualify_table_references(self, sql: str, schema: str | None = None) -> str:
        """
        Qualify table references with schema names.

        Args:
            sql: SQL query to qualify
            schema: Schema name to use for qualification

        Returns:
            SQL with qualified table references
        """
        if not sql or not sql.strip():
            return sql

        try:
            # Parse the SQL
            parsed = sqlglot.parse_one(sql, read=self.target_dialect)

            # Use sqlglot's qualify optimizer
            from sqlglot.optimizer.qualify import qualify

            qualified = qualify(parsed, db=schema)

            return qualified.sql(dialect=self.target_dialect)

        except Exception as e:
            self.logger.warning(f"Failed to qualify table references: {e}")
            return sql
