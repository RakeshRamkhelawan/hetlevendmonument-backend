from __future__ import annotations

import datetime
import importlib
import json
import logging
from datetime import timezone
from typing import TYPE_CHECKING, Any, Optional, cast
from uuid import uuid4

import redis.asyncio as redis

# NOTE: ADR-034 Cat B Stap 3D -- Redis-client voor agent state, startup-koppeling.
# import-linter Contract 7 ignore_imports gedocumenteerd. Backlog: SP-AGT-005.
from src.core.database.redis import get_redis_client
from src.core.shared.interfaces import BaseAgent, ExecutionResult, TaskData
from src.core.types import AgentType

# SP-AGT-004: governance is a TYPE_CHECKING-only import here -- src/core/agents/ has a
# governance runtime-import ceiling of 0 (ADR-034 agent_runtime->governance coupling).
# Runtime access goes through importlib in _governance_contract_for(), matching the
# existing pattern in base_agent.py.
if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.governance.governance_contract import GovernanceContract

logger = logging.getLogger(__name__)

GOVERNANCE_ACTION_PROCESS_TASK = "autonomous_agent.process_task"


class AutonomousAgent(BaseAgent):
    """
    Autonomous agent capable of executing multi-step workflows.
    State is persisted via Redis.
    Progress is reported via Redis Streams.

    GOV-001 (ADR-031): a GovernanceContract is required before any side-effecting
    action (Redis writes, stream publishes). Unlike EnhancedBaseAgent, the tenant
    is not known at construction time -- it arrives per-task via TaskData.tenant_id
    (or task.metadata["tenant_id"] as a fallback) -- so the contract is built lazily
    in process_task() and cached per tenant.

    SP-GOV-ARCH-2 (AUDIT-ARCH-2026-07-02 Dag 3): autonomy_level/risk_category are
    derived per ai_act_classifier.classify_agent() instead of a hardcoded default,
    matching the pattern used in base_agent.py::EnhancedBaseAgent.__init__().
    """

    def __init__(
        self,
        agent_id: str | None = None,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        # Sessie-naad: een Dramatiq-actor draait elke run in een eigen event loop en geeft hier de
        # sessie van zijn eigen poolloze engine mee (src/core/tasks/eigen_loop.py). Zonder naad
        # (None) geldt het oude gedrag: de gepoolde db_manager-sessie. Mag ook na constructie gezet
        # worden (attribuut), voor aanroepers die de agent via een factory zonder argumenten maken.
        self.session_factory = session_factory
        super().__init__(
            agent_id=str(uuid4()) if not agent_id else agent_id,
            agent_type=AgentType.AUTONOMOUS,
        )
        self.redis: redis.Redis | None = None  # type: ignore[type-arg]
        self._governance_contract: GovernanceContract | None = None

    async def _governance_contract_for(self, tenant_id: int) -> GovernanceContract:
        contract = self._governance_contract
        if contract is None or contract.tenant_id != tenant_id:
            _gc_mod = importlib.import_module("src.core.governance.governance_contract")
            _classifier_mod = importlib.import_module("src.core.governance.ai_act_classifier")
            _agent_type_value = getattr(self.agent_type, "value", self.agent_type)
            _risk_category = _classifier_mod.classify_agent(
                name=self.agent_id,
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
            _autonomy_level = _risk_to_autonomy.get(
                _risk_category, _gc_mod.AutonomyLevel.HUMAN_ON_LOOP
            )
            contract = _gc_mod.GovernanceContract(
                agent_id=self.agent_id,
                tenant_id=tenant_id,
                autonomy_level=_autonomy_level,
                risk_category=_risk_category,
            )
            contract.record_evidence(
                "ai_act_classification",
                {
                    "risk_category": _risk_category.value,
                    "autonomy_level": _autonomy_level.value,
                    "department": "general",
                    "specialisation": _agent_type_value,
                },
            )
            # SP-GOV-ARCH-8: read back a HITL-approved contract (see docstring on
            # base_agent.py::_load_persisted_governance_contract for the full
            # rationale -- same merge semantics: fresh classification stays
            # authoritative, only approval-evidence keys are carried over).
            # Fail-open: if repo.load() itself fails, the fresh, conservative
            # contract stays in effect. If load() succeeds but the follow-up
            # repo.save() then fails, the successfully-read approval
            # evidence is still kept in memory (the approval was real; only
            # the redundant re-persist failed) -- intentional, not a bug.
            try:
                _db_mod = importlib.import_module("src.core.database.database")
                if self.session_factory is not None or _db_mod.db_manager.is_initialized():
                    _repo_mod = importlib.import_module(
                        "src.core.governance.governance_contract_repository"
                    )
                    _open_session = self.session_factory or _db_mod.db_manager.get_session
                    async with _open_session() as db:
                        repo = _repo_mod.GovernanceContractRepository(db, tenant_id)
                        persisted = await repo.load(self.agent_id)
                        if persisted is not None:
                            for key in ("approved_actions", "hitl_approval"):
                                if key in persisted.evidence:
                                    contract.evidence[key] = persisted.evidence[key]
                        await repo.save(contract)
            except Exception as e:
                logger.warning(
                    "Could not load persisted governance contract for %s: %s: %s",
                    self.agent_id,
                    type(e).__name__,
                    e,
                )
            self._governance_contract = contract
        return contract

    async def initialize(self) -> bool:
        try:
            self.redis = await get_redis_client()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AutonomousAgent: {e}")
            return False

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """
        Process a task. For autonomous agents, this usually involves
        checking if it's a new workflow or a continuation step.
        """
        if not self.redis:
            await self.initialize()

        logger.info(f"Processing task {task.task_id} with data {task.metadata}")

        # GOV-001 (ADR-031): no tenant_id -> no GovernanceContract can be built ->
        # fail closed, consistent with ADR-005 tenant-isolation-by-default.
        raw_tenant_id = task.tenant_id or task.metadata.get("tenant_id")
        if not raw_tenant_id:
            logger.warning(
                "AutonomousAgent.process_task blocked: no tenant_id, cannot evaluate "
                "GovernanceContract (ADR-031)",
                extra={"agent_id": self.agent_id, "task_id": task.task_id},
            )
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                error_message="Action blocked: tenant_id required for governance evaluation",
                agent_id=self.agent_id,
            )

        try:
            tenant_id = int(raw_tenant_id)
            contract = await self._governance_contract_for(tenant_id)
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"AutonomousAgent.process_task blocked: invalid tenant_id {raw_tenant_id!r} ({exc})",
                extra={"agent_id": self.agent_id, "task_id": task.task_id},
            )
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                error_message="Action blocked: invalid tenant_id for governance evaluation",
                agent_id=self.agent_id,
            )

        if not contract.is_action_permitted(GOVERNANCE_ACTION_PROCESS_TASK):
            logger.warning(
                "AutonomousAgent.process_task blocked by GovernanceContract (ADR-031)",
                extra={"agent_id": self.agent_id, "task_id": task.task_id, "tenant_id": tenant_id},
            )
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                error_message="Action blocked by governance contract (ADR-031)",
                tenant_id=tenant_id,
                agent_id=self.agent_id,
            )

        # Write tenant ownership key before first event so the WS endpoint can
        # validate that only the owning tenant subscribes to this stream.
        if tenant_id and self.redis:
            await self.redis.set(
                f"workflow:{task.task_id}:tenant",
                str(tenant_id),
                ex=86400,  # 24h TTL -- matches typical workflow lifetime
                nx=True,  # SETNX: don't overwrite if already set
            )

        # publish start event
        await self.publish_stream_event(
            stream_key=f"workflow:{task.task_id}:progress",
            event_type="step_started",
            data={"task_id": task.task_id, "status": "running"},
        )

        # Logic for execution would go here or be delegated
        # For now, we simulate success

        await self.publish_stream_event(
            stream_key=f"workflow:{task.task_id}:progress",
            event_type="step_completed",
            data={
                "task_id": task.task_id,
                "status": "completed",
                "result": "simulation_success",
            },
        )

        return ExecutionResult(
            task_id=task.task_id,
            success=True,
            result_data={"message": "Task processed successfully by AutonomousAgent"},
        )

    async def publish_stream_event(
        self,
        stream_key: str,
        event_type: str,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Publish structured event to Redis Stream"""
        if not self.redis:
            await self.initialize()

        payload: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "type": event_type,
            "data": json.dumps(data),
            "timestamp": str(datetime.datetime.now(timezone.utc).timestamp()),
        }
        if self.redis is None:
            raise RuntimeError("Redis client not initialized")
        await self.redis.xadd(
            stream_key,
            cast(dict[Any, Any], payload),  # TODO(TYPE): replace Any with concrete type
        )  # TODO(TYPE): replace Any with concrete type
