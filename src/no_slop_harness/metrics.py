"""Observability and metrics for the No-Slop Harness pipeline.

Provides counters, timers, and histograms for tracking pipeline
performance, task durations, and verification outcomes.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Counter:
    """A monotonically increasing counter with labels."""

    name: str
    description: str = ""
    _value: int = field(default=0, init=False)
    _labels: dict[str, int] = field(default_factory=lambda: defaultdict(int), init=False)

    def inc(self, amount: int = 1, labels: dict[str, str] | None = None) -> None:
        """Increment the counter.

        Args:
            amount: Amount to increment by.
            labels: Optional label dimensions for the increment.
        """
        self._value += amount
        if labels:
            key = _labels_key(labels)
            self._labels[key] += amount

    @property
    def value(self) -> int:
        """Current counter value."""
        return self._value

    def get_label(self, labels: dict[str, str]) -> int:
        """Get counter value for specific label dimensions."""
        return self._labels.get(_labels_key(labels), 0)

    def snapshot(self) -> dict:
        """Return a snapshot of the counter state."""
        return {
            "name": self.name,
            "value": self._value,
            "labels": dict(self._labels),
        }

    def reset(self) -> None:
        """Reset counter to zero."""
        self._value = 0
        self._labels.clear()


@dataclass
class Timer:
    """A wall-clock timer that records duration statistics."""

    name: str
    description: str = ""
    _count: int = field(default=0, init=False)
    _total_ms: float = field(default=0.0, init=False)
    _min_ms: float = field(default=float("inf"), init=False)
    _max_ms: float = field(default=0.0, init=False)

    def record(self, duration_ms: float) -> None:
        """Record a duration in milliseconds.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self._count += 1
        self._total_ms += duration_ms
        self._min_ms = min(self._min_ms, duration_ms)
        self._max_ms = max(self._max_ms, duration_ms)

    def time(self) -> _TimerContext:
        """Context manager for timing a block of code.

        Usage:
            timer = Timer("my_operation")
            with timer.time():
                do_work()
        """
        return _TimerContext(self)

    @property
    def count(self) -> int:
        """Number of recorded observations."""
        return self._count

    @property
    def avg_ms(self) -> float:
        """Average duration in milliseconds."""
        return self._total_ms / self._count if self._count > 0 else 0.0

    @property
    def min_ms(self) -> float:
        """Minimum observed duration in milliseconds."""
        return self._min_ms if self._count > 0 else 0.0

    @property
    def max_ms(self) -> float:
        """Maximum observed duration in milliseconds."""
        return self._max_ms

    @property
    def total_ms(self) -> float:
        """Total accumulated duration in milliseconds."""
        return self._total_ms

    def snapshot(self) -> dict:
        """Return a snapshot of the timer state."""
        return {
            "name": self.name,
            "count": self._count,
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_ms, 3) if self._count > 0 else 0.0,
            "max_ms": round(self.max_ms, 3),
            "total_ms": round(self._total_ms, 3),
        }

    def reset(self) -> None:
        """Reset timer statistics."""
        self._count = 0
        self._total_ms = 0.0
        self._min_ms = float("inf")
        self._max_ms = 0.0


class _TimerContext:
    """Context manager for timing blocks with a Timer."""

    def __init__(self, timer: Timer) -> None:
        self._timer = timer
        self._start: float = 0.0

    def __enter__(self) -> _TimerContext:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        self._timer.record(elapsed_ms)


@dataclass
class Histogram:
    """A histogram with configurable buckets for distribution tracking."""

    name: str
    buckets: tuple[float, ...] = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000)
    description: str = ""
    _counts: list[int] = field(default_factory=list, init=False)
    _sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._counts = [0] * (len(self.buckets) + 1)  # +1 for overflow

    def observe(self, value_ms: float) -> None:
        """Record an observation in milliseconds.

        Args:
            value_ms: Value in milliseconds to record.
        """
        self._count += 1
        self._sum += value_ms
        for i, bound in enumerate(self.buckets):
            if value_ms <= bound:
                self._counts[i] += 1
                return
        self._counts[-1] += 1  # overflow bucket

    def snapshot(self) -> dict:
        """Return a snapshot of the histogram state."""
        return {
            "name": self.name,
            "count": self._count,
            "sum_ms": round(self._sum, 3),
            "avg_ms": round(self._sum / self._count, 3) if self._count > 0 else 0.0,
            "buckets": {
                f"le_{b}": c for b, c in zip(self.buckets, self._counts[:-1], strict=False)
            },
            "overflow": self._counts[-1],
        }


class MetricsRegistry:
    """Central registry for counters, timers, and histograms.

    Usage:
        registry = MetricsRegistry()
        tasks_total = registry.counter("tasks_total", "Total tasks processed")
        task_duration = registry.timer("task_duration_ms", "Task execution time")

        tasks_total.inc()
        with task_duration.time():
            execute_task()

        print(registry.report())
    """

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._timers: dict[str, Timer] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter."""
        if name not in self._counters:
            self._counters[name] = Counter(name=name, description=description)
        return self._counters[name]

    def timer(self, name: str, description: str = "") -> Timer:
        """Get or create a timer."""
        if name not in self._timers:
            self._timers[name] = Timer(name=name, description=description)
        return self._timers[name]

    def histogram(
        self,
        name: str,
        buckets: tuple[float, ...] = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000),
        description: str = "",
    ) -> Histogram:
        """Get or create a histogram."""
        if name not in self._histograms:
            self._histograms[name] = Histogram(
                name=name, buckets=buckets, description=description
            )
        return self._histograms[name]

    def report(self) -> dict:
        """Return a full metrics report."""
        return {
            "counters": {n: c.snapshot() for n, c in self._counters.items()},
            "timers": {n: t.snapshot() for n, t in self._timers.items()},
            "histograms": {n: h.snapshot() for n, h in self._histograms.items()},
        }

    def reset(self) -> None:
        """Reset all metrics."""
        for c in self._counters.values():
            c.reset()
        for t in self._timers.values():
            t.reset()
        # Histograms have no reset — create fresh ones
        self._histograms.clear()


def _labels_key(labels: dict[str, str]) -> str:
    """Create a stable key from label dimensions."""
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
