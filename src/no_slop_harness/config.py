"""Configuration loader -- reads no-slop.toml files from user and project dirs.

Uses the stdlib ``tomllib`` (Python 3.11+) to parse TOML config files.

File locations (later files override earlier ones):
  1. ``~/.config/no-slop/config.toml`` -- user-global defaults
  2. ``./no-slop.toml`` -- per-project overrides

Supported sections:
  [api]
      base_url = "http://localhost:1234/v1"
      model   = "qwen/qwen3.6-35b-a3b"
      api_key = "not-needed"

  [sandbox]
      allowlist = ["python", "pytest", "ruff", "mypy"]
      timeout   = 120

  [worktrees]
      enabled = false
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class APIConfig:
    """LLM API connection settings."""

    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen/qwen3.6-35b-a3b"
    api_key: str = "not-needed"


@dataclass
class SandboxConfigFile:
    """Sandbox security settings (mirrors schema but from TOML)."""

    allowlist: list[str] = field(default_factory=list)
    timeout: int = 120


@dataclass
class WorktreesConfig:
    """Worktree-related settings."""

    enabled: bool = False


@dataclass
class NoSlopConfig:
    """Aggregated configuration from all sources."""

    api: APIConfig = field(default_factory=APIConfig)
    sandbox: SandboxConfigFile = field(default_factory=SandboxConfigFile)
    worktrees: WorktreesConfig = field(default_factory=WorktreesConfig)
    loaded_from: list[str] = field(default_factory=list)


def _load_toml(path: Path) -> dict[str, Any]:
    """Load and parse a TOML file, returning empty dict on missing/bad file."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (FileNotFoundError, PermissionError):
        return {}
    except tomllib.TOMLDecodeError as e:
        import warnings
        warnings.warn(f"Failed to parse config {path}: {e}", stacklevel=2)
        return {}


def _merge_section(
    cfg: dict[str, Any], section: str, defaults: dict[str, Any]
) -> dict[str, Any]:
    """Merge a config section from parsed TOML into defaults."""
    raw = cfg.get(section, {})
    if not isinstance(raw, dict):
        return defaults
    result = dict(defaults)
    result.update({k: v for k, v in raw.items() if v is not None})
    return result


def load_config() -> NoSlopConfig:
    """Load configuration from user and project TOML files.

    Later files override earlier ones:
        1. ~/.config/no-slop/config.toml  (user-global)
        2. ./no-slop.toml                  (project-local)
        3. Environment variables           (NO_SLOP_API_KEY, etc.)

    Returns:
        A merged ``NoSlopConfig`` dataclass.
    """
    config = NoSlopConfig()

    # Locations, in priority order (later wins)
    config_paths: list[Path] = [
        Path.home() / ".config" / "no-slop" / "config.toml",
        Path.cwd() / "no-slop.toml",
    ]

    merged: dict[str, Any] = {}
    for path in config_paths:
        data = _load_toml(path)
        if data:
            config.loaded_from.append(str(path))
            for section, values in data.items():
                if isinstance(values, dict):
                    if section not in merged:
                        merged[section] = {}
                    merged[section].update(values)
                else:
                    merged[section] = values

    # Extract sections with defaults
    api_defaults = {
        "base_url": config.api.base_url,
        "model": config.api.model,
        "api_key": config.api.api_key,
    }
    api_cfg = _merge_section(merged, "api", api_defaults)
    config.api = APIConfig(**api_cfg)

    sandbox_defaults = {
        "allowlist": config.sandbox.allowlist,
        "timeout": config.sandbox.timeout,
    }
    sandbox_cfg = _merge_section(merged, "sandbox", sandbox_defaults)
    config.sandbox = SandboxConfigFile(**sandbox_cfg)

    worktrees_defaults = {"enabled": config.worktrees.enabled}
    worktrees_cfg = _merge_section(merged, "worktrees", worktrees_defaults)
    config.worktrees = WorktreesConfig(**worktrees_cfg)

    # Environment variable overrides
    env_key = os.environ.get("NO_SLOP_API_KEY")
    if env_key:
        config.api.api_key = env_key

    env_base_url = os.environ.get("NO_SLOP_BASE_URL")
    if env_base_url:
        config.api.base_url = env_base_url

    return config
