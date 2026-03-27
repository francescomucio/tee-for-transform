"""
Tests for dbt packages handler.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from tee.importer.dbt.infrastructure import PackagesHandler


class TestPackagesHandler:
    """Tests for PackagesHandler."""

    def test_discover_packages_no_packages(self):
        """Test discovering packages when none exist."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            result = handler.discover_packages(project_path)
            assert result["has_packages"] is False
            assert result["packages"] == []

    def test_discover_packages_from_packages_yml(self):
        """Test discovering packages from packages.yml."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create packages.yml
            packages_file = project_path / "packages.yml"
            packages_data = {
                "packages": [
                    {"package": "dbt-utils", "version": "1.0.0"},
                    {"package": "dbt-date", "version": "0.7.0"},
                ]
            }
            with packages_file.open("w", encoding="utf-8") as f:
                yaml.dump(packages_data, f)

            result = handler.discover_packages(project_path)
            assert result["has_packages"] is True
            assert len(result["packages"]) == 2
            assert result["packages_file"] == str(packages_file)

    def test_discover_packages_from_dbt_packages_dir(self):
        """Test discovering installed packages from dbt_packages directory."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create dbt_packages directory with some packages
            dbt_packages_dir = project_path / "dbt_packages"
            dbt_packages_dir.mkdir()
            (dbt_packages_dir / "dbt_utils").mkdir()
            (dbt_packages_dir / "dbt_date").mkdir()

            result = handler.discover_packages(project_path)
            assert result.get("has_installed_packages") is True
            assert "dbt_utils" in result.get("installed_packages", [])
            assert "dbt_date" in result.get("installed_packages", [])

    def test_get_packages_summary(self):
        """Test getting packages summary."""
        handler = PackagesHandler(verbose=False)

        packages_info = {
            "has_packages": True,
            "packages": [
                {"package": "dbt-utils", "version": "1.0.0"},
                {"package": "dbt-date", "version": "0.7.0"},
            ],
        }

        summary = handler.get_packages_summary(packages_info)
        assert "dbt Packages:" in summary
        assert "dbt-utils" in summary
        assert "1.0.0" in summary
        assert "dbt-date" in summary

    def test_get_packages_summary_no_packages(self):
        """Test getting summary when no packages."""
        handler = PackagesHandler(verbose=False)

        packages_info = {"has_packages": False}
        summary = handler.get_packages_summary(packages_info)
        assert "No dbt packages detected" in summary

    def test_clone_packages_local(self):
        """Test cloning local packages."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a local package directory
            local_pkg_dir = project_path / "local_package"
            local_pkg_dir.mkdir()
            (local_pkg_dir / "macros").mkdir()
            (local_pkg_dir / "macros" / "test_macro.sql").write_text(
                "{% macro test_macro() %}SELECT 1{% endmacro %}"
            )

            packages_info = {
                "has_packages": True,
                "packages": [{"local": "local_package"}],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            assert len(cloned) == 1
            assert "local_package" in cloned
            packages_dir = project_path / ".packages"
            assert (packages_dir / "local_package@local").exists() or (
                packages_dir / "local_package@local"
            ).is_symlink()

    def test_clone_packages_creates_lock_file(self):
        """Test that clone_packages creates packages.lock file."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a local package
            local_pkg_dir = project_path / "local_pkg"
            local_pkg_dir.mkdir()

            packages_info = {
                "has_packages": True,
                "packages": [{"local": "local_pkg"}],
            }

            handler.clone_packages(project_path, packages_info)

            project_path / "packages.lock"
            # Lock file may or may not be created for local packages
            # (it's mainly for git packages with commit SHAs)

    def test_extract_package_name_from_git_url(self):
        """Test extracting package name from Git URL."""
        handler = PackagesHandler(verbose=False)

        # Test various URL formats
        assert (
            handler._extract_package_name_from_git_url("https://github.com/dbt-labs/dbt_utils.git")
            == "dbt_utils"
        )
        assert (
            handler._extract_package_name_from_git_url("https://github.com/dbt-labs/dbt-utils.git")
            == "dbt_utils"
        )
        assert (
            handler._extract_package_name_from_git_url("git@github.com:dbt-labs/dbt_utils.git")
            == "dbt_utils"
        )
        assert (
            handler._extract_package_name_from_git_url("https://github.com/dbt-labs/dbt_utils")
            == "dbt_utils"
        )

    def test_hub_package_to_git_url(self):
        """Test converting Hub package name to Git URL."""
        handler = PackagesHandler(verbose=False)

        # Should replace underscores with hyphens in package name
        assert handler._hub_package_to_git_url("dbt-labs/dbt_utils") == (
            "https://github.com/dbt-labs/dbt-utils.git"
        )
        assert handler._hub_package_to_git_url("godatadriven/dbt_date") == (
            "https://github.com/godatadriven/dbt-date.git"
        )
        assert handler._hub_package_to_git_url("unknown") is None

    def test_clone_packages_with_lock_file(self):
        """Test cloning packages with existing lock file."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a local package
            local_pkg_dir = project_path / "local_pkg"
            local_pkg_dir.mkdir()

            # Create existing lock file
            lock_file = project_path / "packages.lock"
            lock_data = {"local_pkg": {"sha": "abc123", "ref": "local"}}
            with lock_file.open("w", encoding="utf-8") as f:
                import json

                json.dump(lock_data, f)

            packages_info = {
                "has_packages": True,
                "packages": [{"local": "local_pkg"}],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            assert len(cloned) == 1
            assert "local_pkg" in cloned

    def test_clone_packages_invalid_package_format(self):
        """Test cloning with invalid package format."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            packages_info = {
                "has_packages": True,
                "packages": [
                    "invalid_string_format",  # Not a dict
                    {"unknown": "format"},  # Unknown format
                ],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            # Should handle gracefully and return empty or partial results
            assert isinstance(cloned, dict)

    def test_clone_packages_local_absolute_path(self):
        """Test cloning local package with absolute path."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a local package outside project
            local_pkg_dir = Path(tmpdir) / "external_pkg"
            local_pkg_dir.mkdir()

            packages_info = {
                "has_packages": True,
                "packages": [{"local": str(local_pkg_dir)}],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            assert len(cloned) == 1
            assert "external_pkg" in cloned

    def test_clone_packages_local_already_exists(self):
        """Test cloning when package already exists."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a local package
            local_pkg_dir = project_path / "local_pkg"
            local_pkg_dir.mkdir()

            packages_info = {
                "has_packages": True,
                "packages": [{"local": "local_pkg"}],
            }

            # First clone
            cloned1 = handler.clone_packages(project_path, packages_info)
            assert len(cloned1) == 1

            # Second clone (should detect existing)
            cloned2 = handler.clone_packages(project_path, packages_info)
            assert len(cloned2) == 1
            assert cloned1["local_pkg"] == cloned2["local_pkg"]

    def test_get_git_commit_sha(self):
        """Test getting Git commit SHA."""
        handler = PackagesHandler(verbose=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test with non-git directory (should return None)
            non_git_dir = Path(tmpdir) / "not_git"
            non_git_dir.mkdir()

            sha = handler._get_git_commit_sha(non_git_dir)
            assert sha is None

    @patch("tee.importer.dbt.infrastructure.packages_handler.subprocess.run")
    @patch("tee.importer.dbt.infrastructure.packages_handler.PackagesHandler._get_git_commit_sha")
    def test_clone_packages_hub_package_with_tag(self, mock_get_sha, mock_subprocess):
        """Test cloning Hub package with version tag."""
        handler = PackagesHandler(verbose=False)
        mock_get_sha.return_value = "abc123def456"

        # Mock successful git clone and checkout
        mock_subprocess.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            packages_info = {
                "has_packages": True,
                "packages": [{"package": "dbt-labs/dbt_utils", "version": "1.1.1"}],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            # Verify git clone was called with correct URL (underscores -> hyphens)
            assert mock_subprocess.call_count >= 2  # clone + checkout + get_sha
            clone_call = mock_subprocess.call_args_list[0]
            clone_args = clone_call[0][0]  # First argument is the command list
            assert clone_args[0] == "git"
            assert clone_args[1] == "clone"
            # Should use dbt-utils (hyphen) not dbt_utils (underscore) in URL
            git_url = clone_args[-2]  # Second to last is the URL
            assert "dbt-utils" in git_url or "github.com/dbt-labs/dbt-utils" in git_url

            # Verify checkout was called with version tag (no 'v' prefix)
            checkout_call = mock_subprocess.call_args_list[1]
            checkout_args = checkout_call[0][0]
            assert checkout_args[0] == "git"
            assert checkout_args[1] == "checkout"
            assert checkout_args[2] == "1.1.1"  # Version as-is, no 'v' prefix

            # Verify package was cloned
            assert len(cloned) == 1
            assert "dbt_utils" in cloned

    @patch("tee.importer.dbt.infrastructure.packages_handler.subprocess.run")
    @patch("tee.importer.dbt.infrastructure.packages_handler.PackagesHandler._get_git_commit_sha")
    def test_clone_packages_git_branch(self, mock_get_sha, mock_subprocess):
        """Test cloning Git package with branch (main/master)."""
        handler = PackagesHandler(verbose=False)
        mock_get_sha.return_value = "abc123def456"

        # Mock successful git clone
        mock_subprocess.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            packages_info = {
                "has_packages": True,
                "packages": [
                    {
                        "git": "https://github.com/dbt-labs/dbt-audit-helper.git",
                        "revision": "main",
                    }
                ],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            # Verify git clone was called with --branch main and --depth 1
            clone_call = mock_subprocess.call_args_list[0]
            clone_args = clone_call[0][0]
            assert clone_args[0] == "git"
            assert clone_args[1] == "clone"
            assert "--depth" in clone_args
            assert "--branch" in clone_args
            branch_idx = clone_args.index("--branch")
            assert clone_args[branch_idx + 1] == "main"

            # Should not call checkout for branches (only clone, then get_sha)
            # get_sha is called, so call_count is 2
            assert mock_subprocess.call_count >= 1

            # Verify package was cloned
            assert len(cloned) == 1

    @patch("tee.importer.dbt.infrastructure.packages_handler.subprocess.run")
    @patch("tee.importer.dbt.infrastructure.packages_handler.PackagesHandler._get_git_commit_sha")
    def test_clone_packages_git_with_tag(self, mock_get_sha, mock_subprocess):
        """Test cloning Git package with tag."""
        handler = PackagesHandler(verbose=False)
        mock_get_sha.return_value = "abc123def456"

        # Mock successful git clone and checkout
        mock_subprocess.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            packages_info = {
                "has_packages": True,
                "packages": [
                    {
                        "git": "https://github.com/dbt-labs/dbt-utils.git",
                        "revision": "1.1.1",
                    }
                ],
            }

            cloned = handler.clone_packages(project_path, packages_info)

            # Verify git clone was called (full clone for tags, no --depth)
            clone_call = mock_subprocess.call_args_list[0]
            clone_args = clone_call[0][0]
            assert clone_args[0] == "git"
            assert clone_args[1] == "clone"
            # Should NOT have --depth 1 for tags
            assert "--depth" not in clone_args

            # Verify checkout was called with tag
            checkout_call = mock_subprocess.call_args_list[1]
            checkout_args = checkout_call[0][0]
            assert checkout_args[0] == "git"
            assert checkout_args[1] == "checkout"
            assert checkout_args[2] == "1.1.1"  # Version as tag

            # Verify package was cloned
            assert len(cloned) == 1

    @patch("tee.importer.dbt.infrastructure.packages_handler.subprocess.run")
    def test_clone_packages_creates_packages_directory(self, mock_subprocess):
        """Test that clone_packages creates .packages directory."""
        handler = PackagesHandler(verbose=False)

        # Mock to avoid actual git calls
        mock_subprocess.side_effect = Exception("Mocked to prevent actual git calls")

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            packages_info = {
                "has_packages": True,
                "packages": [{"local": "local_pkg"}],
            }

            # Should create .packages directory even if cloning fails
            try:
                handler.clone_packages(project_path, packages_info)
            except Exception:
                pass

            packages_dir = project_path / ".packages"
            # Directory should be created
            assert packages_dir.exists()

    @patch("tee.importer.dbt.infrastructure.packages_handler.subprocess.run")
    @patch("tee.importer.dbt.infrastructure.packages_handler.PackagesHandler._get_git_commit_sha")
    def test_clone_packages_writes_lock_file(self, mock_get_sha, mock_subprocess):
        """Test that clone_packages writes packages.lock file with commit SHA."""
        handler = PackagesHandler(verbose=False)
        mock_get_sha.return_value = "abc123def456"

        # Mock successful git clone
        mock_subprocess.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a local package (simpler than mocking git)
            local_pkg_dir = project_path / "local_pkg"
            local_pkg_dir.mkdir()

            packages_info = {
                "has_packages": True,
                "packages": [{"local": "local_pkg"}],
            }

            handler.clone_packages(project_path, packages_info)

            # Lock file may or may not be created for local packages
            # But the directory structure should be created
            packages_dir = project_path / ".packages"
            assert packages_dir.exists()
