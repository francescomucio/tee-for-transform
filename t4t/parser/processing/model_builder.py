"""
SqlModelMetadata class for creating models from metadata and companion SQL files.

This class is used in metadata-only Python files to automatically create models
by combining metadata with SQL from a companion .sql file.
"""

import logging
import os
from dataclasses import dataclass, field

from t4t.parser.shared.exceptions import ModelConflictError
from t4t.parser.shared.inspect_utils import get_caller_file_and_main
from t4t.parser.shared.model_builder import build_model_from_file
from t4t.parser.shared.registry import ModelRegistry
from t4t.typing import Model, ModelMetadata

logger = logging.getLogger(__name__)


@dataclass
class SqlModelMetadata:
    """
    A dataclass that automatically creates a model from metadata and associated SQL file.

    When instantiated, this class:
    1. Accepts ModelMetadata as parameter
    2. Automatically finds the SQL file based on the Python file that invoked it
    3. Creates a model dictionary using the shared build_model_from_file utility
    4. If invoked from __main__, also prints the created model

    This is designed for metadata-only Python files that need to combine
    metadata with SQL from a companion .sql file.

    Example:
        from t4t.parser.processing.model_builder import SqlModelMetadata
        from t4t.typing import ModelMetadata

        metadata: ModelMetadata = {
            "schema": [
                {"name": "id", "datatype": "number", "description": "Primary key"}
            ]
        }

        # This will automatically find test.sql and create a model
        model = SqlModelMetadata(metadata)
    """

    metadata: ModelMetadata
    model: Model | None = field(default=None, init=False)
    _caller_file: str | None = field(default=None, init=False, repr=False)
    _caller_main: bool = field(default=False, init=False, repr=False)

    def _print_model(self) -> None:
        """
        Print the model in a formatted, human-readable way.

        Displays the complete SQL query from the companion .sql file and all model metadata
        including columns (with datatypes and descriptions), materialization settings,
        incremental configuration, SCD2 details, indexes, tests, partitions, and description.
        The output is formatted with clear sections and visual separators for easy reading.
        """
        if not self.model:
            return

        output = []
        table_name = self.model["model_metadata"]["table_name"]
        output.append("\n" + "━" * 80)
        output.append(f"  📊 MODEL: {table_name}")
        output.append("━" * 80)
        output.append("")

        # SQL Query Section - read original SQL file to preserve formatting
        output.append("  📝 SQL Query:")
        sql_file_path = (
            os.path.splitext(self._caller_file)[0] + ".sql" if self._caller_file else None
        )
        if sql_file_path and os.path.exists(sql_file_path):
            with open(sql_file_path, encoding="utf-8") as f:
                sql_content = f.read().strip()
            sql_lines = sql_content.split("\n")
            for line in sql_lines:
                output.append(f"     {line}")
        else:
            # Fallback to parsed SQL if file not found
            sql = self.model["code"]["sql"]["original_sql"] if self.model.get("code") else ""
            sql_lines = sql.split("\n")
            for line in sql_lines:
                output.append(f"     {line}")
        output.append("")

        # Model Metadata Section - Key highlights
        output.append("  📋 Metadata:")
        metadata = self.model["model_metadata"].get("metadata", {})

        if metadata.get("schema"):
            # Show column details with datatypes and descriptions
            col_details = []
            for col in metadata["schema"]:
                col_str = col["name"]
                if col.get("datatype"):
                    col_str += f" ({col['datatype']})"
                col_details.append(col_str)
            output.append(f"     Columns: {', '.join(col_details)}")
            # Show column descriptions if available
            col_descriptions = [
                f"{col['name']}: {col['description']}"
                for col in metadata["schema"]
                if col.get("description")
            ]
            if col_descriptions:
                for desc in col_descriptions:
                    output.append(f"       {desc}")

        if metadata.get("materialization"):
            output.append(f"     Materialization: {metadata['materialization']}")

        if metadata.get("incremental"):
            inc_config = metadata["incremental"]
            strategy = inc_config.get("strategy", "unknown")
            output.append(f"     Incremental Strategy: {strategy}")
            if inc_config.get("unique_key"):
                output.append(f"       Unique Key: {', '.join(inc_config['unique_key'])}")
            if inc_config.get("merge_key"):
                output.append(f"       Merge Key: {', '.join(inc_config['merge_key'])}")

        if metadata.get("scd2_details"):
            scd2 = metadata["scd2_details"]
            output.append("     SCD2 Configuration:")
            if scd2.get("valid_from_column"):
                output.append(f"       Valid From: {scd2['valid_from_column']}")
            if scd2.get("valid_to_column"):
                output.append(f"       Valid To: {scd2['valid_to_column']}")
            if scd2.get("current_flag_column"):
                output.append(f"       Current Flag: {scd2['current_flag_column']}")

        if metadata.get("indexes"):
            indexes = metadata["indexes"]
            index_strs = []
            for idx in indexes:
                idx_name = idx.get("name", "unnamed")
                idx_cols = idx.get("columns", [])
                if idx_cols:
                    index_strs.append(f"{idx_name}({', '.join(idx_cols)})")
                else:
                    index_strs.append(idx_name)
            if index_strs:
                output.append(f"     Indexes: {', '.join(index_strs)}")

        if metadata.get("tests"):
            test_strs = [
                str(t) if isinstance(t, str) else t.get("name", str(t)) for t in metadata["tests"]
            ]
            output.append(f"     Tests: {', '.join(test_strs)}")

        if metadata.get("partitions"):
            output.append(f"     Partitions: {', '.join(metadata['partitions'])}")

        if self.model["model_metadata"].get("description"):
            output.append(f"     Description: {self.model['model_metadata']['description']}")

        output.append("━" * 80)
        output.append("")

        print("\n".join(output))

    def __post_init__(self) -> None:
        """Post-initialization: find SQL file, read it, and create model."""
        # Get caller file path and whether it's being run as __main__
        # Only call get_caller_file_and_main() if _caller_file is not already set
        # This allows manual setting of _caller_file (e.g., for auto-instantiation)
        if self._caller_file is None:
            self._caller_file, self._caller_main = get_caller_file_and_main()

        # Use build_model_from_file which handles SQL file discovery and model creation
        if self._caller_file:
            self.model = build_model_from_file(
                metadata=self.metadata,
                file_path=self._caller_file,
            )

            # Register the model with ModelRegistry
            if self.model:
                table_name = self.model["model_metadata"]["table_name"]

                # Check for conflicts (only if from a different file)
                existing_model = ModelRegistry.get(table_name)
                if existing_model:
                    existing_file = existing_model.get("model_metadata", {}).get("file_path")
                    if existing_file and existing_file != self._caller_file:
                        raise ModelConflictError(
                            f"Model name conflict: '{table_name}' is already registered from another file. "
                            f"Use a different table name to avoid conflicts."
                        )

                ModelRegistry.register(self.model)
                logger.debug(f"Registered model via SqlModelMetadata: {table_name}")

                # Print if called from __main__
                if self._caller_main:
                    self._print_model()
