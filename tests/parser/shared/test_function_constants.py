"""
Tests for function-related constants.
"""

from t4t.parser.shared.constants import (
    DEFAULT_FUNCTIONS_FOLDER,
    SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS,
)


class TestFunctionConstants:
    """Test function-related constants."""

    def test_default_functions_folder(self):
        """Test that DEFAULT_FUNCTIONS_FOLDER is set correctly."""
        assert DEFAULT_FUNCTIONS_FOLDER == "functions"

    def test_supported_function_override_extensions(self):
        """Test that function override extensions are defined."""
        assert ".sql" in SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS
        assert ".js" in SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS
        assert len(SUPPORTED_FUNCTION_OVERRIDE_EXTENSIONS) == 2
