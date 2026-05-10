"""Configuration management via harness.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class InferenceConfig(BaseModel):
    """Inference server connection settings."""

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "not-needed"
    model: str = "default"
    temperature: float = 0.0
    max_tokens: int = 4096
    max_retries: int = 3
    timeout_seconds: int = 60


class ToolsConfig(BaseModel):
    """Tool execution constraints."""

    bash_timeout: int = 60
    max_file_size_bytes: int = 10_485_760  # 10 MB
    blocked_commands: list[str] = Field(
        default_factory=lambda: ["rm -rf /", "mkfs", "dd if=/dev/zero", ":(){:|:&};:"]
    )


class SecurityConfig(BaseModel):
    """Path restriction and sandbox settings."""

    restrict_paths: bool = True
    allowed_roots: list[str] = Field(default_factory=lambda: ["."])


class LoggingConfig(BaseModel):
    """Logging output settings."""

    level: str = "INFO"
    format: str = "text"  # "text" or "json"


class HarnessConfig(BaseModel):
    """Top-level harness configuration."""

    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: str | Path | None = None) -> HarnessConfig:
    """Load config from a TOML file. Returns defaults if path is None or missing."""
    if path is None:
        path = Path("harness.toml")
    else:
        path = Path(path)

    if not path.exists():
        return HarnessConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    return HarnessConfig.model_validate(raw)


def default_toml() -> str:
    """Return the default harness.toml content for ``harness init``."""
    return """\
[inference]
base_url = "http://localhost:8000/v1"
api_key = "not-needed"
model = "default"
temperature = 0.0
max_tokens = 4096
max_retries = 3
timeout_seconds = 60

[tools]
bash_timeout = 60
max_file_size_bytes = 10485760  # 10 MB
blocked_commands = ["rm -rf /", "mkfs", "dd if=/dev/zero", ":(){:|:&};:"]

[security]
restrict_paths = true
allowed_roots = ["."]

[logging]
level = "INFO"
format = "text"
"""
