"""
Unit tests for MacroParser.
"""

from pathlib import Path


from tee.importer.dbt.parsers import MacroParser


class TestMacroParser:
    """Test cases for MacroParser."""

    def test_discover_macros_basic(self, tmp_path: Path) -> None:
        """Test discovering macro files."""
        # Create macro directory structure
        macros_dir = tmp_path / "macros"
        macros_dir.mkdir()

        # Create a macro file
        macro_file = macros_dir / "test_macro.sql"
        macro_file.write_text("{% macro test_macro() %}SELECT 1{% endmacro %}")

        parser = MacroParser()
        macro_files = parser.discover_macros(tmp_path, ["macros"])

        assert len(macro_files) == 1
        assert "macros/test_macro.sql" in macro_files

    def test_parse_macro_file_simple(self, tmp_path: Path) -> None:
        """Test parsing a simple macro file."""
        macro_file = tmp_path / "test.sql"
        macro_file.write_text(
            "{% macro simple_macro(param1, param2) %}\n"
            "    SELECT {{ param1 }} + {{ param2 }}\n"
            "{% endmacro %}"
        )

        parser = MacroParser()
        macros = parser.parse_macro_file(macro_file)

        assert len(macros) == 1
        assert macros[0]["name"] == "simple_macro"
        assert macros[0]["parameters"] == ["param1", "param2"]
        assert "SELECT" in macros[0]["body"]
        assert not macros[0]["adapter_specific"]

    def test_parse_macro_file_adapter_specific(self, tmp_path: Path) -> None:
        """Test parsing adapter-specific macros."""
        macro_file = tmp_path / "test.sql"
        macro_file.write_text(
            "{% macro postgres__test_macro(param) %}\n    SELECT {{ param }}::text\n{% endmacro %}"
        )

        parser = MacroParser()
        macros = parser.parse_macro_file(macro_file)

        assert len(macros) == 1
        assert macros[0]["name"] == "postgres__test_macro"
        assert macros[0]["adapter_specific"]
        assert macros[0]["adapter"] == "postgres"
        assert macros[0]["base_name"] == "test_macro"

    def test_parse_macro_file_multiple(self, tmp_path: Path) -> None:
        """Test parsing a file with multiple macros."""
        macro_file = tmp_path / "test.sql"
        macro_file.write_text(
            "{% macro macro1() %}SELECT 1{% endmacro %}\n"
            "{% macro macro2(param) %}SELECT {{ param }}{% endmacro %}"
        )

        parser = MacroParser()
        macros = parser.parse_macro_file(macro_file)

        assert len(macros) == 2
        assert macros[0]["name"] == "macro1"
        assert macros[1]["name"] == "macro2"

    def test_parse_all_macros(self, tmp_path: Path) -> None:
        """Test parsing multiple macro files."""
        macros_dir = tmp_path / "macros"
        macros_dir.mkdir()

        macro1 = macros_dir / "macro1.sql"
        macro1.write_text("{% macro macro1() %}SELECT 1{% endmacro %}")

        macro2 = macros_dir / "macro2.sql"
        macro2.write_text("{% macro macro2() %}SELECT 2{% endmacro %}")

        parser = MacroParser()
        macro_files = {"macros/macro1.sql": macro1, "macros/macro2.sql": macro2}
        all_macros = parser.parse_all_macros(macro_files)

        assert len(all_macros) == 2
        assert "macro1" in all_macros
        assert "macro2" in all_macros
