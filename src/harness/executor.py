"""Secure tool executor with path validation and command blocking."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .schemas import (
    BashExecuteArgs,
    BashExecuteResult,
    EditFileAstResult,
    ReadFileResult,
    WriteFileResult,
)
from .tools import TOOL_ARGS_MAP, TOOL_REGISTRY, ToolArgs, ToolResult

if TYPE_CHECKING:
    from .config import HarnessConfig

logger = logging.getLogger(__name__)

SDLC_DIR = ".sdlc"


class SecurityViolation(Exception):
    """Raised when a tool call violates security policy."""


class ToolExecutor:
    """Wraps the tool registry with security checks and config enforcement.

    The ``repo_root`` should be the **working directory** for the current task —
    typically a git worktree path, not the main repo root. This ensures path
    validation allows file operations within the worktree.
    """

    def __init__(
        self,
        config: HarnessConfig,
        repo_root: str | Path,
        *,
        protect_sdlc: bool = False,
    ):
        self.config = config
        self.repo_root = Path(repo_root).resolve()
        self.protect_sdlc = protect_sdlc

    def with_root(self, new_root: str | Path) -> ToolExecutor:
        """Return a copy of this executor rooted at *new_root*."""
        return ToolExecutor(
            self.config,
            new_root,
            protect_sdlc=self.protect_sdlc,
        )

    def execute(self, name: str, arguments: dict) -> ToolResult:
        """Validate and execute a named tool."""
        args_cls = TOOL_ARGS_MAP.get(name)
        handler = TOOL_REGISTRY.get(name)
        if not args_cls or not handler:
            raise ValueError(f"Unknown tool: {name}")

        parsed = args_cls(**arguments)
        self._validate(name, parsed)

        if name == "bash_execute" and isinstance(parsed, BashExecuteArgs):
            return self._execute_bash(parsed)

        return handler(parsed)

    def _validate(self, name: str, args: ToolArgs) -> None:
        if name in ("read_file", "write_file", "edit_file_ast"):
            path_attr = getattr(args, "path", None)
            if path_attr is not None:
                self._validate_path(path_attr, writable=name != "read_file")
        if name == "bash_execute" and isinstance(args, BashExecuteArgs):
            self._validate_command(args.cmd)

    def _validate_path(self, path: str, *, writable: bool = False) -> None:
        resolved = Path(path).resolve()

        if writable and self.protect_sdlc:
            try:
                resolved.relative_to(self.repo_root / SDLC_DIR)
                raise SecurityViolation(
                    f"Implementor cannot modify {SDLC_DIR}/ files: {path}"
                )
            except ValueError:
                pass

        if not self.config.security.restrict_paths:
            return
        allowed = [
            (self.repo_root / r).resolve()
            for r in self.config.security.allowed_roots
        ]
        if not any(_is_subpath(resolved, root) for root in allowed):
            raise SecurityViolation(f"Path outside allowed roots: {path}")

    def _validate_command(self, cmd: str) -> None:
        for blocked in self.config.tools.blocked_commands:
            if blocked in cmd:
                raise SecurityViolation(f"Blocked command pattern: {blocked}")

    def _execute_bash(self, args: BashExecuteArgs) -> BashExecuteResult:
        import subprocess

        try:
            result = subprocess.run(
                args.cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.tools.bash_timeout,
            )
            return BashExecuteResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return BashExecuteResult(
                exit_code=-1,
                stdout="",
                stderr=f"Timed out after {self.config.tools.bash_timeout}s",
            )
        except Exception as e:
            return BashExecuteResult(exit_code=-1, stdout="", stderr=str(e))

    def make_error_result(self, name: str, error: str) -> ToolResult:
        """Create an error result matching the tool's output schema."""
        if name == "read_file":
            return ReadFileResult(content="", success=False, error=error)
        if name == "write_file":
            return WriteFileResult(success=False, error=error)
        if name == "edit_file_ast":
            return EditFileAstResult(success=False, error=error)
        return BashExecuteResult(exit_code=-1, stdout="", stderr=error)


def _is_subpath(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
