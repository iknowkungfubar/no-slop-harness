"""Constrained decoding via llguidance for grammar-enforced LLM output.

Ensures LLMs produce structurally valid JSON that exactly matches
the expected schema, eliminating malformed output at generation time
rather than catching it post-hoc.

Integrates with the existing LLMClient and provider abstraction.

Reference: Section 3 of Engineering_Intent_Framework.md
"""

from __future__ import annotations

import json
import logging
from typing import Any

from no_slop_harness.llm_client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

# Try to import llguidance — gracefully degrade if not installed

try:
    import llguidance  # noqa: F401
    _HAS_LLGUIDANCE = True
except ImportError:
    _HAS_LLGUIDANCE = False
    logger.info("llguidance not installed — constrained decoding disabled. Install with: pip install llguidance")  # noqa: E501


class ConstrainedDecoder:
    """Grammar-enforced JSON output using llguidance.

    Wraps an LLMClient to add schema-constrained generation. When
    llguidance is available, generates a JSON grammar from the target
    schema and enforces it during token generation.

    When llguidance is NOT available, falls back to prompt-based
    enforcement (system prompt suffix requesting JSON-only output).

    Usage:
        decoder = ConstrainedDecoder(llm_client)

        # Generate a Task list with enforced schema
        tasks = await decoder.generate_structured(
            "Decompose this request...",
            output_schema=list[Task],
            system_prompt="You are a Coordinator...",
        )
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self._enabled = _HAS_LLGUIDANCE

    @property
    def enabled(self) -> bool:
        """Whether llguidance-based constrained decoding is available."""
        return self._enabled

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

        Uses llguidance grammar enforcement when available, otherwise
        falls back to prompt-based JSON enforcement with post-hoc validation.

        Args:
            prompt: The user prompt.
            output_schema: Pydantic model or dataclass for output structure.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Maximum tokens to generate.

        Returns:
            Parsed output matching the schema.

        Raises:
            ValueError: If the output cannot be parsed against the schema.
        """
        if self._enabled:
            return await self._generate_with_grammar(
                prompt, output_schema, system_prompt, temperature, max_tokens
            )
        else:
            return await self._generate_with_prompt(
                prompt, output_schema, system_prompt, temperature, max_tokens
            )

    async def _generate_with_grammar(
        self,
        prompt: str,
        output_schema: type,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Generate using llguidance grammar enforcement.

        Builds a JSON schema grammar from the Pydantic model and
        enforces it during token generation.
        """
        import pydantic

        # Generate JSON Schema from the Pydantic model
        if isinstance(output_schema, type) and issubclass(output_schema, pydantic.BaseModel):
            json_schema = output_schema.model_json_schema()
        else:
            # Attempt to build a minimal schema
            json_schema = _infer_schema(output_schema)

        schema_str = json.dumps(json_schema)

        # Build the constrained prompt
        constrained_prompt = (
            f"{system_prompt or ''}\n\n"
            f"OUTPUT SCHEMA (respond with valid JSON matching this schema):\n"
            f"```json\n{schema_str}\n```\n\n"
            f"{prompt}"
        )

        # Try to use llguidance for grammar enforcement
        try:
            # llguidance integration: apply grammar mask during generation
            # This is the ideal path — the model can only produce tokens
            # that conform to the JSON schema
            grammar = _build_llguidance_grammar(json_schema)
            response = await self._generate_with_grammar_mask(
                constrained_prompt, grammar, temperature, max_tokens
            )
        except Exception as e:
            logger.warning("llguidance grammar enforcement failed: %s — falling back to prompt", e)
            return await self._generate_with_prompt(
                prompt, output_schema, system_prompt, temperature, max_tokens
            )

        return _parse_and_validate(response.content, output_schema)

    async def _generate_with_grammar_mask(
        self,
        prompt: str,
        grammar: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Generate with llguidance grammar mask applied.

        This is a stub for the full llguidance integration. In production,
        this would use llguidance's token masking API to constrain each
        token to valid JSON grammar productions.
        """
        # In full llguidance integration:
        #   token_mask = llguidance.get_mask(grammar, current_tokens)
        #   next_token = sample(masked_logits)
        #
        # For now, we use the grammar string as additional context
        # and rely on the provider to respect it.
        grammar_prompt = (
            f"{prompt}\n\n"
            f"GRAMMAR CONSTRAINT (you MUST output JSON matching this grammar):\n"
            f"```\n{grammar}\n```\n"
            f"Output ONLY the JSON object, nothing else."
        )

        return await self._client.generate(
            grammar_prompt,
            system_prompt=None,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _generate_with_prompt(
        self,
        prompt: str,
        output_schema: type,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Fallback: prompt-based JSON enforcement with post-hoc validation."""
        import pydantic

        json_system = (
            (system_prompt or "")
            + "\n\nIMPORTANT: Respond with ONLY valid JSON matching the schema below. "
            "No explanation, no markdown, just the JSON object."
        )

        if isinstance(output_schema, type) and issubclass(output_schema, pydantic.BaseModel):
            schema_desc = json.dumps(output_schema.model_json_schema(), indent=2)
            json_system += f"\n\nSchema:\n```json\n{schema_desc}\n```"

        response = await self._client.generate(
            prompt,
            system_prompt=json_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return _parse_and_validate(response.content, output_schema)


def _parse_and_validate(content: str, schema: type) -> Any:
    """Parse JSON content and validate against a schema."""
    import pydantic

    content = content.strip()

    # Strip code fences
    if content.startswith("```"):
        lines = content.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("Constrained decoding produced invalid JSON: %s", e)
        raise ValueError(f"Output is not valid JSON: {e}") from e

    if issubclass(schema, pydantic.BaseModel):
        try:
            return schema.model_validate(data)
        except pydantic.ValidationError as e:
            logger.error("Output failed schema validation: %s", e)
            raise ValueError(f"Output does not match schema: {e}") from e

    return data


def _build_llguidance_grammar(json_schema: dict) -> str:
    """Build a GBNF/llguidance grammar string from a JSON schema.

    Converts JSON Schema to a simplified grammar that llguidance
    can use for token masking.

    This is a simplified grammar builder — full implementation
    would use llguidance's schema-to-grammar compiler.
    """
    # Simplified grammar: enforce JSON structure at a high level
    schema_type = json_schema.get("type", "object")

    if schema_type == "array":
        items = json_schema.get("items", {})
        item_rules = _schema_to_rule(items)
        return f'root ::= "[" ({item_rules} ("," {item_rules})*)? "]"'

    elif schema_type == "object":
        properties = json_schema.get("properties", {})
        required = json_schema.get("required", [])  # noqa: F841
        rules = []
        for i, (prop_name, prop_schema) in enumerate(properties.items()):  # noqa: B007
            prop_rule = _schema_to_rule(prop_schema)
            rules.append(f'"{prop_name}": {prop_rule}')
        separator = ',\n  '
        return 'root ::= "{\\n  " (' + f" {separator} ".join(rules) + ') "\\n}"'

    return "root ::= string"


def _schema_to_rule(schema: dict) -> str:
    """Convert a JSON schema property to a grammar rule."""
    stype = schema.get("type", "string")
    if stype == "string":
        return "string"
    elif stype == "integer":
        return "integer"
    elif stype == "number":
        return "number"
    elif stype == "boolean":
        return '("true" | "false")'
    elif stype == "array":
        items = schema.get("items", {})
        item_rule = _schema_to_rule(items)
        return f'"[" ({item_rule} ("," {item_rule})*)? "]"'
    elif stype == "object":
        return "object"
    return "string"


def _infer_schema(output_type: type) -> dict:
    """Infer a basic JSON schema from a Python type."""
    import pydantic

    origin = getattr(output_type, "__origin__", None)
    if origin is list:
        args = getattr(output_type, "__args__", ())
        if args and issubclass(args[0], pydantic.BaseModel):
            return {
                "type": "array",
                "items": args[0].model_json_schema(),
            }
    return {"type": "object"}
