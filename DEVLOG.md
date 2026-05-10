# Development Log (Agent Memory)

**Instructions for AI Agents:**
Log significant architectural decisions, environment setup quirks, and resolved blockers here. This file acts as the compressed memory for the project. When your context window approaches its limit, read this file to regain orientation.

---

## [Date: 2026-05-09] - Initialization
*   **Action:** Bootstrapped repository structure.
*   **Decision:** Selected `uv` for dependency management due to speed and deterministic locking.
*   **Decision:** Enforced `llguidance` for all tool calls to guarantee zero-slop structural integrity.
*   **Next Steps:** Agent to begin Phase 1 implementation as per `ARCHITECTURE.md`.

## [Date: 2026-05-10] - Phase 1–4 Implementation
*   **Action:** Implemented all four bootstrap phases from `ARCHITECTURE.md`.
*   **Phase 1:** Created `pyproject.toml`, `requirements.txt`, Pydantic schemas for the four core tools (`read_file`, `write_file`, `edit_file_ast`, `bash_execute`), and tool implementations with a typed registry.
*   **Phase 2:** Built `InferenceClient` wrapping any OpenAI-compatible endpoint. Injects both `response_format` (standard) and `guided_json` (vLLM/llguidance) for logits-level constraint enforcement.
*   **Phase 3:** Implemented `WorktreeManager` for git worktree isolation per task. Built Coordinator, Implementor, and Verifier agent classes. Assembled the full CIV orchestration loop with topological task sorting and fail-fast semantics.
*   **Phase 4:** Created `rich`-based CLI (`harness run`, `harness plan`) with diff-aware table rendering.
*   **Decision:** Used `tree_sitter.QueryCursor` API (v0.25) for AST captures instead of the deprecated `Language.query()` path.
*   **Decision:** Made `vllm` an optional dependency (`[server]` extra) since the harness connects via HTTP API.
*   **Tests:** 25 tests covering schemas, all four tools, and git worktree isolation. All passing.
*   **Next Steps:** Integration tests with a live inference server; extend `edit_file_ast` to support additional languages.

## [Date: 2026-05-10] - Production Readiness
*   **Action:** Hardened entire harness for production deployment.
*   **Config:** Added `harness.toml` configuration via `tomllib` (inference, tools, security, logging sections). `harness init` generates defaults.
*   **Context:** Built `.sdlc/context/` read/write system — persistent agent memory across sessions (markdown + JSON).
*   **Security:** `ToolExecutor` wraps all tool calls with path restriction (allowed_roots) and command blocking (blocked_commands).
*   **Resilience:** `InferenceClient` now retries with exponential backoff, configurable timeouts, and `health_check()` endpoint verification.
*   **Multi-language AST:** Extended `edit_file_ast` to support JS, TS, Go, Rust via optional `tree-sitter-{lang}` packages.
*   **Logging:** Configurable log level and format (text/JSON) via config.
*   **CLI:** Added `--version`, `--config`, `harness init`, `harness verify`, `harness info`. Live TUI during `harness run` via `rich.live`.
*   **CI:** GitHub Actions workflow (lint + test across Python 3.11/3.12/3.13).
*   **Tests:** 66 unit + integration tests, all passing. Lint clean.
*   **Typing:** Added `py.typed` marker for PEP 561 compliance.
