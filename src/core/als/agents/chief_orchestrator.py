"""Chief Orchestrator - Central coordination for the symbiotic organism.

Combines Perfect Orchestrator with ALS capabilities:
- Signal-based coordination (not direct calls)
- Collective memory integration
- Immune system integration
- Multi-tenant aware
"""

import asyncio
import importlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, cast

from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.als.models.organism_registry import OrganismRegistry
from src.core.database.session import get_db_session
from src.core.shared.interfaces import BaseAgent, ExecutionResult, TaskData
from src.core.types import AgentType

# SP-DSM-006/ADR-034: governance is a TYPE_CHECKING-only import here -- agent_runtime's
# fan-out coupling to governance has a ceiling (test_dsm006_ar_governance_fan_out.py).
# Runtime access goes through importlib below, matching base_agent.py's pattern.
if TYPE_CHECKING:
    from src.core.governance.governance_contract import GovernanceContract

logger = logging.getLogger("ChiefOrchestrator")

GOVERNANCE_ACTION_DELEGATE_TASK = "chief_orchestrator.delegate_task"


class OrchestratorMode(Enum):
    """Orchestrator operational modes."""

    AUTONOMOUS = "autonomous"  # Self-directed coordination
    CVA_DIRECTED = "cva_directed"  # Taking orders from CVA
    HYBRID = "hybrid"  # Both


@dataclass
class TaskAssignment:
    """Task assignment to an agent."""

    task_id: str
    assigned_agent: str
    agent_type: str
    priority: int
    estimated_duration: int
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed


@dataclass
class OrchestratorState:
    """Orchestrator operational state."""

    mode: OrchestratorMode
    active_tasks: dict[str, TaskAssignment]
    completed_tasks: list[str]
    agent_load: dict[str, float]  # Agent -> load percentage
    performance_metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    healthy_agents: set[str]
    stressed_agents: set[str]


class ChiefOrchestrator(BaseAgent):
    """
    Chief Orchestrator - CEO of the Symbiotic Organism.

    This orchestrator uses the ALS nervous system (SignalBus) to coordinate
    agents, rather than direct method calls. This enables:
    - Decoupled agent communication
    - Better scalability
    - Natural load balancing
    - Immune system integration

    Attributes:
        signal_bus: Central message bus
        tenant_id: Current tenant scope
        state: Orchestrator state

    Example:
        orchestrator = ChiefOrchestrator(
            tenant_id=123,
            signal_bus=signal_bus
        )
        await orchestrator.initialize()

        # Delegate task via signals
        result = await orchestrator.delegate_task(task_data)
    """

    def __init__(
        self,
        tenant_id: int,
        signal_bus: SignalBus,
        agent_id: str = "chief_orchestrator",
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=AgentType.ORCHESTRATOR)

        self.tenant_id = tenant_id
        self.signal_bus = signal_bus

        # GOV-002 (ADR-031): mandatory governance contract, checked before delegate_task().
        # SP-GOV-ARCH-2 (AUDIT-ARCH-2026-07-02 Dag 3): autonomy_level/risk_category are
        # derived via ai_act_classifier.classify_agent() instead of a hardcoded default,
        # matching the pattern used in base_agent.py::EnhancedBaseAgent.__init__().
        _gc_mod = importlib.import_module("src.core.governance.governance_contract")
        _classifier_mod = importlib.import_module("src.core.governance.ai_act_classifier")
        _agent_type_value = getattr(AgentType.ORCHESTRATOR, "value", AgentType.ORCHESTRATOR)
        _risk_category = _classifier_mod.classify_agent(
            name=agent_id,
            department="general",
            specialisation=_agent_type_value,
            capabilities=[_agent_type_value],
        )
        _risk_to_autonomy = {
            _classifier_mod.AIActRiskLevel.UNACCEPTABLE: _gc_mod.AutonomyLevel.HUMAN_IN_LOOP,
            _classifier_mod.AIActRiskLevel.HIGH_RISK: _gc_mod.AutonomyLevel.HUMAN_IN_LOOP,
            _classifier_mod.AIActRiskLevel.LIMITED: _gc_mod.AutonomyLevel.HUMAN_ON_LOOP,
            _classifier_mod.AIActRiskLevel.MINIMAL: _gc_mod.AutonomyLevel.HUMAN_ON_LOOP,
        }
        _autonomy_level = _risk_to_autonomy.get(_risk_category, _gc_mod.AutonomyLevel.HUMAN_ON_LOOP)
        self._governance_contract: GovernanceContract = _gc_mod.GovernanceContract(
            agent_id=agent_id,
            tenant_id=tenant_id,
            autonomy_level=_autonomy_level,
            risk_category=_risk_category,
        )
        self._governance_contract.record_evidence(
            "ai_act_classification",
            {
                "risk_category": _risk_category.value,
                "autonomy_level": _autonomy_level.value,
                "department": "general",
                "specialisation": _agent_type_value,
            },
        )

        # State
        self.state = OrchestratorState(
            mode=OrchestratorMode.HYBRID,
            active_tasks={},
            completed_tasks=[],
            agent_load={},
            performance_metrics={},
            healthy_agents=set(),
            stressed_agents=set(),
        )

        # Agent registry cache
        self._registered_agents: dict[
            str, dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self._heartbeat_task: asyncio.Task[Any] | None = (
            None  # TODO(TYPE): replace Any with concrete type
        )

        logger.info(
            f"ChiefOrchestrator initialized for tenant {tenant_id}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "event": "orchestrator_init",
            },
        )

    async def _load_persisted_governance_contract(self) -> None:
        """SP-GOV-ARCH-8: read back a HITL-approved GovernanceContract, if any.

        See base_agent.py::_load_persisted_governance_contract for the full
        rationale -- same merge semantics (fresh classification stays
        authoritative, only approval-evidence keys carry over). Fail-open: if
        repo.load() itself fails, the conservative in-memory default built in
        __init__ stays in effect -- a missed refresh this cycle is not a
        security bypass, just a delayed approval pickup. If load() succeeds
        but the follow-up repo.save() then fails, the successfully-read
        approval evidence is still kept in memory (the approval was real;
        only the redundant re-persist failed) -- intentional, not a bug.

        Explicit is_initialized() guard (matching base_agent.py/
        autonomous_agent.py) rather than relying on get_db_session() raising
        fast: this file imports get_db_session eagerly at module scope
        (outside ADR-034 Contract 7's scope, unlike its two sibling classes),
        and the guard keeps that an explicit, checked invariant instead of an
        implicit one that a future change to get_db_session() could silently
        break back into the slow db_manager.initialize() retry loop.
        """
        try:
            _db_mod = importlib.import_module("src.core.database.database")
            if not _db_mod.db_manager.is_initialized():
                return
            _repo_mod = importlib.import_module(
                "src.core.governance.governance_contract_repository"
            )
            async with get_db_session() as db:
                repo = _repo_mod.GovernanceContractRepository(db, self.tenant_id)
                persisted = await repo.load(self._governance_contract.agent_id)
                if persisted is not None:
                    for key in ("approved_actions", "hitl_approval"):
                        if key in persisted.evidence:
                            self._governance_contract.evidence[key] = persisted.evidence[key]
                await repo.save(self._governance_contract)
        except Exception as e:
            logger.warning(
                "Could not load persisted governance contract for %s: %s: %s",
                self.agent_id,
                type(e).__name__,
                e,
            )

    async def initialize(self) -> bool:
        """
        Initialize Chief Orchestrator systems.

        Sets up:
        - Agent registry sync
        - Heartbeat monitoring
        - Signal listeners
        """
        try:
            await self._load_persisted_governance_contract()

            # Sync agent registry from database
            await self._sync_agent_registry()

            # Start heartbeat monitoring
            self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

            logger.info(
                f"ChiefOrchestrator initialized for tenant {self.tenant_id}",
                extra={"tenant_id": self.tenant_id, "event": "orchestrator_ready"},
            )
            return True

        except Exception as e:
            logger.error(
                f"ChiefOrchestrator initialization failed: {e}",
                extra={"tenant_id": self.tenant_id, "error": str(e)},
            )
            return False

    async def delegate_task(
        self, task: TaskData, preferred_agents: list[str] | None = None
    ) -> ExecutionResult:
        """
        Delegate task to appropriate agent(s).

        Uses signal-based coordination:
        1. Emit COGNITIVE signal with task
        2. Collect responses from capable agents
        3. Select best agent based on load/capability
        4. Return result

        Args:
            task: Task to delegate
            preferred_agents: Specific agents to consider

        Returns:
            ExecutionResult from selected agent
        """
        logger.info(
            f"Delegating task {task.id}",
            extra={
                "task_id": task.id,
                "task_title": task.title,
                "tenant_id": self.tenant_id,
            },
        )

        # GOV-002 (ADR-031): block delegation (and the resulting Signal emit) if
        # the governance contract does not permit it.
        if not self._governance_contract.is_action_permitted(GOVERNANCE_ACTION_DELEGATE_TASK):
            logger.warning(
                "ChiefOrchestrator.delegate_task blocked by GovernanceContract (ADR-031)",
                extra={"task_id": task.id, "tenant_id": self.tenant_id},
            )
            return ExecutionResult(
                success=False,
                error_message="Action blocked by governance contract (ADR-031)",
                task_id=task.id,
                tenant_id=self.tenant_id,
            )

        # Query capable agents
        responses = await self.signal_bus.query(
            source_agent=self.agent_id,
            target_agents=preferred_agents or [],  # Empty = broadcast
            query_type="capability_check",
            payload={
                "task_title": task.title,
                "task_tags": task.tags,
                "task_metadata": task.metadata,
            },
            timeout_ms=1000,
            tenant_id=self.tenant_id,
        )

        if not responses:
            return ExecutionResult(
                success=False,
                error_message="No agents available for task",
                task_id=task.id,
            )

        # Select best agent (lowest load + highest capability score)
        best_agent = self._select_best_agent(responses)

        # Assign task
        assignment = TaskAssignment(
            task_id=task.id,
            assigned_agent=best_agent,
            agent_type="symbiotic",  # Will be updated from response
            priority=task.priority,
            estimated_duration=300,  # 5 min default
            status="in_progress",
        )

        self.state.active_tasks[task.id] = assignment

        # Emit task assignment signal
        await self.signal_bus.emit(
            Signal(
                tenant_id=self.tenant_id,
                source_agent_id=self.agent_id,
                target_agent_ids=[best_agent],
                tier=SignalTier.COGNITIVE,
                payload={"action": "execute_task", "task": task.model_dump()},
            )
        )

        # Wait for completion (in real impl, would use async callback)
        # For now, return pending status
        return ExecutionResult(
            success=True,
            result_data={
                "status": "delegated",
                "assigned_agent": best_agent,
                "task_id": task.id,
            },
            task_id=task.id,
        )

    async def broadcast_to_all(
        self,
        message_type: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tier: SignalTier = SignalTier.BROADCAST,
    ) -> list[str]:
        """
        Broadcast message to all agents in tenant.

        Args:
            message_type: Type of broadcast
            payload: Message data
            tier: Signal priority tier

        Returns: List[Any] of signal_ids emitted  # TODO(TYPE): replace Any with concrete type
        """
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=self.agent_id,
            target_agent_ids=[],  # Empty = all
            tier=tier,
            payload={"message_type": message_type, "data": payload},
        )

        signal_id = await self.signal_bus.emit(signal)

        logger.info(
            f"Broadcast {message_type} to all agents",
            extra={
                "message_type": message_type,
                "tier": tier.value,
                "signal_id": signal_id,
            },
        )

        return [signal_id]

    async def get_system_health(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get health status of all agents in tenant."""
        healthy = len(self.state.healthy_agents)
        stressed = len(self.state.stressed_agents)
        total = healthy + stressed

        return {
            "tenant_id": self.tenant_id,
            "total_agents": total,
            "healthy": healthy,
            "stressed": stressed,
            "health_percentage": (healthy / total * 100) if total > 0 else 0,
            "active_tasks": len(self.state.active_tasks),
            "mode": self.state.mode.value,
        }

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        logger.info(
            f"ChiefOrchestrator shutdown for tenant {self.tenant_id}",
            extra={"tenant_id": self.tenant_id, "event": "orchestrator_shutdown"},
        )

    # Internal methods
    async def _sync_agent_registry(self) -> None:
        """Sync agent list from database."""
        async with get_db_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(OrganismRegistry).where(OrganismRegistry.tenant_id == self.tenant_id)
            )
            agents = result.scalars().all()

            self._registered_agents = {
                agent.agent_id: {
                    "type": agent.agent_type,
                    "status": agent.status,
                    "workload": agent.workload,
                }
                for agent in agents
            }

    async def _heartbeat_monitor(self) -> None:
        """Monitor agent heartbeats."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30s
                await self._sync_agent_registry()

                # Update health status
                now = datetime.now(timezone.utc)

                for agent_id, info in self._registered_agents.items():
                    # Simple check: if status is 'healthy', add to healthy set
                    if info.get("status") == "healthy":
                        self.state.healthy_agents.add(agent_id)
                        self.state.stressed_agents.discard(agent_id)
                    else:
                        self.state.stressed_agents.add(agent_id)
                        self.state.healthy_agents.discard(agent_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e}")

    def _select_best_agent(
        self, responses: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Select best agent based on load and capability."""
        # Simple selection: lowest load
        best = min(responses, key=lambda r: r.get("payload", {}).get("current_load", 100))
        return cast(str, best.get("responder", "unknown"))

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """
        Process a task - implements abstract method from BaseAgent.

        ChiefOrchestrator delegates tasks to other agents rather than
        processing them directly. This method provides a direct interface
        when the orchestrator itself needs to handle a task.

        Args:
            task: Task to process

        Returns:
            ExecutionResult from task delegation
        """
        logger.info(
            f"ChiefOrchestrator processing task {task.id}",
            extra={
                "task_id": task.id,
                "task_title": task.title,
                "tenant_id": self.tenant_id,
            },
        )

        # ChiefOrchestrator delegates to other agents
        return await self.delegate_task(task)
