"""Result types for TLA+ verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TLCResult:
    """Outcome of a TLC model-checking run.

    ``passed`` is True when all invariants and temporal properties hold within the
    configured model bounds. ``counterexample`` provides a human-readable trace
    showing the state sequence that violated an invariant, or None when the check
    passes.
    """

    passed: bool
    counterexample: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    error: str | None = None


@dataclass
class StaticAnalysisResult:
    """Result of the built-in static fallback analysis."""

    passed: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
