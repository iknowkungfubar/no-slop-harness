"""Test suite for error types — ensures every exception is importable and raisable."""

from __future__ import annotations

import pytest

from no_slop_harness.errors import (
    CyclicDependencyError,
    NoSlopError,
    SandboxViolationError,
    TaskValidationError,
    ToolExecutionError,
    VerificationError,
)


class TestErrorHierarchy:
    """All errors inherit from NoSlopError and can be raised/caught."""

    def test_no_slop_error_is_base(self) -> None:
        assert issubclass(TaskValidationError, NoSlopError)
        assert issubclass(CyclicDependencyError, NoSlopError)
        assert issubclass(SandboxViolationError, NoSlopError)
        assert issubclass(VerificationError, NoSlopError)
        assert issubclass(ToolExecutionError, NoSlopError)

    def test_task_validation_error(self) -> None:
        with pytest.raises(TaskValidationError):
            raise TaskValidationError("bad task")

    def test_cyclic_dependency_error(self) -> None:
        with pytest.raises(CyclicDependencyError):
            raise CyclicDependencyError("cycle detected")

    def test_sandbox_violation_error(self) -> None:
        with pytest.raises(SandboxViolationError):
            raise SandboxViolationError("blocked command")

    def test_verification_error(self) -> None:
        with pytest.raises(VerificationError):
            raise VerificationError("tests failed")

    def test_tool_execution_error(self) -> None:
        with pytest.raises(ToolExecutionError):
            raise ToolExecutionError("tool crashed")

    def test_catch_by_base_class(self) -> None:
        """All errors can be caught by NoSlopError."""
        errors = [
            TaskValidationError("a"),
            CyclicDependencyError("b"),
            SandboxViolationError("c"),
            VerificationError("d"),
            ToolExecutionError("e"),
        ]
        for e in errors:
            try:
                raise e
            except NoSlopError:
                pass

    def test_error_messages_preserved(self) -> None:
        e = TaskValidationError("specific message here")
        assert "specific message here" in str(e)
