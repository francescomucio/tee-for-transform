"""
Tests for function-related exceptions.
"""

import pytest

from t4t.parser.shared.exceptions import (
    FunctionExecutionError,
    FunctionMetadataError,
    FunctionParsingError,
    ParserError,
)


class TestFunctionExceptions:
    """Test function-related exception classes."""

    def test_function_parsing_error_inherits_from_parser_error(self):
        """Test that FunctionParsingError inherits from ParserError."""
        assert issubclass(FunctionParsingError, ParserError)

    def test_function_execution_error_inherits_from_parser_error(self):
        """Test that FunctionExecutionError inherits from ParserError."""
        assert issubclass(FunctionExecutionError, ParserError)

    def test_function_metadata_error_inherits_from_parser_error(self):
        """Test that FunctionMetadataError inherits from ParserError."""
        assert issubclass(FunctionMetadataError, ParserError)

    def test_function_parsing_error_can_be_raised(self):
        """Test that FunctionParsingError can be raised and caught."""
        with pytest.raises(FunctionParsingError) as exc_info:
            raise FunctionParsingError("Function parsing failed")
        assert str(exc_info.value) == "Function parsing failed"

    def test_function_execution_error_can_be_raised(self):
        """Test that FunctionExecutionError can be raised and caught."""
        with pytest.raises(FunctionExecutionError) as exc_info:
            raise FunctionExecutionError("Function execution failed")
        assert str(exc_info.value) == "Function execution failed"

    def test_function_metadata_error_can_be_raised(self):
        """Test that FunctionMetadataError can be raised and caught."""
        with pytest.raises(FunctionMetadataError) as exc_info:
            raise FunctionMetadataError("Function metadata validation failed")
        assert str(exc_info.value) == "Function metadata validation failed"

    def test_function_exceptions_are_parser_errors(self):
        """Test that all function exceptions are catchable as ParserError."""
        exceptions = [
            FunctionParsingError("test"),
            FunctionExecutionError("test"),
            FunctionMetadataError("test"),
        ]

        for exc in exceptions:
            with pytest.raises(ParserError):
                raise exc
