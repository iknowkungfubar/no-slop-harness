"""Test suite for CLI commands using Click's CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from no_slop_harness.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    d = tmp_path / ".no-slop"
    d.mkdir()
    return d


def _write_state(state_dir: Path, data: dict) -> Path:
    """Write a pipeline state file and return its path."""
    rid = data.get("request_id", "test")
    path = state_dir / f"pipeline-{rid}.json"
    path.write_text(json.dumps(data))
    return path


class TestCLIInit:
    """no-slop init command."""

    def test_init_creates_state_file(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(main, ["init"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "Pipeline initialized" in result.output
        assert len(list(state_dir.glob("pipeline-*.json"))) == 1

    def test_init_with_sandbox_allowlist(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(
            main, ["init", "--sandbox-allowlist", "echo", "--sandbox-allowlist", "python"],
            env={"NO_SLOP_STATE_DIR": str(state_dir)},
        )
        assert result.exit_code == 0, result.output

    def test_init_with_request_id(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(
            main, ["init", "--request-id", "custom-42"],
            env={"NO_SLOP_STATE_DIR": str(state_dir)},
        )
        assert result.exit_code == 0, result.output
        assert "custom-42" in result.output


class TestCLIStatus:
    """no-slop status command."""

    def test_status_no_state(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(main, ["status"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "No pipeline state found" in result.output

    def test_status_with_state(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {"request_id": "test-123"})
        result = runner.invoke(main, ["status"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "test-123" in result.output


class TestCLIList:
    """no-slop list command."""

    def test_list_no_state(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(main, ["list"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "No pipeline state found" in result.output

    def test_list_with_tasks(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {
            "request_id": "abc",
            "tasks": {
                "task1": {"description": "First", "status": "completed", "dependencies": []},
                "task2": {"description": "Second", "status": "pending", "dependencies": ["task1"]},
            },
            "task_order": ["task1", "task2"],
        })
        result = runner.invoke(main, ["list"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "task1" in result.output
        assert "task2" in result.output

    def test_list_empty_tasks(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {"request_id": "empty", "tasks": {}, "task_order": []})
        result = runner.invoke(main, ["list"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "No tasks" in result.output


class TestCLIVersion:
    """no-slop version command."""

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0, result.output
        assert "0.9.0" in result.output


class TestCLIReport:
    """no-slop report command."""

    def test_report_no_state(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(main, ["report", "task1"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output

    def test_report_success(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {
            "request_id": "rpt",
            "tasks": {"task1": {"description": "T", "status": "pending", "dependencies": []}},
        })
        result = runner.invoke(
            main, ["report", "task1", "-r", "Done", "--success"],
            env={"NO_SLOP_STATE_DIR": str(state_dir)},
        )
        assert result.exit_code == 0, result.output
        assert "COMPLETED" in result.output

    def test_report_failure(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {
            "request_id": "fail",
            "tasks": {"task1": {"description": "T", "status": "pending", "dependencies": []}},
        })
        result = runner.invoke(
            main, ["report", "task1", "-r", "Error", "--fail"],
            env={"NO_SLOP_STATE_DIR": str(state_dir)},
        )
        assert result.exit_code == 0, result.output
        assert "FAILED" in result.output

    def test_report_unknown_task(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {"request_id": "unk", "tasks": {}})
        result = runner.invoke(
            main, ["report", "ghost"],
            env={"NO_SLOP_STATE_DIR": str(state_dir)},
        )
        assert result.exit_code == 0, result.output
        assert "Unknown" in result.output


class TestCLIVerify:
    """no-slop verify command."""

    def test_verify_no_state(self, runner: CliRunner, state_dir: Path) -> None:
        result = runner.invoke(main, ["verify", "t1"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output

    def test_verify_pass(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {
            "request_id": "vfy",
            "tasks": {"t1": {"description": "T", "status": "completed", "dependencies": []}},
        })
        result = runner.invoke(main, ["verify", "t1", "--passed"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "VERIFIED" in result.output

    def test_verify_fail(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {
            "request_id": "vfy2",
            "tasks": {"t1": {"description": "T", "status": "completed", "dependencies": []}},
        })
        result = runner.invoke(
            main, ["verify", "t1", "--failed", "-d", "Tests failed"],
            env={"NO_SLOP_STATE_DIR": str(state_dir)},
        )
        assert result.exit_code == 0, result.output
        assert "FAILED" in result.output

    def test_verify_unknown_task(self, runner: CliRunner, state_dir: Path) -> None:
        _write_state(state_dir, {"request_id": "vfy3", "tasks": {}})
        result = runner.invoke(main, ["verify", "ghost"], env={"NO_SLOP_STATE_DIR": str(state_dir)})
        assert result.exit_code == 0, result.output
        assert "Unknown" in result.output


class TestCLIVerbose:
    """Verbose flag."""

    def test_verbose(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["-v", "version"])
        assert result.exit_code == 0
        assert "0.9.0" in result.output


class TestCLIMainDirect:
    """Main function callable."""

    def test_main_is_callable(self) -> None:
        assert callable(main)
