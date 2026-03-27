"""Tag management for Snowflake database objects."""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tee.adapters.base.core import DatabaseAdapter

logger = logging.getLogger(__name__)


class TagManager:
    """Manages tag attachment for Snowflake objects."""

    _ALLOWED_OBJECT_TYPES = {
        "TABLE",
        "VIEW",
        "SCHEMA",
        "MATERIALIZED VIEW",
        "DYNAMIC TABLE",
        "ICEBERG TABLE",
        "FUNCTION",
    }
    _OBJECT_NAME_PATTERN = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*){0,2}$"
    )
    _IDENTIFIER_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_]")

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """
        Initialize the tag manager.

        Args:
            adapter: SnowflakeAdapter instance
        """
        self.adapter = adapter
        self.config = adapter.config
        self.logger = adapter.logger

    @property
    def connection(self) -> Any:
        """Get connection from adapter."""
        return self.adapter.connection

    def attach_tags(self, object_type: str, object_name: str, tags: list[str]) -> None:
        """
        Attach tags to a Snowflake database object.

        Snowflake supports tags on tables, views, and other objects using:
        ALTER TABLE/VIEW object_name SET TAG tag_name = 'tag_value'

        For simple string tags, we create/use a generic 'tag' tag and set values.

        Args:
            object_type: Type of object ('TABLE', 'VIEW', etc.)
            object_name: Fully qualified object name (DATABASE.SCHEMA.OBJECT)
            tags: List of tag strings to attach
        """
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        if not tags:
            return

        normalized_object_type = self._normalize_object_type(object_type)
        self._validate_object_name(object_name)
        cursor = self.connection.cursor()
        try:
            for tag_value in tags:
                if not tag_value or not isinstance(tag_value, str) or not tag_value.strip():
                    continue

                sanitized_tag = self._sanitize_identifier(
                    f"tee_tag_{tag_value.lower()}",
                    fallback_prefix="tee_tag",
                )
                self._attach_single_tag(
                    cursor=cursor,
                    normalized_object_type=normalized_object_type,
                    object_name=object_name,
                    tag_identifier=sanitized_tag,
                    tag_value=str(tag_value),
                    warning_context=f"tag '{tag_value}'",
                    success_label="tag",
                    function_skip_label="tag attachment",
                )

            self.logger.info(
                f"Attached {len(tags)} tag(s) to {normalized_object_type} {object_name}"
            )

        except Exception as e:
            self.logger.warning(
                f"Error attaching tags to {normalized_object_type} {object_name}: {e}"
            )
            # Don't raise - tag attachment is optional
        finally:
            cursor.close()

    def attach_object_tags(
        self, object_type: str, object_name: str, object_tags: dict[str, str]
    ) -> None:
        """
        Attach object tags (key-value pairs) to a Snowflake database object.

        This method handles database-style tags where each tag is a key-value pair,
        like {"sensitivity_tag": "pii", "classification": "public"}.

        Snowflake syntax: ALTER TABLE/VIEW object_name SET TAG tag_name = 'tag_value'

        Args:
            object_type: Type of object ('TABLE', 'VIEW', etc.)
            object_name: Fully qualified object name (DATABASE.SCHEMA.OBJECT)
            object_tags: Dictionary of tag key-value pairs
        """
        if not self.connection:
            raise RuntimeError("Not connected to database. Call connect() first.")

        if not object_tags or not isinstance(object_tags, dict):
            return

        normalized_object_type = self._normalize_object_type(object_type)
        self._validate_object_name(object_name)
        cursor = self.connection.cursor()
        try:
            for tag_key, tag_value in object_tags.items():
                if not tag_key or not isinstance(tag_key, str):
                    continue
                if tag_value is None:
                    continue

                # Sanitize tag key (Snowflake tag names must be valid identifiers)
                sanitized_tag_key = self._sanitize_identifier(
                    tag_key,
                    fallback_prefix="tag",
                )

                # Convert tag value to string
                tag_value_str = str(tag_value)
                self._attach_single_tag(
                    cursor=cursor,
                    normalized_object_type=normalized_object_type,
                    object_name=object_name,
                    tag_identifier=sanitized_tag_key,
                    tag_value=tag_value_str,
                    warning_context=f"object tag '{tag_key}'='{tag_value}'",
                    success_label="object tag",
                    function_skip_label="object tag attachment",
                )

            self.logger.info(
                f"Attached {len(object_tags)} object tag(s) to {normalized_object_type} {object_name}"
            )

        except Exception as e:
            self.logger.warning(
                f"Error attaching object tags to {normalized_object_type} {object_name}: {e}"
            )
            # Don't raise - tag attachment is optional
        finally:
            cursor.close()

    @classmethod
    def _normalize_object_type(cls, object_type: str) -> str:
        normalized = " ".join(object_type.strip().upper().split())
        if normalized not in cls._ALLOWED_OBJECT_TYPES:
            raise ValueError(f"Unsupported object type for tag attachment: {object_type!r}")
        return normalized

    @classmethod
    def _validate_object_name(cls, object_name: str) -> None:
        if not object_name or not cls._OBJECT_NAME_PATTERN.fullmatch(object_name):
            raise ValueError(f"Invalid object name for tag attachment: {object_name!r}")

    @classmethod
    def _sanitize_identifier(cls, value: str, fallback_prefix: str) -> str:
        sanitized = cls._IDENTIFIER_SAFE_CHARS.sub("_", value.strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        if not sanitized:
            sanitized = fallback_prefix
        if sanitized[0].isdigit():
            sanitized = f"{fallback_prefix}_{sanitized}"
        return sanitized[:128]

    def _attach_single_tag(
        self,
        cursor: Any,
        normalized_object_type: str,
        object_name: str,
        tag_identifier: str,
        tag_value: str,
        warning_context: str,
        success_label: str,
        function_skip_label: str,
    ) -> None:
        try:
            self._ensure_tag_exists(cursor, tag_identifier)

            if normalized_object_type == "FUNCTION":
                self.logger.debug(
                    f"Skipping {function_skip_label} for FUNCTION {object_name}: "
                    f"Snowflake requires function signature for ALTER FUNCTION statements"
                )
                return

            escaped_value = tag_value.replace("'", "''")
            alter_sql = (
                f"ALTER {normalized_object_type} {object_name} "
                f"SET TAG {tag_identifier} = '{escaped_value}'"
            )
            cursor.execute(alter_sql)
            self.logger.debug(
                f"Attached {success_label} {tag_identifier}='{tag_value}' "
                f"to {normalized_object_type} {object_name}"
            )
        except Exception as e:
            self.logger.warning(
                f"Could not attach {warning_context} to {normalized_object_type} {object_name}: {e}"
            )

    def _ensure_tag_exists(self, cursor: Any, tag_identifier: str) -> None:
        try:
            create_tag_sql = f"CREATE TAG IF NOT EXISTS {tag_identifier}"
            cursor.execute(create_tag_sql)
            self.logger.debug(f"Created tag: {tag_identifier}")
        except Exception:
            # Tag might already exist, continue.
            return
