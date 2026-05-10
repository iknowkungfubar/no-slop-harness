"""Tests for CLI argument parsing and init command."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.cli import _build_parser, _cmd_init


class TestParser:
    def test_version_flag(self):
        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_run_command(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "do something"])
        assert args.command == "run"
        assert args.prompt == "do something"

    def test_plan_command(self):
        parser = _build_parser()
        args = parser.parse_args(["plan", "make a plan"])
        assert args.command == "plan"
        assert args.prompt == "make a plan"

    def test_init_command(self):
        parser = _build_parser()
        args = parser.parse_args(["init"])
        assert args.command == "init"

    def test_verify_command(self):
        parser = _build_parser()
        args = parser.parse_args(["verify"])
        assert args.command == "verify"

    def test_info_command(self):
        parser = _build_parser()
        args = parser.parse_args(["info"])
        assert args.command == "info"

    def test_config_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-c", "custom.toml", "run", "test"])
        assert args.config == "custom.toml"

    def test_verbose_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-v", "run", "test"])
        assert args.verbose is True


class TestInitCommand:
    def test_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        args = type("Args", (), {})()
        _cmd_init(args)
        assert (tmp_path / "harness.toml").exists()

    def test_no_overwrite(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "harness.toml").write_text("existing")
        args = type("Args", (), {"config": "harness.toml"})()
        _cmd_init(args)
        assert (tmp_path / "harness.toml").read_text() == "existing"

    def test_custom_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        args = type("Args", (), {"config": "custom.toml"})()
        _cmd_init(args)
        assert (tmp_path / "custom.toml").exists()
        assert not (tmp_path / "harness.toml").exists()
