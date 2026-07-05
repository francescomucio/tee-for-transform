# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-07-05

### Added
- CI workflow with Python version matrix (3.12, 3.13, 3.14)
- Release automation via GitHub Actions, gated on the test matrix and a
  tag/version consistency check

### Changed
- Lowered minimum Python version from 3.14 to 3.12 (3.11 excluded: the code
  uses PEP 701 f-string quote reuse, and 3.11 is close to end of support)

### Fixed
- CI matrix now actually tests each Python version (uv previously pinned all
  jobs to `.python-version`)
- Quickstart: the "Add a Test" step now uses model metadata, which is how
  tests are attached to models (a bare SQL file in `tests/` is not discovered)
- dbt users guide: snapshots map to t4t's SCD2 materialization (was listed
  as unsupported)

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
