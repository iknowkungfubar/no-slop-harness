# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
