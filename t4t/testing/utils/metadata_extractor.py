"""
Metadata extraction utilities.

Extracts metadata extraction logic from TestExecutor to eliminate duplication.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extracts metadata from model and function data."""

    @staticmethod
    def extract_model_metadata(model_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract metadata from model data.

        Args:
            model_data: Model data dictionary

        Returns:
            Metadata dictionary or None if not found
        """
        try:
            # First, try to get metadata from model_metadata
            model_metadata = model_data.get("model_metadata", {})
            if model_metadata and "metadata" in model_metadata:
                nested_metadata = model_metadata["metadata"]
                if nested_metadata:
                    return nested_metadata

            # Fallback to any other metadata in the model data
            if "metadata" in model_data:
                file_metadata = model_data["metadata"]
                if file_metadata:
                    return file_metadata

            return None
        except Exception as e:
            logger.warning(f"Error extracting model metadata: {e}")
            return None

    @staticmethod
    def extract_function_metadata(function_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract metadata from function data.

        Args:
            function_data: Function data dictionary

        Returns:
            Metadata dictionary or None if not found
        """
        try:
            # First, try to get metadata from function_metadata
            function_metadata = function_data.get("function_metadata", {})
            if function_metadata and "metadata" in function_metadata:
                nested_metadata = function_metadata["metadata"]
                if nested_metadata:
                    return nested_metadata

            # Fallback to function_metadata directly
            if function_metadata:
                return function_metadata

            # Fallback to any other metadata in the function data
            if "metadata" in function_data:
                file_metadata = function_data["metadata"]
                if file_metadata:
                    return file_metadata

            return None
        except Exception as e:
            logger.warning(f"Error extracting function metadata: {e}")
            return None
