"""
Integration tests for dbt importer using real dbt projects.
"""

import tempfile
from pathlib import Path

import pytest

from t4t.importer.dbt.importer import import_dbt_project
from t4t.importer.detector import ProjectType, detect_project_type


class TestDbtImporterIntegration:
    """Integration tests with real dbt projects."""

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent.parent.parent
            / "examples"
            / "jaffle-shop"
            / "dbt_project.yml"
        ).exists(),
        reason="jaffle-shop example project not found",
    )
    def test_import_jaffle_shop_project(self):
        """Test importing the jaffle-shop example dbt project."""
        jaffle_shop_path = Path(__file__).parent.parent.parent.parent / "examples" / "jaffle-shop"

        # Verify it's a valid dbt project
        project_type = detect_project_type(jaffle_shop_path)
        assert project_type == ProjectType.DBT

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "imported_jaffle_shop"

            # Import the project
            import_dbt_project(
                source_path=jaffle_shop_path,
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Verify basic structure was created
            assert target_path.exists()
            assert (target_path / "models").exists()
            assert (target_path / "tests").exists()
            assert (target_path / "seeds").exists()
            assert (target_path / "functions").exists()
            assert (target_path / "data").exists()
            assert (target_path / "output").exists()

            # Verify seeds directory structure (jaffle-shop has seeds)
            target_path / "seeds"
            # Note: seeds files themselves won't be copied until Phase 2,
            # but the directory should exist

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent.parent.parent
            / "examples"
            / "jaffle-shop"
            / "dbt_project.yml"
        ).exists(),
        reason="jaffle-shop example project not found",
    )
    def test_import_jaffle_shop_project_ots_format(self):
        """Test importing jaffle-shop project in OTS format."""
        jaffle_shop_path = Path(__file__).parent.parent.parent.parent / "examples" / "jaffle-shop"

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "imported_jaffle_shop_ots"

            import_dbt_project(
                source_path=jaffle_shop_path,
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                validate_execution=False,
                verbose=False,
            )

            # Verify OTS structure
            assert (target_path / "ots_modules").exists()
            # Note: functions directory may exist if macros were converted to UDFs
            # OTS format supports functions/UDFs, so this is expected

    @pytest.mark.skipif(
        not (
            Path(__file__).parent.parent.parent.parent
            / "examples"
            / "jaffle-shop"
            / "dbt_project.yml"
        ).exists(),
        reason="jaffle-shop example project not found",
    )
    def test_import_jaffle_shop_project_verbose(self):
        """Test importing jaffle-shop project with verbose output."""
        jaffle_shop_path = Path(__file__).parent.parent.parent.parent / "examples" / "jaffle-shop"

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "imported_jaffle_shop_verbose"

            # Should not raise with verbose=True
            import_dbt_project(
                source_path=jaffle_shop_path,
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                validate_execution=False,
                verbose=True,
            )

            assert (target_path / "models").exists()
