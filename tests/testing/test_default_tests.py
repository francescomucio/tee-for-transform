from t4t.testing.default_tests import inject_default_tests


class TestInjectDefaultTests:
    def test_disable_all_default_tests(self):
        metadata = {
            "table_type": "dim",
            "schema": [{"name": "shop_id", "datatype": "integer"}],
            "disable_default_tests": True,
        }

        out, warnings = inject_default_tests("dwh.dim_shop", metadata)

        assert warnings == []
        assert out["schema"][0].get("tests") is None

    def test_flat_dim_exactly_one_pk_candidate_injects_primary_key(self):
        metadata = {
            "table_type": "dim",
            "schema": [
                {"name": "shop_id", "datatype": "integer"},
                {"name": "city", "datatype": "string"},
            ],
        }

        out, warnings = inject_default_tests("dwh.dim_shop", metadata)

        assert warnings == []
        shop_col = next(c for c in out["schema"] if c["name"] == "shop_id")
        assert "primary_key" in shop_col.get("tests", [])

    def test_flat_dim_zero_pk_candidates_warns_no_injection(self):
        metadata = {
            "table_type": "dim",
            "schema": [
                {"name": "created_at", "datatype": "timestamp"},
                {"name": "city", "datatype": "string"},
            ],
        }

        out, warnings = inject_default_tests("dwh.dim_shop", metadata)

        assert len(warnings) == 1
        assert all("primary_key" not in (c.get("tests") or []) for c in out["schema"])

    def test_flat_dim_multiple_pk_candidates_warns_no_injection(self):
        metadata = {
            "table_type": "dim",
            "schema": [
                {"name": "shop_id", "datatype": "integer"},
                {"name": "region_id", "datatype": "integer"},
                {"name": "city", "datatype": "string"},
            ],
        }

        out, warnings = inject_default_tests("dwh.dim_shop", metadata)

        assert len(warnings) == 1
        assert all("primary_key" not in (c.get("tests") or []) for c in out["schema"])

    def test_hierarchy_dim_injects_level_tests(self):
        metadata = {
            "table_type": "dim",
            "schema": [
                {"name": "region_id", "datatype": "integer"},
                {"name": "region_name", "datatype": "string"},
                {"name": "shop_id", "datatype": "integer"},
                {"name": "shop_name", "datatype": "string"},
                {"name": "shop_external_id", "datatype": "string"},
            ],
            "hierarchy": {
                "type": "Fixed-Depth Hierarchy",
                "levels": [
                    {
                        "level_number": 1,
                        "name": "Region",
                        "column": "region_name",
                        "primary_key": "region_id",
                    },
                    {
                        "level_number": 2,
                        "name": "Shop",
                        "column": "shop_name",
                        "primary_key": "shop_id",
                        "columns": ["shop_external_id"],
                    },
                ],
            },
        }

        out, warnings = inject_default_tests("dwh.dim_shop", metadata)

        assert warnings == []

        region_col = next(c for c in out["schema"] if c["name"] == "region_id")
        shop_col = next(c for c in out["schema"] if c["name"] == "shop_id")
        assert "primary_key" in region_col.get("tests", [])
        assert "primary_key" in shop_col.get("tests", [])

        # Model-level tests should be present.
        model_tests = out.get("tests", [])
        names = []
        for t in model_tests:
            if isinstance(t, str):
                names.append(t)
            elif isinstance(t, dict):
                names.append(t.get("name"))
        assert "level_uniqueness" in names
        assert "hierarchy_no_split" in names

    def test_fact_with_dimension_injects_relationships(self):
        metadata = {
            "table_type": "fact",
            "schema": [
                {"name": "sale_id", "datatype": "integer"},
                {
                    "name": "sale_date",
                    "datatype": "date",
                    "dimension": "date",
                },
            ],
        }

        out, warnings = inject_default_tests("dwh.fct_sales", metadata)
        assert warnings == []

        sale_date_col = next(c for c in out["schema"] if c["name"] == "sale_date")
        rel_tests = sale_date_col.get("tests", [])
        assert any(
            isinstance(t, dict)
            and t.get("name") == "relationships"
            and t.get("to") == "dwh.dim_date"
            and t.get("field") == "date_id"
            for t in rel_tests
        )

    def test_disable_primary_key_only(self):
        metadata = {
            "table_type": "dim",
            "disable_default_tests": ["primary_key"],
            "schema": [
                {"name": "shop_id", "datatype": "integer"},
                {"name": "city", "datatype": "string"},
            ],
        }

        out, warnings = inject_default_tests("dwh.dim_shop", metadata)
        assert warnings == []
        shop_col = next(c for c in out["schema"] if c["name"] == "shop_id")
        assert "primary_key" not in shop_col.get("tests", [])
