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

Test via Python imports — do NOT actually execute dangerous commands:

```python
from harness.config import HarnessConfig
from harness.executor import ToolExecutor, SecurityViolation

cfg = HarnessConfig()
ex = ToolExecutor(cfg, '/tmp')

# These should raise SecurityViolation:
ex.execute('bash_execute', {'cmd': 'rm -rf ./data'})       # combined flags
ex.execute('bash_execute', {'cmd': 'rm -r -f /tmp/data'})   # separated flags
ex.execute('bash_execute', {'cmd': 'rm --recursive /tmp'})  # long flag
ex.execute('bash_execute', {'cmd': 'shred /dev/sda'})       # unconditional block
ex.execute('bash_execute', {'cmd': 'wipefs /dev/sda'})      # unconditional block

# This should NOT raise (plain rm without destructive flags):
ex.execute('bash_execute', {'cmd': 'rm nonexistent 2>/dev/null; true'})
```

### 2. Context Sanitization

```python
from harness.context import ContextManager
import tempfile

with tempfile.TemporaryDirectory() as d:
    cm = ContextManager(d)
    path = cm.save_task_summary('../../etc/passwd', 'evil', 'failed')
    assert path.parent == cm.context_dir  # must stay inside context dir
    assert '..' not in path.name          # no path traversal chars
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
