"""
Agent Lifecycle Manager - Sprint E Implementation.

Manages agent lifecycle within departments:
- Registration/deregistration
- Health monitoring and heartbeats
- Status transitions (IDLE, BUSY, DEGRADED, OFFLINE)
- Capability tracking
- Resource usage monitoring

NON-NEGOTIABLE:
- All agents must heartbeat or be marked OFFLINE
- Health status affects routing decisions
- Resource limits enforced per agent
- Tenant isolation for all agent operations
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.infrastructure.signal_bus import SignalBus

logger = logging.getLogger("AgentLifecycle")


class AgentStatus(Enum):
    """Agent lifecycle states."""

    REGISTERING = "registering"  # Initial registration
    IDLE = "idle"  # Ready for work
    BUSY = "busy"  # Processing task
    STRESSED = "stressed"  # High load
    DEGRADED = "degraded"  # Reduced capacity
    OFFLINE = "offline"  # Not responding
    SHUTDOWN = "shutdown"  # Gracefully stopped


class AgentType(Enum):
    """Types of agents in the system."""

    SPECIALIST = "specialist"  # Domain-specific (Finance, HR, etc.)
    GENERALIST = "generalist"  # Multi-purpose
    ORCHESTRATOR = "orchestrator"  # Department/Enterprise level
    SYSTEM = "system"  # System agents


@dataclass
class AgentHealth:
    """Health metrics for an agent."""

    agent_id: str
    status: AgentStatus

    # Timing
    registered_at: datetime
    last_heartbeat: datetime
    last_task_completed: datetime | None = None

    # Performance
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_task_duration_ms: float = 0.0

    # Resources
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    prana_available: int = 0

    # Health score (0-100)
    health_score: int = 100

    def is_healthy(self) -> bool:
        """Check if agent is in healthy state."""
        return self.status in {AgentStatus.IDLE, AgentStatus.BUSY}

    def is_available_for_work(self) -> bool:
        """Check if agent can accept new work."""
        return self.status == AgentStatus.IDLE and self.health_score >= 50


@dataclass
class AgentCapabilities:
    """Capabilities and metadata for an agent."""

    agent_id: str
    agent_type: AgentType
    department: str
    tenant_id: int

    # Capabilities
    skills: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    max_concurrent_tasks: int = 1

    # Limits
    max_prana_per_task: int = 100
    timeout_seconds: int = 300

    # Metadata
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class AgentLifecycleManager:
    """
    Sprint E: Agent Lifecycle & Health Monitoring.

    Manages all agents in the enterprise:
    - Registration with capabilities
    - Health monitoring via heartbeats
    - Status transitions
    - Resource tracking
    - Automatic cleanup of dead agents

    NON-NEGOTIABLE:
    - Heartbeat timeout = 60s (configurable)
    - Agents without heartbeat marked OFFLINE
    - Health score < 50 = not routed new work
    - Tenant isolation enforced
    """

    # Configuration
    HEARTBEAT_TIMEOUT_SECONDS = 60
    HEALTH_CHECK_INTERVAL_SECONDS = 30
    MAX_OFFLINE_TIME_SECONDS = 300  # Auto-unregister after 5 min offline

    def __init__(self, signal_bus: SignalBus | None = None) -> None:
        self.signal_bus = signal_bus

        # Agent storage: tenant_id -> {agent_id -> AgentCapabilities}
        self._capabilities: dict[int, dict[str, AgentCapabilities]] = {}

        # Health storage: tenant_id -> {agent_id -> AgentHealth}
        self._health: dict[int, dict[str, AgentHealth]] = {}

        # Async locks per tenant
        self._locks: dict[int, asyncio.Lock] = {}

        # Background tasks
        self._monitor_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._running = False

        # Metrics
        self._metrics = {
            "registered": 0,
            "deregistered": 0,
            "health_checks": 0,
            "marked_offline": 0,
        }

        logger.info("AgentLifecycleManager initialized")

    def _lock_for(self, tenant_id: int) -> asyncio.Lock:
        """DE lock van deze tenant -- aangemaakt bij eerste gebruik, daarna hergebruikt.

        Waarom dit bestaat (ADR-036 OP-195/OP-206, gemeten 2026-09-07). Vier plekken deden
        `self._locks.get(tenant_id, asyncio.Lock())`. Dat leest als een veilige default maar is
        het omgekeerde: bij een ontbrekende sleutel levert het een VERSE lock, en twee
        gelijktijdige aanroepers krijgen dan elk hun eigen lock. Er is dan geen wederzijdse
        uitsluiting, en anders dan een deadlock is dat STIL.

        Dat de sleutel in de praktijk altijd bestond (`register_agent` vult
        `_capabilities`/`_health` pas NA `self._locks[tenant_id]`) maakte het construct
        onbereikbaar, niet correct: die volgorde is nergens als invariant vastgelegd en een
        tweede schrijver naar `_health` maakt hem levend. En een kale index zou in de
        monitorlus een `KeyError` geven -- erger dan wat hij oplost. Vandaar: een plek die de
        lock aanmaakt EN opslaat, gebruikt door alle aanroepers.
        """
        # GEEN `await` tussen het opzoeken en het opslaan, en dat is dragend: deze functie is
        # alleen atomair omdat de coroutine er niet tussenuit kan stappen. Zet er ooit een
        # await tussen, dan kunnen twee aanroepers elk hun eigen lock aanmaken en is de
        # splitsing uit OP-206 terug zonder dat een test omvalt. Aangedragen door de blinde
        # Gate 2-review van 2026-09-07 als latente val -- daarom staat het hier en niet in
        # een overdracht.
        lock = self._locks.get(tenant_id)
        if lock is None:
            lock = self._locks[tenant_id] = asyncio.Lock()
        return lock

    async def start(self) -> None:
        """Start health monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("AgentLifecycleManager started")

    async def stop(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("AgentLifecycleManager stopped")

    # =========================================================================
    # Registration
    # =========================================================================

    async def register_agent(
        self,
        agent_id: str,
        agent_type: AgentType,
        department: str,
        tenant_id: int,
        skills: list[str] | None = None,
        technologies: list[str] | None = None,
        max_concurrent_tasks: int = 1,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Register a new agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent
            department: Department name
            tenant_id: Tenant ID
            skills: List[Any] of capability strings  # TODO(TYPE): replace Any with concrete type
            technologies: List[Any] of technologies (ml, llm, vision, etc.)  # TODO(TYPE): replace Any with concrete type
            max_concurrent_tasks: Max parallel tasks
            metadata: Additional metadata

        Returns:
            True if registered successfully
        """
        async with self._lock_for(tenant_id):
            # Initialize tenant storage
            if tenant_id not in self._capabilities:
                self._capabilities[tenant_id] = {}
                self._health[tenant_id] = {}

            # Check for duplicate
            if agent_id in self._capabilities[tenant_id]:
                logger.warning(f"Agent {agent_id} already registered")
                return False

            now = datetime.now(timezone.utc)

            # Store capabilities
            self._capabilities[tenant_id][agent_id] = AgentCapabilities(
                agent_id=agent_id,
                agent_type=agent_type,
                department=department,
                tenant_id=tenant_id,
                skills=skills or [],
                technologies=technologies or [],
                max_concurrent_tasks=max_concurrent_tasks,
                metadata=metadata or {},
            )

            # Initialize health
            self._health[tenant_id][agent_id] = AgentHealth(
                agent_id=agent_id,
                status=AgentStatus.IDLE,
                registered_at=now,
                last_heartbeat=now,
                health_score=100,
            )

            self._metrics["registered"] += 1

            logger.info(
                "Agent registered",
                extra={
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "department": department,
                    "type": agent_type.value,
                },
            )

            return True

    async def unregister_agent(self, agent_id: str, tenant_id: int, reason: str = "") -> bool:
        """
        Unregister an agent.

        Args:
            agent_id: Agent to unregister
            tenant_id: Tenant ID
            reason: Reason for unregistration

        Returns:
            True if unregistered successfully
        """
        if tenant_id not in self._capabilities:
            return False

        async with self._lock_for(tenant_id):
            return await self._unregister_locked(agent_id, tenant_id, reason)

    async def _unregister_locked(self, agent_id: str, tenant_id: int, reason: str = "") -> bool:
        """Verwijder een agent TERWIJL DE AANROEPER DE TENANT-LOCK AL VASTHOUDT.

        VOORWAARDE: `self._lock_for(tenant_id)` is al genomen. Deze functie neemt hem NIET.

        Waarom deze splitsing bestaat (ADR-036 OP-195, gemeten 2026-09-02). Voor de splitsing
        hield `_check_all_agents` de tenant-lock vast en riep binnen dat blok
        `unregister_agent()` aan, die dezelfde lock opnieuw pakte. `asyncio.Lock` is niet
        reentrant, dus de coroutine wachtte op een lock die hij zelf vasthield: geen fout, geen
        timeout, permanent. Bewezen door uitvoering, niet door lezen -- het pad wordt betreden
        zodra een agent langer offline is dan `MAX_OFFLINE_TIME_SECONDS`, en omdat
        `_health_monitor_loop` deze functie in zijn lus await stopte daarmee de
        agent-gezondheidsbewaking voor het hele proces.

        Wie deze functie nog een aanroeper wil geven: neem eerst de lock. `asyncio.Lock` kan
        niet zeggen WIE hem vasthoudt, dus deze voorwaarde is niet in code af te dwingen; de
        onderstreping in de naam en deze docstring zijn de enige waarschuwing.
        """
        if agent_id not in self._capabilities[tenant_id]:
            return False

        del self._capabilities[tenant_id][agent_id]
        del self._health[tenant_id][agent_id]

        self._metrics["deregistered"] += 1

        logger.info(
            "Agent unregistered",
            extra={"agent_id": agent_id, "tenant_id": tenant_id, "reason": reason},
        )

        return True

    # =========================================================================
    # Health & Heartbeat
    # =========================================================================

    async def heartbeat(
        self,
        agent_id: str,
        tenant_id: int,
        status: AgentStatus | None = None,
        health_metrics: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Process agent heartbeat.

        Args:
            agent_id: Agent ID
            tenant_id: Tenant ID
            status: Current status (optional)
            health_metrics: Health metrics (cpu, memory, etc.)

        Returns:
            True if heartbeat processed
        """
        if tenant_id not in self._health:
            return False

        if agent_id not in self._health[tenant_id]:
            return False

        async with self._lock_for(tenant_id):
            health = self._health[tenant_id][agent_id]

            # Update heartbeat time
            health.last_heartbeat = datetime.now(timezone.utc)

            # Update status if provided
            if status:
                health.status = status
            elif health.status == AgentStatus.OFFLINE:
                # Agent was offline, mark as idle again
                health.status = AgentStatus.IDLE

            # Update health metrics
            if health_metrics:
                health.cpu_percent = health_metrics.get("cpu_percent", health.cpu_percent)
                health.memory_percent = health_metrics.get("memory_percent", health.memory_percent)
                health.prana_available = health_metrics.get(
                    "prana_available", health.prana_available
                )

                # Recalculate health score
                health.health_score = self._calculate_health_score(health)

            return True

    async def update_task_metrics(
        self, agent_id: str, tenant_id: int, task_duration_ms: float, success: bool
    ) -> None:
        """Update agent task completion metrics."""
        if tenant_id not in self._health:
            return

        if agent_id not in self._health[tenant_id]:
            return

        async with self._lock_for(tenant_id):
            health = self._health[tenant_id][agent_id]

            if success:
                health.tasks_completed += 1
            else:
                health.tasks_failed += 1

            # Update rolling average
            total_tasks = health.tasks_completed + health.tasks_failed
            health.avg_task_duration_ms = (
                health.avg_task_duration_ms * (total_tasks - 1) + task_duration_ms
            ) / total_tasks

            health.last_task_completed = datetime.now(timezone.utc)

    def get_agent_health(self, agent_id: str, tenant_id: int) -> AgentHealth | None:
        """Get health status for an agent."""
        if tenant_id not in self._health:
            return None
        return self._health[tenant_id].get(agent_id)

    def get_agent_capabilities(self, agent_id: str, tenant_id: int) -> AgentCapabilities | None:
        """Get capabilities for an agent."""
        if tenant_id not in self._capabilities:
            return None
        return self._capabilities[tenant_id].get(agent_id)

    def get_agents_by_department(
        self, department: str, tenant_id: int, healthy_only: bool = False
    ) -> list[str]:
        """
        Get all agents in a department.

        Args:
            department: Department name
            tenant_id: Tenant ID
            healthy_only: Only return healthy agents

        Returns: List[Any] of agent IDs  # TODO(TYPE): replace Any with concrete type
        """
        if tenant_id not in self._capabilities:
            return []

        agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, caps in self._capabilities[tenant_id].items():
            if caps.department == department:
                if healthy_only:
                    health = self._health[tenant_id].get(agent_id)
                    if health and health.is_healthy():
                        agents.append(agent_id)
                else:
                    agents.append(agent_id)

        return agents

    def get_agents_by_capability(
        self, skill: str, tenant_id: int, available_only: bool = False
    ) -> list[str]:
        """
        Get agents with specific capability.

        Args:
            skill: Required skill
            tenant_id: Tenant ID
            available_only: Only return available agents

        Returns: List[Any] of agent IDs  # TODO(TYPE): replace Any with concrete type
        """
        if tenant_id not in self._capabilities:
            return []

        agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, caps in self._capabilities[tenant_id].items():
            if skill in caps.skills:
                if available_only:
                    health = self._health[tenant_id].get(agent_id)
                    if health and health.is_available_for_work():
                        agents.append(agent_id)
                else:
                    agents.append(agent_id)

        return agents

    def get_department_health_summary(self, department: str, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get health summary for a department."""
        agent_ids = self.get_agents_by_department(department, tenant_id)

        if not agent_ids:
            return {
                "department": department,
                "total_agents": 0,
                "healthy": 0,
                "degraded": 0,
                "offline": 0,
                "avg_health_score": 0,
            }

        healthy = 0
        degraded = 0
        offline = 0
        total_score = 0

        for agent_id in agent_ids:
            health = self._health[tenant_id].get(agent_id)
            if health:
                total_score += health.health_score
                if health.is_healthy():
                    healthy += 1
                elif health.status == AgentStatus.DEGRADED:
                    degraded += 1
                elif health.status == AgentStatus.OFFLINE:
                    offline += 1

        return {
            "department": department,
            "total_agents": len(agent_ids),
            "healthy": healthy,
            "degraded": degraded,
            "offline": offline,
            "avg_health_score": total_score / len(agent_ids),
        }

    def get_all_agents(self, tenant_id: int) -> list[str]:
        """Get all agent IDs for a tenant."""
        if tenant_id not in self._capabilities:
            return []
        return list(self._capabilities[tenant_id].keys())

    def get_metrics(self) -> dict[str, int]:
        """Get lifecycle metrics."""
        return self._metrics.copy()

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _calculate_health_score(self, health: AgentHealth) -> int:
        """Calculate health score based on metrics."""
        score = 100

        # Penalize high resource usage
        if health.cpu_percent > 80:
            score -= 20
        elif health.cpu_percent > 60:
            score -= 10

        if health.memory_percent > 80:
            score -= 20
        elif health.memory_percent > 60:
            score -= 10

        # Penalize task failures
        total_tasks = health.tasks_completed + health.tasks_failed
        if total_tasks > 0:
            failure_rate = health.tasks_failed / total_tasks
            score -= int(failure_rate * 30)

        return max(0, score)

    async def _health_monitor_loop(self) -> None:
        """Background loop to check agent health."""
        while self._running:
            try:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL_SECONDS)
                await self._check_all_agents()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def _check_all_agents(self) -> None:
        """Check health of all registered agents."""
        now = datetime.now(timezone.utc)

        for tenant_id in list(self._health.keys()):
            async with self._lock_for(tenant_id):
                for agent_id, health in list(self._health[tenant_id].items()):
                    elapsed = (now - health.last_heartbeat).total_seconds()

                    if elapsed > self.HEARTBEAT_TIMEOUT_SECONDS:
                        if health.status != AgentStatus.OFFLINE:
                            health.status = AgentStatus.OFFLINE
                            health.health_score = 0
                            self._metrics["marked_offline"] += 1

                            logger.warning(
                                "Agent marked OFFLINE",
                                extra={"agent_id": agent_id, "tenant_id": tenant_id},
                            )

                    # Auto-unregister after extended offline time
                    if health.status == AgentStatus.OFFLINE:
                        offline_time = (now - health.last_heartbeat).total_seconds()
                        if offline_time > self.MAX_OFFLINE_TIME_SECONDS:
                            # De lock-nemende variant NIET aanroepen: die pakt dezelfde
                            # niet-reentrante lock die hierboven al vast zit (ADR-036 OP-195).
                            await self._unregister_locked(
                                agent_id, tenant_id, "auto-cleanup: offline too long"
                            )

        self._metrics["health_checks"] += 1


# Convenience function for creating agents
def create_agent_capabilities(
    agent_id: str,
    department: str,
    tenant_id: int,
    skills: list[str],
    agent_type: AgentType = AgentType.SPECIALIST,
    technologies: list[str] | None = None,
) -> AgentCapabilities:
    """
    Create agent capabilities.

    Usage:
        caps = create_agent_capabilities(
            agent_id="finance_agent_1",
            department="finance",
            tenant_id=1,
            skills=["budget_analysis", "forecasting"],
            technologies=["ml", "llm"]
        )
    """
    return AgentCapabilities(
        agent_id=agent_id,
        agent_type=agent_type,
        department=department,
        tenant_id=tenant_id,
        skills=skills,
        technologies=technologies or [],
    )
