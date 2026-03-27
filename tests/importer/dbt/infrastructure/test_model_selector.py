"""
Unit tests for DbtModelSelector.
"""

from pathlib import Path


from tee.importer.dbt.infrastructure import DbtModelSelector


class TestDbtModelSelector:
    """Test cases for DbtModelSelector."""

    def test_no_patterns_selects_all(self) -> None:
        """Test that with no patterns, all models are selected."""
        selector = DbtModelSelector()
        assert selector.is_selected("customers", [])
        assert selector.is_selected("orders", ["tag1"])
        assert selector.is_selected("products", None)

    def test_select_by_name_exact_match(self) -> None:
        """Test selecting models by exact name."""
        selector = DbtModelSelector(select_patterns=["customers"])
        assert selector.is_selected("customers", [])
        assert not selector.is_selected("orders", [])

    def test_select_by_name_wildcard(self) -> None:
        """Test selecting models by wildcard pattern."""
        selector = DbtModelSelector(select_patterns=["staging_*"])
        assert selector.is_selected("staging_customers", [])
        assert selector.is_selected("staging_orders", [])
        assert not selector.is_selected("marts_customers", [])

    def test_select_by_tag(self) -> None:
        """Test selecting models by tag."""
        selector = DbtModelSelector(select_patterns=["tag:nightly"])
        assert selector.is_selected("customers", ["nightly"])
        assert selector.is_selected("orders", ["nightly", "other"])
        assert not selector.is_selected("products", ["daily"])

    def test_select_by_name_or_tag(self) -> None:
        """Test selecting models by name or tag (OR logic)."""
        selector = DbtModelSelector(select_patterns=["customers", "tag:nightly"])
        assert selector.is_selected("customers", [])  # Matches name
        assert selector.is_selected("orders", ["nightly"])  # Matches tag
        assert selector.is_selected("customers", ["nightly"])  # Matches both
        assert not selector.is_selected("products", ["daily"])  # Matches neither

    def test_exclude_by_name(self) -> None:
        """Test excluding models by name."""
        selector = DbtModelSelector(exclude_patterns=["deprecated"])
        assert not selector.is_selected("deprecated", [])
        assert selector.is_selected("customers", [])

    def test_exclude_by_tag(self) -> None:
        """Test excluding models by tag."""
        selector = DbtModelSelector(exclude_patterns=["tag:test"])
        assert not selector.is_selected("customers", ["test"])
        assert selector.is_selected("customers", ["production"])

    def test_select_and_exclude(self) -> None:
        """Test combining select and exclude patterns."""
        selector = DbtModelSelector(
            select_patterns=["staging_*"], exclude_patterns=["tag:deprecated"]
        )
        assert selector.is_selected("staging_customers", [])
        assert not selector.is_selected("staging_customers", ["deprecated"])
        assert not selector.is_selected("marts_customers", [])

    def test_exclude_overrides_select(self) -> None:
        """Test that exclude takes precedence over select."""
        selector = DbtModelSelector(
            select_patterns=["customers"], exclude_patterns=["tag:deprecated"]
        )
        assert not selector.is_selected("customers", ["deprecated"])
        assert selector.is_selected("customers", [])

    def test_filter_models(self) -> None:
        """Test filtering a dictionary of model files."""
        model_files = {
            "models/staging/customers.sql": Path("models/staging/customers.sql"),
            "models/staging/orders.sql": Path("models/staging/orders.sql"),
            "models/marts/products.sql": Path("models/marts/products.sql"),
        }
        model_tags_map = {
            "customers": ["nightly"],
            "orders": [],
            "products": ["deprecated"],
        }

        selector = DbtModelSelector(select_patterns=["customers", "orders"])
        filtered = selector.filter_models(model_files, model_tags_map)
        assert len(filtered) == 2
        assert "models/staging/customers.sql" in filtered
        assert "models/staging/orders.sql" in filtered
        assert "models/marts/products.sql" not in filtered

    def test_filter_models_by_tag(self) -> None:
        """Test filtering models by tag."""
        model_files = {
            "models/customers.sql": Path("models/customers.sql"),
            "models/orders.sql": Path("models/orders.sql"),
            "models/products.sql": Path("models/products.sql"),
        }
        model_tags_map = {
            "customers": ["nightly"],
            "orders": ["daily"],
            "products": [],
        }

        selector = DbtModelSelector(select_patterns=["tag:nightly"])
        filtered = selector.filter_models(model_files, model_tags_map)
        assert len(filtered) == 1
        assert "models/customers.sql" in filtered

    def test_filter_models_exclude(self) -> None:
        """Test filtering models with exclude pattern."""
        model_files = {
            "models/customers.sql": Path("models/customers.sql"),
            "models/orders.sql": Path("models/orders.sql"),
            "models/products.sql": Path("models/products.sql"),
        }
        model_tags_map = {
            "customers": ["deprecated"],
            "orders": [],
            "products": [],
        }

        selector = DbtModelSelector(exclude_patterns=["tag:deprecated"])
        filtered = selector.filter_models(model_files, model_tags_map)
        assert len(filtered) == 2
        assert "models/customers.sql" not in filtered
        assert "models/orders.sql" in filtered
        assert "models/products.sql" in filtered

    def test_case_insensitive_name_matching(self) -> None:
        """Test that name matching is case-insensitive."""
        selector = DbtModelSelector(select_patterns=["Customers"])
        assert selector.is_selected("customers", [])
        assert selector.is_selected("Customers", [])

    def test_case_insensitive_tag_matching(self) -> None:
        """Test that tag matching is case-insensitive."""
        selector = DbtModelSelector(select_patterns=["tag:Nightly"])
        assert selector.is_selected("customers", ["nightly"])
        assert selector.is_selected("customers", ["Nightly"])
