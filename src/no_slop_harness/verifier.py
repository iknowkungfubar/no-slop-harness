"""Verification and test-running utilities for the Verifier agent."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple


class VerificationResult(NamedTuple):
    """Result of a verification run — avoids pytest collection clash with TestResult."""

    passed: bool
    output: str
    returncode: int


class Verifier:
    """Runs verification checks on completed tasks.

    Executes test suites, linters, and type checks against the
    generated code to ensure quality before acceptance.
    """

    def __init__(self, working_dir: Path | None = None, timeout: int = 60) -> None:
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout

    def run_command(self, cmd: list[str]) -> VerificationResult:
        """Run a shell command and capture results."""
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            output = proc.stdout + proc.stderr
            return VerificationResult(
                passed=proc.returncode == 0,
                output=output,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                output=f"Command timed out after {self.timeout}s",
                returncode=-1,
            )
        except FileNotFoundError:
            return VerificationResult(
                passed=False,
                output=f"Command not found: {cmd[0]}",
                returncode=-1,
            )

    def run_pytest(self, test_path: str | None = None) -> VerificationResult:
        """Run pytest on the project."""
        cmd = ["python", "-m", "pytest"]
        if test_path:
            cmd.append(test_path)
        return self.run_command(cmd)

    def run_lint(self) -> VerificationResult:
        """Run ruff linting."""
        return self.run_command(["python", "-m", "ruff", "check", "src/"])

    def run_typecheck(self) -> VerificationResult:
        """Run mypy type checking."""
        return self.run_command(["python", "-m", "mypy", "src/", "--ignore-missing-imports"])

    def verify_diff(self, target_path: Path, original: str, patched: str) -> bool:
        """Verify that a patch applies cleanly and doesn't break syntax."""
        if not patched.strip():
            return False
        try:
            compile(patched, target_path, "exec")
            return True
        except SyntaxError:
            return False
