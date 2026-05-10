"""OpenAI-compatible inference client with constrained decoding and resilience."""

from __future__ import annotations

import json
import logging
import time
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

    Includes retry with exponential backoff and health checking.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "not-needed",
        model: str = "default",
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self.openai = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        self.model = model
        self.max_retries = max_retries

    def health_check(self) -> bool:
        """Verify the inference endpoint is reachable."""
        try:
            self.openai.models.list()
            return True
        except Exception as e:
            logger.warning("Health check failed: %s", e)
            return False

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

        return self._call_with_retry(kwargs)

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

    def _call_with_retry(self, kwargs: dict) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                completion = self.openai.chat.completions.create(**kwargs)
                return completion.choices[0].message.content or ""
            except Exception as e:
                last_error = e
                if not self._is_retryable(e) or attempt >= self.max_retries:
                    break
                wait = min(2**attempt, 30)
                logger.warning(
                    "Attempt %d/%d failed (%s), retrying in %ds",
                    attempt + 1,
                    self.max_retries + 1,
                    e,
                    wait,
                )
                time.sleep(wait)
        raise RuntimeError(
            f"All {self.max_retries + 1} attempts failed"
        ) from last_error

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Return True for transient errors worth retrying."""
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
        if isinstance(exc, APIStatusError) and exc.status_code >= 500:
            return True
        return False

    @classmethod
    def from_config(cls, config) -> InferenceClient:
        """Create a client from a ``HarnessConfig`` or ``InferenceConfig``."""
        from .config import HarnessConfig, InferenceConfig

        if isinstance(config, HarnessConfig):
            cfg = config.inference
        elif isinstance(config, InferenceConfig):
            cfg = config
        else:
            raise TypeError(f"Expected HarnessConfig or InferenceConfig, got {type(config)}")

        return cls(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            max_retries=cfg.max_retries,
            timeout=cfg.timeout_seconds,
        )
