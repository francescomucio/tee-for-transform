# Contributing to t4t

Thank you for your interest in contributing to t4t! This guide will help you get started.

## Getting Started

### Prerequisites

- **Python 3.11+** - t4t requires Python 3.11 or higher
- **uv** - Fast Python package manager (recommended)
- **Git** - Version control

### Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/francescomucio/tee-for-transform.git
   cd tee-for-transform
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Verify installation:**
   ```bash
   uv run t4t --help
   ```

4. **Install the pre-commit hooks** (mechanical checks run on every commit;
   CI runs the same checks, so this saves round-trips):
   ```bash
   uvx pre-commit install
   ```
   This installs git hooks that run `ruff check`, `ruff format`, and other
   checks automatically before every commit. You can also run them manually:
   ```bash
   uvx pre-commit run --all-files
   ```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Changes

- Write clean, readable code
- Follow existing code style
- Add tests for new features
- Update documentation as needed

### 3. Run Tests

Most day-to-day work should use the **fast suite**, which **excludes live Snowflake E2E** tests. Those tests connect to a real Snowflake warehouse, need credentials, and take **much longer** than everything else combined. Use the **full suite** (including Snowflake E2E) before merging or when you change Snowflake-specific code and need warehouse-level validation.

See **[tests/README.md](https://github.com/francescomucio/tee-for-transform/blob/main/tests/README.md)** for the full rationale, credential setup, and CI notes.

```bash
# Default for local development (no Snowflake credentials required)
uv run pytest tests/ -m "not snowflake_e2e"

# Full suite including Snowflake E2E (requires tests/.snowflake_config.json or env vars; slow)
uv run pytest tests/

# Only Snowflake E2E (debugging Snowflake integration)
uv run pytest tests/ -m snowflake_e2e

# Run with coverage
uv run pytest --cov=t4t --cov-report=html

# Run specific test file
uv run pytest tests/cli/commands/test_run.py

# Run with verbose output
uv run pytest -v
```

### 4. Check Code Quality

```bash
# Lint and format (also run automatically by pre-commit and enforced in CI)
uv run ruff check t4t tests
uv run ruff format t4t tests

# Check for dead code
uv run vulture t4t/
```

### 5. Commit Changes

```bash
git add .
git commit -m "feat: add new feature description"
```

Commit message conventions:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `chore:` - Maintenance

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Style

### Python Style Guide

- Follow PEP 8
- Use type hints
- Write docstrings for all public functions/classes
- Keep functions focused and small
- Use meaningful variable names

### Example

```python
from typing import Optional, List

def execute_model(
    model_name: str,
    sql: str,
    variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a SQL model.

    Args:
        model_name: Name of the model to execute
        sql: SQL query to execute
        variables: Optional variables for SQL substitution

    Returns:
        Dictionary containing execution results

    Raises:
        ExecutionError: If execution fails
    """
    ...
```

### Import Organization

```python
# Standard library
import sys
from pathlib import Path
from typing import Dict, Any

# Third-party
import typer
from pydantic import BaseModel

# Local
from t4t.parser import ProjectParser
from t4t.engine import ExecutionEngine
```

## Testing Guidelines

### Test Coverage

- Aim for 90%+ coverage
- Focus on critical paths
- Test edge cases
- Mock external dependencies

### Writing Tests

```python
import pytest
from unittest.mock import Mock, patch
from t4t.cli.commands import cmd_run

def test_cmd_run_success():
    """Test successful model execution."""
    with patch('t4t.cli.commands.run.ProjectParser') as mock_parser:
        # Setup
        mock_parser.return_value.collect_models.return_value = []

        # Execute
        cmd_run(project_folder="./test_project", verbose=False)

        # Assert
        mock_parser.assert_called_once()
```

### Test Organization

- Mirror source structure: `tests/cli/commands/test_run.py`
- One test file per module
- Use descriptive test names
- Group related tests in classes

## Documentation

### Code Documentation

- Write docstrings for all public APIs
- Use Google-style docstrings
- Include examples for complex functions
- Document parameters and return values

### User Documentation

- Update user guides when adding features
- Add examples for new functionality
- Keep documentation in sync with code
- Use clear, concise language

## Pull Request Process

### Before Submitting

1. **Run all tests:**
   ```bash
   uv run pytest
   ```

2. **Check code quality:**
   ```bash
   uv run ruff check .
   uv run ruff format .
   ```

3. **Update documentation:**
   - Update relevant docs
   - Add examples if needed
   - Update changelog (if applicable)

4. **Write a clear PR description:**
   - What changes were made
   - Why the changes were needed
   - How to test the changes
   - Any breaking changes

### PR Review Process

1. **Automated Checks:**
   - Tests must pass
   - Code quality checks must pass
   - Coverage must not decrease

2. **Code Review:**
   - At least one approval required
   - Address review comments
   - Keep PR focused and small

3. **Merge:**
   - Squash and merge (preferred)
   - Delete branch after merge

## Adding New Features

### New CLI Commands

1. Create command function in `t4t/cli/commands/`
2. Register in `t4t/cli/main.py`
3. Add tests in `tests/cli/commands/`
4. Update CLI reference documentation

### New Database Adapters

1. Create adapter class in `t4t/adapters/`
2. Inherit from `BaseAdapter`
3. Implement required methods
4. Add tests
5. Update adapter documentation

### New Test Types

1. Create test class in `t4t/testing/`
2. Inherit from `TestType`
3. Implement test logic
4. Register in test executor
5. Add tests and documentation

## Reporting Issues

### Bug Reports

Include:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment (Python version, OS, etc.)
- Error messages/logs

### Feature Requests

Include:
- Description of the feature
- Use case
- Proposed solution (if any)
- Alternatives considered

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Provide constructive feedback
- Focus on what's best for the project

## Getting Help

- **Documentation:** Check the [docs](../README.md)
- **Issues:** Open an issue on GitHub
- **Discussions:** Use GitHub Discussions
- **Questions:** Ask in issues or discussions

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md (if applicable)
- Credited in release notes
- Appreciated by the community!

## Development Tools

### Recommended IDE Setup

- **VS Code** with Python extension
- **PyCharm** - Full-featured Python IDE
- **Cursor** - AI-powered editor

### Useful Commands

```bash
# Run tests in watch mode (if available)
uv run pytest-watch

# Generate documentation
uv run mkdocs serve

# Run specific test
uv run pytest tests/cli/commands/test_run.py::test_cmd_run_success
```

## Project Structure

```
tee-for-transform/
├── t4t/                 # Main package
│   ├── cli/            # CLI commands
│   ├── parser/         # SQL parsing
│   ├── engine/         # Execution engine
│   ├── adapters/       # Database adapters
│   └── testing/        # Testing framework
├── tests/              # Test files
├── docs/               # Documentation
├── examples/           # Example projects
└── pyproject.toml      # Project configuration
```

## Questions?

If you have questions about contributing:
- Check existing documentation
- Open an issue for discussion
- Ask in GitHub Discussions

Thank you for contributing to t4t! 🎉
