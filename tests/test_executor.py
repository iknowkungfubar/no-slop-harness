"""Tests for the secure tool executor."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.config import HarnessConfig, SecurityConfig, ToolsConfig
from harness.executor import SecurityViolation, ToolExecutor


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "hello.py").write_text("print('hello')")
    return tmp_path


class TestPathValidation:
    def test_allowed_path(self, repo: Path):
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=True, allowed_roots=["."]))
        ex = ToolExecutor(cfg, repo)
        result = ex.execute("read_file", {"path": str(repo / "hello.py")})
        assert result.success  # type: ignore[union-attr]

    def test_blocked_path(self, repo: Path):
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=True, allowed_roots=["."]))
        ex = ToolExecutor(cfg, repo)
        with pytest.raises(SecurityViolation, match="outside allowed roots"):
            ex.execute("read_file", {"path": "/etc/passwd"})

    def test_restriction_disabled(self, repo: Path):
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=False))
        ex = ToolExecutor(cfg, repo)
        # Should not raise even for paths outside repo
        result = ex.execute("read_file", {"path": "/etc/hostname"})
        assert result is not None


class TestCommandBlocking:
    def test_blocked_command(self, repo: Path):
        cfg = HarnessConfig(
            tools=ToolsConfig(blocked_commands=["rm -rf /"])
        )
        ex = ToolExecutor(cfg, repo)
        with pytest.raises(SecurityViolation, match="Blocked command"):
            ex.execute("bash_execute", {"cmd": "rm -rf / --no-preserve-root"})

    def test_allowed_command(self, repo: Path):
        cfg = HarnessConfig()
        ex = ToolExecutor(cfg, repo)
        result = ex.execute("bash_execute", {"cmd": "echo OK"})
        assert result.stdout.strip() == "OK"  # type: ignore[union-attr]


class TestUnknownTool:
    def test_unknown_tool_raises(self, repo: Path):
        ex = ToolExecutor(HarnessConfig(), repo)
        with pytest.raises(ValueError, match="Unknown tool"):
            ex.execute("nonexistent_tool", {})


class TestSdlcProtection:
    def test_write_to_sdlc_blocked(self, repo: Path):
        (repo / ".sdlc" / "context").mkdir(parents=True)
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=False))
        ex = ToolExecutor(cfg, repo, protect_sdlc=True)
        with pytest.raises(SecurityViolation, match="cannot modify .sdlc"):
            ex.execute("write_file", {
                "path": str(repo / ".sdlc" / "context" / "bad.md"),
                "content": "evil",
            })

    def test_read_sdlc_allowed(self, repo: Path):
        sdlc = repo / ".sdlc" / "context"
        sdlc.mkdir(parents=True)
        (sdlc / "note.md").write_text("ok")
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=False))
        ex = ToolExecutor(cfg, repo, protect_sdlc=True)
        result = ex.execute("read_file", {"path": str(sdlc / "note.md")})
        assert result.success  # type: ignore[union-attr]

    def test_sdlc_protection_off_by_default(self, repo: Path):
        (repo / ".sdlc" / "context").mkdir(parents=True)
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=False))
        ex = ToolExecutor(cfg, repo)
        result = ex.execute("write_file", {
            "path": str(repo / ".sdlc" / "context" / "ok.md"),
            "content": "fine",
        })
        assert result.success  # type: ignore[union-attr]


class TestWithRoot:
    def test_with_root_changes_root(self, repo: Path):
        cfg = HarnessConfig(security=SecurityConfig(restrict_paths=True, allowed_roots=["."]))
        ex = ToolExecutor(cfg, repo, protect_sdlc=True)
        new_dir = repo / "subdir"
        new_dir.mkdir()
        (new_dir / "file.txt").write_text("hi")

        child = ex.with_root(new_dir)
        assert child.repo_root == new_dir.resolve()
        assert child.protect_sdlc is True
        result = child.execute("read_file", {"path": str(new_dir / "file.txt")})
        assert result.success  # type: ignore[union-attr]


class TestErrorResult:
    def test_make_error_result_read(self, repo: Path):
        ex = ToolExecutor(HarnessConfig(), repo)
        r = ex.make_error_result("read_file", "oops")
        assert r.error == "oops"  # type: ignore[union-attr]
        assert not r.success  # type: ignore[union-attr]

    def test_make_error_result_bash(self, repo: Path):
        ex = ToolExecutor(HarnessConfig(), repo)
        r = ex.make_error_result("bash_execute", "oops")
        assert r.stderr == "oops"  # type: ignore[union-attr]
