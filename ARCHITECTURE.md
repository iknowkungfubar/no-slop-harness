# System Architecture: The CIV Pattern

## 1. Top-Level Design
The framework operates on a strict, synchronous lifecycle:
`User Prompt -> Coordinator -> Implementor (Isolated) -> Verifier -> Commit/Reject`

## 2. Component Specifications

### 2.1 Inference Layer
*   **Engine:** `vLLM` optimized for KV-cache reuse across agent loops.
*   **Hardware Profile:** Optimized for consumer hardware (e.g., AMD RX 7900 GRE class).
*   **Quantization:** GGUF Q4_K_M for maximum memory bandwidth efficiency.

### 2.2 Constrained Decoding (Slop Prevention)
*   **Library:** `llguidance`
*   **Rule:** The orchestrator will physically block any output token that violates the defined schema for tool calls. No "json parsing" retry loops allowed; the generation is constrained at the logits level.

### 2.3 Tool Registry (The "Tiny Core")
Agents are granted exactly four tools, heavily typed:
1.  `read_file(path: str) -> str`
2.  `write_file(path: str, content: str) -> bool`
3.  `edit_file_ast(path: str, node_target: str, replacement: str) -> bool` (Tree-sitter powered, prevents regex slop)
4.  `bash_execute(cmd: str) -> Tuple[int, str, str]`

## 3. Implementation Plan (Bootstrap Sequence)
*   **Phase 1:** Setup `uv` project, define minimal Pydantic schemas for the four core tools.
*   **Phase 2:** Implement the OpenAI-compatible client wrapper that automatically injects `llguidance` state machines into the sampling parameters.
*   **Phase 3:** Build the Git isolation layer (each Implementor task runs in a separate git worktree).
*   **Phase 4:** Construct the CLI / TUI interface (flicker-free, diff-based).
