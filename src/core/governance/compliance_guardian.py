"""ComplianceGuardianAgent - Phase 3: Intelligence + Alerting.

Autonomous post-execution compliance monitoring agent.
Subscribes to system signals and enforces EU AI Act obligations:
  - Art. 61: Post-market surveillance (task.completed -> LearningInsight)
  - Art. 72: Authority reporting (critical task.failed -> AuthorityReport)
  - Art. 15: Accuracy monitoring (accuracy.drift > 20% -> alert)
  - Art. 17: Quality management (repeated governance.block > 5/24h -> AdaptationRule)
"""

from __future__ import annotations

from typing import Any


class ComplianceGuardianAgent:
    """Autonomous agent that monitors post-execution compliance signals."""

    # Art. 15: drift threshold -- alert when drift exceeds 20%
    DRIFT_THRESHOLD = 0.2
    # Art. 17: block threshold -- adaptation rule when more than 5 blocks in 24h
    BLOCK_THRESHOLD = 5

    def __init__(
        self,
        signal_bus: Any,  # TODO(TYPE): replace Any with concrete type
        alert_manager: Any,  # TODO(TYPE): replace Any with concrete type
        authority_reporter: Any,  # TODO(TYPE): replace Any with concrete type
        insight_repo: Any,  # TODO(TYPE): replace Any with concrete type
        adaptation_repo: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self._bus = signal_bus
        self._alert_manager = alert_manager
        self._authority_reporter = authority_reporter
        self._insight_repo = insight_repo
        self._adaptation_repo = adaptation_repo
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        self._bus.subscribe("task.completed", self._on_task_completed)
        self._bus.subscribe("task.failed", self._on_task_failed)
        self._bus.subscribe("governance.block", self._on_governance_block)
        self._bus.subscribe("accuracy.drift", self._on_accuracy_drift)
        self._bus.subscribe("agent.created", self._on_agent_lifecycle)
        self._bus.subscribe("agent.deactivated", self._on_agent_lifecycle)

    async def _on_task_completed(
        self, signal: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Art. 61: Post-market surveillance -- record insight for every completed task."""
        from src.core.learning.loop import LearningInsight

        insight = LearningInsight(
            tenant_id=signal.get("tenant_id"),
            source_agent=signal.get("agent_name"),
            category="task_surveillance",
            finding=f"Task completed by {signal.get('agent_name')}",
            context={
                "confidence_score": signal.get("confidence_score"),
                "duration_ms": signal.get("duration_ms"),
                "risk_level": signal.get("risk_level"),
            },
            confidence=signal.get("confidence_score", 1.0),
            processed=False,
        )
        await self._insight_repo.save(insight, str(signal.get("tenant_id", "")))

    async def _on_task_failed(
        self, signal: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Art. 72: Critical failures must be reported to the surveillance authority."""
        if signal.get("severity") != "critical":
            return

        await self._authority_reporter.report_incident(
            tenant_id=signal.get("tenant_id"),
            incident_type="critical_task_failure",
            agent_name=signal.get("agent_name"),
            details=signal,
        )

    async def _on_accuracy_drift(
        self, signal: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Art. 15: Significant accuracy drift (>20%) triggers a compliance alert."""
        drift_score = signal.get("drift_score", 0.0)
        if drift_score <= self.DRIFT_THRESHOLD:
            return

        await self._alert_manager.handle_violation(
            tenant_id=signal.get("tenant_id"),
            agent_name=signal.get("agent_name"),
            violation_type="accuracy_drift",
            details=signal,
        )

    async def _on_governance_block(
        self, signal: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Art. 17: Repeated blocks (>5 in 24h) trigger an adaptation rule + alert."""
        tenant_id = signal.get("tenant_id")
        agent = signal.get("agent")

        count = await self._adaptation_repo.count_recent(
            tenant_id=tenant_id,
            agent=agent,
            hours=24,
        )
        if count <= self.BLOCK_THRESHOLD:
            return

        from src.core.learning.loop import AdaptationRule

        rule = AdaptationRule(
            tenant_id=tenant_id,
            rule_type="governance_block_pattern",
            target_agent=agent,
            trigger_condition=f"repeated_blocks:{agent}",
            adaptation_action="restrict_agent",
            confidence=1.0,
            active=True,
        )
        await self._adaptation_repo.save(rule, str(tenant_id))

        await self._alert_manager.handle_violation(
            tenant_id=tenant_id,
            agent_name=agent,
            violation_type="repeated_governance_blocks",
            details={"count": count, "reason": signal.get("reason")},
        )

    async def _on_agent_lifecycle(
        self, signal: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Handle agent lifecycle events (created/deactivated)."""
        pass
