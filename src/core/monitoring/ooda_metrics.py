import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from collections.abc import Iterator

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)


class OODAPhase(str, Enum):
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"


@dataclass
class PhaseTiming:
    execution_id: str
    agent_id: str
    tenant_id: str
    phase: str
    started_at: float
    timestamp: str
    success: bool | None = None
    duration_seconds: float | None = None
    start_metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    end_metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


# Prometheus Metrics
OODA_PHASE_DURATION = Histogram(
    "ooda_phase_duration_seconds",
    "Time spent in each OODA phase",
    ["agent_id", "tenant_id", "phase"],
)

OODA_CYCLE_COUNT = Counter(
    "ooda_cycles_total",
    "Total number of OODA cycles completed",
    ["agent_id", "tenant_id", "status"],
)

AGENT_CONFIDENCE = Gauge(
    "agent_decision_confidence",
    "Confidence score of the latest agent decision",
    ["agent_id", "tenant_id"],
)


class OODAMonitor:
    """
    Core engine for OODA loop monitoring and telemetry. (Singleton)
    """

    _instance: Optional["OODAMonitor"] = None
    _latest_metrics: dict[str, dict[str, float]]

    def __new__(cls) -> "OODAMonitor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Local buffer for fast API access
            cls._instance._latest_metrics = {}
        return cls._instance

    @contextmanager
    def track_phase(
        self, agent_id: str | None, tenant_id: int | None, phase: str
    ) -> Iterator[None]:
        """
        Context manager to track duration of an OODA phase.
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start_time

            if agent_id and tenant_id:
                # Update Prometheus
                OODA_PHASE_DURATION.labels(
                    agent_id=agent_id, tenant_id=str(tenant_id), phase=phase
                ).observe(duration)

                # Update local buffer
                key = f"{tenant_id}:{agent_id}"
                if key not in self._latest_metrics:
                    self._latest_metrics[key] = {}
                self._latest_metrics[key][phase] = duration

                logger.debug(
                    f"OODA Phase '{phase}' for {agent_id} (tenant {tenant_id}) took {duration:.4f}s"
                )

    def log_decision(self, agent_id: str, tenant_id: int, confidence: float) -> None:
        """Log decision confidence."""
        AGENT_CONFIDENCE.labels(agent_id=agent_id, tenant_id=str(tenant_id)).set(confidence)

    def get_agent_metrics(self, agent_id: str, tenant_id: int) -> dict[str, float]:
        """Returns the latest measured phase durations for an agent."""
        key = f"{tenant_id}:{agent_id}"
        return self._latest_metrics.get(key, {})


class OODAMetrics:
    """Backward-compatible async metrics collector used by older monitoring tests."""

    def __init__(self) -> None:
        self._monitor = OODAMonitor()
        self._MAX_HISTORY_SIZE = 1000
        self._active_phases: dict[tuple[str, str], PhaseTiming] = {}
        self._execution_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self._phase_timings: dict[str, list[PhaseTiming]] = {}

    async def start_phase(
        self,
        execution_id: str,
        agent_id: str,
        phase: OODAPhase,
        tenant_id: str,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        timing = PhaseTiming(
            execution_id=execution_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            phase=phase.value,
            started_at=time.perf_counter(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            start_metadata=metadata or {},
        )
        self._active_phases[(execution_id, phase.value)] = timing

    async def end_phase(
        self,
        execution_id: str,
        phase: OODAPhase,
        success: bool = True,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> float | None:
        active = self._active_phases.pop((execution_id, phase.value), None)
        if active is None:
            return None

        duration = time.perf_counter() - active.started_at
        tenant_str = str(active.tenant_id)
        agent_id = active.agent_id
        try:
            tenant_metric_id = int(tenant_str) if tenant_str.isdigit() else None
        except Exception:
            tenant_metric_id = None

        if tenant_metric_id is not None:
            self._monitor.log_decision(agent_id, tenant_metric_id, 1.0 if success else 0.0)
            with self._monitor.track_phase(agent_id, tenant_metric_id, phase.value):
                pass

        self._execution_history.append(
            {
                "execution_id": execution_id,
                "agent_id": agent_id,
                "phase": phase.value,
                "tenant_id": tenant_str,
                "success": success,
                "duration_seconds": duration,
                "timestamp": active.timestamp,
                "start_metadata": active.start_metadata,
                "end_metadata": metadata or {},
            }
        )
        active.success = success
        active.duration_seconds = duration
        active.end_metadata = metadata or {}
        self._phase_timings.setdefault(execution_id, []).append(active)
        self._rotate_history_if_needed()
        return duration

    def clear_history(self) -> None:
        self._execution_history.clear()
        self._active_phases.clear()
        self._phase_timings.clear()

    def _rotate_history_if_needed(self) -> None:
        if len(self._execution_history) <= self._MAX_HISTORY_SIZE:
            return
        keep = max(1, self._MAX_HISTORY_SIZE // 2)
        self._execution_history = self._execution_history[-keep:]

    async def get_execution_summary(self, execution_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        timings = self._phase_timings.get(execution_id)
        if not timings:
            return None

        return {
            "execution_id": execution_id,
            "agent_id": timings[0].agent_id,
            "tenant_id": timings[0].tenant_id,
            "phases_completed": len(timings),
            "all_phases_successful": all(t.success for t in timings),
            "total_duration_ms": sum((t.duration_seconds or 0.0) for t in timings) * 1000,
            "phases": [
                {
                    "phase": t.phase,
                    "success": t.success,
                    "duration_ms": (t.duration_seconds or 0.0) * 1000,
                    "start_metadata": t.start_metadata,
                    "end_metadata": t.end_metadata,
                }
                for t in timings
            ],
        }

    async def get_average_cycle_time(
        self, agent_id: str, tenant_id: str
    ) -> dict[str, dict[str, float]]:
        relevant = [
            item
            for item in self._execution_history
            if item["agent_id"] == agent_id and item["tenant_id"] == tenant_id
        ]
        grouped: dict[str, list[float]] = {}
        for item in relevant:
            grouped.setdefault(item["phase"], []).append(item["duration_seconds"] * 1000)

        return {
            phase: {
                "count": len(values),
                "avg_ms": sum(values) / len(values) if values else 0.0,
            }
            for phase, values in grouped.items()
        }


__all__ = [
    "OODAMetrics",
    "OODAMonitor",
    "OODAPhase",
    "PhaseTiming",
    "AGENT_CONFIDENCE",
    "OODA_CYCLE_COUNT",
    "OODA_PHASE_DURATION",
]
