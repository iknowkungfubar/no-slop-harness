"""Test suite for verifier module."""

from __future__ import annotations

from no_slop_harness.verifier import Verifier


class TestVerifierCommandExecution:
    """Verifier executes commands correctly."""

    def test_successful_command(self) -> None:
        v = Verifier()
        result = v.run_command(["echo", "-n", "hello"])
        assert result.passed is True
        assert result.output.strip() == "hello"
        assert result.returncode == 0

    def test_failing_command(self) -> None:
        v = Verifier()
        result = v.run_command(["false"])
        assert result.passed is False
        assert result.returncode != 0

    def test_timeout_handling(self) -> None:
        v = Verifier(timeout=1)
        result = v.run_command(["sleep", "5"])
        assert result.passed is False
        assert result.returncode == -1
        assert "timed out" in result.output.lower()

    def test_nonexistent_command(self) -> None:
        v = Verifier()
        result = v.run_command(["this_command_does_not_exist_xyz"])
        assert result.passed is False
        assert result.returncode == -1


class TestVerifierDiffCheck:
    """Verify diff validation works."""

    def test_valid_python(self, tmp_path) -> None:
        v = Verifier()
        path = tmp_path / "test.py"
        result = v.verify_diff(path, "", "x = 1\n")
        assert result is True

    def test_invalid_python(self, tmp_path) -> None:
        v = Verifier()
        path = tmp_path / "test.py"
        result = v.verify_diff(path, "", "def broken(:\n")
        assert result is False
