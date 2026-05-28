"""Test suite for .sdlc/ context injection."""

from __future__ import annotations

from no_slop_harness.sdlc import SDLCContext, SDLCLoader


class TestSDLCContext:
    """SDLCContext rendering and properties."""

    def test_empty_context(self) -> None:
        ctx = SDLCContext()
        text = ctx.to_prompt_text()
        assert text == ""

    def test_adr_injection(self) -> None:
        ctx = SDLCContext()
        ctx.adrs.append(
            {
                "title": "Use CIV Pattern",
                "content": "We decided to use the CIV pattern for all agent workflows.",
            }
        )
        text = ctx.to_prompt_text()
        assert "Use CIV Pattern" in text
        assert "CIV pattern" in text

    def test_standards_injection(self) -> None:
        ctx = SDLCContext()
        ctx.standards.append(
            {
                "title": "Python Style",
                "content": "- Use type annotations\n- Max line length 100",
            }
        )
        text = ctx.to_prompt_text()
        assert "Python Style" in text
        assert "type annotations" in text

    def test_max_chars_truncation(self) -> None:
        ctx = SDLCContext()
        ctx.adrs.append(
            {
                "title": "ADR 1",
                "content": "x" * 5000,
            }
        )
        text = ctx.to_prompt_text(max_chars=100)
        assert len(text) <= 100 + len("...(truncated)\n\n")

    def test_patterns_injection(self) -> None:
        ctx = SDLCContext()
        ctx.patterns.append(
            {
                "title": "Model Template",
                "content": "class BaseModel:\n    pass",
            }
        )
        text = ctx.to_prompt_text()
        assert "Model Template" in text
        assert "BaseModel" in text


class TestSDLCLoader:
    """SDLCLoader reads .sdlc/ directory structure."""

    def test_no_sdlc_directory(self, tmp_path) -> None:
        loader = SDLCLoader(tmp_path)
        assert not loader.exists
        ctx = loader.load()
        assert ctx.adrs == []
        assert ctx.standards == []

    def test_init_sdlc_creates_structure(self, tmp_path) -> None:
        loader = SDLCLoader(tmp_path)
        path = loader.init_sdlc()
        assert path.exists()
        assert (path / "adr").is_dir()
        assert (path / "standards").is_dir()
        assert (path / "patterns").is_dir()
        assert (path / "memory").is_dir()
        assert (path / "config.yaml").is_file()

    def test_load_adrs(self, tmp_path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.init_sdlc()
        adr_file = tmp_path / ".sdlc" / "adr" / "001-test.md"
        adr_file.write_text("# Test ADR\nThis is a test architecture decision.")

        ctx = loader.load()
        assert len(ctx.adrs) == 1
        assert ctx.adrs[0]["title"] == "Test ADR"
        assert "test architecture decision" in ctx.adrs[0]["content"]

    def test_load_standards(self, tmp_path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.init_sdlc()
        std_file = tmp_path / ".sdlc" / "standards" / "python.md"
        std_file.write_text("# Python Rules\n- Use types")

        ctx = loader.load()
        assert len(ctx.standards) == 1
        assert "Python Rules" in ctx.standards[0]["title"]

    def test_save_and_load_memory(self, tmp_path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.init_sdlc()
        loader.save_memory("last_run", "2026-05-28")
        loader.save_memory("model_used", "qwen-35b")

        ctx = loader.load()
        assert ctx.memory["last_run"] == "2026-05-28"
        assert ctx.memory["model_used"] == "qwen-35b"

    def test_load_patterns(self, tmp_path) -> None:
        loader = SDLCLoader(tmp_path)
        loader.init_sdlc()
        pat_file = tmp_path / ".sdlc" / "patterns" / "model.py"
        pat_file.write_text("class Base:\n    pass")

        ctx = loader.load()
        assert len(ctx.patterns) == 1
        assert "Base" in ctx.patterns[0]["content"]
