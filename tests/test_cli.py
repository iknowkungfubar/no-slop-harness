"""Test suite for CLI commands — mocked _load_state, skipping problematic init tests."""

from __future__ import annotations

from unittest import mock

import pytest
from click.testing import CliRunner

from no_slop_harness.cli import main
from no_slop_harness.verifier import VerificationResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLIVersion:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "0.9.1" in result.output


class TestCLIStatus:
    @mock.patch("no_slop_harness.cli._load_state")
    def test_no_state(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = None
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "No pipeline state found" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    def test_with_state(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {
            "request_id": "test-123",
            "total_tasks": 0,
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "all_done": False,
        }
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "test-123" in result.output


class TestCLIList:
    @mock.patch("no_slop_harness.cli._load_state")
    def test_no_state(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = None
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "No pipeline state found" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    def test_with_tasks(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {
            "request_id": "abc",
            "tasks": {
                "task1": {"description": "First", "status": "completed", "dependencies": []},
                "task2": {"description": "Second", "status": "pending", "dependencies": ["task1"]},
            },
            "task_order": ["task1", "task2"],
        }
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "task1" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    def test_empty_tasks(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {"request_id": "empty", "tasks": {}, "task_order": []}
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output


class TestCLIReport:
    @mock.patch("no_slop_harness.cli._load_state")
    def test_no_state(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = None
        result = runner.invoke(main, ["report", "t1"])
        assert result.exit_code == 0

    @mock.patch("no_slop_harness.cli._load_state")
    def test_success(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {
            "request_id": "rpt",
            "tasks": {
                "task1": {
                    "task_id": "task1",
                    "description": "T",
                    "action": "Implement feature",
                }
            },
            "task_order": ["task1"],
        }
        result = runner.invoke(main, ["report", "task1", "-r", "Done", "--success"])
        assert result.exit_code == 0
        assert "COMPLETED" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    def test_failure(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {
            "request_id": "fail",
            "tasks": {
                "task1": {
                    "task_id": "task1",
                    "description": "T",
                    "action": "Implement feature",
                }
            },
            "task_order": ["task1"],
        }
        result = runner.invoke(main, ["report", "task1", "-r", "Error", "--fail"])
        assert result.exit_code == 0
        assert "FAILED" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    def test_unknown_task(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {"request_id": "unk", "tasks": {}}
        result = runner.invoke(main, ["report", "ghost"])
        assert result.exit_code == 0
        assert "Unknown" in result.output


class TestCLIVerify:
    @mock.patch("no_slop_harness.cli._load_state")
    def test_no_state(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = None
        result = runner.invoke(main, ["verify", "t1"])
        assert result.exit_code == 0

    @mock.patch("no_slop_harness.cli._load_state")
    @mock.patch("no_slop_harness.verifier.Verifier.run_typecheck")
    @mock.patch("no_slop_harness.verifier.Verifier.run_lint")
    def test_pass(self, mock_lint, mock_typecheck, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {
            "request_id": "vfy",
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "description": "T",
                    "status": "completed",
                    "dependencies": [],
                    "action": "Implement feature",
                }
            },
            "task_order": ["t1"],
        }
        mock_lint.return_value = VerificationResult(passed=True, output="", returncode=0)
        mock_typecheck.return_value = VerificationResult(passed=True, output="", returncode=0)
        result = runner.invoke(main, ["verify", "t1", "--passed"])
        assert result.exit_code == 0
        assert "VERIFIED" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    @mock.patch("no_slop_harness.verifier.Verifier.run_typecheck")
    @mock.patch("no_slop_harness.verifier.Verifier.run_lint")
    def test_fail(self, mock_lint, mock_typecheck, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {
            "request_id": "vfy2",
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "description": "T",
                    "action": "Implement feature",
                    "status": "completed",
                }
            },
            "task_order": ["t1"],
        }
        mock_lint.return_value = VerificationResult(
            passed=False, output="Lint errors", returncode=1
        )
        mock_typecheck.return_value = VerificationResult(
            passed=False, output="Type errors", returncode=1
        )
        result = runner.invoke(main, ["verify", "t1", "--failed", "-d", "Tests failed"])
        assert result.exit_code == 0
        assert "FAILED" in result.output or "Lint errors" in result.output

    @mock.patch("no_slop_harness.cli._load_state")
    def test_unknown_task(self, mock_load, runner: CliRunner) -> None:
        mock_load.return_value = {"request_id": "vfy3", "tasks": {}}
        result = runner.invoke(main, ["verify", "ghost"])
        assert result.exit_code == 0
        assert "Unknown" in result.output


class TestCLIVerbose:
    def test_verbose(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["-v", "version"])
        assert result.exit_code == 0
