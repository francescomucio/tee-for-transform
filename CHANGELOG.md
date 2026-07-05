# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-07-05

### Added
- CI workflow running the test suite on every push/PR
- Release automation via GitHub Actions, gated on tests passing and a
  tag/version consistency check

### Changed
- Python version policy: t4t deliberately tracks the newest stable Python
  (currently 3.14). The brief floor-lowering to 3.11/3.12 is reverted; the
  CI matrix is wired so future versions can be added as they release.

### Fixed
- CI now tests the intended Python version (uv previously ignored the
  workflow's Python setup in favor of `.python-version`)
- Latent bug: `inspect.FrameType` → `types.FrameType` in
  `parser/shared/inspect_utils.py` (the attribute does not exist; harmless
  under lazy annotation evaluation, but wrong)
- Quickstart: the "Add a Test" step now uses model metadata, which is how
  tests are attached to models (a bare SQL file in `tests/` is not discovered)
- dbt users guide: snapshots map to t4t's SCD2 materialization (was listed
  as unsupported)
- Lookup generator tests no longer depend on an out-of-repo project

## [0.1.2] - 2026-07-05

### Added
- Initial public release
- DuckDB, Snowflake, PostgreSQL, BigQuery adapters
- SQL dialect conversion
- Data quality testing framework
- dbt project import
- OTS (Open Transformation Specification) support
- Incremental materialization
- Documentation site generation
