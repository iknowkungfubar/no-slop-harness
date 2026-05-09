# Minimalist Agentic Harness

**Objective:** A deterministic, local-first LLM orchestration framework implementing the Coordinator-Implementor-Verifier (CIV) pattern. Designed for zero-slop, high-fidelity software engineering.

## Core Philosophy
1.  **Token Efficiency:** System prompts < 1,000 tokens.
2.  **Deterministic Output:** All agent-to-agent communication enforced via strict GBNF grammars or JSON schemas (via `llguidance` / `outlines`).
3.  **Local Inference:** Optimized for 4-bit quantized FOSS models (Qwen-3-Coder, DeepSeek-V4).
4.  **Fail-Fast Execution:** Syntax errors or test failures trigger immediate context-aware rollbacks, not endless retry loops.

## Setup Instructions
1. Initialize environment: `uv venv`
2. Install dependencies: `uv pip install -r requirements.txt` (Target minimal dependencies: `vllm`, `llguidance`, `tree-sitter`).
3. Start local inference server exposing OpenAI-compatible endpoints.

## Directory Structure
*   `.sdlc/`: Persistent agent memory and structural context.
*   `src/`: Core implementation logic.
*   `tests/`: Verifier agent validation scripts.
