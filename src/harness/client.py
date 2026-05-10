"""OpenAI-compatible inference client with constrained decoding support."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class InferenceClient:
    """Wraps an OpenAI-compatible endpoint, injecting schema constraints into sampling params.

    Supports two constraint mechanisms:
    - Standard ``response_format`` (OpenAI / vLLM structured output)
    - ``guided_json`` extra body parameter (vLLM-specific llguidance integration)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "not-needed",
        model: str = "default",
    ):
        self.openai = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def generate(
        self,
        messages: list[dict[str, str]],
        schema: type[T] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text, optionally constrained to *schema* at the logits level."""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if schema is not None:
            json_schema = schema.model_json_schema()
            # Standard OpenAI structured-output format
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": json_schema,
                    "strict": True,
                },
            }
            # vLLM guided-decoding extension (llguidance state-machine injection)
            kwargs["extra_body"] = {"guided_json": json.dumps(json_schema)}

        completion = self.openai.chat.completions.create(**kwargs)
        return completion.choices[0].message.content or ""

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        """Generate and parse a schema-validated response."""
        raw = self.generate(
            messages=messages,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return schema.model_validate_json(raw)
