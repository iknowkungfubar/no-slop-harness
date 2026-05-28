"""Test suite for advanced performance metrics."""

from __future__ import annotations

import pytest

from no_slop_harness.advanced_metrics import (
    AdvancedMetricsRegistry,
    InterStepTimer,
    TokenEntropyTracker,
    VariancePenalty,
)


class TestTokenEntropyTracker:
    """Token entropy tracking."""

    def test_uniform_distribution(self) -> None:
        tracker = TokenEntropyTracker()
        # Uniform distribution over 4 tokens → max entropy = 2.0 bits
        entropy = tracker.observe([0.25, 0.25, 0.25, 0.25], token_count=4)
        assert entropy == pytest.approx(2.0, abs=0.01)

    def test_deterministic_distribution(self) -> None:
        tracker = TokenEntropyTracker()
        # One token with probability 1.0 → entropy = 0.0
        entropy = tracker.observe([1.0], token_count=1)
        assert entropy == 0.0

    def test_mean_entropy(self) -> None:
        tracker = TokenEntropyTracker()
        tracker.observe([0.5, 0.5], token_count=2)  # 1.0 bits
        tracker.observe([1.0], token_count=1)  # 0.0 bits
        assert tracker.mean_entropy == pytest.approx(0.5, abs=0.01)

    def test_slop_detection(self) -> None:
        tracker = TokenEntropyTracker()
        # High entropy + high token count → slop (threshold: mean_entropy > 4.0, mean_tokens > 500)
        # Uniform distribution over 20 tokens gives -log2(1/20) = 4.32 bits > 4.0
        for _ in range(10):
            tracker.observe([0.05] * 20, token_count=1000)
        assert tracker.is_slop_likely

    def test_not_slop_when_low_entropy(self) -> None:
        tracker = TokenEntropyTracker()
        tracker.observe([1.0], token_count=10)
        assert not tracker.is_slop_likely

    def test_snapshot(self) -> None:
        tracker = TokenEntropyTracker()
        tracker.observe([0.5, 0.5], token_count=2)
        snap = tracker.snapshot()
        assert "mean_entropy_bits" in snap
        assert "slop_likely" in snap


class TestVariancePenalty:
    """Variance penalty P = α · σ²."""

    def test_no_variance(self) -> None:
        vp = VariancePenalty()
        vp.record(0.9)
        vp.record(0.9)
        vp.record(0.9)
        assert vp.variance == 0.0
        assert vp.penalty == 0.0

    def test_high_variance(self) -> None:
        vp = VariancePenalty(alpha=2.0)
        vp.record(0.1)
        vp.record(0.9)
        assert vp.variance > 0.1
        assert vp.penalty > 0.2
        assert vp.is_unstable

    def test_single_observation(self) -> None:
        vp = VariancePenalty()
        vp.record(0.5)
        assert vp.variance == 0.0
        assert vp.penalty == 0.0

    def test_snapshot(self) -> None:
        vp = VariancePenalty(alpha=1.5)
        vp.record(0.8)
        vp.record(0.6)
        snap = vp.snapshot()
        assert snap["alpha"] == 1.5
        assert "variance_sigma2" in snap
        assert "penalty" in snap


class TestInterStepTimer:
    """Phase timing and bottleneck detection."""

    def test_record_phase(self) -> None:
        timer = InterStepTimer()
        timer.record_phase("coordinator", 500.0)
        timer.record_phase("implement", 2000.0)
        timer.record_phase("verify", 300.0)

        stats = timer.phase_stats()
        assert stats["coordinator"]["count"] == 1
        assert stats["implement"]["mean_ms"] == 2000.0

    def test_bottleneck_detection(self) -> None:
        timer = InterStepTimer()
        timer.record_phase("coordinator", 100.0)
        timer.record_phase("implement", 5000.0)
        timer.record_phase("verify", 200.0)

        assert timer.bottleneck_phase == "implement"

    def test_pct_of_total(self) -> None:
        timer = InterStepTimer()
        timer.record_phase("a", 250.0)
        timer.record_phase("b", 750.0)

        stats = timer.phase_stats()
        assert stats["a"]["pct_of_total"] == 25.0
        assert stats["b"]["pct_of_total"] == 75.0


class TestAdvancedMetricsRegistry:
    """Unified metrics registry."""

    def test_report(self) -> None:
        reg = AdvancedMetricsRegistry()
        reg.entropy.observe([0.5, 0.5], token_count=2)
        reg.variance.record(0.9)
        reg.timing.record_phase("coordinator", 100.0)

        report = reg.report()
        assert "entropy" in report
        assert "variance_penalty" in report
        assert "inter_step_timing" in report
        assert "overall_health" in report
        assert report["overall_health"]["status"] in ("healthy", "degraded")
