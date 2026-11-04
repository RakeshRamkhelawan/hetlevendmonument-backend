"""
Memory Domain Observability
===========================

Prometheus metrics + structured logging helpers for the digital twin
memory layer.

All metrics follow the platform naming convention:
  sanskritisetu_memory_<name>_<unit>

Sprint C integration:
  - ConsolidationWorker imports and updates these counters after each run
  - MemoryRetrievalService calls RETRIEVAL_LATENCY.observe()
  - MemoryWriteService calls WRITE_OPERATIONS.inc()

Metrics are registered on the shared platform registry so they appear
in the existing /metrics endpoint without extra wiring.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import the shared registry helpers from the platform metrics module
# ---------------------------------------------------------------------------
_get_or_create_counter: Callable[[str, str, list[str]], Any] | None = (
    None  # TODO(TYPE): replace Any with concrete type
)
_get_or_create_histogram: Callable[[str, str, list[str]], Any] | None = (
    None  # TODO(TYPE): replace Any with concrete type
)
_get_or_create_gauge: Callable[[str, str, list[str] | None], Any] | None = (
    None  # TODO(TYPE): replace Any with concrete type
)

try:
    from src.core.observability.metrics import (
        _get_or_create_counter,
        _get_or_create_gauge,
        _get_or_create_histogram,
    )

    _METRICS_AVAILABLE = True
except Exception:
    _METRICS_AVAILABLE = False
    logger.warning(
        "Memory domain: prometheus metrics unavailable "
        "(src.core.observability.metrics not importable). "
        "Using no-op stubs."
    )


# ---------------------------------------------------------------------------
# No-op stubs so the rest of the code works even without prometheus_client
# ---------------------------------------------------------------------------


class _NoOpCounter:
    def __init__(self) -> None:
        self.count: float = 0.0

    def labels(self, **_kw: Any) -> _NoOpCounter:  # TODO(TYPE): replace Any with concrete type
        return self

    def inc(self, n: float = 1) -> None:
        self.count += float(n)


class _NoOpHistogram:
    MAX_OBSERVATIONS = 1000

    def __init__(self, maxlen: int = MAX_OBSERVATIONS) -> None:
        self.observations: deque[float] = deque(maxlen=maxlen)

    def labels(self, **_kw: Any) -> _NoOpHistogram:  # TODO(TYPE): replace Any with concrete type
        return self

    def observe(self, v: float) -> None:
        self.observations.append(float(v))


class _NoOpGauge:
    def __init__(self) -> None:
        self.value: float = 0.0

    def labels(self, **_kw: Any) -> _NoOpGauge:  # TODO(TYPE): replace Any with concrete type
        return self

    def set(self, v: float) -> None:
        self.value = float(v)

    def inc(self, n: float = 1) -> None:
        self.value += float(n)


def _counter(
    name: str, desc: str, labels: list[str] | None = None
) -> Any:  # TODO(TYPE): replace Any with concrete type
    if _METRICS_AVAILABLE and _get_or_create_counter is not None:
        try:
            return _get_or_create_counter(name, desc, labels or [])
        except Exception:
            pass
    return _NoOpCounter()


def _histogram(
    name: str, desc: str, labels: list[str] | None = None
) -> Any:  # TODO(TYPE): replace Any with concrete type
    if _METRICS_AVAILABLE and _get_or_create_histogram is not None:
        try:
            return _get_or_create_histogram(name, desc, labels or [])
        except Exception:
            pass
    return _NoOpHistogram()


def _gauge(
    name: str, desc: str, labels: list[str] | None = None
) -> Any:  # TODO(TYPE): replace Any with concrete type
    if _METRICS_AVAILABLE and _get_or_create_gauge is not None:
        try:
            return _get_or_create_gauge(name, desc, labels or [])
        except Exception:
            pass
    return _NoOpGauge()


# ---------------------------------------------------------------------------
# Consolidation metrics
# ---------------------------------------------------------------------------

CONSOLIDATION_RUNS = _counter(
    "sanskritisetu_memory_consolidation_runs_total",
    "Total consolidation runs by tenant and status",
    ["tenant_id", "status"],
)

CONSOLIDATION_ITEMS_CREATED = _counter(
    "sanskritisetu_memory_consolidation_items_created_total",
    "Memory items promoted during consolidation",
    ["tenant_id"],
)

CONSOLIDATION_ITEMS_ARCHIVED = _counter(
    "sanskritisetu_memory_consolidation_items_archived_total",
    "Memory items archived during consolidation",
    ["tenant_id"],
)

CONSOLIDATION_DURATION = _histogram(
    "sanskritisetu_memory_consolidation_duration_seconds",
    "Duration of a consolidation run in seconds",
    ["tenant_id"],
)

CONSOLIDATION_ERRORS = _counter(
    "sanskritisetu_memory_consolidation_errors_total",
    "Failed consolidation runs by tenant",
    ["tenant_id"],
)

# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

RETRIEVAL_LATENCY = _histogram(
    "sanskritisetu_memory_retrieval_latency_seconds",
    "Latency of memory retrieval queries in seconds",
    ["tenant_id", "method"],
)

RETRIEVAL_RESULTS = _histogram(
    "sanskritisetu_memory_retrieval_results",
    "Number of items returned per retrieval query",
    ["tenant_id", "method"],
)

# ---------------------------------------------------------------------------
# Write metrics
# ---------------------------------------------------------------------------

WRITE_OPERATIONS = _counter(
    "sanskritisetu_memory_write_operations_total",
    "Memory item write operations by tenant and outcome",
    ["tenant_id", "outcome"],  # outcome: created | duplicate_skipped
)

# ---------------------------------------------------------------------------
# Profile metrics
# ---------------------------------------------------------------------------

PROFILE_VERSION = _gauge(
    "sanskritisetu_memory_profile_version",
    "Current version number of an agent's memory profile",
    ["tenant_id", "agent_id"],
)

DRIFT_SCORE = _gauge(
    "sanskritisetu_memory_drift_score",
    "Current profile drift score for an agent (0.0-1.0)",
    ["tenant_id", "agent_id"],
)

DRIFT_EVENTS = _counter(
    "sanskritisetu_memory_drift_events_total",
    "Number of drift events detected per agent",
    ["tenant_id", "agent_id", "severity"],
)
