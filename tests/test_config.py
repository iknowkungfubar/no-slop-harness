"""Tests for configuration management."""

from __future__ import annotations

from pathlib import Path

from harness.config import HarnessConfig, default_toml, load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path: Path):
        cfg = load_config(tmp_path / "missing.toml")
        assert cfg.inference.base_url == "http://localhost:8000/v1"
        assert cfg.inference.max_retries == 3
        assert cfg.tools.bash_timeout == 60
        assert cfg.security.restrict_paths is True

    def test_load_from_file(self, tmp_path: Path):
        toml_file = tmp_path / "harness.toml"
        toml_file.write_text(
            '[inference]\nbase_url = "http://myserver:9000/v1"\nmodel = "qwen"\n'
            "[tools]\nbash_timeout = 120\n"
        )
        cfg = load_config(toml_file)
        assert cfg.inference.base_url == "http://myserver:9000/v1"
        assert cfg.inference.model == "qwen"
        assert cfg.tools.bash_timeout == 120
        # Unset fields retain defaults
        assert cfg.inference.max_retries == 3
        assert cfg.security.restrict_paths is True

    def test_partial_override(self, tmp_path: Path):
        toml_file = tmp_path / "harness.toml"
        toml_file.write_text("[security]\nrestrict_paths = false\n")
        cfg = load_config(toml_file)
        assert cfg.security.restrict_paths is False
        assert cfg.inference.base_url == "http://localhost:8000/v1"


class TestDefaults:
    def test_harness_config_defaults(self):
        cfg = HarnessConfig()
        assert cfg.inference.temperature == 0.0
        assert cfg.inference.max_tokens == 4096
        assert cfg.tools.max_file_size_bytes == 10_485_760
        assert len(cfg.tools.blocked_commands) > 0
        assert cfg.logging.level == "INFO"
        assert cfg.logging.format == "text"


class TestDefaultToml:
    def test_default_toml_is_valid(self, tmp_path: Path):
        toml_file = tmp_path / "harness.toml"
        toml_file.write_text(default_toml())
        cfg = load_config(toml_file)
        assert cfg.inference.base_url == "http://localhost:8000/v1"
        assert cfg.tools.bash_timeout == 60
