"""AgentHealthMonitorAgent - rolling window health monitoring per ADR-023."""

from __future__ import annotations

import collections
import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ADR-023 constants
ROLLING_WINDOW_SIZE = 50
ERROR_RATE_WARNING = 0.20
ERROR_RATE_CRITICAL = 0.50
SUCCESS_RATE_WARNING = 0.80
LATENCY_WARNING_MS = 5000.0
LOAD_WARNING = 0.90  # NOTE: reserved for future load-based alerting (ADR-023)
ALERT_COOLDOWN_SECONDS = 600
CONSECUTIVE_FAILURE_DISABLE = 3


class HealthStatus(enum.Enum):
    """Agent health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DISABLED = "disabled"


@dataclass
class HealthRecord:
    """Single task execution record for health tracking."""

    agent_id: str
    tenant_id: int
    success: bool
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: str | None = None


@dataclass
class HealthMetrics:
    """Computed health metrics for an agent."""

    agent_id: str
    total_tasks: int
    success_count: int
    error_count: int
    avg_latency_ms: float
    error_rate: float
    success_rate: float
    status: HealthStatus
    consecutive_failures: int


@dataclass
class HealthAlert:
    """Alert generated when health thresholds are breached."""

    agent_id: str
    tenant_id: int
    alert_type: str
    severity: str
    message: str
    metrics: HealthMetrics
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HealthMonitorService:
    """Core health monitoring logic with rolling window metrics.

    NOTE: Tenant isolation relies on each AgentHealthMonitorAgent having its own
    HealthMonitorService instance. Do not share across tenants.
    """

    def __init__(self, window_size: int = ROLLING_WINDOW_SIZE) -> None:
        self._window_size = window_size
        # agent_id -> deque of HealthRecord
        self._windows: dict[str, collections.deque[HealthRecord]] = {}
        # agent_id -> consecutive failure count
        self._consecutive_failures: dict[str, int] = {}
        # agent_id -> last alert timestamp (cooldown tracking)
        self._last_alert_time: dict[str, datetime] = {}
        # set of disabled agent ids
        self._disabled_agents: set[str] = set()

    def record(self, record: HealthRecord) -> None:
        """Record a single task execution result."""
        agent_id = record.agent_id

        if agent_id not in self._windows:
            self._windows[agent_id] = collections.deque(maxlen=self._window_size)
            self._consecutive_failures[agent_id] = 0

        self._windows[agent_id].append(record)

        if record.success:
            self._consecutive_failures[agent_id] = 0
        else:
            self._consecutive_failures[agent_id] += 1

    def get_metrics(self, agent_id: str) -> HealthMetrics | None:
        """Compute current metrics for an agent from its rolling window."""
        window = self._windows.get(agent_id)
        if window is None:
            return None

        total = len(window)
        successes = sum(1 for r in window if r.success)
        errors = total - successes
        avg_latency = sum(r.latency_ms for r in window) / total if total > 0 else 0.0
        error_rate = errors / total if total > 0 else 0.0
        success_rate = successes / total if total > 0 else 0.0

        status = self._compute_status(error_rate, success_rate, avg_latency)

        return HealthMetrics(
            agent_id=agent_id,
            total_tasks=total,
            success_count=successes,
            error_count=errors,
            avg_latency_ms=avg_latency,
            error_rate=error_rate,
            success_rate=success_rate,
            status=status,
            consecutive_failures=self._consecutive_failures.get(agent_id, 0),
        )

    def _compute_status(
        self, error_rate: float, success_rate: float, avg_latency_ms: float
    ) -> HealthStatus:
        """Determine health status from metrics against ADR-023 thresholds."""
        if error_rate >= ERROR_RATE_CRITICAL:
            return HealthStatus.CRITICAL
        if (
            error_rate >= ERROR_RATE_WARNING
            or success_rate < SUCCESS_RATE_WARNING
            or avg_latency_ms > LATENCY_WARNING_MS
        ):
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY

    def check_alerts(self, agent_id: str, *, tenant_id: int) -> list[HealthAlert]:
        """Check agent health and generate alerts if thresholds breached."""
        metrics = self.get_metrics(agent_id)
        if metrics is None:
            return []

        # Cooldown check
        last = self._last_alert_time.get(agent_id)
        now = datetime.now(timezone.utc)
        if last is not None and (now - last) < timedelta(seconds=ALERT_COOLDOWN_SECONDS):
            return []

        alerts: list[HealthAlert] = []

        # Consecutive failure -> disable
        if (
            metrics.consecutive_failures >= CONSECUTIVE_FAILURE_DISABLE
            and agent_id not in self._disabled_agents
        ):
            self._disabled_agents.add(agent_id)
            alerts.append(
                HealthAlert(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    alert_type="agent_disabled",
                    severity="critical",
                    message=(
                        f"Agent {agent_id} disabled after "
                        f"{metrics.consecutive_failures} consecutive failures"
                    ),
                    metrics=metrics,
                )
            )

        # Error rate alert
        if metrics.error_rate >= ERROR_RATE_WARNING:
            severity = "critical" if metrics.error_rate >= ERROR_RATE_CRITICAL else "warning"
            alerts.append(
                HealthAlert(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    alert_type="high_error_rate",
                    severity=severity,
                    message=(
                        f"Agent {agent_id} error rate {metrics.error_rate:.0%} "
                        f"exceeds threshold"
                    ),
                    metrics=metrics,
                )
            )

        # Latency alert
        if metrics.avg_latency_ms > LATENCY_WARNING_MS:
            alerts.append(
                HealthAlert(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    alert_type="high_latency",
                    severity="warning",
                    message=(
                        f"Agent {agent_id} avg latency {metrics.avg_latency_ms:.0f}ms "
                        f"exceeds {LATENCY_WARNING_MS:.0f}ms"
                    ),
                    metrics=metrics,
                )
            )

        # Success rate alert
        if metrics.success_rate < SUCCESS_RATE_WARNING:
            alerts.append(
                HealthAlert(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    alert_type="low_success_rate",
                    severity="warning",
                    message=(
                        f"Agent {agent_id} success rate {metrics.success_rate:.0%} "
                        f"below threshold"
                    ),
                    metrics=metrics,
                )
            )

        if alerts:
            self._last_alert_time[agent_id] = now

        return alerts

    def get_health_report(self) -> list[HealthMetrics]:
        """Return health metrics for every tracked agent."""
        report: list[HealthMetrics] = []
        for agent_id in self._windows:
            metrics = self.get_metrics(agent_id)
            if metrics is None:  # pragma: no cover - defensive
                continue
            if agent_id in self._disabled_agents:
                metrics = HealthMetrics(
                    agent_id=metrics.agent_id,
                    total_tasks=metrics.total_tasks,
                    success_count=metrics.success_count,
                    error_count=metrics.error_count,
                    avg_latency_ms=metrics.avg_latency_ms,
                    error_rate=metrics.error_rate,
                    success_rate=metrics.success_rate,
                    status=HealthStatus.DISABLED,
                    consecutive_failures=metrics.consecutive_failures,
                )
            report.append(metrics)
        return report

    def is_disabled(self, agent_id: str) -> bool:
        """Check whether an agent has been disabled."""
        return agent_id in self._disabled_agents

    def enable_agent(self, agent_id: str) -> None:
        """Re-enable a previously disabled agent."""
        self._disabled_agents.discard(agent_id)


class AgentHealthMonitorAgent:
    """Agent wrapper around HealthMonitorService per ADR-023.

    Provides a clean interface for the orchestration layer to record
    task results, check alerts, and query agent availability.
    """

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self.name = "AgentHealthMonitorAgent"
        self.description = "Monitors agent health via rolling window metrics (ADR-023)"
        self._service = HealthMonitorService()

    def record_task_result(
        self,
        agent_id: str,
        success: bool,
        latency_ms: float,
        error_type: str | None = None,
    ) -> None:
        """Record a task execution result for an agent."""
        self._service.record(
            HealthRecord(
                agent_id=agent_id,
                tenant_id=self.tenant_id,
                success=success,
                latency_ms=latency_ms,
                error_type=error_type,
            )
        )

    def get_agent_health(self, agent_id: str) -> HealthMetrics | None:
        """Get current health metrics for an agent."""
        return self._service.get_metrics(agent_id)

    def check_agent_alerts(self, agent_id: str) -> list[HealthAlert]:
        """Check for threshold breaches and return any alerts."""
        return self._service.check_alerts(agent_id, tenant_id=self.tenant_id)

    def is_agent_available(self, agent_id: str) -> bool:
        """Check if an agent is available (not disabled)."""
        return not self._service.is_disabled(agent_id)

    def get_health_report(self) -> dict[str, HealthMetrics]:
        """Get health metrics for all tracked agents as a dict keyed by agent_id."""
        return {m.agent_id: m for m in self._service.get_health_report()}

    def enable_agent(self, agent_id: str) -> None:
        """Re-enable a previously disabled agent."""
        self._service.enable_agent(agent_id)
