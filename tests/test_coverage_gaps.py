"""Additional coverage for worktree, sdlc, runner, and openai provider."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from no_slop_harness.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from no_slop_harness.runner import CIVPipeline
from no_slop_harness.sdlc import SDLCContext, SDLCLoader
from no_slop_harness.worktree import IsolatedContext, WorktreeIsolation


class TestIsolatedContext:
    def test_cwd_property(self) -> None:
        ctx = IsolatedContext(
            task_id="t1",
            branch_name="br",
            worktree_path=Path("/tmp/wt"),  # noqa: S108
            repo_path=Path("/tmp/repo"),  # noqa: S108
        )
        assert ctx.cwd == Path("/tmp/wt")  # noqa: S108


class TestWorktreeInit:
    def test_custom_worktrees_dir(self, tmp_path: Path) -> None:
        iso = WorktreeIsolation(repo_path=tmp_path, worktrees_dir=tmp_path / "custom")
        assert iso.worktrees_dir == tmp_path / "custom"

    def test_default_worktrees_dir(self, tmp_path: Path) -> None:
        iso = WorktreeIsolation(repo_path=tmp_path)
        assert iso.worktrees_dir == tmp_path / ".no-slop" / "worktrees"

    def test_list_empty(self, tmp_path: Path) -> None:
        iso = WorktreeIsolation(repo_path=tmp_path)
        assert iso.list_active() == []


class TestSDLCContextExtra:
    def test_truncation_boundary(self) -> None:
        ctx = SDLCContext()
        ctx.adrs.append({"title": "ADR 1", "content": "x" * 100})
        text = ctx.to_prompt_text(max_chars=50)
        assert len(text) <= 50 + 20  # Some overhead for truncation message

    def test_max_patterns_limit(self) -> None:
        ctx = SDLCContext()
        for i in range(5):
            ctx.patterns.append({"title": f"P{i}", "content": f"code{i}"})
        text = ctx.to_prompt_text()
        # Only first 3 should appear
        assert "P0" in text
        assert "P3" not in text

    def test_max_adrs_limit(self) -> None:
        ctx = SDLCContext()
        for i in range(10):
            ctx.adrs.append({"title": f"ADR {i}", "content": f"content {i}"})
        text = ctx.to_prompt_text()
        # Only last 5 should appear
        assert "ADR 5" in text
        assert "ADR 0" not in text


class TestSDLCLoaderExtra:
    def test_load_config_yaml(self, tmp_path: Path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.init_sdlc()
        # config.yaml was written during init
        ctx = loader.load()
        assert isinstance(ctx.config, dict)

    def test_save_memory_new_file(self, tmp_path: Path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.save_memory("key1", "value1")
        ctx = loader.load()
        assert ctx.memory["key1"] == "value1"

    def test_save_memory_overwrite(self, tmp_path: Path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.save_memory("x", 1)
        loader.save_memory("x", 2)
        ctx = loader.load()
        assert ctx.memory["x"] == 2


class TestOpenAIProvider:
    def test_config_defaults(self) -> None:
        cfg = OpenAICompatibleConfig()
        assert cfg.base_url == "http://localhost:1234/v1"
        assert cfg.api_key == "not-needed"

    def test_config_custom(self) -> None:
        cfg = OpenAICompatibleConfig(
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            api_key="sk-test",
            timeout_seconds=60,
            max_retries=5,
        )
        assert cfg.model == "gpt-4o"
        assert cfg.timeout_seconds == 60

    def test_provider_no_httpx_raises(self) -> None:
        """Provider raises helpful error without httpx."""
        with mock_httpx(False):
            with pytest.raises(ImportError, match="httpx"):
                OpenAICompatibleProvider()


class TestCIVPipelineInit:
    def test_init_defaults(self) -> None:
        pipeline = CIVPipeline(base_url="https://example.com/v1", model="test")
        assert pipeline._client is not None
        assert pipeline._coordinator is not None
        assert pipeline._implementor is not None
        assert pipeline._verifier is not None

    def test_init_with_sandbox(self) -> None:
        from no_slop_harness.schemas import SandboxConfig

        sandbox = SandboxConfig(allowed_commands=["ls"], timeout_seconds=30)
        pipeline = CIVPipeline(
            base_url="https://example.com/v1", model="test", sandbox_config=sandbox
        )
        assert pipeline._sandbox.allowed_commands == ["ls"]

    def test_init_with_work_dir(self, tmp_path: Path) -> None:
        pipeline = CIVPipeline(base_url="https://example.com/v1", model="test", work_dir=tmp_path)
        assert pipeline._work_dir == tmp_path

    def test_close(self, tmp_path: Path) -> None:
        pipeline = CIVPipeline(base_url="https://example.com/v1", model="test")
        asyncio.run(pipeline.close())


def mock_httpx(available: bool):
    """Context manager to mock _HAS_HTTPX in the provider module."""
    from unittest import mock

    import no_slop_harness.providers.openai_compatible as mod

    return mock.patch.object(mod, "_HAS_HTTPX", available)
