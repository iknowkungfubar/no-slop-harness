"""OpenAI-compatible LLM provider.

Works with any OpenAI-compatible API endpoint:
- LM Studio (http://localhost:1234/v1)
- OpenRouter (https://openrouter.ai/api/v1)
- OpenAI (https://api.openai.com/v1)
- Any self-hosted vLLM/Ollama endpoint
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field  # noqa: F401
from typing import Any

import httpx

from no_slop_harness.llm_client import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class OpenAICompatibleConfig:
    """Configuration for an OpenAI-compatible API endpoint."""

    base_url: str = "http://localhost:1234/v1"
    api_key: str = "not-needed"
    model: str = "qwen/qwen3.6-35b-a3b"
    timeout_seconds: float = 120.0
    max_retries: int = 3


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for any OpenAI-compatible chat completions API.

    Usage:
        provider = OpenAICompatibleProvider(
            config=OpenAICompatibleConfig(
                base_url="http://localhost:1234/v1",
                model="qwen/qwen3.6-35b-a3b",
            )
        )
        response = await provider.generate("Write a Python function...")
    """

    def __init__(self, config: OpenAICompatibleConfig | None = None) -> None:
        self.config = config or OpenAICompatibleConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )

    @property
    def provider_name(self) -> str:
        return f"openai_compatible@{self.config.base_url}"

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion via the chat completions API."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop_sequences:
            body["stop"] = stop_sequences

        logger.debug(
            "Calling %s/chat/completions with model=%s", self.config.base_url, self.config.model
        )  # noqa: E501

        resp = await self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.config.model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def generate_structured(
        self,
        prompt: str,
        output_schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        """Generate a structured output by requesting JSON and parsing it.

        Uses a system prompt suffix to force JSON output, then parses
        the response into the given schema.
        """
        import pydantic

        json_system = (
            (system_prompt or "")
            + "\n\nIMPORTANT: Respond with ONLY valid JSON. No explanation, no markdown fences, just the JSON object."  # noqa: E501
        )

        response = await self.generate(
            prompt,
            system_prompt=json_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM response: %s...", content[:200])
            raise ValueError(f"LLM did not return valid JSON. Response: {content[:500]}")  # noqa: B904

        if issubclass(output_schema, pydantic.BaseModel):
            return output_schema.model_validate(data)
        return output_schema(**data) if isinstance(data, dict) else data

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatibleProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
