# Release Process

This document describes the process for releasing new versions of t4t to PyPI.

## Versioning

t4t follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (SemVer):

- **MAJOR** version for incompatible API changes
- **MINOR** version for new functionality in a backward-compatible manner
- **PATCH** version for backward-compatible bug fixes

Pre-release versions use suffixes like `-alpha`, `-beta`, `-rc1`.

## Release Steps

### 1. Prepare the Release

1. Ensure all changes for the release are merged to `main`.
2. Update `CHANGELOG.md`:
   - Move changes from `[Unreleased]` to a new version section
   - Add the release date
   - Review for completeness
3. Update the version in `pyproject.toml`:
   ```bash
   # Example: bump from 0.1.2 to 0.1.3
   # Edit pyproject.toml version field
   ```
4. Commit the version bump and changelog update:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore: bump version to X.Y.Z"
   ```

### 2. Create a Tag

Create and push a signed tag matching the version:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

### 3. Automated Release

Pushing a tag `v*.*.*` triggers the [release workflow](../.github/workflows/release.yml), which:

1. **Builds** the package with `uv build`
2. **Publishes** to PyPI using trusted publishing (OIDC) via `pypa/gh-action-pypi-publish`
3. **Creates a GitHub Release** with auto-generated release notes and the built artifacts attached

### 4. Verify

1. Check that the [GitHub Release](https://github.com/francescomucio/tee-for-transform/releases) was created
2. Verify the package is published on [PyPI](https://pypi.org/project/t4t/)
3. Test installation:
   ```bash
   pip install t4t
   t4t --version
   ```

## Required Secrets

The release workflow uses **trusted publishing (OIDC)** via `pypa/gh-action-pypi-publish` with `attestations: false`. No PyPI token is needed — the workflow authenticates directly through GitHub OIDC.

No repository secrets are required for publishing. If you need to configure trusted publishing for a new PyPI project, follow the [PyPI trusted publishing guide](https://docs.pypi.org/trusted-publishers/).

## Hotfix Releases

For urgent bug fixes:

1. Create a branch from the release tag:
   ```bash
   git checkout -b hotfix/vX.Y.Z+1 vX.Y.Z
   ```
2. Apply the fix
3. Bump the patch version
4. Tag and push as above

## Pre-release Versions

For testing before a full release:

1. Set version to `X.Y.Zrc1` or `X.Y.Zb1` in `pyproject.toml`
2. Tag as `vX.Y.Zrc1`
3. Push the tag — the workflow will publish to PyPI as a pre-release
