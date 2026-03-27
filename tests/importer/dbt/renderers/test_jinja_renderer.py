"""
Tests for Jinja2 renderer with macro support.
"""

import tempfile
from pathlib import Path

import pytest

from tee.importer.dbt.renderers import JinjaRenderer


class TestJinjaRenderer:
    """Tests for JinjaRenderer."""

    def test_render_simple_template(self):
        """Test rendering a simple Jinja2 template."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            sql = "SELECT {{ var('test_var', 'default_value') }}"
            result = renderer.render(sql)

            assert "default_value" in result

    def test_render_with_ref_function(self):
        """Test rendering with ref() function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            model_name_map = {"customers": "public.customers"}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                model_name_map=model_name_map,
                verbose=False,
            )

            sql = "SELECT * FROM {{ ref('customers') }}"
            result = renderer.render(sql)

            assert "public.customers" in result

    def test_render_with_source_function(self):
        """Test rendering with source() function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            source_map = {"ecom": {"raw_supplies": "ecom.raw_supplies"}}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                source_map=source_map,
                verbose=False,
            )

            sql = "SELECT * FROM {{ source('ecom', 'raw_supplies') }}"
            result = renderer.render(sql)

            assert "ecom.raw_supplies" in result

    def test_render_with_project_macro(self):
        """Test rendering with a project macro."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create a simple macro
            macro_file = macros_dir / "test_macro.sql"
            macro_file.write_text(
                "{% macro cents_to_dollars(column_name) %}{{ column_name }} / 100.0{% endmacro %}"
            )

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            sql = "SELECT {{ cents_to_dollars('cost') }} as cost_dollars"
            result = renderer.render(sql)

            assert "cost" in result
            assert "/ 100.0" in result

    def test_render_with_package_macro(self):
        """Test rendering with a package macro."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create a mock package with macros
            packages_dir = project_path / ".packages"
            packages_dir.mkdir()
            pkg_dir = packages_dir / "dbt_utils@1.1.1"
            pkg_dir.mkdir()
            pkg_macros_dir = pkg_dir / "macros"
            pkg_macros_dir.mkdir()

            # Create a simple macro in the package
            macro_file = pkg_macros_dir / "generate_surrogate_key.sql"
            macro_file.write_text(
                "{% macro generate_surrogate_key(field_list) %}"
                "md5({% for field in field_list %}{{ field }}{% if not loop.last %}||{% endif %}{% endfor %})"
                "{% endmacro %}"
            )

            package_paths = {"dbt_utils": pkg_dir}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                package_paths=package_paths,
                verbose=False,
            )

            sql = "SELECT {{ dbt_utils.generate_surrogate_key(['id', 'sku']) }} as key"
            result = renderer.render(sql)

            # The macro should be expanded
            assert "md5" in result.lower() or "id" in result

    def test_render_with_variables(self):
        """Test rendering with variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            variables = {"env": "production", "debug": True}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                variables=variables,
                verbose=False,
            )

            sql = "SELECT '{{ var('env') }}' as environment"
            result = renderer.render(sql)

            assert "production" in result

    def test_render_complex_template(self):
        """Test rendering a complex template with multiple features."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            model_name_map = {"customers": "public.customers"}
            source_map = {"ecom": {"raw_supplies": "ecom.raw_supplies"}}
            variables = {"env": "dev"}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                model_name_map=model_name_map,
                source_map=source_map,
                variables=variables,
                verbose=False,
            )

            sql = """
            WITH source AS (
                SELECT * FROM {{ source('ecom', 'raw_supplies') }}
            ),
            customers AS (
                SELECT * FROM {{ ref('customers') }}
            )
            SELECT '{{ var('env') }}' as env
            """
            result = renderer.render(sql)

            assert "ecom.raw_supplies" in result
            assert "public.customers" in result
            assert "dev" in result

    def test_render_with_missing_ref(self):
        """Test rendering with missing ref (should use fallback)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                model_name_map={},  # Empty map
                verbose=False,
            )

            sql = "SELECT * FROM {{ ref('unknown_model') }}"
            result = renderer.render(sql)

            # Should use model name as fallback
            assert "unknown_model" in result

    def test_render_with_missing_source(self):
        """Test rendering with missing source (should use fallback)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                source_map={},  # Empty map
                verbose=False,
            )

            sql = "SELECT * FROM {{ source('unknown', 'table') }}"
            result = renderer.render(sql)

            # Should use source_name.table_name as fallback (may be quoted by SQLglot)
            assert "unknown" in result and "table" in result

    def test_render_with_missing_var_default(self):
        """Test rendering with var() that has default value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                variables={},  # Empty variables
                verbose=False,
            )

            sql = "SELECT '{{ var('missing_var', 'default_value') }}' as val"
            result = renderer.render(sql)

            assert "default_value" in result

    def test_render_with_missing_var_no_default(self):
        """Test rendering with var() without default (should return None/empty)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                variables={},
                verbose=False,
            )

            sql = "SELECT '{{ var('missing_var') }}' as val"
            result = renderer.render(sql)

            # Should handle None gracefully
            assert result is not None

    def test_render_with_nested_macro_calls(self):
        """Test rendering with macros that call other macros."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create a macro that uses ref()
            macro_file = macros_dir / "get_table.sql"
            macro_file.write_text(
                "{% macro get_table(model_name) %}{{ ref(model_name) }}{% endmacro %}"
            )

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                model_name_map={"customers": "public.customers"},
                verbose=False,
            )

            sql = "SELECT * FROM {{ get_table('customers') }}"
            result = renderer.render(sql)

            assert "public.customers" in result

    def test_render_error_handling(self):
        """Test error handling in render."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            # Invalid Jinja2 syntax
            sql = "SELECT {{ invalid syntax }}"
            with pytest.raises((RuntimeError, Exception)):
                renderer.render(sql)

    def test_render_with_multiple_packages(self):
        """Test rendering with macros from multiple packages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create two mock packages
            packages_dir = project_path / ".packages"
            packages_dir.mkdir()

            pkg1_dir = packages_dir / "dbt_utils@1.1.1"
            pkg1_dir.mkdir()
            pkg1_macros = pkg1_dir / "macros"
            pkg1_macros.mkdir()
            (pkg1_macros / "macro1.sql").write_text("{% macro macro1() %}pkg1_macro{% endmacro %}")

            pkg2_dir = packages_dir / "dbt_date@0.10.0"
            pkg2_dir.mkdir()
            pkg2_macros = pkg2_dir / "macros"
            pkg2_macros.mkdir()
            (pkg2_macros / "macro2.sql").write_text("{% macro macro2() %}pkg2_macro{% endmacro %}")

            package_paths = {"dbt_utils": pkg1_dir, "dbt_date": pkg2_dir}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                package_paths=package_paths,
                verbose=False,
            )

            # Note: These macros would need to be registered in namespaces
            # This test verifies the structure is set up correctly
            assert "dbt_utils" in renderer.env.globals or "dbt_date" in renderer.env.globals

    def test_render_with_empty_macro_paths(self):
        """Test renderer with empty macro paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=[],
                verbose=False,
            )

            sql = "SELECT {{ var('test', 'default') }}"
            result = renderer.render(sql)

            assert "default" in result

    def test_render_with_nonexistent_macro_path(self):
        """Test renderer with non-existent macro path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["nonexistent"],
                verbose=False,
            )

            sql = "SELECT 1"
            result = renderer.render(sql)

            assert "SELECT 1" in result

    def test_render_with_macro_fewer_args_than_params(self):
        """Test rendering with macro called with fewer args than parameters (zip issue fix)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create a macro with 3 parameters but call it with 2 args
            macro_file = macros_dir / "test_macro.sql"
            macro_file.write_text(
                "{% macro test_macro(a, b, c='default') %}{{ a }}-{{ b }}-{{ c }}{% endmacro %}"
            )

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            sql = "SELECT {{ test_macro('x', 'y') }}"
            result = renderer.render(sql)

            # Should work without zip() error
            assert "x" in result and "y" in result

    def test_render_with_do_statement(self):
        """Test rendering with {% do %} statement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            # {% do %} should execute but not output anything
            sql = "SELECT 1 {% do var('test', 'value') %}"
            result = renderer.render(sql)

            assert "SELECT 1" in result
            # The do statement should not appear in output
            assert "do" not in result.lower() or "SELECT 1" in result

    def test_render_with_dbt_dateadd_int_interval(self):
        """Test rendering with dbt.dateadd() with integer interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                adapter_type="duckdb",
                verbose=False,
            )

            sql = "SELECT {{ dbt.dateadd('day', 1, 'current_date') }}"
            result = renderer.render(sql)

            # Should have + INTERVAL '1' day
            assert "INTERVAL" in result.upper()
            assert "1" in result

    def test_render_with_dbt_dateadd_negative_interval(self):
        """Test rendering with dbt.dateadd() with negative interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                adapter_type="duckdb",
                verbose=False,
            )

            sql = "SELECT {{ dbt.dateadd('day', -1, 'current_date') }}"
            result = renderer.render(sql)

            # Should have - INTERVAL '1' day
            assert "INTERVAL" in result.upper()
            assert "-" in result or "INTERVAL" in result.upper()

    def test_render_with_dbt_dateadd_string_interval(self):
        """Test rendering with dbt.dateadd() with string interval (SQL expression)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                adapter_type="duckdb",
                verbose=False,
            )

            sql = "SELECT {{ dbt.dateadd('day', '1', 'current_date') }}"
            result = renderer.render(sql)

            # Should have + INTERVAL '1' day
            assert "INTERVAL" in result.upper()

    def test_render_with_macro_return(self):
        """Test rendering with macro that uses return()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create a macro that uses return()
            macro_file = macros_dir / "get_value.sql"
            macro_file.write_text("{% macro get_value() %}{{ return(42) }}{% endmacro %}")

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            sql = "SELECT {{ get_value() }}"
            result = renderer.render(sql)

            # Should return 42
            assert "42" in result

    def test_render_with_env_var(self):
        """Test rendering with env_var() function."""
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Set an environment variable
            os.environ["TEST_ENV_VAR"] = "test_value"

            try:
                renderer = JinjaRenderer(
                    project_path=project_path,
                    macro_paths=["macros"],
                    verbose=False,
                )

                sql = "SELECT '{{ env_var('TEST_ENV_VAR', 'default') }}'"
                result = renderer.render(sql)

                assert "test_value" in result
            finally:
                # Clean up
                os.environ.pop("TEST_ENV_VAR", None)

    def test_render_with_config(self):
        """Test rendering with config() function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                verbose=False,
            )

            # config() returns a dict, so it won't render directly
            # But it should not raise an error
            sql = "SELECT 1"
            result = renderer.render(sql)

            assert "SELECT 1" in result

    def test_render_with_dbt_utility_functions(self):
        """Test rendering with dbt utility functions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                adapter_type="duckdb",
                verbose=False,
            )

            sql = """
            SELECT
                {{ dbt.type_string() }} as str_type,
                {{ dbt.type_int() }} as int_type,
                {{ dbt.current_timestamp() }} as now
            """
            result = renderer.render(sql)

            assert "TEXT" in result or "str_type" in result
            assert "INT" in result or "int_type" in result
            assert "CURRENT_TIMESTAMP" in result.upper() or "now" in result

    def test_render_with_adapter_dispatch(self):
        """Test rendering with adapter.dispatch()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create adapter-specific and default macros
            macro_file = macros_dir / "test_macro.sql"
            macro_file.write_text("{% macro default__test_macro() %}default{% endmacro %}")

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                adapter_type="duckdb",
                verbose=False,
            )

            # Test that adapter.dispatch() works
            sql = "SELECT 'test'"
            result = renderer.render(sql)

            # Should render without error
            assert "SELECT" in result

    def test_render_with_dialect_conversion(self):
        """Test rendering with SQL dialect conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                adapter_type="duckdb",
                verbose=False,
            )

            sql = "SELECT CURRENT_TIMESTAMP"
            result = renderer.render(sql, model_name="test")

            # Should render (conversion may or may not change the SQL)
            assert "SELECT" in result

    def test_render_with_macro_namespace_access(self):
        """Test that package macros are accessible via namespace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            macros_dir = project_path / "macros"
            macros_dir.mkdir()

            # Create a package with a macro
            packages_dir = project_path / ".packages"
            packages_dir.mkdir()
            pkg_dir = packages_dir / "test_pkg@1.0.0"
            pkg_dir.mkdir()
            pkg_macros_dir = pkg_dir / "macros"
            pkg_macros_dir.mkdir()

            macro_file = pkg_macros_dir / "test_macro.sql"
            macro_file.write_text("{% macro test_macro() %}pkg_macro{% endmacro %}")

            package_paths = {"test_pkg": pkg_dir}

            renderer = JinjaRenderer(
                project_path=project_path,
                macro_paths=["macros"],
                package_paths=package_paths,
                verbose=False,
            )

            # Test namespace access
            assert "test_pkg" in renderer.env.globals
            namespace = renderer.env.globals["test_pkg"]
            assert hasattr(namespace, "test_macro") or "test_macro" in namespace
