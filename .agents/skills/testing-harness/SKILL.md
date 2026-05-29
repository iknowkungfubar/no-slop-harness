---
name: testing-harness
description: Test the no-slop-harness CLI app end-to-end. Use when verifying security, CLI, or core functionality changes.
---

# Testing no-slop-harness

This is a CLI-only Python application (no web UI). All testing is done via shell commands — no screen recording needed.

## Environment Setup

```bash
cd /home/ubuntu/repos/no-slop-harness
# Dependencies should already be installed via blueprint
# If not:
uv venv && uv pip install -e ".[dev]"
```

## Running Tests

```bash
# Full test suite
.venv/bin/python -m pytest tests/ -v

# Lint
.venv/bin/ruff check src/ tests/
```

## Key Testing Areas

### 1. Security Command Blocking

Test via Python imports. Commands that SHOULD raise `SecurityViolation` are
caught before execution and never reach `subprocess.run`:

```python
from harness.config import HarnessConfig
from harness.executor import ToolExecutor, SecurityViolation

cfg = HarnessConfig()
ex = ToolExecutor(cfg, '/tmp')

# These SHOULD raise SecurityViolation (blocked before execution):
ex.execute('bash_execute', {'cmd': 'rm -rf ./data'})       # combined flags
ex.execute('bash_execute', {'cmd': 'rm -r -f /tmp/data'})   # separated flags
ex.execute('bash_execute', {'cmd': 'rm --recursive /tmp'})  # long flag
ex.execute('bash_execute', {'cmd': 'shred /dev/sda'})       # unconditional block
ex.execute('bash_execute', {'cmd': 'wipefs /dev/sda'})      # unconditional block
```

**WARNING**: Commands that should NOT raise SecurityViolation WILL actually
execute via `subprocess.run(shell=True)`. Only use harmless commands in
"allowed" examples:

```python
# This should NOT raise — but it WILL execute the command via subprocess.
# Use only harmless commands here (e.g., echo, true, listing files).
ex.execute('bash_execute', {'cmd': 'echo safe'})
```

### 2. Context Sanitization

```python
from harness.context import ContextManager
import tempfile

with tempfile.TemporaryDirectory() as d:
    cm = ContextManager(d)
    path = cm.save_task_summary('../../etc/passwd', 'evil', 'failed')
    assert path.resolve().parent == cm.context_dir.resolve()  # must stay inside
    assert '..' not in path.name          # no path traversal chars

    # Deep traversal must also be contained
    path = cm.save_task_summary('../../../../../../../../tmp/evil', 'deep', 'failed')
    assert path.resolve().parent == cm.context_dir.resolve()
```

### 3. CLI Commands

```bash
# Version check
harness --version
# Expected: harness X.Y.Z

# Init with custom config path (-c must come BEFORE subcommand)
harness -c custom.toml init
# Expected: creates custom.toml, NOT harness.toml

# Info (shows config summary)
harness info

# Verify (checks inference endpoint — will show UNREACHABLE without server)
harness verify
```

**Important**: The `-c`/`--config` flag is on the main parser, not the subcommand parser. It must come before the subcommand: `harness -c custom.toml init`, NOT `harness init -c custom.toml`.

### 4. Features Requiring Live Server

`harness plan` and `harness run` require a running vLLM or OpenAI-compatible inference server. These cannot be tested without one. If a server is available, set `base_url` in `harness.toml` under `[inference]`.

## Devin Secrets Needed

No secrets required for local testing. An inference server endpoint would be needed to test `plan`/`run` commands but is not required for core functionality testing.

## Tips

- The app uses `uv` for dependency management — never use pip directly
- Test files are in `tests/` and use pytest
- Configuration is via `harness.toml` (TOML format)
- The `.sdlc/context/` directory is used for persistent agent memory
- Security tests should verify both blocking (dangerous commands raise) AND allowing (safe commands pass through)
- When adding "allowed command" test examples, remember they actually execute — never use destructive commands even if they wouldn't trigger SecurityViolation
