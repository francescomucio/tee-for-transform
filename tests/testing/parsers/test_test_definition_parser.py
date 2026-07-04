"""
Unit tests for TestDefinitionParser.
"""

from t4t.testing.base import TestSeverity
from t4t.testing.parsers.test_definition_parser import TestDefinitionParser


class TestTestDefinitionParser:
    """Test cases for TestDefinitionParser."""

    def test_parse_string_test_def(self):
        """Test parsing a string test definition."""
        severity_overrides = {"my_test": TestSeverity.WARNING}

        result = TestDefinitionParser.parse("my_test", severity_overrides, "context")

        assert result is not None
        assert result.test_name == "my_test"
        assert result.params is None
        assert result.expected is None
        assert result.severity_override == TestSeverity.WARNING

    def test_parse_string_test_def_no_override(self):
        """Test parsing a string test definition without override."""
        severity_overrides = {}

        result = TestDefinitionParser.parse("my_test", severity_overrides, "context")

        assert result is not None
        assert result.test_name == "my_test"
        assert result.severity_override is None

    def test_parse_dict_test_def_with_name(self):
        """Test parsing a dict test definition with 'name' key."""
        severity_overrides = {}
        test_def = {"name": "my_test", "param1": 10, "param2": 20}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.test_name == "my_test"
        assert result.params == {"param1": 10, "param2": 20}
        assert result.expected is None
        assert result.severity_override is None

    def test_parse_dict_test_def_with_test_key(self):
        """Test parsing a dict test definition with 'test' key."""
        severity_overrides = {}
        test_def = {"test": "my_test", "param1": 10}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.test_name == "my_test"
        assert result.params == {"param1": 10}

    def test_parse_dict_test_def_with_expected(self):
        """Test parsing a dict test definition with expected value."""
        severity_overrides = {}
        test_def = {"name": "my_test", "expected": 42}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.expected == 42

    def test_parse_dict_test_def_with_severity(self):
        """Test parsing a dict test definition with severity."""
        severity_overrides = {}
        test_def = {"name": "my_test", "severity": "warning"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.severity_override == TestSeverity.WARNING

    def test_parse_dict_test_def_with_invalid_severity(self):
        """Test parsing a dict test definition with invalid severity."""
        severity_overrides = {}
        test_def = {"name": "my_test", "severity": "invalid"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.severity_override is None  # Should fall back to None

    def test_parse_dict_test_def_with_severity_override_from_dict(self):
        """Test parsing with severity override from overrides dict."""
        severity_overrides = {"context.my_test": TestSeverity.WARNING}
        test_def = {"name": "my_test"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.severity_override == TestSeverity.WARNING

    def test_parse_dict_test_def_with_severity_override_by_test_name(self):
        """Test parsing with severity override by test name only."""
        severity_overrides = {"my_test": TestSeverity.WARNING}
        test_def = {"name": "my_test"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.severity_override == TestSeverity.WARNING

    def test_parse_dict_test_def_no_params(self):
        """Test parsing a dict test definition with no params."""
        severity_overrides = {}
        test_def = {"name": "my_test"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.params is None

    def test_parse_dict_test_def_empty_params(self):
        """Test parsing a dict test definition with only name/test/severity."""
        severity_overrides = {}
        test_def = {"name": "my_test", "severity": "error"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.params is None

    def test_parse_dict_test_def_missing_name(self):
        """Test parsing a dict test definition missing name."""
        severity_overrides = {}
        test_def = {"param1": 10}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is None

    def test_parse_invalid_type(self):
        """Test parsing an invalid test definition type."""
        severity_overrides = {}
        test_def = 123  # Invalid type

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is None

    def test_parse_dict_test_def_excludes_metadata_fields(self):
        """Test that params exclude name, test, severity, and expected."""
        severity_overrides = {}
        test_def = {
            "name": "my_test",
            "test": "my_test",  # Should be excluded
            "severity": "error",  # Should be excluded
            "expected": 42,  # Should be excluded
            "param1": 10,
            "param2": 20,
        }

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.params == {"param1": 10, "param2": 20}
        assert result.expected == 42
        assert result.severity_override == TestSeverity.ERROR

    def test_parse_dict_test_def_severity_case_insensitive(self):
        """Test that severity parsing is case insensitive."""
        severity_overrides = {}
        test_def = {"name": "my_test", "severity": "WARNING"}

        result = TestDefinitionParser.parse(test_def, severity_overrides, "context")

        assert result is not None
        assert result.severity_override == TestSeverity.WARNING
