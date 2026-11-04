"""
AgentHealthMonitorAgent - Real-time health & performance monitoring for the
SanskritiSetu agent ecosystem.

Responsibilities:
- Polls all registered agents for heartbeat / last-seen timestamps
- Tracks per-agent: error rate, avg latency, success rate, load
- Fires alerts (via event_emitter) when thresholds are breached
- Exposes a health_report() for dashboards and AgentRouterAgent
- Feeds CritiqueStore summaries into the health picture

Design:
- Runs a background asyncio task (_monitoring_loop) when started
- Stores health snapshots in memory (HealthSnapshot per agent)
- Alert cooldown prevents alert storms (one alert per agent per 10 min)
- SILENT CriticMixin so its own outputs are passively critiqued

M-MDP: sync threshold checks, async polling and alert dispatch.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

if TYPE_CHECKING:
    from src.core.agents.agent_router_agent import AgentRouterAgent

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.autonomy.self_healing_system import FailureType, SystemFailure
from src.core.agents.llm_types import (
    AgentCategory,
    AgentProfile,
    TaskComplexity,
    agent_model_matcher,
)
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.types import AgentType

logger = logging.getLogger(__name__)

# --- Thresholds ---------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "max_error_rate": 0.20,  # > 20 % errors -> WARNING
    "min_success_rate": 0.80,  # < 80 % success -> WARNING
    "max_avg_latency_ms": 5_000,  # > 5 s avg -> WARNING
    "max_load": 0.90,  # > 90 % load -> WARNING
    "heartbeat_timeout_s": 120,  # no ping for 2 min -> STALE
}

ALERT_COOLDOWN_S = 600  # 10 minutes between repeated alerts per agent


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass
class HealthSnapshot:
    agent_id: str
    agent_type: str
    status: HealthStatus = HealthStatus.UNKNOWN
    error_rate: float = 0.0
    success_rate: float = 1.0
    avg_latency_ms: float = 0.0
    current_load: float = 0.0
    tasks_processed: int = 0
    last_heartbeat: datetime | None = None
    last_alert_at: datetime | None = None
    alerts: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Rolling window of recent latencies (last 50 tasks)
    _latency_window: deque[float] = field(default_factory=lambda: deque(maxlen=50), repr=False)
    _failures: int = field(default=0, repr=False)

    def record_execution(self, latency_ms: float, success: bool) -> None:
        self.tasks_processed += 1
        self._latency_window.append(latency_ms)
        self.avg_latency_ms = sum(self._latency_window) / len(self._latency_window)
        if not success:
            self._failures += 1
        total = self.tasks_processed
        self.error_rate = self._failures / total
        self.success_rate = 1.0 - self.error_rate
        self.last_heartbeat = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class AgentHealthMonitorAgent(CriticMixin, EnhancedBaseAgent):
    """
    Monitors the health of every agent in the SanskritiSetu ecosystem.

    Usage:
        monitor = get_health_monitor(tenant_id)
        await monitor.start()                     # begin background polling
        monitor.record(agent_id, latency, success) # called by each agent post-task
        report = monitor.health_report()           # snapshot of all agents
        await monitor.stop()
    """

    def __init__(
        self,
        agent_id: str = "agent_health_monitor_001",
        tenant_id: int = 1,
        poll_interval_s: int = 30,
        thresholds: dict[str, float] | None = None,
        # TODO(TYPE): replace Any with concrete type
        router_ref: Any
        | None = None,  # AgentRouterAgent | None at runtime  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.MONITOR,
            tenant_id=tenant_id,
        )
        self.__init_critic__(mode=CriticMode.SILENT)

        self.specialization = "agent_ecosystem_health_monitoring"
        self._poll_interval = poll_interval_s
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

        # Health state: agent_id -> HealthSnapshot
        self._snapshots: dict[str, HealthSnapshot] = {}
        self._lock = asyncio.Lock()

        # Batched updates for high-throughput scenarios
        self._pending_records: list[
            dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = []  # TODO(TYPE): replace Any with concrete type
        self._batch_size = 100
        self._batch_flush_interval = 5  # seconds
        self._batch_task: asyncio.Task[Any] | None = (  # TODO(TYPE): replace Any with concrete type
            None  # TODO(TYPE): replace Any with concrete type
        )

        # Alert callback - replace with event_emitter integration if desired
        self._alert_handlers: list[
            Callable[..., Any]
        ] = []  # TODO(TYPE): replace Any with concrete type
        self._alert_cooldowns: dict[str, datetime] = {}  # agent_id -> last_alert
        self._alert_cooldown_seconds = 600  # 10 minutes

        # Background task handle
        self._monitor_task: (
            # TODO(TYPE): replace Any with concrete type
            asyncio.Task[Any] | None
        ) = (  # TODO(TYPE): replace Any with concrete type
            None  # TODO(TYPE): replace Any with concrete type
        )
        self._running = False

        # Metrics
        self._alerts_fired = 0
        self._checks_performed = 0
        self._records_processed = 0
        self._batch_flushes = 0

        # Optional SelfHealingSystem integration (set via set_healing_system)
        self._healing_system: Any | None = None  # TODO(TYPE): replace Any with concrete type

        # Write-bridge: push health transitions to AgentRouterAgent (opt-in, set via set_router)
        self._router_ref: Any | None = (  # TODO(TYPE): replace Any with concrete type
            router_ref  # AgentRouterAgent | None at runtime  # TODO(TYPE): replace Any with concrete type
        )

        self._register_agent_profile()
        logger.info("AgentHealthMonitorAgent %s initialised (tenant=%d)", agent_id, tenant_id)

    def set_router(self, router_ref: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Wire AgentRouterAgent for health write-bridge (post-construction)."""
        self._router_ref = router_ref

    async def _push_to_router(
        self,
        agent_id: str,
        status: str,
        success_rate: float,
        avg_latency_ms: float,
    ) -> None:
        """Push a health status transition to the wired AgentRouterAgent.

        NOTE: best_effort -- exceptions are logged, not re-raised, so the
        monitoring loop continues uninterrupted.
        """
        if self._router_ref is None:
            return
        if getattr(self._router_ref, "tenant_id", None) != self.tenant_id:
            return  # tenant isolation guard
        try:
            await self._router_ref.update_health_status(
                agent_id=agent_id,
                status=status,
                metrics={
                    "success_rate": success_rate,
                    "avg_latency_ms": avg_latency_ms,
                },
            )
        except Exception as exc:
            logger.warning(
                "AgentHealthMonitorAgent push_to_router failed agent=%s: %s",
                agent_id,
                exc,
            )

    def _register_agent_profile(self) -> None:
        profile = AgentProfile(
            agent_type="monitor",
            category=AgentCategory.SUPPORT,
            typical_complexity=TaskComplexity.SIMPLE,
            reasoning_required=0.4,
            speed_priority=0.9,
            cost_sensitivity=0.95,
            context_needs=500,
            special_requirements=["monitoring"],
        )
        agent_model_matcher.register_agent_profile(profile)

    async def initialize(self) -> bool:
        return True

    async def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="health_monitoring",
                description="Real-time health, performance and anomaly monitoring for system agents",
                input_types=["heartbeat", "metrics", "health_query"],
                output_types=["health_report", "health_alert"],
            )
        ]

    # -- Lifecycle -------------------------------------------------------------

    async def start(self) -> None:
        """Start the background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(
            self._monitoring_loop(), name=f"health_monitor_{self.agent_id}"
        )
        logger.info(
            "AgentHealthMonitorAgent %s started (poll=%ds)",
            self.agent_id,
            self._poll_interval,
        )

    async def stop(self) -> None:
        """Stop the background monitoring loop gracefully."""
        self._running = False
        # Cancel pending batch-flush task first (sleeps up to _batch_flush_interval)
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
            self._batch_task = None
        # Cancel monitor loop task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("AgentHealthMonitorAgent %s stopped", self.agent_id)

    # -- Standard agent interface ----------------------------------------------

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Returns a health report as an ExecutionResult."""
        start = time.perf_counter()
        report = self.health_report()
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data=report,
            execution_time=time.perf_counter() - start,
        )

    # -- Recording (called by other agents) -----------------------------------

    async def record(
        self,
        agent_id: str,
        agent_type: str,
        latency_ms: float,
        success: bool,
        load: float = 0.0,
        batch: bool = True,
    ) -> None:
        """
        Record one task execution. Called post-process_task by each agent
        (or by MasterOrchestratorAgent after receiving an ExecutionResult).

        Args:
            batch: If True, may be queued for batch processing (higher throughput)
        """
        if batch and len(self._pending_records) < self._batch_size:
            # Queue for batch processing
            self._pending_records.append(
                {
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "latency_ms": latency_ms,
                    "success": success,
                    "load": load,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

            # Start batch flush task if not running
            if self._batch_task is None or self._batch_task.done():
                self._batch_task = asyncio.create_task(self._flush_batch_after_delay())

            return

        # Immediate processing
        await self._process_record(agent_id, agent_type, latency_ms, success, load)

    async def _flush_batch_after_delay(self) -> None:
        """Flush pending records after a short delay or when batch is full."""
        await asyncio.sleep(self._batch_flush_interval)
        await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Process all pending records in batch."""
        if not self._pending_records:
            return

        records = self._pending_records.copy()
        self._pending_records.clear()
        self._batch_flushes += 1

        # Process all records
        for record in records:
            await self._process_record(
                record["agent_id"],
                record["agent_type"],
                record["latency_ms"],
                record["success"],
                record["load"],
            )

        self._records_processed += len(records)
        logger.debug(f"Flushed {len(records)} health records in batch")

    async def flush(self) -> None:
        """Flush all pending records immediately. For testing use."""
        await self._flush_batch()

    async def _process_record(
        self,
        agent_id: str,
        agent_type: str,
        latency_ms: float,
        success: bool,
        load: float = 0.0,
    ) -> None:
        """Process a single health record (metrics only -- status evaluated by _check_all)."""
        async with self._lock:
            if agent_id not in self._snapshots:
                self._snapshots[agent_id] = HealthSnapshot(agent_id=agent_id, agent_type=agent_type)
            snap = self._snapshots[agent_id]
            snap.record_execution(latency_ms, success)
            snap.current_load = load
            # Status is intentionally NOT updated here; _check_all() owns status
            # transitions so that healing is triggered exactly once per transition.

    # -- Background loop (async) -----------------------------------------------

    async def _monitoring_loop(self) -> None:
        """Periodic check loop - evaluates all snapshots and fires alerts."""
        while self._running:
            try:
                await self._check_all()
            except Exception as exc:
                logger.warning("AgentHealthMonitorAgent check failed: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _check_all(self) -> None:
        self._checks_performed += 1
        now = datetime.now(timezone.utc)
        # Collect (agent_id, status_str, success_rate, avg_latency_ms) tuples for
        # write-bridge pushes. Scalars are captured inside the lock; awaiting happens
        # outside to avoid holding self._lock across I/O (Redis or network call).
        to_push: list[tuple[str, str, float, float]] = []
        async with self._lock:
            for snap in self._snapshots.values():
                prev_status = snap.status
                self._evaluate_status(snap)

                # Heartbeat staleness check
                if snap.last_heartbeat:
                    age = (now - snap.last_heartbeat).total_seconds()
                    if age > self._thresholds["heartbeat_timeout_s"]:
                        snap.status = HealthStatus.STALE
                        snap.alerts.append(
                            f"No heartbeat for {int(age)}s (threshold={self._thresholds['heartbeat_timeout_s']}s)"
                        )

                if snap.status != prev_status:
                    # Alerts and healing only for non-HEALTHY transitions
                    if snap.status != HealthStatus.HEALTHY:
                        self._maybe_fire_alert(snap)
                        # Trigger healing for CRITICAL/STALE transitions only
                        if snap.status in (HealthStatus.CRITICAL, HealthStatus.STALE):
                            self._trigger_healing(snap)
                    # Write-bridge: push ALL transitions (including recovery to HEALTHY)
                    to_push.append(
                        (
                            snap.agent_id,
                            snap.status.value.upper(),
                            snap.success_rate,
                            snap.avg_latency_ms,
                        )
                    )

        # Push outside the lock so I/O does not block self._lock
        for agent_id, status, success_rate, avg_latency_ms in to_push:
            await self._push_to_router(agent_id, status, success_rate, avg_latency_ms)

    # -- Evaluation (sync - M-MDP) ---------------------------------------------

    def _evaluate_status(self, snap: HealthSnapshot) -> None:
        """Compute health status from current metrics. Pure sync logic."""
        snap.alerts = []
        issues = 0

        if snap.error_rate > self._thresholds["max_error_rate"]:
            issues += 1
            snap.alerts.append(
                f"Error rate {snap.error_rate:.1%} > threshold {self._thresholds['max_error_rate']:.1%}"
            )
        if snap.success_rate < self._thresholds["min_success_rate"]:
            issues += 1
            snap.alerts.append(
                f"Success rate {snap.success_rate:.1%} < threshold {self._thresholds['min_success_rate']:.1%}"
            )
        if snap.avg_latency_ms > self._thresholds["max_avg_latency_ms"]:
            issues += 1
            snap.alerts.append(
                f"Avg latency {snap.avg_latency_ms:.0f}ms > threshold {self._thresholds['max_avg_latency_ms']}ms"
            )
        if snap.current_load > self._thresholds["max_load"]:
            issues += 1
            snap.alerts.append(
                f"Load {snap.current_load:.1%} > threshold {self._thresholds['max_load']:.1%}"
            )

        if issues == 0:
            snap.status = HealthStatus.HEALTHY
        elif issues == 1:
            snap.status = HealthStatus.WARNING
        else:
            snap.status = HealthStatus.CRITICAL

    def _trigger_healing(self, snap: HealthSnapshot) -> None:
        """Fire-and-forget: ask SelfHealingSystem to diagnose CRITICAL/STALE agent."""
        if self._healing_system is None:
            return
        failure = SystemFailure(
            failure_id=f"health_{snap.agent_id}_{int(datetime.now(timezone.utc).timestamp())}",
            failure_type=FailureType.AGENT_CRASH,
            component=snap.agent_id,
            severity=9 if snap.status == HealthStatus.CRITICAL else 6,
            timestamp=datetime.now(timezone.utc),
            description=f"Agent {snap.agent_id} entered {snap.status.value} state",
        )
        asyncio.create_task(self._healing_system.detect_and_diagnose_failure(failure))

    def _maybe_fire_alert(self, snap: HealthSnapshot) -> None:
        """Fire alert with cooldown to prevent alert storms."""
        now = datetime.now(timezone.utc)
        if snap.last_alert_at:
            age = (now - snap.last_alert_at).total_seconds()
            if age < ALERT_COOLDOWN_S:
                return
        snap.last_alert_at = now
        self._alerts_fired += 1
        for handler in self._alert_handlers:
            try:
                handler(snap.agent_id, snap)
            except Exception as exc:
                logger.warning("Alert handler failed: %s", exc)
        logger.warning(
            "HEALTH ALERT agent=%s status=%s alerts=%s",
            snap.agent_id,
            snap.status.value,
            snap.alerts,
        )

    # -- Public API ------------------------------------------------------------

    def set_healing_system(
        self,
        healing_system: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Wire a SelfHealingSystem to trigger repairs on CRITICAL/STALE agents."""
        self._healing_system = healing_system

    def add_alert_handler(
        self, handler: Callable[..., Any]
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a callback fired on health degradation."""
        self._alert_handlers.append(handler)

    def health_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Full snapshot of all monitored agents."""
        now = datetime.now(timezone.utc)
        by_status: dict[str, int] = defaultdict(int)
        agent_reports: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for snap in self._snapshots.values():
            by_status[snap.status.value] += 1
            agent_reports.append(
                {
                    "agent_id": snap.agent_id,
                    "agent_type": snap.agent_type,
                    "status": snap.status.value,
                    "error_rate": round(snap.error_rate, 4),
                    "success_rate": round(snap.success_rate, 4),
                    "avg_latency_ms": round(snap.avg_latency_ms, 1),
                    "current_load": round(snap.current_load, 3),
                    "tasks_processed": snap.tasks_processed,
                    "alerts": snap.alerts,
                    "last_heartbeat": (
                        snap.last_heartbeat.isoformat() if snap.last_heartbeat else None
                    ),
                }
            )

        return {
            "generated_at": now.isoformat(),
            "tenant_id": self.tenant_id,
            "total_agents": len(self._snapshots),
            "by_status": dict(by_status),
            "checks_performed": self._checks_performed,
            "alerts_fired": self._alerts_fired,
            "agents": sorted(agent_reports, key=lambda x: x["status"]),
        }

    def agent_status(self, agent_id: str) -> HealthSnapshot | None:
        return self._snapshots.get(agent_id)

    def critical_agents(self) -> list[HealthSnapshot]:
        return [
            s
            for s in self._snapshots.values()
            if s.status in (HealthStatus.CRITICAL, HealthStatus.STALE)
        ]

    def metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "monitored_agents": len(self._snapshots),
            "checks_performed": self._checks_performed,
            "alerts_fired": self._alerts_fired,
            "running": self._running,
        }


# --- Singleton ----------------------------------------------------------------

_instances: dict[int, AgentHealthMonitorAgent] = {}
_instances_lock = threading.Lock()


def get_health_monitor(
    tenant_id: int = 1,
    router_ref: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> AgentHealthMonitorAgent:
    """Return the singleton AgentHealthMonitorAgent for the given tenant.

    Pass router_ref to wire the write-bridge on first creation, or to wire it
    post-construction if not yet wired. Wiring must happen at app startup
    (e.g. app_lifespan.py) to activate health-aware routing in production.
    """
    with _instances_lock:
        if tenant_id not in _instances:
            _instances[tenant_id] = AgentHealthMonitorAgent(
                agent_id=f"agent_health_monitor_{tenant_id:03d}",
                tenant_id=tenant_id,
                router_ref=router_ref,
            )
        elif router_ref is not None and _instances[tenant_id]._router_ref is None:
            _instances[tenant_id].set_router(router_ref)
        return _instances[tenant_id]
