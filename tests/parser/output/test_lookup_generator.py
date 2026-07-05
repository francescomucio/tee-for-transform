import shutil
from pathlib import Path

import pytest

from t4t.parser.output.lookup_generator import generate_lookups

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "lookup_conflict_project"


@pytest.fixture
def conflict_project(tmp_path):
    """Copy the lookup-conflict fixture project into a temp dir.

    Both dims declare a hierarchy level named "Region", so lookup generation
    must either raise (default) or auto-resolve by prefixing the dim name.
    Copying keeps generated files out of the repository.
    """
    project = tmp_path / "lookup_conflict_project"
    shutil.copytree(FIXTURE, project)
    return project


class TestLookupGenerator:
    def test_generate_lookups_conflicting_names_raise_error_by_default(self, conflict_project):
        with pytest.raises(ValueError, match="Lookup level name conflict detected"):
            generate_lookups(conflict_project)

    def test_generate_lookups_auto_resolves_conflicting_names(self, conflict_project):
        created = generate_lookups(conflict_project, auto_resolve_level_conflicts=True)

        generated_dir = conflict_project / "models" / "dwh" / "_generated"
        assert generated_dir.exists()
        assert created

        # Conflicting "Region" levels are prefixed with their dim name.
        for safe in ["shop_region", "customer_region"]:
            assert (generated_dir / f"lkp_{safe}.sql").exists()
            assert (generated_dir / f"lkp_{safe}.py").exists()

        # Leaf levels do not produce lookups.
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
