import shutil
from pathlib import Path

import pytest

from tee.parser.output.lookup_generator import generate_lookups


class TestLookupGenerator:
    def test_generate_lookups_conflicting_names_raise_error_by_default(self):
        repo_root = Path(__file__).resolve().parents[3]  # tee-for-transform
        project_root = repo_root.parent  # /home/mucio/tee
        test_project = project_root / "test_project"

        dim_dir = test_project / "models" / "dwh"
        generated_dir = dim_dir / "_generated"
        assert dim_dir.exists()

        # Ensure clean state.
        if generated_dir.exists():
            shutil.rmtree(generated_dir)

        with pytest.raises(ValueError, match="Lookup level name conflict detected"):
            generate_lookups(test_project)

    def test_generate_lookups_auto_resolves_conflicting_names(self):
        repo_root = Path(__file__).resolve().parents[3]  # tee-for-transform
        project_root = repo_root.parent  # /home/mucio/tee
        test_project = project_root / "test_project"

        dim_dir = test_project / "models" / "dwh"
        generated_dir = dim_dir / "_generated"
        assert dim_dir.exists()

        # Ensure clean state.
        if generated_dir.exists():
            shutil.rmtree(generated_dir)

        created = generate_lookups(test_project, auto_resolve_level_conflicts=True)

        assert generated_dir.exists()
        assert created
        for safe in ["shop_region", "customer_region", "category", "subcategory"]:
            assert (generated_dir / f"lkp_{safe}.sql").exists()
            assert (generated_dir / f"lkp_{safe}.py").exists()
        assert not (generated_dir / "lkp_shop.sql").exists()
        assert not (generated_dir / "lkp_shop.py").exists()

        # Validate generated SQL structure (basic checks).
        shop_region_sql = (generated_dir / "lkp_shop_region.sql").read_text(encoding="utf-8")
        assert "select distinct" in shop_region_sql.lower()
        assert "from dwh.dim_shop" in shop_region_sql.lower()
        assert "region_id" in shop_region_sql
        assert "region_name" in shop_region_sql

        # Validate generated metadata basic shape.
        customer_region_py = (generated_dir / "lkp_customer_region.py").read_text(encoding="utf-8")
        assert (
            "'table_type': 'lookup'" in customer_region_py
            or '"table_type": "lookup"' in customer_region_py
        )
        assert (
            "'name': 'customer_region'" in customer_region_py
            or '"name": "customer_region"' in customer_region_py
        )
        assert (
            "'primary_key': 'region_id'" in customer_region_py
            or '"primary_key": "region_id"' in customer_region_py
        )
        assert "'description':" in customer_region_py or '"description":' in customer_region_py
        assert "'fk_to'" in customer_region_py or '"fk_to"' in customer_region_py
        assert (
            "'table': 'dwh.dim_customer'" in customer_region_py
            or '"table": "dwh.dim_customer"' in customer_region_py
        )
        assert (
            "'column': 'region_id'" in customer_region_py
            or '"column": "region_id"' in customer_region_py
        )
