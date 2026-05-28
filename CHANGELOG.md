# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial CIV (Coordinator-Implementor-Verifier) pipeline orchestration via `PipelineOrchestrator`
- Pydantic schemas for all agent data types: `Task`, `CIVMessage`, `ToolCall`, `SandboxConfig`, `PipelineState`
- Deterministic DAG scheduler using Kahn's algorithm with priority-aware topological sort
- Sandboxed command execution with allowlisting, blocklisting, timeouts, and output truncation
- Tree-sitter powered AST editor with regex fallback and syntax validation
- Automated verifier: pytest runner, ruff linter, mypy type checker, diff validation
- Click-based CLI with `init` and `status` commands
- Exception hierarchy: `NoSlopError`, `TaskValidationError`, `CyclicDependencyError`, `SandboxViolationError`, `VerificationError`, `ToolExecutionError`
- `TaskScheduler` and `ResultCollector` for pipeline execution management
- Structured logging configuration module
- Async pipeline orchestrator with asyncio-based parallel task execution
- Observability module: counters, timers, histograms
- LLM client abstraction with pluggable provider backends
- Plugin system with discovery, registration, and lifecycle hooks
- Comprehensive test suite: 90+ tests across 8 test modules
- Project documentation: README, AGENTS.md, CONTRIBUTING.md, ARCHITECTURE.md

### Fixed
- Removed accidentally committed API keys from LICENSE file

### Changed
- N/A (initial release)

### Deprecated
- N/A (initial release)

### Removed
- N/A (initial release)

### Security
- Sandbox configuration with implicit dangerous command blocklist
- Command allowlisting enforcement
- Timeout enforcement on all sandboxed commands
- Output truncation to prevent memory exhaustion

## [0.1.0] — 2026-05-10

### Added
- Project bootstrap with CIV pattern specification
- Initial documentation framework (README, AGENTS.md, ARCHITECTURE.md)
- Core schema definitions (Task, CIVMessage, ToolCall)
