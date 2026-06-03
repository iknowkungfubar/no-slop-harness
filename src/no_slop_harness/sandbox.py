"""Sandboxed command execution."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .schemas import SandboxConfig

# Always-blocked commands (security critical)
_IMPLICIT_BLOCKLIST = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ">:",
    "chmod 777",
    "chmod -R 777",
    "chown root",
    ":(){ :|:& };:",
    "fork bomb",
    "nohup",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
]


class SandboxViolation(Exception):  # noqa: N818
    """Raised when a command violates sandbox policy."""


def execute_sandboxed(cmd: str, config: SandboxConfig) -> tuple[int, str, str]:
    """Execute a command within the security sandbox.

    Returns (returncode, stdout, stderr).
    Raises SandboxViolation for blocked commands.
    """
    import time

    # Check blocklist
    normalized = cmd.strip().lower()
    for blocked in _IMPLICIT_BLOCKLIST:
        if blocked.lower() in normalized:
            raise SandboxViolation(f"Command blocked by sandbox policy: {cmd!r}")
    for blocked in [b.lower() for b in config.blocked_commands]:
        if blocked in normalized:
            raise SandboxViolation(f"Command blocked by sandbox policy: {cmd!r}")

    # Check allowlist (if non-empty)
    if config.allowed_commands:
        base_cmd = shlex.split(cmd)[0] if cmd.strip() else ""
        if base_cmd not in config.allowed_commands:
            raise SandboxViolation(
                f"Command {base_cmd!r} not in allowlist: {config.allowed_commands}"
            )

    working_dir = Path(config.working_directory)
    working_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Parse command into list form to avoid shell injection.
        # This replaces `shell=True` which allowed allowlist bypass via
        # subshells ($(...), `...`), pipes, and chained commands.
        # If the command requires shell features (pipes, redirects),
        # create a script file and run it via an allowed interpreter.
        cmd_parts = shlex.split(cmd)
        t0 = time.monotonic()
        proc = subprocess.run(
            cmd_parts,
            shell=False,
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000  # noqa: F841

        # Truncate output if too large
        stdout = proc.stdout
        stderr = proc.stderr
        max_bytes = config.max_output_bytes
        if len(stdout.encode()) > max_bytes:
            stdout = stdout[:max_bytes] + "\n[TRUNCATED]"
        if len(stderr.encode()) > max_bytes:
            stderr = stderr[:max_bytes] + "\n[TRUNCATED]"

        return proc.returncode, stdout, stderr

    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {config.timeout_seconds}s"
    except Exception as e:
        return -1, "", str(e)
