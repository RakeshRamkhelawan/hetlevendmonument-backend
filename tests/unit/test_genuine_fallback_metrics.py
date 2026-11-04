"""Unit tests for in-memory fallback metric tracking in performance_optimizer and memory/observability."""

import pytest

from src.core.agents.performance_optimizer import DummyCounter, DummyGauge, DummyHistogram
from src.domains.memory.observability import _NoOpCounter, _NoOpGauge, _NoOpHistogram


def test_performance_optimizer_dummy_counter_tracking() -> None:
    counter = DummyCounter()
    assert counter.value == 0.0
    counter.inc()
    assert counter.value == 1.0
    counter.labels(agent="test").inc(5.5)
    assert counter.value == 6.5


def test_performance_optimizer_dummy_gauge_tracking() -> None:
    gauge = DummyGauge()
    assert gauge.value == 0.0
    gauge.set(42.0)
    assert gauge.value == 42.0
    gauge.inc(8.0)
    assert gauge.value == 50.0
    gauge.labels(pool="db").dec(15.0)
    assert gauge.value == 35.0


def test_performance_optimizer_dummy_histogram_tracking() -> None:
    hist = DummyHistogram()
    assert list(hist.observations) == []
    hist.observe(0.12)
    hist.labels(path="/api").observe(0.45)
    assert list(hist.observations) == [0.12, 0.45]


def test_performance_optimizer_dummy_histogram_bounded() -> None:
    hist = DummyHistogram(maxlen=5)
    for i in range(10):
        hist.observe(float(i))
    assert len(hist.observations) == 5
    assert list(hist.observations) == [5.0, 6.0, 7.0, 8.0, 9.0]


def test_memory_observability_noop_counter_tracking() -> None:
    counter = _NoOpCounter()
    assert counter.count == 0.0
    counter.inc()
    assert counter.count == 1.0
    counter.labels(tenant_id=1).inc(3)
    assert counter.count == 4.0


def test_memory_observability_noop_gauge_tracking() -> None:
    gauge = _NoOpGauge()
    assert gauge.value == 0.0
    gauge.set(100.0)
    assert gauge.value == 100.0
    gauge.labels(tenant_id=2).inc(25.0)
    assert gauge.value == 125.0


def test_memory_observability_noop_histogram_tracking() -> None:
    hist = _NoOpHistogram()
    assert list(hist.observations) == []
    hist.observe(1.23)
    hist.labels(tenant_id=1).observe(4.56)
    assert list(hist.observations) == [1.23, 4.56]


def test_memory_observability_noop_histogram_bounded() -> None:
    hist = _NoOpHistogram(maxlen=3)
    for i in range(6):
        hist.observe(float(i))
    assert len(hist.observations) == 3
    assert list(hist.observations) == [3.0, 4.0, 5.0]
