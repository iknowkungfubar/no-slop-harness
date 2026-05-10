# Minimalist Agentic Harness

**Deterministic, local-first LLM orchestration implementing the Coordinator-Implementor-Verifier (CIV) pattern.**

Zero-slop software engineering: every agent output is schema-constrained at the logits level via `llguidance` / structured decoding. No conversational filler. No regex-based code edits — tree-sitter AST manipulation only.

## Core Principles

1. **Token Efficiency** — System prompts < 1,000 tokens per agent.
2. **Constrained Decoding** — All agent ↔ agent communication enforced via JSON schemas injected into the sampling loop.
3. **Local Inference** — Optimized for FOSS models (Qwen-3-Coder, DeepSeek-V4) served via vLLM.
4. **Fail-Fast** — Verification failures trigger immediate rollback, not retry loops.
5. **Git Isolation** — Each task runs in a dedicated git worktree. Verified work merges; failures discard.

## Quick Start

```bash
# Install
uv venv && uv pip install -e ".[dev]"

# Create config (optional — defaults work for local vLLM)
harness init

# Verify your inference endpoint is reachable
harness verify

# Plan a task (Coordinator only)
harness plan "Refactor auth module to use JWT"

# Execute full CIV pipeline
harness run "Add pagination to the /users endpoint"
```

## Architecture

```
User Request
     │
     ▼
┌──────────┐   TaskPlan (JSON DAG)
│Coordinator│──────────────────────┐
└──────────┘                      │
                                  ▼
                    ┌──────────────────┐
                    │ For each Task:   │
                    │  ┌────────────┐  │
                    │  │Implementor │  │  git worktree
                    │  └─────┬──────┘  │  isolation
                    │        │ diff    │
                    │  ┌─────▼──────┐  │
                    │  │  Verifier  │  │
                    │  └─────┬──────┘  │
                    │     pass│fail    │
                    │   merge │ abort  │
                    └─────────────────┘
```

**Agents:**
| Role | Model Target | Capabilities |
|------|-------------|-------------|
| Coordinator | DeepSeek-V4-Pro / Kimi-K2 | Decomposes requests into task DAG. No code, no bash. |
| Implementor | Qwen-3-Coder-30B | Executes tasks via 4 tools. Isolated in git worktree. |
| Verifier | Local compiler + fast LLM | Validates diffs, runs tests. Read-only source access. |

**Four Core Tools:**
| Tool | Description |
|------|-------------|
| `read_file(path)` | Read file contents (with size limit) |
| `write_file(path, content)` | Write file, creating parent dirs |
| `edit_file_ast(path, query, replacement)` | Tree-sitter AST-targeted edit |
| `bash_execute(cmd)` | Run shell command (sandboxed, timeout-enforced) |

## Configuration

Create `harness.toml` in your project root (or use `harness init`):

```toml
[inference]
base_url = "http://localhost:8000/v1"
model = "default"
max_retries = 3
timeout_seconds = 60

[tools]
bash_timeout = 60
max_file_size_bytes = 10485760
blocked_commands = ["rm -rf /", "mkfs"]

[security]
restrict_paths = true
allowed_roots = ["."]

[logging]
level = "INFO"   # DEBUG | INFO | WARNING | ERROR
format = "text"  # "text" | "json"
```

## CLI Reference

```
harness [OPTIONS] COMMAND

Options:
  -V, --version         Show version
  -c, --config FILE     Config file (default: harness.toml)
  --repo PATH           Repository path (default: .)
  -v, --verbose         Debug logging

Commands:
  run PROMPT            Execute full CIV pipeline with live TUI
  plan PROMPT           Generate Coordinator plan only
  init                  Create default harness.toml
  verify                Health-check inference endpoint
  info                  Show config and supported AST languages
```

## Python API

```python
from harness import InferenceClient, Orchestrator, HarnessConfig, load_config

config = load_config("harness.toml")
client = InferenceClient.from_config(config)

orch = Orchestrator(client, repo_path=".", config=config)
result = orch.run("Add error handling to the API layer")

print(result.summary())  # "3 passed, 0 failed, 3 total"
```

## Directory Structure

```
.sdlc/context/       Persistent agent memory (task summaries, JSON state)
src/harness/
  schemas.py         Pydantic models for tools, agents, plans
  tools.py           4 core tool implementations + registry
  client.py          OpenAI-compatible client with retries + constrained decoding
  config.py          TOML config management
  context.py         .sdlc/ context read/write
  executor.py        Secure tool executor (path validation, command blocking)
  agents.py          Coordinator, Implementor, Verifier
  orchestrator.py    Full CIV pipeline with topological sort
  git_isolation.py   Git worktree lifecycle management
  cli.py             CLI entry point with live TUI
tests/               Unit + integration tests
```

## AST Language Support

Python is included by default. Install additional grammars:

```bash
# JavaScript + TypeScript
uv pip install -e ".[languages]"

# Or individually
uv pip install tree-sitter-javascript tree-sitter-typescript
```

Supported extensions: `.py`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.go`, `.rs`

## Development

```bash
uv venv && uv pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Fix lint
ruff check --fix src/ tests/
```

## License

MIT
