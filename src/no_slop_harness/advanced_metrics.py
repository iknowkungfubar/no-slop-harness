"""Advanced performance metrics for the No-Slop Harness.

Tracks token entropy, response variance, inter-step timing, and
implements the variance penalty function described in the
Engineering Intent Framework:

    P = α · σ²   (variance penalty)
    H = -Σ p_k log p_k   (token entropy)

These metrics enable continuous optimization of the agent pipeline
by identifying when the system is producing high-variance or
high-entropy outputs that indicate slop.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class TokenEntropyTracker:
    """Tracks per-response token entropy to detect low-information output.

    Calculates Shannon entropy over token probability distributions.
    High entropy → uncertain/unfocused output. Low entropy → confident/deterministic.
    """

    name: str = "token_entropy"
    _entropies: list[float] = field(default_factory=list)
    _token_counts: list[int] = field(default_factory=list)

    def observe(self, token_probs: Sequence[float], token_count: int) -> float:
        """Record token probabilities and compute entropy.

        Args:
            token_probs: Probability of each token in the response.
            token_count: Total number of tokens.

        Returns:
            Shannon entropy in bits.
        """
        # Shannon entropy: H = -Σ p_i * log2(p_i)
        entropy = 0.0
        for p in token_probs:
            if p > 0:
                entropy -= p * math.log2(p)

        self._entropies.append(entropy)
        self._token_counts.append(token_count)
        return entropy

    @property
    def mean_entropy(self) -> float:
        """Mean Shannon entropy across all observations."""
        if not self._entropies:
            return 0.0
        return sum(self._entropies) / len(self._entropies)

    @property
    def entropy_variance(self) -> float:
        """Variance of entropy values — high variance indicates inconsistent output quality."""
        if len(self._entropies) < 2:
            return 0.0
        mean = self.mean_entropy
        return sum((e - mean) ** 2 for e in self._entropies) / (len(self._entropies) - 1)

    @property
    def mean_token_count(self) -> float:
        """Average tokens per response."""
        if not self._token_counts:
            return 0.0
        return sum(self._token_counts) / len(self._token_counts)

    @property
    def is_slop_likely(self) -> bool:
        """Heuristic: high entropy + high token count → likely slop.

        Returns True if mean entropy exceeds 4.0 bits AND mean tokens exceed 500.
        """
        return self.mean_entropy > 4.0 and self.mean_token_count > 500

    def snapshot(self) -> dict:
        """Return a snapshot of entropy statistics."""
        return {
            "name": self.name,
            "observations": len(self._entropies),
            "mean_entropy_bits": round(self.mean_entropy, 3),
            "entropy_variance": round(self.entropy_variance, 4),
            "mean_tokens": round(self.mean_token_count, 1),
            "slop_likely": self.is_slop_likely,
        }


@dataclass
class VariancePenalty:
    """Implements the variance penalty function from the Engineering Intent Framework.

    P = α · σ²

    Where:
    - σ² is the variance of response embeddings/scores across dialogue rounds
    - α is a scaling factor (default 1.0)

    A high variance penalty means the system is producing inconsistent
    responses across rounds — a signal of slop or hallucination.
    """

    alpha: float = 1.0
    _scores: list[float] = field(default_factory=list)

    def record(self, score: float) -> None:
        """Record a response quality score.

        Args:
            score: Quality score (e.g., faithfulness, relevance, 0.0-1.0).
        """
        self._scores.append(score)

    @property
    def variance(self) -> float:
        """Population variance σ² of recorded scores."""
        n = len(self._scores)
        if n < 2:
            return 0.0
        mean = sum(self._scores) / n
        return sum((s - mean) ** 2 for s in self._scores) / n

    @property
    def penalty(self) -> float:
        """Computed penalty P = α · σ²."""
        return self.alpha * self.variance

    @property
    def mean_score(self) -> float:
        """Mean of recorded scores."""
        if not self._scores:
            return 0.0
        return sum(self._scores) / len(self._scores)

    @property
    def is_unstable(self) -> bool:
        """Heuristic: penalty > 0.1 means the system is unstable."""
        return self.penalty > 0.1

    def snapshot(self) -> dict:
        """Return a snapshot of variance statistics."""
        return {
            "observations": len(self._scores),
            "mean_score": round(self.mean_score, 4),
            "variance_sigma2": round(self.variance, 6),
            "penalty": round(self.penalty, 6),
            "unstable": self.is_unstable,
            "alpha": self.alpha,
        }


@dataclass
class InterStepTimer:
    """Tracks timing between CIV pipeline phases.

    Measures the latency of each phase transition to identify
    bottlenecks in the agent pipeline.
    """

    _phase_times: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _step_count: int = 0

    def record_phase(self, phase: str, duration_ms: float) -> None:
        """Record the duration of a pipeline phase.

        Args:
            phase: Phase name (e.g., "coordinator", "implement", "verify").
            duration_ms: Duration in milliseconds.
        """
        self._phase_times[phase].append(duration_ms)
        self._step_count += 1

    def phase_stats(self) -> dict[str, dict]:
        """Compute statistics for each phase.

        Returns:
            Dict mapping phase name to {count, mean_ms, min_ms, max_ms}.
        """
        stats: dict[str, dict] = {}
        for phase, times in self._phase_times.items():
            if not times:
                continue
            stats[phase] = {
                "count": len(times),
                "mean_ms": round(sum(times) / len(times), 1),
                "min_ms": round(min(times), 1),
                "max_ms": round(max(times), 1),
                "total_ms": round(sum(times), 1),
            }

        # Calculate % of total time per phase
        total = sum(s["total_ms"] for s in stats.values())
        if total > 0:
            for phase in stats:
                stats[phase]["pct_of_total"] = round(
                    stats[phase]["total_ms"] / total * 100, 1
                )

        return stats

    @property
    def bottleneck_phase(self) -> str | None:
        """Identify the slowest phase."""
        stats = self.phase_stats()
        if not stats:
            return None
        return max(stats, key=lambda p: stats[p]["mean_ms"])

    def snapshot(self) -> dict:
        """Return a snapshot of inter-step timing."""
        return {
            "step_count": self._step_count,
            "phases": self.phase_stats(),
            "bottleneck": self.bottleneck_phase,
        }


class AdvancedMetricsRegistry:
    """Unified registry for advanced pipeline metrics.

    Combines token entropy tracking, variance penalty, and inter-step
    timing into a single reportable interface.

    Usage:
        reg = AdvancedMetricsRegistry()
        reg.entropy.observe([0.1, 0.2, 0.3, 0.4], token_count=4)
        reg.variance.record(0.85)
        reg.timing.record_phase("coordinator", 1500.0)
        print(reg.report())
    """

    def __init__(self) -> None:
        self.entropy = TokenEntropyTracker()
        self.variance = VariancePenalty()
        self.timing = InterStepTimer()

    def report(self) -> dict:
        """Return a comprehensive metrics report."""
        return {
            "entropy": self.entropy.snapshot(),
            "variance_penalty": self.variance.snapshot(),
            "inter_step_timing": self.timing.snapshot(),
            "overall_health": self._health_assessment(),
        }

    def _health_assessment(self) -> dict:
        """Assess overall pipeline health based on metrics."""
        issues: list[str] = []

        if self.entropy.is_slop_likely:
            issues.append("High token entropy detected — possible slop")

        if self.variance.is_unstable:
            issues.append("High response variance — system may be unstable")

        bottleneck = self.timing.bottleneck_phase
        if bottleneck:
            stats = self.timing.phase_stats().get(bottleneck, {})
            if stats.get("pct_of_total", 0) > 60:
                issues.append(f"Bottleneck at '{bottleneck}' phase ({stats['pct_of_total']}% of time)")  # noqa: E501

        return {
            "status": "healthy" if not issues else "degraded",
            "issues": issues,
        }
