"""Test suite for constrained decoding module."""

from __future__ import annotations

import pytest

from no_slop_harness.constrained import (
    ConstrainedDecoder,
    _build_llguidance_grammar,
    _parse_and_validate,
    _schema_to_rule,
)
from no_slop_harness.llm_client import LLMClient, LLMClientConfig


class TestGrammarBuilder:
    """llguidance grammar construction from JSON Schema."""

    def test_string_rule(self) -> None:
        assert _schema_to_rule({"type": "string"}) == "string"

    def test_integer_rule(self) -> None:
        assert _schema_to_rule({"type": "integer"}) == "integer"

    def test_boolean_rule(self) -> None:
        rule = _schema_to_rule({"type": "boolean"})
        assert "true" in rule and "false" in rule

    def test_object_grammar(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name"],
        }
        grammar = _build_llguidance_grammar(schema)
        assert "name" in grammar
        assert "count" in grammar
        assert "root ::=" in grammar


class TestParseAndValidate:
    """JSON parsing and schema validation."""

    def test_valid_object(self) -> None:
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            value: int

        result = _parse_and_validate('{"name": "test", "value": 42}', TestModel)
        assert result.name == "test"
        assert result.value == 42

    def test_invalid_json_raises(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_and_validate("not json", M)

    def test_schema_mismatch_raises(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        with pytest.raises(ValueError, match="does not match schema"):
            _parse_and_validate('{"wrong_field": 1}', M)

    def test_strips_code_fences(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        result = _parse_and_validate('```json\n{"x": 1}\n```', M)
        assert result.x == 1


class TestConstrainedDecoder:
    """ConstrainedDecoder initialization and fallback behavior."""

    def test_init(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        decoder = ConstrainedDecoder(client)
        assert decoder._client is client

    def test_enabled_property(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        decoder = ConstrainedDecoder(client)
        # llguidance may or may not be installed — just check it's a bool
        assert isinstance(decoder.enabled, bool)
