# no-slop-harness — Agent Context

## Overview

no-slop-harness is a deterministic, local-first LLM orchestration framework implementing the CIV (Coordinator-Implementor-Verifier) pattern for zero-slop, high-fidelity software engineering.

## Tech Stack

- **Language:** Python 3.11+
- **Build System:** hatchling
- **Linting:** ruff (select E, F, I, N, W, UP, B, S)
- **Type Checking:** mypy (strict-lite)
- **Testing:** pytest with pytest-asyncio
- **Schema Enforcement:** pydantic v2
- **CLI:** click

## Architecture

```
User Request → Coordinator (decomposes into DAG of Task objects)
                    ↓
             Implementor (executes tasks with constrained toolset)
                    ↓
              Verifier (validates via tests, lint, typecheck)
                    ↓
              Feedback loop → Coordinator adjusts plan
```

## Key Patterns

- **CIV Pattern**: All inter-agent messages use `CIVMessage` schema — typed communication between phases
- **Topological Sort**: Kahn's algorithm with priority-aware scheduling for task DAG
- **Sandboxed Execution**: Command allowlisting, blocklisting, timeout enforcement, output truncation
- **Graceful Degradation**: Tree-sitter → regex, llguidance → prompt-based JSON enforcement

## Repository Structure

```
src/no_slop_harness/
├── agents/               # CIV agent implementations
│   ├── coordinator.py    # Task decomposition agent
│   ├── implementor.py    # Task execution agent
│   └── verifier.py       # Automated verification agent
├── providers/            # LLM provider backends
│   └── openai_compatible.py
├── orchestrator.py       # CIV PipelineOrchestrator lifecycle
├── runner.py             # End-to-end CIV pipeline runner
├── schemas.py            # Pydantic models
├── dag.py                # Topological sort + DAG validation
├── sandbox.py            # Sandboxed command execution
├── verifier.py           # Test/lint/typecheck runner
├── ast_editor.py         # AST-based editing (tree-sitter or regex)
├── constrained.py        # Grammar-enforced JSON output
├── sdlc.py               # SDLC context injection
├── rag.py                # RAG + hallucination detection
├── worktree.py           # Git worktree isolation
├── tla_bridge.py         # TLA+ formal verification bridge
├── plugin.py             # Plugin system
├── metrics.py            # Observability
├── cli.py                # Click CLI
└── ...
```

## Conventions

- **Type hints**: Required on all public functions
- **Docstrings**: Google-style for all public modules and functions
- **Tests**: One test file per source module, mirror structure
- **Optional deps**: try/except with _HAS_X pattern for graceful degradation
- **Commits**: `feat:|fix:|refactor:|test:|docs:|chore: [scope] — [message]`

## Quality Gates

- `ruff check src/ tests/` — 0 errors
- `ruff format src/ tests/ --check` — passes
- `mypy src/` — 0 errors
- `pytest tests/ -q` — all pass
