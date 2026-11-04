"""Integration test: ProactiveMonitor -> Council -> decision flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    Severity,
)
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.types import Signal


class HealthMonitor(ProactiveMonitor):
    name = "health"
    version = "1.0.0"
    interval_seconds = 60

    def __init__(
        self,
        copilot_service: Any,
        dispatcher: Any,
        tenant_id: int | None = None,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._tenant_id = tenant_id

    async def detect(self, tenant_id: int) -> list[Signal]:
        return [
            Signal(
                tenant_id=tenant_id,
                affected_user_id=1,
                monitor_name=self.name,
                title="Agent failing",
                body="Error rate > 50%",
                severity=Severity.HIGH,
                data_classification=DataClassification.INTERNAL,
                suggested_actions=[{"label": "Investigate", "action": "navigate"}],
                detection_reasoning="rolling window error rate",
                confidence=0.92,
                context={"agent_id": "router"},
            )
        ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_monitor_to_council_decision(
    db_session: Any,
    real_council_factory: Any,
) -> None:
    """End-to-end: monitor builds Signal -> Proposal -> Council -> decision."""
    council = real_council_factory()
    mock_dispatcher = AsyncMock()

    # Wrap real council in a minimal copilot-service-like object
    class FakeCopilotService:
        async def submit_proactive_proposal(self, proposal: Any) -> CouncilDecision:
            return await council.deliberate(proposal)

    service = FakeCopilotService()
    monitor = HealthMonitor(service, mock_dispatcher)

    signals = await monitor.detect(tenant_id=1)
    assert len(signals) == 1
    signal = signals[0]

    decision = await monitor.propose_to_council(signal)

    assert isinstance(decision, CouncilDecision)
    assert decision.tenant_id == 1
    assert decision.verdict in {
        DecisionVerdict.APPROVED,
        DecisionVerdict.MODIFIED,
        DecisionVerdict.HITL_REQUIRED,
        DecisionVerdict.DEFERRED,
        DecisionVerdict.BLOCKED,
    }
    assert decision.decision_hash is not None
    assert decision.explanation_for_user

    # Dispatch only on APPROVED
    if decision.verdict == DecisionVerdict.APPROVED:
        mock_dispatcher.dispatch.assert_awaited_once()
    else:
        mock_dispatcher.dispatch.assert_not_awaited()
