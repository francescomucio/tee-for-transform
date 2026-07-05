"""
Tests for the structure converter.
"""

import tempfile
from pathlib import Path

from t4t.importer.dbt.infrastructure import StructureConverter


class TestStructureConverter:
    """Tests for structure converter."""

    def test_create_t4t_structure(self):
        """Test creating t4t project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test_project"

            converter = StructureConverter(
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                verbose=False,
            )
            converter.create_structure()

            # Check directories were created
            assert (target_path / "models").exists()
            assert (target_path / "tests").exists()
            assert (target_path / "seeds").exists()
            assert (target_path / "functions").exists()
            assert (target_path / "data").exists()
            assert (target_path / "output").exists()

    def test_create_ots_structure(self):
        """Test creating OTS project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test_project"

            converter = StructureConverter(
                target_path=target_path,
                output_format="ots",
                preserve_filenames=False,
                verbose=False,
            )
            converter.create_structure()

            # Check directories were created
            assert (target_path / "models").exists()
            assert (target_path / "tests").exists()
            assert (target_path / "seeds").exists()
            assert (target_path / "ots_modules").exists()
            assert (target_path / "data").exists()
            assert (target_path / "output").exists()

            # OTS format should not have functions directory
            assert not (target_path / "functions").exists()

    def test_create_structure_verbose(self):
        """Test creating structure with verbose output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test_project"

            converter = StructureConverter(
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                verbose=True,
            )
            # Should not raise
            converter.create_structure()

            assert (target_path / "models").exists()

    def test_create_structure_preserve_filenames(self):
        """Test that preserve_filenames flag is stored correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test_project"

            converter = StructureConverter(
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=True,
                verbose=False,
            )

            assert converter.preserve_filenames is True
            converter.create_structure()

            assert (target_path / "models").exists()

    def test_create_structure_idempotent(self):
        """Test that creating structure multiple times doesn't fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test_project"

            converter = StructureConverter(
                target_path=target_path,
                output_format="t4t",
                preserve_filenames=False,
                verbose=False,
            )

            # Create structure twice
            converter.create_structure()
            converter.create_structure()

            # Should still work
            assert (target_path / "models").exists()
            assert (target_path / "tests").exists()
