# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] — 2026-05-28

### Added — Phase 1: Core Framework
- Initial CIV (Coordinator-Implementor-Verifier) pipeline orchestration via `PipelineOrchestrator`
- Pydantic schemas for all agent data types: `Task`, `CIVMessage`, `ToolCall`, `SandboxConfig`, `PipelineState`
- Deterministic DAG scheduler using Kahn's algorithm with priority-aware topological sort
- Sandboxed command execution with allowlisting, blocklisting, timeouts, and output truncation
- Tree-sitter powered AST editor with regex fallback and syntax validation
- Automated verifier: pytest runner, ruff linter, mypy type checker, diff validation
- Click-based CLI with `init`, `status`, `list`, `verify`, `report`, `version` commands
- Exception hierarchy: `NoSlopError`, `TaskValidationError`, `CyclicDependencyError`, `SandboxViolationError`, `VerificationError`, `ToolExecutionError`
- `TaskScheduler` and `ResultCollector` for pipeline execution management
- Structured logging configuration module with JSONFormatter and PipelineLogger
- Async pipeline orchestrator with asyncio-based parallel task execution
- Observability module: counters, timers, histograms, MetricsRegistry
- LLM client abstraction with pluggable provider backends and retry logic
- Plugin system with file-path-based discovery, registration, and lifecycle hooks
- PEP 561 `py.typed` marker
- `.pre-commit-config.yaml` with ruff + mypy hooks
- GitHub Actions CI: 3-python matrix + gitleaks security scan
- `[tool.coverage]` with 75% fail-under threshold
- `.github/CODEOWNERS`
- Developer documentation: README, AGENTS.md, CONTRIBUTING.md, ARCHITECTURE.md, CODE_REVIEW.md

### Added — Phase 2: CIV Agents & LLM Integration
- `providers/openai_compatible.py`: OpenAI-compatible provider (LM Studio, OpenRouter, vLLM, Ollama, OpenAI)
- `agents/coordinator.py`: Task decomposition agent with auto-fix for malformed LLM output
- `agents/implementor.py`: Task execution agent with sandboxed file ops and commands
- `agents/verifier.py`: Automated verification via pytest/ruff/mypy + LLM-generated fix suggestions
- `runner.py`: `CIVPipeline` — end-to-end Coordinator→Implementor→Verifier loop with retry
- System prompt templates for all three CIV agents (`prompts/*.txt`)
- `examples/demo.py`: Working end-to-end demo against any OpenAI-compatible API

### Added — Phase 3: Slop-Proof Defense Layer
- `worktree.py`: Git worktree isolation per task (isolate → implement → verify → merge/abort)
- `sdlc.py`: `.sdlc/` context injection system (ADRs, coding standards, patterns, persistent memory)
- `constrained.py`: llguidance grammar-enforced JSON output with schema-to-grammar compiler
- `rag.py`: RAG + self-healing hallucination detection
  - `EmbeddingStore`: TF-IDF vector store with cosine similarity search
  - `HallucinationDetector`: 4 failure patterns (numeric contradiction, negation flip, answer drift, ungrounded assertions)
  - `SelfHealingRAG`: Issue detection, correction prompt generation, entity scrubbing
- `advanced_metrics.py`: Token entropy tracker, variance penalty (P = α·σ²), inter-step timing, bottleneck detection, health assessment
- `tla_bridge.py`: TLA+ formal verification bridge (spec generator, TLC model checker, static fallback, Verifier-compatible gate)

### Fixed
- Removed accidentally committed API keys from LICENSE
- Deduplicated dependency edges in `ingest_tasks`
- SandboxConfig blocklist synced between `sandbox.py` and `schemas.py`
- `TestResult` renamed to `VerificationResult` to fix pytest collection warning
- `str, Enum` migrated to `StrEnum` for Python 3.11+ compatibility
- Plugin `discover_directory` uses `importlib.util.spec_from_file_location` for correct file-path imports
- Worktree merge handles both `main` and `master` default branches
- Negation flip detector no longer double-prepends "use" to captured phrases

## [0.1.0] — 2026-05-10

### Added
- Project bootstrap with CIV pattern specification
- Initial documentation framework (README, AGENTS.md, ARCHITECTURE.md)
- Core schema definitions (Task, CIVMessage, ToolCall)
