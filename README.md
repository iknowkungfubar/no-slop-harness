# No-Slop Harness

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-90%20passed-brightgreen.svg)](tests/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Type checking: mypy](https://img.shields.io/badge/type%20checking-mypy-informational.svg)](https://mypy-lang.org/)

**Deterministic, local-first LLM orchestration framework implementing the CIV (Coordinator-Implementor-Verifier) pattern for zero-slop, high-fidelity software engineering.**

## Overview

No-Slop Harness is an agentic framework that enforces structured, verifiable LLM workflows. It rejects the "black-box agent" model in favor of a **three-phase pipeline** where each phase has explicit constraints, validated schemas, and deterministic handoffs.

### The CIV Pattern

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Coordinator │ ──▶ │ Implementor │ ──▶ │  Verifier   │
│   (plan)    │     │  (execute)  │     │  (validate) │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                       │
       └─────────── feedback loop ─────────────┘
```

- **Coordinator**: Decomposes user requests into a DAG of typed `Task` objects
- **Implementor**: Executes tasks using a constrained toolset (`read_file`, `write_file`, `edit_file_ast`, `bash_execute`)
- **Verifier**: Validates output via tests, linting, type checking — rejects slop before it merges

### Key Features

- **Deterministic scheduling** — Kahn's algorithm with priority-aware topological sort
- **Sandboxed execution** — command allowlisting, blocklisting, timeout enforcement, output truncation
- **Structured inter-agent protocol** — `CIVMessage` schema enforces typed communication between phases
- **AST-aware editing** — tree-sitter powered code modifications with syntax validation fallback
- **Pydantic schema enforcement** — every tool call, task, and message is validated at the boundary
- **Zero external dependencies for core** — only pydantic, rich, click, tree-sitter

## Quick Start

### Installation

```bash
pip install no-slop-harness
```

Or from source:

```bash
git clone https://github.com/your-org/no-slop-harness.git
cd no-slop-harness
pip install -e ".[dev]"
```

### Basic Usage

```bash
# Initialize a pipeline session
no-slop init --sandbox-allowlist echo --sandbox-allowlist python

# Check pipeline status
no-slop status
```

### Programmatic Usage

```python
from no_slop_harness.orchestrator import PipelineOrchestrator
from no_slop_harness.schemas import Task, SandboxConfig

# Configure sandbox security
sandbox = SandboxConfig(
    allowed_commands=["echo", "python", "pytest"],
    timeout_seconds=120,
)

# Create pipeline
pipeline = PipelineOrchestrator(sandbox_config=sandbox)

# Ingest tasks (from Coordinator/LLM)
tasks = [
    Task(task_id="add_model", description="Create User model", action="Add SQLAlchemy model"),
    Task(task_id="add_tests", description="Add unit tests", action="Write pytest suite", dependencies=["add_model"]),
]
msg = pipeline.ingest_tasks(tasks)

# Execute and verify each task
while task := pipeline.next_task():
    # ... LLM implements task ...
    pipeline.report_result(task.task_id, result_output, success=True)
    pipeline.verify_task(task.task_id)
    pipeline.verification_complete(task.task_id, passed=True)

print(pipeline.status())
```

## Architecture

```
src/no_slop_harness/
├── __init__.py              # Package version
├── cli.py                   # Click-based CLI entrypoint
├── schemas.py               # Pydantic models (Task, CIVMessage, ToolCall, etc.)
├── orchestrator.py          # CIV PipelineOrchestrator lifecycle
├── dag.py                   # Topological sort + DAG validation
├── pipeline_scheduler.py    # TaskScheduler + ResultCollector
├── sandbox.py               # Sandboxed command execution
├── ast_editor.py            # Tree-sitter AST editor with regex fallback
├── verifier.py              # Test/lint/typecheck runner
├── errors.py                # Exception hierarchy
├── logging_config.py        # Structured logging setup
├── async_orchestrator.py    # Async pipeline for parallel task execution
├── metrics.py               # Observability (counters, timers, histograms)
├── llm_client.py            # LLM provider abstraction
└── plugin.py                # Plugin system for extensibility
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

### Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

### Code Quality

```bash
python -m ruff check src/ tests/
python -m mypy src/ --ignore-missing-imports
```

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Design decisions, data flow, and phase lifecycle
- [AGENTS.md](AGENTS.md) — AI agent operating rules and context conventions
- [CONTRIBUTING.md](CONTRIBUTING.md) — Development workflow and PR process
- [CHANGELOG.md](CHANGELOG.md) — Version history

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
