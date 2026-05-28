"""Error types used by the No-Slop Harness."""

from __future__ import annotations


class NoSlopError(Exception):
    """Base exception for all No-Slop Harness errors."""


class TaskValidationError(NoSlopError):
    """A task failed schema validation."""


class CyclicDependencyError(NoSlopError):
    """The task graph contains a cycle."""


class SandboxViolationError(NoSlopError):
    """A command violated the sandbox security policy."""


class VerificationError(NoSlopError):
    """The Verifier rejected a task's output."""


class ToolExecutionError(NoSlopError):
    """A tool call failed during execution."""
