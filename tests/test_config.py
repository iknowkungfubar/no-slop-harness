"""Tests for config module — TOML loading, merging, and environment overrides."""

from __future__ import annotations

from pathlib import Path

import pytest
from src.no_slop_harness.config import (
    APIConfig,
    NoSlopConfig,
    SandboxConfigFile,
    WorktreesConfig,
    _load_toml,
    _merge_section,
    load_config,
)


class TestDataclassDefaults:
    """Config dataclasses should have sensible defaults."""

    def test_api_config_defaults(self):
        cfg = APIConfig()
        assert cfg.base_url == "http://localhost:1234/v1"
        assert cfg.model == "qwen/qwen3.6-35b-a3b"
        assert cfg.api_key == "not-needed"

    def test_sandbox_config_defaults(self):
        cfg = SandboxConfigFile()
        assert cfg.allowlist == []
        assert cfg.timeout == 120

    def test_worktrees_config_defaults(self):
        cfg = WorktreesConfig()
        assert cfg.enabled is False

    def test_no_slop_config_defaults(self):
        cfg = NoSlopConfig()
        assert isinstance(cfg.api, APIConfig)
        assert isinstance(cfg.sandbox, SandboxConfigFile)
        assert isinstance(cfg.worktrees, WorktreesConfig)
        assert cfg.loaded_from == []


class TestLoadToml:
    """_load_toml helper - core parsing logic."""

    def test_loads_valid_toml(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        path.write_text('api = { base_url = "http://test:8080" }')
        result = _load_toml(path)
        assert result == {"api": {"base_url": "http://test:8080"}}

    def test_returns_empty_on_missing_file(self, tmp_path: Path):
        path = tmp_path / "nonexistent.toml"
        result = _load_toml(path)
        assert result == {}

    def test_returns_empty_on_permission_error(self, tmp_path: Path):
        path = tmp_path / "noperm.toml"
        path.write_text("key = 1")
        path.chmod(0o000)
        try:
            result = _load_toml(path)
            assert result == {}
        finally:
            path.chmod(0o644)

    def test_returns_empty_and_warns_on_bad_toml(self, tmp_path: Path):
        path = tmp_path / "bad.toml"
        path.write_text("{{invalid [[[toml")
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _load_toml(path)
            assert result == {}
            assert len(w) == 1
            assert "Failed to parse" in str(w[0].message)

    def test_handles_empty_toml(self, tmp_path: Path):
        path = tmp_path / "empty.toml"
        path.write_text("")
        result = _load_toml(path)
        assert result == {}


class TestMergeSection:
    """_merge_section helper - merges TOML data into defaults."""

    def test_merges_with_defaults(self):
        cfg = {"api": {"base_url": "http://test:9090", "model": "gpt-4"}}
        defaults = {"base_url": "http://localhost:1234/v1", "model": "default", "api_key": "no-key"}
        result = _merge_section(cfg, "api", defaults)
        assert result["base_url"] == "http://test:9090"
        assert result["model"] == "gpt-4"
        assert result["api_key"] == "no-key"

    def test_ignores_none_values(self):
        """None values from TOML should not override defaults."""
        cfg = {"api": {"base_url": None, "model": "test-model"}}
        defaults = {"base_url": "http://default:1234", "model": "default", "api_key": "key"}
        result = _merge_section(cfg, "api", defaults)
        assert result["base_url"] == "http://default:1234"
        assert result["model"] == "test-model"

    def test_returns_defaults_on_missing_section(self):
        cfg = {"other": {}}
        defaults = {"key": "val"}
        result = _merge_section(cfg, "missing", defaults)
        assert result == defaults

    def test_returns_defaults_on_non_dict_section(self):
        cfg = {"section": "not_a_dict"}
        defaults = {"key": "val"}
        result = _merge_section(cfg, "section", defaults)
        assert result == defaults

    def test_empty_toml_returns_defaults(self):
        cfg: dict = {}
        defaults = {"key1": "v1", "key2": "v2"}
        result = _merge_section(cfg, "missing", defaults)
        assert result == defaults


class TestLoadConfig:
    """load_config - full integration test with temp files."""

    def test_default_config_with_no_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When no config files exist, defaults should be returned."""
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg.api.base_url == "http://localhost:1234/v1"
        assert cfg.api.model == "qwen/qwen3.6-35b-a3b"
        assert cfg.sandbox.timeout == 120
        assert cfg.sandbox.allowlist == []
        assert cfg.loaded_from == []

    def test_loads_project_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A no-slop.toml in cwd should be loaded."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "no-slop.toml").write_text(
            '[api]\nbase_url = "http://project:8080"\nmodel = "project-model"\n'
        )
        cfg = load_config()
        assert cfg.api.base_url == "http://project:8080"
        assert cfg.api.model == "project-model"
        assert len(cfg.loaded_from) >= 1
        assert "no-slop.toml" in cfg.loaded_from[0]

    def test_env_var_overrides_api_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """NO_SLOP_API_KEY env var should override TOML values."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_SLOP_API_KEY", "env-key-123")
        cfg = load_config()
        assert cfg.api.api_key == "env-key-123"

    def test_env_var_overrides_base_url(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """NO_SLOP_BASE_URL env var should override TOML values."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NO_SLOP_BASE_URL", "http://env-host:9999")
        cfg = load_config()
        assert cfg.api.base_url == "http://env-host:9999"

    def test_user_config_takes_lower_priority(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """User config should be loaded, but project config overrides it."""
        monkeypatch.chdir(tmp_path)

        # Mock user config dir
        user_config_dir = tmp_path / ".config" / "no-slop"
        user_config_dir.mkdir(parents=True)
        (user_config_dir / "config.toml").write_text(
            '[sandbox]\nallowlist = ["python", "bash"]\ntimeout = 60\n'
        )

        # Mock home dir
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        cfg = load_config()
        assert cfg.sandbox.allowlist == ["python", "bash"]
        assert cfg.sandbox.timeout == 60

    def test_project_config_overrides_user(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Project config should override user config."""
        monkeypatch.chdir(tmp_path)

        # User config
        user_config_dir = tmp_path / ".config" / "no-slop"
        user_config_dir.mkdir(parents=True)
        (user_config_dir / "config.toml").write_text('[api]\nbase_url = "http://user:5000"\n')

        # Project config
        (tmp_path / "no-slop.toml").write_text('[api]\nbase_url = "http://project:8080"\n')

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        cfg = load_config()
        assert cfg.api.base_url == "http://project:8080"
