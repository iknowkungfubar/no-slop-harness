"""LLM client abstraction with pluggable provider backends.

Supports multiple LLM providers through a unified interface,
with built-in retry logic, structured output parsing, and
metrics collection.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .metrics import MetricsRegistry

logger = logging.getLogger(__name__)


# ── Provider protocol ───────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """Standardized LLM response across all providers."""

    content: str
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    raw: Any = None  # Provider-specific raw response


class LLMProvider(ABC):
    """Abstract base for LLM provider implementations."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion from the provider.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.
            stop_sequences: Optional stop sequences.

        Returns:
            Standardized LLMResponse.
        """
        ...

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        output_schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        """Generate a structured output matching the given schema.

        Args:
            prompt: The user prompt.
            output_schema: Pydantic model or dataclass for output parsing.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens.

        Returns:
            Parsed output matching the schema.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
        ...


# ── LLM Client ──────────────────────────────────────────────────────────────


@dataclass
class LLMClientConfig:
    """Configuration for the LLM client."""

    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 120.0
    system_prompt: str | None = None


class LLMClient:
    """Unified LLM client with provider abstraction and retry logic.

    Usage:
        client = LLMClient(config=LLMClientConfig(provider="openai", model="gpt-4o"))
        client.register_provider("openai", OpenAIProvider(api_key="..."))

        response = await client.generate("Explain the CIV pattern.")
        tasks = await client.generate_structured(
            "Decompose this into tasks",
            output_schema=list[Task],
        )
    """

    def __init__(
        self,
        config: LLMClientConfig | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.config = config or LLMClientConfig()
        self.metrics = metrics or MetricsRegistry()
        self._providers: dict[str, LLMProvider] = {}
        self._generate_timer = self.metrics.timer("llm_generate_ms", "LLM generation latency")
        self._generate_counter = self.metrics.counter("llm_requests_total", "Total LLM requests")
        self._error_counter = self.metrics.counter("llm_errors_total", "Total LLM errors")

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        """Register an LLM provider backend.

        Args:
            name: Provider name (e.g., "openai", "anthropic", "local").
            provider: Provider implementation.
        """
        self._providers[name] = provider
        logger.info("Registered LLM provider: %s", name)

    def get_provider(self, name: str | None = None) -> LLMProvider:
        """Get a registered provider by name.

        Args:
            name: Provider name. Uses config default if None.

        Returns:
            The LLMProvider instance.

        Raises:
            ValueError: If the provider is not registered.
        """
        name = name or self.config.provider
        if name not in self._providers:
            raise ValueError(
                f"Provider '{name}' not registered. Available: {list(self._providers)}"
            )
        return self._providers[name]

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion with automatic retries.

        Args:
            prompt: The user prompt.
            system_prompt: Optional override for system prompt.
            temperature: Optional override for temperature.
            max_tokens: Optional override for max tokens.
            stop_sequences: Optional stop sequences.

        Returns:
            Standardized LLMResponse.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        provider = self.get_provider()
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        sys_prompt = system_prompt if system_prompt is not None else self.config.system_prompt

        last_error: Exception | None = None

        for attempt in range(self.config.max_retries):
            try:
                with self._generate_timer.time():
                    response = await asyncio.wait_for(
                        provider.generate(
                            prompt,
                            system_prompt=sys_prompt,
                            temperature=temp,
                            max_tokens=tokens,
                            stop_sequences=stop_sequences,
                        ),
                        timeout=self.config.timeout_seconds,
                    )
                self._generate_counter.inc()
                return response
            except TimeoutError:
                last_error = TimeoutError(
                    f"LLM request timed out after {self.config.timeout_seconds}s"
                )
                logger.warning("LLM timeout (attempt %d/%d)", attempt + 1, self.config.max_retries)
            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM error (attempt %d/%d): %s",
                    attempt + 1,
                    self.config.max_retries,
                    e,
                )

            if attempt < self.config.max_retries - 1:
                delay = self.config.retry_delay_seconds * (2 ** attempt)
                await asyncio.sleep(delay)

        self._error_counter.inc()
        raise RuntimeError(
            f"LLM generation failed after {self.config.max_retries} attempts. "
            f"Last error: {last_error}"
        )

    async def generate_structured(
        self,
        prompt: str,
        output_schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        """Generate a structured output using the provider's native parsing.

        Args:
            prompt: The user prompt.
            output_schema: Pydantic model or dataclass for parsing.
            system_prompt: Optional override for system prompt.
            temperature: Optional override for temperature.
            max_tokens: Optional override for max tokens.

        Returns:
            Parsed output matching the schema.
        """
        provider = self.get_provider()
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        sys_prompt = system_prompt if system_prompt is not None else self.config.system_prompt

        with self._generate_timer.time():
            result = await asyncio.wait_for(
                provider.generate_structured(
                    prompt,
                    output_schema,
                    system_prompt=sys_prompt,
                    temperature=temp,
                    max_tokens=tokens,
                ),
                timeout=self.config.timeout_seconds,
            )
        self._generate_counter.inc()
        return result

    def list_providers(self) -> list[str]:
        """List registered provider names."""
        return list(self._providers.keys())
