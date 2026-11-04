"""GovernanceIntegration - Orchestrates pre/post execution governance (Phase 2+3).

Reuses existing OversightGate (no duplication), adds:
- Persistent accuracy tracking (Art. 15)
- Drift detection -> alert escalation
- ML behavioral analysis
- Provenance logging (Art. 12)
- [Phase 3] Learning loop: block -> LearningInsight, drift -> AdaptationRule + Feedback
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.core.governance.accuracy_monitor import AccuracyMonitor
from src.core.governance.alert_manager import AlertManager
from src.core.governance.ml_strategy import MLStrategy
from src.core.governance.oversight_gate import OversightGate, OversightResult

if TYPE_CHECKING:
    from src.core.learning.repository import AdaptationRuleRepository, LearningInsightRepository
    from src.core.learning.service import FeedbackProcessingService


class GovernanceIntegration:
    """Orchestrates all governance checks around agent execution."""

    def __init__(
        self,
        oversight_gate: OversightGate,
        accuracy_monitor: AccuracyMonitor,
        alert_manager: AlertManager,
        ml_strategy: MLStrategy,
        # Phase 3: optional learning loop dependencies
        feedback_service: FeedbackProcessingService | None = None,
        insight_repo: LearningInsightRepository | None = None,
        adaptation_repo: AdaptationRuleRepository | None = None,
    ) -> None:
        self._oversight = oversight_gate
        self._accuracy = accuracy_monitor
        self._alerts = alert_manager
        self._ml = ml_strategy
        self._feedback = feedback_service
        self._insights = insight_repo
        self._adaptations = adaptation_repo

    async def pre_execution(
        self,
        tenant_id: int,
        user_id: int,
        agent_name: str,
        agent_department: str,
        agent_specialisation: str,
        agent_capabilities: list[str],
        task_action: str,
        task_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> OversightResult:
        """PHASE 1: Pre-execution check via existing OversightGate (no duplication)."""
        result = await self._oversight.check(
            agent_name=agent_name,
            agent_department=agent_department,
            agent_specialisation=agent_specialisation,
            agent_capabilities=agent_capabilities,
            task_action=task_action,
            task_params=task_params,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Phase 3: governance block -> LearningInsight (closes governance -> learning loop)
        if not result.allowed and self._insights:
            from src.core.learning.loop import LearningInsight

            insight = LearningInsight(
                tenant_id=tenant_id,
                source_agent=agent_name,
                category="governance_block",
                finding=result.reason,
                context={
                    "action": task_action,
                    "risk_level": (
                        result.risk_level.value
                        if hasattr(result.risk_level, "value")
                        else str(result.risk_level)
                    ),
                },
                confidence=1.0,
                processed=False,
            )
            await self._insights.save(insight, str(tenant_id))

        return result

    async def post_execution(
        self,
        tenant_id: int,
        agent_name: str,
        success: bool,
        confidence_score: float | None,
        execution_time_ms: int,
        model_provider: str | None = None,
        model_version: str | None = None,
    ) -> None:
        """PHASE 2: Post-execution monitoring -- accuracy, drift, ML analysis."""
        # Art. 15: track accuracy
        await self._accuracy.track_result(
            tenant_id=tenant_id,
            agent_name=agent_name,
            success=success,
            confidence_score=confidence_score,
            execution_time_ms=execution_time_ms,
        )

        # Art. 12: provenance logging requires a db session -- inject ProvenanceService to enable
        if model_provider:
            import logging as _log

            _log.getLogger(__name__).info(
                "provenance logging skipped: inject ProvenanceService to enable",
                extra={
                    "provider": model_provider,
                    "model_version": model_version,
                    "tenant_id": tenant_id,
                },
            )

        # Art. 15: drift detection -> alert
        drift = await self._accuracy.check_drift(tenant_id, agent_name)
        if drift:
            await self._alerts.handle_violation(
                tenant_id=tenant_id,
                agent_name=agent_name,
                violation_type="accuracy_drift",
                details=drift,
            )
            # Phase 3: drift -> AdaptationRule (restrict confidence threshold)
            if self._adaptations:
                from src.core.learning.loop import AdaptationRule

                rule = AdaptationRule(
                    tenant_id=tenant_id,
                    rule_type="accuracy_drift",
                    target_agent=agent_name,
                    trigger_condition=f"drift:{agent_name}",
                    adaptation_action="lower_confidence_threshold",
                    confidence=1.0,
                    active=True,
                )
                await self._adaptations.save(rule, str(tenant_id))

        # Phase 3: feedback service (always, when configured)
        if self._feedback:
            await self._feedback.process_feedback(
                {
                    "feedback_type": "governance_result",
                    "tenant_id": tenant_id,
                    "agent_name": agent_name,
                    "confidence": confidence_score,
                    "had_violations": bool(drift),
                }
            )

        # ML behavioral analysis
        event = {
            "event_id": f"{agent_name}:{datetime.now(timezone.utc).isoformat()}",
            "agent_name": agent_name,
            "tenant_id": tenant_id,
            "agent_tenant_id": tenant_id,
            "success": success,
            "execution_time_ms": execution_time_ms,
            "risk_level": "medium",
        }
        violation = await self._ml.analyze(tenant_id, event)
        if violation:
            await self._alerts.handle_violation(
                tenant_id=tenant_id,
                agent_name=agent_name,
                violation_type=violation["type"],
                details=violation,
            )
