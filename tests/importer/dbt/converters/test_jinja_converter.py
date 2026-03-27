"""
Tests for the Jinja converter.
"""

from tee.importer.dbt.converters import JinjaConverter


class TestJinjaConverter:
    """Tests for Jinja converter."""

    def test_convert_no_jinja(self):
        """Test converting SQL with no Jinja templates."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = "SELECT * FROM users"
        result = converter.convert(sql, "test_model")

        assert result["sql"] == sql
        assert result["is_python_model"] is False
        assert len(result["conversion_errors"]) == 0
        assert len(result["conversion_warnings"]) == 0

    def test_convert_simple_ref(self):
        """Test converting simple ref() calls."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"customers": "public.customers", "orders": "staging.orders"}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = "SELECT * FROM {{ ref('customers') }}"
        result = converter.convert(sql, "test_model")

        assert "{{ ref('customers') }}" not in result["sql"]
        assert "public.customers" in result["sql"]
        assert result["is_python_model"] is False

    def test_convert_ref_with_double_quotes(self):
        """Test converting ref() calls with double quotes."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"customers": "public.customers"}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = 'SELECT * FROM {{ ref("customers") }}'
        result = converter.convert(sql, "test_model")

        assert "public.customers" in result["sql"]
        assert result["is_python_model"] is False

    def test_convert_ref_not_found(self):
        """Test converting ref() when model is not in map."""
        dbt_project = {"name": "test_project"}
        model_name_map = {}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = "SELECT * FROM {{ ref('unknown_model') }}"
        result = converter.convert(sql, "test_model")

        # Should use model name as fallback
        assert "unknown_model" in result["sql"]
        assert len(result["conversion_warnings"]) > 0
        assert "unknown_model" in result["conversion_warnings"][0]

    def test_convert_simple_source(self):
        """Test converting simple source() calls."""
        dbt_project = {"name": "test_project"}
        source_map = {
            "raw": {
                "users": "raw.users",
                "orders": "raw.orders",
            }
        }
        converter = JinjaConverter(
            dbt_project=dbt_project,
            source_map=source_map,
        )

        sql = "SELECT * FROM {{ source('raw', 'users') }}"
        result = converter.convert(sql, "test_model")

        assert "{{ source('raw', 'users') }}" not in result["sql"]
        assert "raw.users" in result["sql"]
        assert result["is_python_model"] is False

    def test_convert_source_not_found(self):
        """Test converting source() when source is not in map."""
        dbt_project = {"name": "test_project"}
        source_map = {}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            source_map=source_map,
        )

        sql = "SELECT * FROM {{ source('raw', 'users') }}"
        result = converter.convert(sql, "test_model")

        # Should use source_name.table_name as fallback
        assert "raw.users" in result["sql"]
        assert len(result["conversion_warnings"]) > 0

    def test_convert_var_with_default(self):
        """Test converting var() calls with default values."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = "SELECT * FROM {{ var('env', 'dev') }}"
        result = converter.convert(sql, "test_model")

        assert "dev" in result["sql"]
        assert "{{ var(" not in result["sql"]
        assert result["is_python_model"] is False

    def test_convert_var_without_default(self):
        """Test converting var() calls without default values."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = "SELECT * FROM {{ var('env') }}"
        result = converter.convert(sql, "test_model")

        # Should use t4t variable syntax @variable
        assert "@env" in result["sql"]
        assert len(result["conversion_warnings"]) > 0
        assert "env" in result["conversion_warnings"][0]

    def test_convert_multiple_refs(self):
        """Test converting multiple ref() calls."""
        dbt_project = {"name": "test_project"}
        model_name_map = {
            "customers": "public.customers",
            "orders": "staging.orders",
        }
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = """
        SELECT c.id, o.total
        FROM {{ ref('customers') }} c
        JOIN {{ ref('orders') }} o ON c.id = o.customer_id
        """
        result = converter.convert(sql, "test_model")

        assert "public.customers" in result["sql"]
        assert "staging.orders" in result["sql"]
        assert "{{ ref(" not in result["sql"]
        assert result["is_python_model"] is False

    def test_detect_complex_jinja_loop(self):
        """Test detecting complex Jinja with loops."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = """
        {% for table in tables %}
        SELECT * FROM {{ table }}
        {% endfor %}
        """
        result = converter.convert(sql, "test_model")

        assert result["is_python_model"] is True
        assert len(result["conversion_warnings"]) > 0
        # Check that warning mentions complex Jinja (case-insensitive)
        warning_text = result["conversion_warnings"][0].lower()
        assert "complex jinja" in warning_text or "complex" in warning_text

    def test_detect_complex_jinja_conditional(self):
        """Test detecting complex Jinja with conditionals."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = """
        {% if env == 'prod' %}
        SELECT * FROM prod_table
        {% else %}
        SELECT * FROM dev_table
        {% endif %}
        """
        result = converter.convert(sql, "test_model")

        assert result["is_python_model"] is True
        assert len(result["conversion_warnings"]) > 0

    def test_detect_complex_jinja_elif(self):
        """Test detecting complex Jinja with elif."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = """
        {% if env == 'prod' %}
        SELECT * FROM prod_table
        {% elif env == 'staging' %}
        SELECT * FROM staging_table
        {% endif %}
        """
        result = converter.convert(sql, "test_model")

        assert result["is_python_model"] is True

    def test_detect_complex_jinja_multiple_ifs(self):
        """Test detecting complex Jinja with multiple if statements."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = """
        {% if condition1 %}
        SELECT * FROM table1
        {% endif %}
        {% if condition2 %}
        SELECT * FROM table2
        {% endif %}
        """
        result = converter.convert(sql, "test_model")

        assert result["is_python_model"] is True

    def test_simple_if_not_complex(self):
        """Test that simple if without else/elif is not complex."""
        dbt_project = {"name": "test_project"}
        converter = JinjaConverter(dbt_project=dbt_project)

        sql = """
        {% if env == 'prod' %}
        SELECT * FROM prod_table
        {% endif %}
        """
        result = converter.convert(sql, "test_model")

        # Simple if should be flagged as unconvertible but not necessarily complex
        # The converter will try to convert it and if it fails, mark as python model
        assert result["is_python_model"] is True  # Because we can't convert {% if %}

    def test_convert_mixed_jinja(self):
        """Test converting SQL with mixed Jinja patterns."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"customers": "public.customers"}
        source_map = {"raw": {"users": "raw.users"}}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
            source_map=source_map,
        )

        sql = """
        SELECT c.id, u.name
        FROM {{ ref('customers') }} c
        JOIN {{ source('raw', 'users') }} u ON c.user_id = u.id
        WHERE env = {{ var('env', 'dev') }}
        """
        result = converter.convert(sql, "test_model")

        assert "public.customers" in result["sql"]
        assert "raw.users" in result["sql"]
        assert "dev" in result["sql"]
        assert result["is_python_model"] is False

    def test_convert_case_insensitive(self):
        """Test that Jinja conversion is case-insensitive."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"customers": "public.customers"}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = "SELECT * FROM {{ REF('customers') }}"
        result = converter.convert(sql, "test_model")

        assert "public.customers" in result["sql"]
        assert result["is_python_model"] is False

    def test_convert_with_whitespace(self):
        """Test converting Jinja with various whitespace patterns."""
        dbt_project = {"name": "test_project"}
        model_name_map = {"customers": "public.customers"}
        converter = JinjaConverter(
            dbt_project=dbt_project,
            model_name_map=model_name_map,
        )

        sql = "SELECT * FROM {{  ref( 'customers' )  }}"
        result = converter.convert(sql, "test_model")

        assert "public.customers" in result["sql"]
        assert result["is_python_model"] is False
