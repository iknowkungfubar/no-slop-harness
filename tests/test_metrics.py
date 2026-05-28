"""Test suite for the observability metrics module."""

from __future__ import annotations

from no_slop_harness.metrics import Counter, Histogram, MetricsRegistry, Timer, _labels_key


class TestCounter:
    """Counter tracks monotonically increasing values with labels."""

    def test_initial_value_is_zero(self) -> None:
        c = Counter("test_counter")
        assert c.value == 0

    def test_inc_increments(self) -> None:
        c = Counter("test_counter")
        c.inc()
        assert c.value == 1
        c.inc(5)
        assert c.value == 6

    def test_inc_with_labels(self) -> None:
        c = Counter("test_counter")
        c.inc(labels={"status": "success"})
        c.inc(labels={"status": "success"})
        c.inc(labels={"status": "failed"})
        assert c.get_label({"status": "success"}) == 2
        assert c.get_label({"status": "failed"}) == 1
        assert c.get_label({"unknown": "key"}) == 0

    def test_snapshot(self) -> None:
        c = Counter("test_counter", description="A test counter")
        c.inc(3)
        snap = c.snapshot()
        assert snap["name"] == "test_counter"
        assert snap["value"] == 3

    def test_reset(self) -> None:
        c = Counter("test_counter")
        c.inc(10)
        c.inc(labels={"x": "y"})
        c.reset()
        assert c.value == 0
        assert c.get_label({"x": "y"}) == 0


class TestTimer:
    """Timer records wall-clock durations and computes statistics."""

    def test_empty_timer_returns_zeros(self) -> None:
        t = Timer("test_timer")
        assert t.count == 0
        assert t.avg_ms == 0.0
        assert t.min_ms == 0.0
        assert t.max_ms == 0.0
        assert t.total_ms == 0.0

    def test_record_updates_statistics(self) -> None:
        t = Timer("test_timer")
        t.record(10.0)
        t.record(20.0)
        assert t.count == 2
        assert t.avg_ms == 15.0
        assert t.min_ms == 10.0
        assert t.max_ms == 20.0
        assert t.total_ms == 30.0

    def test_time_context_manager(self) -> None:
        t = Timer("test_timer")
        with t.time():
            pass
        assert t.count == 1
        assert t.avg_ms > 0

    def test_snapshot(self) -> None:
        t = Timer("test_timer")
        t.record(42.5)
        snap = t.snapshot()
        assert snap["name"] == "test_timer"
        assert snap["count"] == 1
        assert snap["avg_ms"] == 42.5

    def test_reset(self) -> None:
        t = Timer("test_timer")
        t.record(100.0)
        t.reset()
        assert t.count == 0
        assert t.avg_ms == 0.0


class TestHistogram:
    """Histogram tracks value distributions across configurable buckets."""

    def test_default_buckets(self) -> None:
        h = Histogram("test_hist")
        # Default: (1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000)
        assert len(h.buckets) == 10

    def test_custom_buckets(self) -> None:
        h = Histogram("test_hist", buckets=(10, 50, 100))
        h.observe(5)  # goes in le_10
        h.observe(25)  # goes in le_50
        h.observe(75)  # goes in le_100
        h.observe(200)  # overflow

        snap = h.snapshot()
        assert snap["buckets"]["le_10"] == 1
        assert snap["buckets"]["le_50"] == 1
        assert snap["buckets"]["le_100"] == 1
        assert snap["overflow"] == 1
        assert snap["count"] == 4

    def test_avg_calculation(self) -> None:
        h = Histogram("test_hist", buckets=(10, 50))
        h.observe(10)
        h.observe(50)
        assert h.snapshot()["avg_ms"] == 30.0

    def test_snapshot_keys(self) -> None:
        h = Histogram("test_hist")
        h.observe(1)
        snap = h.snapshot()
        assert set(snap.keys()) == {"name", "count", "sum_ms", "avg_ms", "buckets", "overflow"}


class TestMetricsRegistry:
    """MetricsRegistry provides singleton access to counters, timers, and histograms."""

    def test_counter_singleton(self) -> None:
        reg = MetricsRegistry()
        c1 = reg.counter("requests")
        c2 = reg.counter("requests")
        assert c1 is c2

    def test_timer_singleton(self) -> None:
        reg = MetricsRegistry()
        t1 = reg.timer("latency")
        t2 = reg.timer("latency")
        assert t1 is t2

    def test_histogram_singleton(self) -> None:
        reg = MetricsRegistry()
        h1 = reg.histogram("sizes")
        h2 = reg.histogram("sizes")
        assert h1 is h2

    def test_report_aggregates_all(self) -> None:
        reg = MetricsRegistry()
        reg.counter("tasks").inc(3)
        reg.timer("duration").record(100)
        reg.histogram("latency").observe(50)

        report = reg.report()
        assert "counters" in report
        assert "timers" in report
        assert "histograms" in report
        assert report["counters"]["tasks"]["value"] == 3
        assert report["timers"]["duration"]["count"] == 1
        assert report["histograms"]["latency"]["count"] == 1

    def test_reset_clears_counters_and_timers(self) -> None:
        reg = MetricsRegistry()
        reg.counter("c").inc(5)
        reg.timer("t").record(10)
        reg.reset()
        assert reg.counter("c").value == 0
        assert reg.timer("t").count == 0

    def test_counter_with_description(self) -> None:
        reg = MetricsRegistry()
        c = reg.counter("errors", description="Total error count")
        assert c.description == "Total error count"


class TestLabelsKey:
    """_labels_key produces stable, sorted label keys."""

    def test_single_label(self) -> None:
        assert _labels_key({"a": "1"}) == "a=1"

    def test_multiple_labels_sorted(self) -> None:
        key = _labels_key({"z": "last", "a": "first"})
        assert key == "a=first,z=last"

    def test_same_dicts_same_key(self) -> None:
        k1 = _labels_key({"x": "y", "a": "b"})
        k2 = _labels_key({"a": "b", "x": "y"})
        assert k1 == k2
