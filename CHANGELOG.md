# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.1] - 2026-05-10

### Fixed
- Removed `getattr` usage in `ToolExecutor._validate` — uses proper `isinstance` type narrowing.
- Removed dead `self.implementor` field from `Orchestrator.__init__`.
- `_cmd_init` now respects `--config` flag instead of always writing `harness.toml`.
- `InferenceClient._call_with_retry` re-raises the original exception instead of wrapping in `RuntimeError`.
- `merge_to_base` attempts fast-forward via `git fetch` before destructive checkout.
- `ContextManager.save_task_summary` and `save_json` sanitize names to prevent path traversal.
- Hardened command blocking: detects destructive `rm` even with separated flags (`rm -r -f`).
- Removed duplicate `git_repo` fixture from `test_integration.py` (uses shared `conftest.py`).

### Added
- `LICENSE` file (MIT).
- Proper type annotations: `TOOL_REGISTRY`, `TOOL_ARGS_MAP`, callback lists, `ToolHandler` alias.
- `Worktree.__repr__` for debugging.
- `.gitignore` entries for `harness.toml` and `.worktrees/`.

### Removed
- Redundant `requirements.txt` (pyproject.toml is source of truth).
- `test-plan.md` and `test-report.md` session artifacts.

### Changed
- Stale test counts corrected across CHANGELOG and DEVLOG.

## [0.2.0] - 2026-05-10

### Added
- `harness.toml` configuration system (inference, tools, security, logging).
- `harness init` command to generate default config.
- `harness verify` command to health-check inference endpoint.
- `harness info` command to display config and supported AST languages.
- `--version` / `-V` CLI flag.
- `--config` / `-c` CLI flag for custom config path.
- `ContextManager` for `.sdlc/context/` persistent agent memory (markdown + JSON).
- `ToolExecutor` secure wrapper with path validation and command blocking.
- `InferenceClient` retry with exponential backoff and health check.
- `InferenceClient.from_config()` factory method.
- Multi-language AST support: JavaScript, TypeScript, Go, Rust (via optional deps).
- `[languages]` optional dependency group for JS/TS grammars.
- Live TUI display during `harness run` via `rich.live.Live`.
- Orchestrator lifecycle callbacks (`on_task_start`, `on_task_end`).
- Orchestrator automatic context persistence after each task.
- GitHub Actions CI pipeline (lint + test across Python 3.11-3.13).
- `py.typed` marker for PEP 561 compliance.
- Comprehensive README with architecture diagram, CLI reference, Python API examples.
- Integration test suite with mocked inference client (16 tests).
- CLI test suite (10 tests).
- Config test suite (5 tests).
- Context test suite (7 tests).
- Executor/security test suite (14 tests).

### Changed
- Version bumped to 0.2.0.
- `Orchestrator` now accepts `HarnessConfig` and uses `ToolExecutor` for sandboxed tool calls.
- `Implementor` now accepts optional `ToolExecutor` for security-enforced execution.
- `OrchestratorResult` gains `.summary()` method.

## [0.1.0] - 2026-05-10

### Added
- Repository bootstrap structure.
- CIV (Coordinator-Implementor-Verifier) architectural definitions.
- Strict agent rules and constraint guidelines.
- `pyproject.toml` with `uv`-compatible project configuration.
- Pydantic schemas for tool I/O, agent actions, task plans, and verification results.
- Four core tool implementations: `read_file`, `write_file`, `edit_file_ast` (tree-sitter), `bash_execute`.
- `InferenceClient` with dual-path constrained decoding (`response_format` + `guided_json`).
- `WorktreeManager` for per-task git worktree isolation.
- Coordinator, Implementor, and Verifier agent classes.
- Full CIV `Orchestrator` with topological sort, fail-fast, and merge-or-reject lifecycle.
- `rich`-based CLI entry point (`harness run`, `harness plan`).
- `.sdlc/context/` persistent agent memory directory.
- 25 unit tests covering schemas, tools, and git isolation.
