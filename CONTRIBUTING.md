# Contributing to No-Slop Harness

## Development Setup

### Prerequisites
- Python 3.11+
- `pip` 23+
- Git

### First-Time Setup

```bash
# Clone the repository
git clone https://github.com/your-org/no-slop-harness.git
cd no-slop-harness

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev,inference,constrained]"
```

### Verify Installation

```bash
# Run the full test suite
python -m pytest tests/ -v

# Check linting
python -m ruff check src/ tests/

# Check types
python -m mypy src/ --ignore-missing-imports
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/my-feature
# or: fix/my-fix, docs/my-docs, refactor/my-refactor
```

### 2. Make Changes

Follow TDD (Test-Driven Development):
1. Write a failing test
2. Run to verify failure: `python -m pytest tests/test_module.py::test_name -v`
3. Write minimal implementation
4. Run to verify pass
5. Run full suite: `python -m pytest tests/ -v`
6. Commit

### 3. Code Quality Checks

Before submitting a PR, ensure all checks pass:

```bash
# Linting
python -m ruff check src/ tests/

# Auto-fix linting issues
python -m ruff check src/ tests/ --fix

# Type checking
python -m mypy src/ --ignore-missing-imports

# Full test suite
python -m pytest tests/ -v
```

### 4. Commit Messages

Format: `<type>: <imperative description>`

| Type | Use Case |
|------|----------|
| `feat` | New feature or module |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `refactor` | Code restructuring (no behavior change) |
| `test` | Adding or updating tests |
| `chore` | Build, CI, dependencies |
| `security` | Security fixes |

Examples:
```
feat: add async pipeline orchestrator with asyncio
fix: remove exposed API keys from LICENSE
docs: add architecture decision record for plugin system
test: add edge case tests for cyclic dependency detection
```

### 5. Open a Pull Request

1. Push your branch
2. Create a PR against `main`
3. Fill out the PR template (description, testing, checklist)
4. Request review
5. Address review feedback
6. Squash-merge once approved

## Code Style

### Python Conventions

- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Imports**: `from __future__ import annotations` at top of every file
- **Type annotations**: All public functions must have full type annotations
- **Docstrings**: All public modules, classes, and functions must have docstrings
- **Pydantic models**: Always set `model_config = {"extra": "forbid"}`
- **Error handling**: Use the exception hierarchy from `errors.py`, never bare `Exception`

### Example

```python
from __future__ import annotations

from .errors import TaskValidationError


class TaskExecutor:
    """Executes a single task within the CIV pipeline."""

    def __init__(self, timeout: int = 60) -> None:
        """Initialize executor with configurable timeout.

        Args:
            timeout: Maximum execution time in seconds.
        """
        self.timeout = timeout

    def execute(self, task_id: str) -> str:
        """Execute a task by ID.

        Args:
            task_id: The unique task identifier.

        Returns:
            Execution result string.

        Raises:
            TaskValidationError: If the task fails validation.
        """
        ...
```

## Project Structure

```
src/no_slop_harness/   # Source code
tests/                 # Test suite (mirrors src/)
docs/                  # Documentation
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `schemas.py` | All Pydantic data models |
| `orchestrator.py` | CIV pipeline lifecycle |
| `dag.py` | Topological sort + validation |
| `sandbox.py` | Secure command execution |
| `ast_editor.py` | Syntax-aware file editing |
| `verifier.py` | Test/lint/type check runner |
| `cli.py` | CLI entrypoint |
| `errors.py` | Exception hierarchy |
| `pipeline_scheduler.py` | Task scheduling |
| `logging_config.py` | Structured logging |
| `async_orchestrator.py` | Async pipeline |
| `metrics.py` | Observability |
| `llm_client.py` | LLM provider abstraction |
| `plugin.py` | Plugin discovery |

## Testing

### Test Organization

- One test file per source module: `test_<module>.py`
- Class-based organization with descriptive names
- Use `pytest` fixtures for shared setup
- Use `pytest.mark.parametrize` for edge cases

### Running Specific Tests

```bash
# Single test
python -m pytest tests/test_dag.py::TestTopologicalSort::test_linear_chain -v

# Test file
python -m pytest tests/test_dag.py -v

# With coverage
python -m pytest tests/ --cov=src/no_slop_harness --cov-report=term-missing
```

### Writing New Tests

```python
from __future__ import annotations

import pytest
from no_slop_harness.dag import topological_sort, CyclicDependencyError
from no_slop_harness.schemas import Task


class TestNewFeature:
    """Description of what this test class covers."""

    def test_happy_path(self) -> None:
        """Test the expected normal behavior."""
        ...

    def test_edge_case(self) -> None:
        """Test boundary conditions."""
        ...

    def test_error_handling(self) -> None:
        """Test that errors are raised appropriately."""
        with pytest.raises(CyclicDependencyError):
            ...
```

## Release Process

1. Update `CHANGELOG.md` with changes since last release
2. Bump version in `pyproject.toml` and `src/no_slop_harness/__init__.py`
3. Create a release commit: `git commit -m "chore: bump version to X.Y.Z"`
4. Tag the release: `git tag vX.Y.Z`
5. Push: `git push origin main --tags`

## Questions?

Open an issue or start a discussion. We follow a "no question is too basic" policy.
