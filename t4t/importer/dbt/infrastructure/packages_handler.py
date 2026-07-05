"""
dbt packages handler for importer.

Detects and documents dbt package dependencies.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import yaml

from t4t.importer.dbt.constants import PACKAGES_FILE

logger = logging.getLogger(__name__)


class PackagesHandler:
    """Handles dbt package dependencies."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize packages handler.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def discover_packages(self, project_path: Path) -> dict[str, Any]:
        """
        Discover dbt packages from packages.yml or dbt_packages directory.

        Args:
            project_path: Path to dbt project root

        Returns:
            Dictionary with package information
        """
        packages_info: dict[str, Any] = {
            "packages": [],
            "has_packages": False,
            "packages_file": None,
            "warnings": [],
        }

        # Check for packages.yml
        packages_file = project_path / PACKAGES_FILE
        if packages_file.exists():
            packages_info["packages_file"] = str(packages_file)
            try:
                with packages_file.open("r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)

                if isinstance(content, dict) and "packages" in content:
                    packages_list = content["packages"]
                    if isinstance(packages_list, list):
                        packages_info["packages"] = packages_list
                        packages_info["has_packages"] = len(packages_list) > 0

                        if self.verbose:
                            logger.info(f"Found {len(packages_list)} package(s) in {PACKAGES_FILE}")

                        # Extract package names and versions
                        for pkg in packages_list:
                            if isinstance(pkg, dict) and "package" in pkg:
                                pkg_name = pkg["package"]
                                pkg_version = pkg.get("version", "latest")
                                if self.verbose:
                                    logger.info(f"  - {pkg_name} (version: {pkg_version})")

            except Exception as e:
                error_msg = f"Error parsing {PACKAGES_FILE}: {e}"
                packages_info["warnings"].append(error_msg)
                logger.warning(error_msg)

        # Check for dbt_packages directory (installed packages)
        dbt_packages_dir = project_path / "dbt_packages"
        if dbt_packages_dir.exists():
            packages_info["has_installed_packages"] = True
            if self.verbose:
                logger.info(f"Found dbt_packages directory at: {dbt_packages_dir}")

            # Try to detect installed packages
            installed_packages = []
            for item in dbt_packages_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    installed_packages.append(item.name)

            if installed_packages:
                packages_info["installed_packages"] = installed_packages
                if self.verbose:
                    logger.info(f"Detected {len(installed_packages)} installed package(s)")

        if packages_info["has_packages"]:
            packages_info["warnings"].append(
                "This project uses dbt packages. Package macros and models may need to be "
                "manually converted or inlined. Check the import report for details."
            )

        return packages_info

    def get_packages_summary(self, packages_info: dict[str, Any]) -> str:
        """
        Get human-readable summary of packages.

        Args:
            packages_info: Packages information dictionary

        Returns:
            Summary string
        """
        if not packages_info.get("has_packages"):
            return "No dbt packages detected."

        packages = packages_info.get("packages", [])
        if not packages:
            return "dbt packages detected but no package list found."

        lines = ["dbt Packages:"]
        for pkg in packages:
            if isinstance(pkg, dict):
                pkg_name = pkg.get("package", "unknown")
                pkg_version = pkg.get("version", "latest")
                lines.append(f"  - {pkg_name} (version: {pkg_version})")

        return "\n".join(lines)

    def clone_packages(self, project_path: Path, packages_info: dict[str, Any]) -> dict[str, Path]:
        """
        Clone dbt packages to .packages/<name>@<ref>/ directory.

        Args:
            project_path: Path to dbt project root
            packages_info: Packages information from discover_packages()

        Returns:
            Dictionary mapping package names to their cloned paths
        """
        cloned_packages: dict[str, Path] = {}
        packages_dir = project_path / ".packages"
        packages_dir.mkdir(exist_ok=True)

        packages = packages_info.get("packages", [])
        if not packages:
            return cloned_packages

        # Load or create packages.lock
        lock_file = project_path / "packages.lock"
        lock_data: dict[str, Any] = {}
        if lock_file.exists():
            try:
                with lock_file.open("r", encoding="utf-8") as f:
                    lock_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read packages.lock: {e}")

        for pkg in packages:
            if not isinstance(pkg, dict):
                continue

            # Handle different package formats
            pkg_name = None
            pkg_ref = None
            pkg_path = None

            # Git package: git: + revision:/ref:
            if "git" in pkg:
                git_url = pkg["git"]
                pkg_ref = pkg.get("revision") or pkg.get("ref") or "main"
                # Extract package name from git URL
                pkg_name = self._extract_package_name_from_git_url(git_url)

            # Local package: local:
            elif "local" in pkg:
                local_path = Path(pkg["local"]).expanduser()
                if not local_path.is_absolute():
                    local_path = project_path / local_path
                pkg_path = local_path
                pkg_name = local_path.name
                pkg_ref = "local"

            # Hub package: package: + version: (map to Git URL)
            elif "package" in pkg:
                hub_package = pkg["package"]
                version = pkg.get("version")
                # Map to Git URL (simplified - dbt Hub packages are typically on GitHub)
                git_url = self._hub_package_to_git_url(hub_package)
                if git_url:
                    # For Hub packages, versions are tags, not branches
                    # Use version as-is (e.g., "1.1.1")
                    pkg_ref = version or "main"
                    # Extract name from hub package (e.g., "dbt-labs/dbt_utils" -> "dbt_utils")
                    # Use the last part of the package name as the namespace
                    if "/" in hub_package:
                        pkg_name = hub_package.split("/")[-1].replace("-", "_")
                    else:
                        pkg_name = hub_package.replace("-", "_")

            if not pkg_name:
                logger.warning(f"Could not determine package name for: {pkg}")
                continue

            # Check if already cloned (from lock file or existing directory)
            pkg_dir_name = f"{pkg_name}@{pkg_ref}"
            pkg_target = packages_dir / pkg_dir_name

            # Check lock file for commit SHA
            lock_key = pkg_name
            commit_sha = None
            if lock_key in lock_data:
                commit_sha = lock_data[lock_key].get("sha")

            if pkg_path:
                # Local package - create symlink or copy
                if pkg_target.exists():
                    if self.verbose:
                        logger.info(f"Package {pkg_name} already cloned at {pkg_target}")
                else:
                    try:
                        # Create symlink for local packages
                        pkg_target.symlink_to(pkg_path)
                        if self.verbose:
                            logger.info(f"Linked local package {pkg_name} from {pkg_path}")
                    except Exception as e:
                        logger.warning(f"Could not link local package {pkg_name}: {e}")
                cloned_packages[pkg_name] = pkg_target
            else:
                # Git package - clone or checkout
                if pkg_target.exists():
                    if self.verbose:
                        logger.info(f"Package {pkg_name} already cloned at {pkg_target}")
                    # Update lock file with current commit if needed
                    if commit_sha:
                        current_sha = self._get_git_commit_sha(pkg_target)
                        if current_sha and current_sha != commit_sha:
                            if self.verbose:
                                logger.info(
                                    f"Package {pkg_name} commit changed: {commit_sha} -> {current_sha}"
                                )
                            if lock_key in lock_data:
                                lock_data[lock_key]["sha"] = current_sha
                else:
                    # First, check if package exists in dbt_packages (from dbt deps)
                    dbt_packages_dir = project_path / "dbt_packages"
                    dbt_pkg_path = None
                    if dbt_packages_dir.exists():
                        # Look for package in dbt_packages (might have different naming)
                        for item in dbt_packages_dir.iterdir():
                            if item.is_dir() and (
                                pkg_name in item.name.lower()
                                or item.name.lower().replace("-", "_") == pkg_name
                            ):
                                dbt_pkg_path = item
                                break

                    if dbt_pkg_path and dbt_pkg_path.exists():
                        # Use existing dbt_packages installation
                        if self.verbose:
                            logger.info(f"Using existing package from dbt_packages: {dbt_pkg_path}")
                        # Create symlink to dbt_packages version
                        try:
                            if not pkg_target.exists():
                                pkg_target.symlink_to(dbt_pkg_path)
                            cloned_packages[pkg_name] = pkg_target
                            continue
                        except Exception as e:
                            logger.warning(
                                f"Could not link package from dbt_packages {pkg_name}: {e}"
                            )

                    # Try to clone from Git
                    try:
                        # Clone the repository
                        if self.verbose:
                            logger.info(f"Cloning package {pkg_name} from {git_url}@{pkg_ref}")

                        # Check if pkg_ref is a branch (main/master) or a tag (version)
                        is_branch = pkg_ref in ["main", "master", "develop"]

                        if is_branch:
                            # Clone specific branch with shallow clone
                            subprocess.run(
                                [
                                    "git",
                                    "clone",
                                    "--depth",
                                    "1",
                                    "--branch",
                                    pkg_ref,
                                    git_url,
                                    str(pkg_target),
                                ],
                                check=True,
                                capture_output=not self.verbose,
                            )
                        else:
                            # For tags (versions), clone full repo and checkout the tag
                            # Full clone is needed to ensure tags are available
                            subprocess.run(
                                ["git", "clone", git_url, str(pkg_target)],
                                check=True,
                                capture_output=not self.verbose,
                            )

                            # Checkout the tag (version as-is, e.g., "1.1.1")
                            subprocess.run(
                                ["git", "checkout", pkg_ref],
                                cwd=pkg_target,
                                check=True,
                                capture_output=not self.verbose,
                            )

                        # Get commit SHA
                        commit_sha = self._get_git_commit_sha(pkg_target)
                        if commit_sha:
                            if lock_key not in lock_data:
                                lock_data[lock_key] = {}
                            lock_data[lock_key]["sha"] = commit_sha
                            lock_data[lock_key]["git"] = git_url
                            lock_data[lock_key]["ref"] = pkg_ref
                        if self.verbose:
                            logger.info(f"Cloned package {pkg_name} to {pkg_target}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Failed to clone package {pkg_name}: {e}")
                        # Try to use dbt_packages as fallback if available
                        if dbt_pkg_path and dbt_pkg_path.exists():
                            logger.info(
                                f"Falling back to dbt_packages for {pkg_name}: {dbt_pkg_path}"
                            )
                            try:
                                if not pkg_target.exists():
                                    pkg_target.symlink_to(dbt_pkg_path)
                                cloned_packages[pkg_name] = pkg_target
                            except Exception:
                                pass
                        continue
                    except Exception as e:
                        logger.error(f"Error cloning package {pkg_name}: {e}")
                        # Try to use dbt_packages as fallback if available
                        if dbt_pkg_path and dbt_pkg_path.exists():
                            logger.info(
                                f"Falling back to dbt_packages for {pkg_name}: {dbt_pkg_path}"
                            )
                            try:
                                if not pkg_target.exists():
                                    pkg_target.symlink_to(dbt_pkg_path)
                                cloned_packages[pkg_name] = pkg_target
                            except Exception:
                                pass
                        continue

                cloned_packages[pkg_name] = pkg_target

        # Write updated lock file
        if lock_data:
            try:
                with lock_file.open("w", encoding="utf-8") as f:
                    json.dump(lock_data, f, indent=2)
                if self.verbose:
                    logger.info("Updated packages.lock file")
            except Exception as e:
                logger.warning(f"Could not write packages.lock: {e}")

        return cloned_packages

    def _extract_package_name_from_git_url(self, git_url: str) -> str:
        """
        Extract package name from Git URL.

        In dbt, package namespaces are typically the package name from the repo.
        For example: https://github.com/dbt-labs/dbt_utils.git -> dbt_utils
        """
        # Handle various Git URL formats
        # https://github.com/dbt-labs/dbt_utils.git -> dbt_utils
        # git@github.com:dbt-labs/dbt_utils.git -> dbt_utils
        # https://github.com/dbt-labs/dbt_utils -> dbt_utils
        url = git_url.rstrip("/").rstrip(".git")
        if "/" in url:
            parts = url.split("/")
            name = parts[-1]
            # Keep underscores, convert hyphens to underscores for namespace
            # This matches dbt's convention where package namespaces use underscores
            return name.replace("-", "_")
        name = url.split(":")[-1]
        return name.replace("-", "_")

    def _hub_package_to_git_url(self, hub_package: str) -> str | None:
        """
        Convert dbt Hub package name to Git URL.

        Args:
            hub_package: Package name like "dbt-labs/dbt_utils"

        Returns:
            Git URL or None if cannot be determined
        """
        # Most dbt Hub packages are on GitHub
        # Format: owner/package -> https://github.com/owner/package.git
        # Replace underscores with hyphens in the package name
        if "/" in hub_package:
            owner, package = hub_package.split("/", 1)
            # Replace underscores with hyphens in package name
            package_normalized = package.replace("_", "-")
            return f"https://github.com/{owner}/{package_normalized}.git"
        return None

    def _get_git_commit_sha(self, repo_path: Path) -> str | None:
        """Get current commit SHA from a Git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                check=True,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return None
