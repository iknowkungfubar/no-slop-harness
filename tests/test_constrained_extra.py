"""Additional coverage tests for constrained decoding module."""

from __future__ import annotations

import pytest

from no_slop_harness.constrained import (
    ConstrainedDecoder,
    _build_llguidance_grammar,
    _infer_schema,
    _parse_and_validate,
    _schema_to_rule,
)
from no_slop_harness.llm_client import LLMClient, LLMClientConfig, LLMProvider, LLMResponse


class MockDecoderProvider(LLMProvider):
    def __init__(self, response: str = '{"name": "test", "value": 42}') -> None:
        self._response = response

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(
        self, prompt, *, system_prompt=None, temperature=0.7, max_tokens=4096, stop_sequences=None
    ):
        return LLMResponse(content=self._response)

    async def generate_structured(
        self, prompt, output_schema, *, system_prompt=None, temperature=0.0, max_tokens=4096
    ):
        return {"name": "test", "value": 42}


class TestGrammarBuilder:
    def test_array_grammar(self) -> None:
        schema = {"type": "array", "items": {"type": "string"}}
        grammar = _build_llguidance_grammar(schema)
        assert "root ::=" in grammar
        assert "string" in grammar

    def test_object_with_required(self) -> None:
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "boolean"}},
            "required": ["x"],
        }
        grammar = _build_llguidance_grammar(schema)
        assert "x" in grammar
        assert "y" in grammar

    def test_number_rule(self) -> None:
        assert _schema_to_rule({"type": "number"}) == "number"

    def test_array_of_integers(self) -> None:
        rule = _schema_to_rule({"type": "array", "items": {"type": "integer"}})
        assert "integer" in rule

    def test_nested_object_fallback(self) -> None:
        assert _schema_to_rule({"type": "object"}) == "object"

    def test_default_rule(self) -> None:
        assert _schema_to_rule({"type": "unknown"}) == "string"


class TestInferSchema:
    def test_list_of_basemodel(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        schema = _infer_schema(list[M])
        assert schema["type"] == "array"

    def test_plain_type(self) -> None:
        schema = _infer_schema(dict)
        assert schema["type"] == "object"


class TestParseAndValidate:
    def test_bare_json(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            a: int

        result = _parse_and_validate('{"a": 99}', M)
        assert result.a == 99

    def test_code_fence_variants(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        # json fence
        result = _parse_and_validate('```json\n{"x": 1}\n```', M)
        assert result.x == 1
        # bare fence
        result = _parse_and_validate('```\n{"x": 2}\n```', M)
        assert result.x == 2

    def test_non_pydantic_schema(self) -> None:
        result = _parse_and_validate('{"a": 1}', dict)
        assert result == {"a": 1}


class TestConstrainedDecoderPrompt:
    def test_generate_structured_prompt_fallback(self) -> None:
        import asyncio

        from pydantic import BaseModel

        class M(BaseModel):
            name: str

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockDecoderProvider('{"name": "hello"}'))
        decoder = ConstrainedDecoder(client)

        result = asyncio.run(decoder.generate_structured("test", M))
        assert result.name == "hello"

    def test_generate_structured_invalid_json(self) -> None:
        import asyncio

        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockDecoderProvider("not json"))
        decoder = ConstrainedDecoder(client)

        with pytest.raises(ValueError):
            asyncio.run(decoder.generate_structured("test", M))
