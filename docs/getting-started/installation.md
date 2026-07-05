# Installation

The **supported way to use t4t today** is to install from a clone of the GitHub repository (there is no published PyPI release aligned with these docs yet). The CLI entry point is `t4t`.

## Prerequisites

- Python 3.12+ (see `requires-python` in the repository `pyproject.toml`)
- [uv](https://github.com/astral-sh/uv) (recommended)

## Install from GitHub (recommended)

```bash
git clone https://github.com/francescomucio/tee-for-transform.git
cd tee-for-transform

# Install project + dependencies into .venv (exposes `t4t` via uv run)
uv sync

# Optional: editable install so `t4t` is on PATH when the venv is active
uv pip install -e .
```

Run the CLI:

```bash
uv run t4t --help
```

## PyPI / `pip install` (not available yet)

When a release is published to PyPI, installation may look like `pip install t4t` or `uv add t4t`. Until then, use the clone workflow above.

## Database drivers

Core dependencies (including DuckDB and the Snowflake connector) are already listed in the repository `pyproject.toml` and are installed with `uv sync`. If you add optional backends or trim dependencies for a custom setup:

- **PostgreSQL**: add `psycopg2-binary` (or your preferred driver) to the environment
- **BigQuery**: add `google-cloud-bigquery`

## Verify installation

```python
from t4t.adapters import list_available_adapters

print("t4t import OK")
print("Adapters:", ", ".join(sorted(list_available_adapters())))
```

## Next steps

- [Quick Start](quick-start.md) — create a project with `t4t init`
- [Configuration](configuration.md) — `project.toml` and connection settings
