"""
Governance helper for applying OversightGate checks across execution paths.

Provides reusable governance checkpoint for all 6 execution paths.
"""

import importlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Feature flag for governance
GOVERNANCE_AVAILABLE = True


class PolicyEngineAdapter:
    def __init__(self) -> None:
        from src.core.governance.policy_engine import PolicyEngine

        self._engine = PolicyEngine()

    async def validate_action(
        self,
        action: str,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        from src.core.governance.policy_engine import ActionContext, PolicyRiskLevel

        ctx = ActionContext(
            action_name=action,
            parameters=params,
            risk_level=PolicyRiskLevel.MEDIUM,  # Default, actual risk level is determined by classifier
            tenant_id=str(context.get("tenant_id")) if context.get("tenant_id") else None,
            user_id=str(context.get("user_id")) if context.get("user_id") else None,
        )
        result = await self._engine.validate_action(ctx)
        return {
            "allowed": result.allowed,
            "violations": [result.reason] if not result.allowed else [],
        }


class AuditServiceAdapter:
    async def log_security_event(
        self, event_type: str, details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        from src.core.governance.services.audit_service import (
            log_security_event as async_log_security_event,
        )

        await async_log_security_event(
            event_type=event_type, details=details, tenant_id=details.get("tenant_id")
        )


# Per-tenant cache so ShadowCEO's threat_memory/threat_vetoes persist across
# governance checks -- a fresh instance per call means _assess_byzantine_risk()
# and _check_threat_patterns() can never find anything (they read threat_memory).
# Known limitation: per-worker-process memory, not shared across Gunicorn workers.
_shadow_ceo_instances: dict[int, Any] = {}  # TODO(TYPE): replace Any with concrete type


def _get_shadow_ceo(tenant_id: int) -> Any:  # TODO(TYPE): replace Any with concrete type
    # importlib avoids direct ImportFrom (DSM boundary governance -> agent_runtime)
    shadow_ceo_mod = importlib.import_module("src.core.als.enterprise.shadow.shadow_ceo")
    redis_pool_mod = importlib.import_module("src.core.als.infrastructure.redis_pool")
    signal_bus_mod = importlib.import_module("src.core.als.infrastructure.signal_bus")
    ShadowCEO = shadow_ceo_mod.ShadowCEO
    get_redis_pool = redis_pool_mod.get_redis_pool
    SignalBus = signal_bus_mod.SignalBus

    if tenant_id not in _shadow_ceo_instances:
        # Same pattern as src/core/api/v1/als/shared.py::get_orchestrator() --
        # SignalBus.emit() publishes over the shared Redis pool, so a fresh
        # SignalBus wrapping that same pool still reaches whatever
        # ChiefOrchestrator is subscribed for this tenant. get_als()/
        # ALSInitialization is a separate, never-initialized registry
        # (initialize_all_tenants() is a stub) -- deliberately not used here.
        try:
            pool = get_redis_pool()
            signal_bus: Any = SignalBus(pool)  # TODO(TYPE): replace Any with concrete type
        except Exception as e:
            logger.warning(
                "ShadowCEO for tenant %s created without an active SignalBus "
                "(%s) -- vetoes will not be broadcast to chief_orchestrator.",
                tenant_id,
                e,
            )
            signal_bus = None
        _shadow_ceo_instances[tenant_id] = ShadowCEO(tenant_id=tenant_id, signal_bus=signal_bus)
    return _shadow_ceo_instances[tenant_id]


async def apply_governance_check(
    agent_name: str,
    task_action: str,
    agent_department: str = "unknown",
    agent_specialisation: str = "general",
    agent_capabilities: list[Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    task_params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> tuple[bool, str | None]:
    """
    Apply governance checkpoint to any execution path.

    Returns:
        (allowed: bool, reason: Optional[str])
        - (True, None) if governance allows execution
        - (False, reason) if governance blocks execution
    """
    if not GOVERNANCE_AVAILABLE:
        logger.error("Governance check unavailable for %s/%s", agent_name, task_action)
        return False, "Governance system unavailable"

    try:
        from src.core.governance.oversight_gate import OversightGate

        oversight_gate = OversightGate(
            policy_engine=PolicyEngineAdapter(), audit_service=AuditServiceAdapter()
        )
        oversight_result = await oversight_gate.check(
            agent_name=agent_name,
            agent_department=agent_department,
            agent_specialisation=agent_specialisation,
            agent_capabilities=agent_capabilities or [],
            task_action=task_action,
            task_params=task_params or {},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not oversight_result.allowed:
            logger.warning(
                f"Governance check blocked {agent_name}/{task_action}: {oversight_result.reason}"
            )
            return False, oversight_result.reason

        if oversight_result.requires_human_approval:
            # We fail-secure pre-execution if human approval is required but not handled
            reason = f"Human approval required: {oversight_result.reason}"
            logger.warning(f"Governance check blocked {agent_name}/{task_action}: {reason}")
            return False, reason

        # ShadowCEO pre-execution veto check
        try:
            from src.core.shared.interfaces import TaskData

            # review_task takes a TaskData + the proposed agent (not task_type/payload).
            # Build a minimal task from the governance inputs; task_params feeds the
            # ShadowCEO complexity/threat assessment via task.metadata.
            review_task_data = TaskData(
                title=task_action,
                description=f"Governance pre-execution review for {agent_name}",
                metadata=task_params or {},
            )
            shadow_ceo = _get_shadow_ceo(tenant_id or 1)
            veto = await shadow_ceo.review_task(
                task=review_task_data,
                proposed_agent=agent_name,
            )
            # review_task returns a VetoDecision only when the task must be blocked;
            # None means approved.
            if veto is not None:
                reason = f"ShadowCEO veto: {veto.veto_reason}"
                logger.warning(f"Governance check blocked {agent_name}/{task_action}: {reason}")
                return False, reason
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"ShadowCEO check failed: {e}")

        return True, None

    except ImportError:
        logger.error("OversightGate import failed for %s/%s", agent_name, task_action)
        return False, "OversightGate unavailable"
    except Exception as e:
        logger.error(f"Governance check error: {e}")
        return False, "Governance check failed"


__all__ = [
    "apply_governance_check",
    "GOVERNANCE_AVAILABLE",
    "PolicyEngineAdapter",
    "AuditServiceAdapter",
]
