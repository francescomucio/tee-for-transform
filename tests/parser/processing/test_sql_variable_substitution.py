"""
Tests for SQL variable substitution functionality.
"""

import pytest

from tee.parser.processing.variable_substitution import (
    _format_sql_value,
    get_nested_value,
    substitute_sql_variables,
    validate_sql_variables,
)
from tee.parser.shared.exceptions import VariableSubstitutionError


class TestSQLVariableSubstitution:
    """Test SQL variable substitution functionality."""

    def test_format_sql_value_string(self):
        """Test formatting string values for SQL."""
        assert _format_sql_value("hello") == "'hello'"
        assert _format_sql_value("O'Connor") == "'O''Connor'"
        assert _format_sql_value("") == "''"
        assert _format_sql_value("test'value") == "'test''value'"

    def test_format_sql_value_numbers(self):
        """Test formatting numeric values for SQL."""
        assert _format_sql_value(123) == "123"
        assert _format_sql_value(98.5) == "98.5"
        assert _format_sql_value(0) == "0"
        assert _format_sql_value(-42) == "-42"

    def test_format_sql_value_booleans(self):
        """Test formatting boolean values for SQL."""
        assert _format_sql_value(True) == "TRUE"
        assert _format_sql_value(False) == "FALSE"

    def test_format_sql_value_none(self):
        """Test formatting None values for SQL."""
        assert _format_sql_value(None) == "NULL"

    def test_format_sql_value_other_types(self):
        """Test formatting other types for SQL."""
        assert _format_sql_value({"key": "value"}) == "'{''key'': ''value''}'"
        assert _format_sql_value([1, 2, 3]) == "'[1, 2, 3]'"

    def test_get_nested_value_simple(self):
        """Test getting simple nested values."""
        data = {"key": "value"}
        assert get_nested_value(data, "key") == "value"

    def test_get_nested_value_nested(self):
        """Test getting nested values with dot notation."""
        data = {"config": {"database": {"host": "localhost"}}}
        assert get_nested_value(data, "config.database.host") == "localhost"
        assert get_nested_value(data, "config.database") == {"host": "localhost"}

    def test_get_nested_value_missing_key(self):
        """Test getting nested values with missing keys."""
        data = {"key": "value"}
        with pytest.raises(KeyError, match="Key 'missing' not found"):
            get_nested_value(data, "missing")

    def test_get_nested_value_missing_nested_key(self):
        """Test getting nested values with missing nested keys."""
        data = {"config": {"database": {"host": "localhost"}}}
        with pytest.raises(KeyError, match="Key 'config.missing' not found"):
            get_nested_value(data, "config.missing")

    def test_substitute_at_variables_simple(self):
        """Test substituting simple @ variables."""
        sql = "SELECT * FROM users WHERE name = @name AND age = @age"
        variables = {"name": "John", "age": 25}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE name = 'John' AND age = 25"
        assert result == expected

    def test_substitute_at_variables_with_defaults(self):
        """Test substituting @ variables with default values."""
        sql = "SELECT * FROM users WHERE status = @status:active AND role = @role:user"
        variables = {"status": "inactive"}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE status = 'inactive' AND role = 'user'"
        assert result == expected

    def test_substitute_at_variables_nested(self):
        """Test substituting @ variables with nested object access."""
        sql = "SELECT * FROM users WHERE host = @config.database.host"
        variables = {"config": {"database": {"host": "localhost"}}}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE host = 'localhost'"
        assert result == expected

    def test_substitute_jinja_variables_simple(self):
        """Test substituting {{ variable }} syntax."""
        sql = "SELECT * FROM users WHERE name = {{ name }} AND age = {{ age }}"
        variables = {"name": "Jane", "age": 30}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE name = 'Jane' AND age = 30"
        assert result == expected

    def test_substitute_jinja_variables_with_defaults(self):
        """Test substituting {{ variable }} syntax with defaults."""
        sql = "SELECT * FROM users WHERE status = {{ status:active }} AND role = {{ role:user }}"
        variables = {"status": "inactive"}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE status = 'inactive' AND role = 'user'"
        assert result == expected

    def test_substitute_jinja_variables_nested(self):
        """Test substituting {{ variable }} syntax with nested access."""
        sql = "SELECT * FROM users WHERE host = {{ config.database.host }}"
        variables = {"config": {"database": {"host": "localhost"}}}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE host = 'localhost'"
        assert result == expected

    def test_substitute_mixed_syntax(self):
        """Test substituting both @ and {{ }} syntax in the same SQL."""
        sql = "SELECT * FROM users WHERE name = @name AND status = {{ status:active }}"
        variables = {"name": "Bob", "status": "inactive"}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE name = 'Bob' AND status = 'inactive'"
        assert result == expected

    def test_substitute_complex_sql(self):
        """Test substituting variables in complex SQL statements."""
        sql = """
        SELECT u.id, u.name, u.environment, u.debug_mode
        FROM users u
        WHERE u.environment = @env
          AND u.debug_mode = @debug
          AND u.created_at > @start_date
          AND u.host = @config.database.host
          AND u.status = {{ status:active }}
          AND u.version = @version:1.0.0
        """
        variables = {
            "env": "prod",
            "debug": True,
            "start_date": "2024-01-01",
            "config": {"database": {"host": "localhost"}},
            "status": "inactive",
        }
        result = substitute_sql_variables(sql, variables)

        # Check that all variables were substituted
        assert "@env" not in result
        assert "@debug" not in result
        assert "@start_date" not in result
        assert "@config.database.host" not in result
        assert "{{ status:active }}" not in result
        assert "@version:1.0.0" not in result

        # Check that values are properly formatted
        assert "'prod'" in result
        assert "TRUE" in result
        assert "'2024-01-01'" in result
        assert "'localhost'" in result
        assert "'inactive'" in result

    def test_substitute_missing_variable_no_default(self):
        """Test that missing variable without default returns original SQL."""
        sql = "SELECT * FROM users WHERE name = @name"
        variables = {"age": 25}

        result = substitute_sql_variables(sql, variables)
        # Should return original SQL unchanged when variable is missing and no default
        assert result == sql

    def test_substitute_missing_variable_with_default(self):
        """Test using default when variable is missing."""
        sql = "SELECT * FROM users WHERE name = @name:Unknown"
        variables = {"age": 25}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE name = 'Unknown'"
        assert result == expected

    def test_substitute_empty_variables(self):
        """Test substitution with empty variables dict."""
        sql = "SELECT * FROM users WHERE name = @name:Default"
        variables = {}
        result = substitute_sql_variables(sql, variables)
        # When no variables are provided, defaults are not processed
        expected = "SELECT * FROM users WHERE name = @name:Default"
        assert result == expected

    def test_substitute_no_variables(self):
        """Test substitution when no variables are provided."""
        sql = "SELECT * FROM users WHERE name = @name"
        result = substitute_sql_variables(sql, {})
        # Should return original SQL when no variables provided
        assert result == sql

    def test_validate_sql_variables_valid(self):
        """Test validation with valid variables."""
        sql = "SELECT * FROM users WHERE name = @name AND age = @age"
        variables = {"name": "John", "age": 25}
        result = validate_sql_variables(sql, variables)
        assert result["valid"] is True
        assert result["missing_vars"] == []
        assert "name" in result["referenced_vars"]
        assert "age" in result["referenced_vars"]

    def test_validate_sql_variables_missing(self):
        """Test validation with missing variables."""
        sql = "SELECT * FROM users WHERE name = @name AND age = @age"
        variables = {"name": "John"}

        with pytest.raises(VariableSubstitutionError, match="Missing variables"):
            validate_sql_variables(sql, variables)

    def test_validate_sql_variables_with_defaults(self):
        """Test validation with default values."""
        sql = "SELECT * FROM users WHERE name = @name AND age = @age:25"
        variables = {"name": "John"}
        result = validate_sql_variables(sql, variables)
        assert result["valid"] is True
        assert result["missing_vars"] == []

    def test_validate_sql_variables_mixed_syntax(self):
        """Test validation with mixed @ and {{ }} syntax."""
        sql = "SELECT * FROM users WHERE name = @name AND status = {{ status:active }}"
        variables = {"name": "John"}
        result = validate_sql_variables(sql, variables)
        assert result["valid"] is True
        assert result["missing_vars"] == []

    def test_validate_sql_variables_nested(self):
        """Test validation with nested variable access."""
        sql = "SELECT * FROM users WHERE host = @config.database.host"
        variables = {"config": {"database": {"host": "localhost"}}}
        result = validate_sql_variables(sql, variables)
        assert result["valid"] is True
        assert result["missing_vars"] == []

    def test_validate_sql_variables_unused(self):
        """Test validation with unused variables."""
        sql = "SELECT * FROM users WHERE name = @name"
        variables = {"name": "John", "age": 25, "status": "active"}
        result = validate_sql_variables(sql, variables)
        assert result["valid"] is True
        # Order may vary, so check that both unused vars are present
        assert set(result["unused_vars"]) == {"age", "status"}

    def test_sql_injection_protection(self):
        """Test that SQL injection is prevented through proper escaping."""
        sql = "SELECT * FROM users WHERE name = @name"
        variables = {"name": "'; DROP TABLE users; --"}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE name = '''; DROP TABLE users; --'"
        assert result == expected
        # The single quotes should be properly escaped
        assert "''" in result

    def test_special_characters_in_variables(self):
        """Test handling of special characters in variable values."""
        sql = "SELECT * FROM users WHERE description = @desc"
        variables = {"desc": "User with 'quotes' and \"double quotes\""}
        result = substitute_sql_variables(sql, variables)
        expected = (
            "SELECT * FROM users WHERE description = 'User with ''quotes'' and \"double quotes\"'"
        )
        assert result == expected

    def test_boolean_values_in_sql(self):
        """Test boolean values are properly formatted for SQL."""
        sql = "SELECT * FROM users WHERE active = @active AND verified = @verified"
        variables = {"active": True, "verified": False}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE active = TRUE AND verified = FALSE"
        assert result == expected

    def test_numeric_values_in_sql(self):
        """Test numeric values are properly formatted for SQL."""
        sql = "SELECT * FROM users WHERE id = @id AND score = @score"
        variables = {"id": 123, "score": 98.5}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE id = 123 AND score = 98.5"
        assert result == expected

    def test_null_values_in_sql(self):
        """Test NULL values are properly formatted for SQL."""
        sql = "SELECT * FROM users WHERE data = @data"
        variables = {"data": None}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE data = NULL"
        assert result == expected

    def test_complex_nested_objects(self):
        """Test complex nested objects in variables."""
        sql = "SELECT * FROM users WHERE config = @config"
        variables = {
            "config": {"database": {"host": "localhost", "port": 5432}, "cache": {"enabled": True}}
        }
        result = substitute_sql_variables(sql, variables)
        # Should convert complex object to string and quote it
        assert result.startswith("SELECT * FROM users WHERE config = '")
        assert "localhost" in result
        assert "5432" in result
        assert "True" in result

    def test_multiple_occurrences_same_variable(self):
        """Test multiple occurrences of the same variable."""
        sql = "SELECT @name, @name FROM users WHERE name = @name"
        variables = {"name": "John"}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT 'John', 'John' FROM users WHERE name = 'John'"
        assert result == expected

    def test_whitespace_handling_in_jinja_syntax(self):
        """Test proper handling of whitespace in {{ }} syntax."""
        sql = "SELECT * FROM users WHERE name = {{ name }} AND status = {{ status }}"
        variables = {"name": "John", "status": "active"}
        result = substitute_sql_variables(sql, variables)
        expected = "SELECT * FROM users WHERE name = 'John' AND status = 'active'"
        assert result == expected

    def test_edge_case_empty_string_default(self):
        """Test edge case with empty string as default value."""
        sql = "SELECT * FROM users WHERE name = @name:"
        variables = {}
        result = substitute_sql_variables(sql, variables)
        # When no variables are provided, defaults are not processed
        expected = "SELECT * FROM users WHERE name = @name:"
        assert result == expected

    def test_edge_case_boolean_default(self):
        """Test edge case with boolean as default value."""
        sql = "SELECT * FROM users WHERE active = @active:true"
        variables = {}
        result = substitute_sql_variables(sql, variables)
        # When no variables are provided, defaults are not processed
        expected = "SELECT * FROM users WHERE active = @active:true"
        assert result == expected
