"""
Unit tests for MacroConverter.
"""

from pathlib import Path

from t4t.importer.dbt.converters import MacroConverter


class TestMacroConverter:
    """Test cases for MacroConverter."""

    def test_can_convert_simple_macro(self, tmp_path: Path) -> None:
        """Test that simple macros can be converted."""
        converter = MacroConverter(target_path=tmp_path)

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "SELECT {{ param1 }} * 2",
            "adapter_specific": False,
            "adapter": None,
            "file": str(tmp_path / "test.sql"),
        }

        assert converter._can_convert_macro(macro_def)

    def test_cannot_convert_complex_macro(self, tmp_path: Path) -> None:
        """Test that complex macros cannot be converted."""
        converter = MacroConverter(target_path=tmp_path)

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "{% for item in items %}SELECT {{ item }}{% endfor %}",
            "adapter_specific": False,
            "adapter": None,
            "file": str(tmp_path / "test.sql"),
        }

        assert not converter._can_convert_macro(macro_def)

    def test_convert_macro_to_udf(self, tmp_path: Path) -> None:
        """Test converting a macro to UDF."""
        converter = MacroConverter(target_path=tmp_path)

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "SELECT {{ param1 }} * 2",
            "adapter_specific": False,
            "adapter": None,
            "file": str(tmp_path / "macros" / "test.sql"),
        }

        converter._convert_macro_to_udf(macro_def, [macro_def])

        # Check that SQL file was created
        sql_file = tmp_path / "functions" / "public" / "test_macro.sql"
        assert sql_file.exists()

        # Check that Python metadata file was created
        py_file = tmp_path / "functions" / "public" / "test_macro.py"
        assert py_file.exists()

        # Check SQL content
        sql_content = sql_file.read_text()
        assert "CREATE OR REPLACE FUNCTION" in sql_content
        assert "test_macro" in sql_content

    def test_convert_macros_summary(self, tmp_path: Path) -> None:
        """Test converting multiple macros and getting summary."""
        converter = MacroConverter(target_path=tmp_path)

        all_macros = {
            "simple_macro": [
                {
                    "name": "simple_macro",
                    "base_name": "simple_macro",
                    "parameters": ["param"],
                    "body": "SELECT {{ param }}",
                    "adapter_specific": False,
                    "adapter": None,
                    "file": str(tmp_path / "test.sql"),
                }
            ],
            "complex_macro": [
                {
                    "name": "complex_macro",
                    "base_name": "complex_macro",
                    "parameters": [],
                    "body": "{% for x in items %}{{ x }}{% endfor %}",
                    "adapter_specific": False,
                    "adapter": None,
                    "file": str(tmp_path / "test2.sql"),
                }
            ],
        }

        results = converter.convert_macros(all_macros)

        assert results["converted"] == 1
        assert results["unconvertible"] == 1
        assert results["total"] == 2

    def test_default_schema_configurable(self, tmp_path: Path) -> None:
        """Test that default schema can be configured."""
        converter = MacroConverter(target_path=tmp_path, default_schema="custom_schema")

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "SELECT {{ param1 }}",
            "adapter_specific": False,
            "adapter": None,
            "file": str(tmp_path / "test.sql"),
        }

        converter._convert_macro_to_udf(macro_def, [macro_def])

        # Check that function was created in custom schema
        sql_file = tmp_path / "functions" / "custom_schema" / "test_macro.sql"
        assert sql_file.exists()

    def test_target_dialect_conversion(self, tmp_path: Path) -> None:
        """Test that SQL is converted to target dialect."""
        converter = MacroConverter(target_path=tmp_path, target_dialect="snowflake")

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "SELECT {{ param1 }}",
            "adapter_specific": False,
            "adapter": None,
            "file": str(tmp_path / "test.sql"),
        }

        converter._convert_macro_to_udf(macro_def, [macro_def])

        # Check SQL file was created
        sql_file = tmp_path / "functions" / "public" / "test_macro.sql"
        assert sql_file.exists()

        # SQLGlot may convert the syntax, but function should exist
        sql_content = sql_file.read_text()
        assert "test_macro" in sql_content

    def test_extract_description_from_comments(self, tmp_path: Path) -> None:
        """Test that descriptions are extracted from macro comments."""
        converter = MacroConverter(target_path=tmp_path)

        # Create a macro file with comments
        macro_file = tmp_path / "macros" / "test_macro.sql"
        macro_file.parent.mkdir(parents=True)
        macro_file.write_text(
            "{# This is a test macro description #}\n"
            "{% macro test_macro(param1) %}\n"
            "SELECT {{ param1 }}\n"
            "{% endmacro %}\n"
        )

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "SELECT {{ param1 }}",
            "adapter_specific": False,
            "adapter": None,
            "file": str(macro_file),
        }

        description = converter._extract_description_from_macro(macro_def)
        assert "test macro description" in description

    def test_extract_description_fallback(self, tmp_path: Path) -> None:
        """Test that description falls back to generic if no comment found."""
        converter = MacroConverter(target_path=tmp_path)

        macro_file = tmp_path / "macros" / "test_macro.sql"
        macro_file.parent.mkdir(parents=True)
        macro_file.write_text(
            "{% macro test_macro(param1) %}\nSELECT {{ param1 }}\n{% endmacro %}\n"
        )

        macro_def = {
            "name": "test_macro",
            "base_name": "test_macro",
            "parameters": ["param1"],
            "body": "SELECT {{ param1 }}",
            "adapter_specific": False,
            "adapter": None,
            "file": str(macro_file),
        }

        description = converter._extract_description_from_macro(macro_def)
        assert description == "Function converted from dbt macro"

    def test_normalize_dialect_postgresql_to_postgres(self, tmp_path: Path) -> None:
        """Test that dialect name is normalized correctly."""
        converter = MacroConverter(target_path=tmp_path, target_dialect="postgresql")

        # Should normalize to "postgres" for SQLGlot
        assert converter.target_dialect == "postgres"

    def test_normalize_dialect_unknown(self, tmp_path: Path) -> None:
        """Test that unknown dialects are lowercased."""
        converter = MacroConverter(target_path=tmp_path, target_dialect="CUSTOM_DIALECT")

        # Should lowercase unknown dialects
        assert converter.target_dialect == "custom_dialect"
