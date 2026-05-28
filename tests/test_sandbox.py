"""Test suite for sandbox security module."""

from __future__ import annotations

import pytest

from no_slop_harness.sandbox import SandboxViolation, execute_sandboxed
from no_slop_harness.schemas import SandboxConfig


class TestSandboxBlockedCommands:
    """Implicitly blocked commands cannot be executed."""

    @pytest.mark.parametrize("dangerous_cmd", [
        "rm -rf /",
        "echo 'mkfs' && mkfs",
        "chmod 777 /etc/passwd",
        "chmod -R 777 /tmp",
        "chown root:root /etc/shadow",
    ])
    def test_dangerous_commands_blocked(self, dangerous_cmd: str) -> None:
        config = SandboxConfig()
        with pytest.raises(SandboxViolation):
            execute_sandboxed(dangerous_cmd, config)


class TestSandboxAllowlist:
    """Allowlist enforcement restricts commands."""

    def test_allowlisted_command_passes(self) -> None:
        config = SandboxConfig(allowed_commands=["echo", "ls"], timeout_seconds=5)
        returncode, stdout, stderr = execute_sandboxed("echo hello", config)
        assert returncode == 0
        assert "hello" in stdout

    def test_non_allowlisted_command_blocked(self) -> None:
        config = SandboxConfig(allowed_commands=["echo"], timeout_seconds=5)
        with pytest.raises(SandboxViolation) as exc_info:
            execute_sandboxed("cat /etc/passwd", config)
        assert "cat" in str(exc_info.value) or "allowlist" in str(exc_info.value).lower()

    def test_empty_allowlist_allows_all(self) -> None:
        """Empty allowlist means no restriction on command names."""
        config = SandboxConfig(allowed_commands=[], timeout_seconds=5)
        returncode, stdout, _ = execute_sandboxed("echo unrestricted", config)
        assert returncode == 0
        assert "unrestricted" in stdout


class TestSandboxTimeout:
    """Command timeout enforcement."""

    def test_timeout_triggers(self) -> None:
        config = SandboxConfig(timeout_seconds=1)
        returncode, stdout, stderr = execute_sandboxed("sleep 5", config)
        assert returncode == -1
        assert "timed out" in stderr.lower() or "timed out" in stdout.lower()


class TestSandboxOutputTruncation:
    """Large output is truncated to max_output_bytes."""

    def test_output_truncated(self) -> None:
        config = SandboxConfig(
            allowed_commands=["echo"],
            timeout_seconds=5,
            max_output_bytes=10,  # Very small limit for testing
        )
        returncode, stdout, stderr = execute_sandboxed("echo 'this is a very long string'", config)
        assert returncode == 0
        assert "[TRUNCATED]" in stdout


class TestSandboxWorkingDirectory:
    """Commands execute within the configured working directory."""

    def test_working_directory_used(self, tmp_path) -> None:
        config = SandboxConfig(
            allowed_commands=["pwd", "echo"],
            timeout_seconds=5,
            working_directory=str(tmp_path),
        )
        returncode, stdout, _ = execute_sandboxed("pwd", config)
        assert returncode == 0
        assert tmp_path.resolve().as_posix() in stdout
