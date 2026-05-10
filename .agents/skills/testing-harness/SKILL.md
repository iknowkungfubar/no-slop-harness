---
name: testing-harness
description: Test the no-slop-harness CLI and security features end-to-end. Use when verifying CLI commands, security enforcement, config system, or context management changes.
---

# Testing the Harness

## Environment Setup

```bash
cd $REPO_DIR
uv venv && uv pip install -e ".[dev]"
```

The blueprint already handles this, so deps should be pre-installed.

## What Can Be Tested Without an Inference Server

Most features work without a running vLLM/OpenAI server:

| Command | Requires Server? | Expected Behavior |
|---------|-----------------|--------------------|
| `harness --version` | No | Prints `harness <version>` |
| `harness init` | No | Creates `harness.toml` with defaults |
| `harness info` | No | Shows config table with version, model, endpoint, languages |
| `harness verify` | Yes (but testable) | Prints "UNREACHABLE" + exit 1 when no server |
| `harness plan` | Yes | Requires live inference |
| `harness run` | Yes | Requires live inference + git repo |

## CLI Testing (Shell-Based, No Recording)

All CLI testing is done via shell commands. Do NOT record — there is no browser/GUI interaction.

### Key Assertions

1. **Version**: `harness --version` → output matches `__version__` in `src/harness/__init__.py`
2. **Init creates file**: Run in a temp dir, verify `harness.toml` exists with all 4 sections (`[inference]`, `[tools]`, `[security]`, `[logging]`)
3. **Init no-overwrite**: Run init twice, second time prints "harness.toml already exists."
4. **Info defaults**: Table shows Version, Model="default", Endpoint="http://localhost:8000/v1", Max retries=3, Bash timeout=60s, Path restriction=True, AST languages=python
5. **Info custom config**: Create `harness.toml` with custom values, verify they appear in info output
6. **Verify without server**: Output contains "UNREACHABLE", exit code is 1

## Security Testing (Python API)

Test security features via Python one-liners or scripts:

```python
from harness.config import HarnessConfig, SecurityConfig
from harness.executor import ToolExecutor, SecurityViolation
```

### Key Security Assertions

1. **Path restriction**: `restrict_paths=True` + `read_file('/etc/passwd')` → `SecurityViolation("outside allowed roots")`
2. **Command blocking**: `bash_execute('rm -rf /')` → `SecurityViolation("Blocked command")`
3. **SDLC write protection**: `protect_sdlc=True` + `write_file('.sdlc/...')` → `SecurityViolation("cannot modify .sdlc")`
4. **SDLC read allowed**: `protect_sdlc=True` + `read_file('.sdlc/...')` → succeeds (reads are fine)
5. **Cycle detection**: Cyclic task dependencies → `CyclicDependencyError("Cycle detected")`

## Context Persistence Testing

```python
from harness.context import ContextManager
cm = ContextManager(tmp_dir)
cm.save_task_summary('task-1', 'desc', 'completed', 'log')
assert 'task-1' in cm.load()
assert 'completed' in cm.load()
```

## Full Test Suite

```bash
.venv/bin/python -m pytest tests/ -v   # Expect 72+ tests passing
.venv/bin/ruff check src/ tests/        # Expect "All checks passed!"
```

## Limitations

- `harness plan` and `harness run` require a live OpenAI-compatible inference server (e.g., vLLM). These cannot be tested without one.
- Multi-language AST grammars (JS/TS/Go/Rust) require optional packages (`uv pip install -e ".[languages]"`). Only Python grammar is installed by default.
- The `with_root()` worktree path validation fix is covered by unit tests but difficult to test end-to-end without a live server.

## Devin Secrets Needed

No secrets required for offline testing. A running inference server endpoint would be needed for `plan`/`run` testing.
