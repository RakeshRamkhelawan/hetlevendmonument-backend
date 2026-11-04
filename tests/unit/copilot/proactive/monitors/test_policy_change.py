"""Unit tests for PolicyChangeMonitor."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitors.policy_change import PolicyChangeMonitor


class FakeTenantRepo:
    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1

    async def get_tenant_id_for_user(self, user_id: int) -> int | None:
        return 1

    async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None:
        # Simulate workflow "unknown" as not found; all others belong to tenant 1.
        if str(workflow_id) == "unknown":
            return None
        return 1


class FakeRedis:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True


class FakeEventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Any]] = {}
        self.events_published: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, event_type: str, handler: Any) -> None:
        if event_type not in self._subs:
            self._subs[event_type] = []
        self._subs[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        if event_type in self._subs:
            self._subs[event_type] = [h for h in self._subs[event_type] if h is not handler]

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events_published.append((event_type, payload))
        for handler in self._subs.get(event_type, []):
            await handler(payload)


class MockCopilotService:
    def __init__(self) -> None:
        self.proposals: list[Any] = []

    async def submit_proactive_proposal(self, proposal: Any) -> Any:
        from src.core.copilot.council.types import CouncilDecision, DecisionVerdict

        self.proposals.append(proposal)
        return CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=DecisionVerdict.APPROVED,
            officer_verdicts=(),
            explanation_for_user="ok",
            decision_hash="abc",
            previous_decision_hash=None,
            deliberation_ms=10,
        )


class MockDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[Any] = []

    async def dispatch(self, signal: Any, decision: Any) -> None:
        self.dispatched.append((signal, decision))


@pytest.mark.unit
class TestPolicyChangeMonitor:
    async def test_detect_returns_empty(self) -> None:
        bus = FakeEventBus()
        monitor = PolicyChangeMonitor(None, None, FakeTenantRepo(), FakeRedis(), bus)
        assert await monitor.detect(1) == []

    async def test_subscribes_on_init(self) -> None:
        bus = FakeEventBus()
        monitor = PolicyChangeMonitor(None, None, FakeTenantRepo(), FakeRedis(), bus)
        assert "workflow.config_updated" in bus._subs

    async def test_signal_on_pii_workflow(self) -> None:
        bus = FakeEventBus()
        service = MockCopilotService()
        dispatcher = MockDispatcher()
        monitor = PolicyChangeMonitor(service, dispatcher, FakeTenantRepo(), FakeRedis(), bus)
        await bus.publish(
            "workflow.config_updated",
            {
                "tenant_id": 1,
                "workflow_id": "wf-1",
                "workflow_name": "Onboarding",
                "has_pii_fields": True,
            },
        )
        assert len(service.proposals) == 1
        assert len(dispatcher.dispatched) == 1
        signal = dispatcher.dispatched[0][0]
        assert signal.severity == Severity.MEDIUM
        assert "Onboarding" in signal.title

    async def test_no_signal_when_no_pii(self) -> None:
        bus = FakeEventBus()
        service = MockCopilotService()
        dispatcher = MockDispatcher()
        monitor = PolicyChangeMonitor(service, dispatcher, FakeTenantRepo(), FakeRedis(), bus)
        await bus.publish(
            "workflow.config_updated",
            {
                "tenant_id": 1,
                "workflow_id": "wf-1",
                "workflow_name": "Onboarding",
                "has_pii_fields": False,
            },
        )
        assert len(service.proposals) == 0

    async def test_dedup_prevents_duplicate(self) -> None:
        bus = FakeEventBus()
        service = MockCopilotService()
        dispatcher = MockDispatcher()
        monitor = PolicyChangeMonitor(service, dispatcher, FakeTenantRepo(), FakeRedis(), bus)
        payload = {
            "tenant_id": 1,
            "workflow_id": "wf-1",
            "workflow_name": "Onboarding",
            "has_pii_fields": True,
        }
        await bus.publish("workflow.config_updated", payload)
        await bus.publish("workflow.config_updated", payload)
        assert len(service.proposals) == 1

    async def test_invalid_payload_is_ignored(self) -> None:
        bus = FakeEventBus()
        service = MockCopilotService()
        dispatcher = MockDispatcher()
        monitor = PolicyChangeMonitor(service, dispatcher, FakeTenantRepo(), FakeRedis(), bus)
        await bus.publish(
            "workflow.config_updated",
            {"tenant_id": None, "workflow_id": "", "has_pii_fields": True},
        )
        assert len(service.proposals) == 0

    async def test_context_contains_workflow_info(self) -> None:
        bus = FakeEventBus()
        service = MockCopilotService()
        dispatcher = MockDispatcher()
        monitor = PolicyChangeMonitor(service, dispatcher, FakeTenantRepo(), FakeRedis(), bus)
        await bus.publish(
            "workflow.config_updated",
            {
                "tenant_id": 1,
                "workflow_id": "wf-99",
                "workflow_name": "Payroll",
                "has_pii_fields": True,
            },
        )
        signal = dispatcher.dispatched[0][0]
        assert signal.context["workflow_id"] == "wf-99"
        assert signal.context["workflow_name"] == "Payroll"
        assert signal.context["has_pii_fields"] is True

    async def test_interval_is_zero(self) -> None:
        assert PolicyChangeMonitor.interval_seconds == 0

    async def test_suggested_actions_include_dpia(self) -> None:
        bus = FakeEventBus()
        service = MockCopilotService()
        dispatcher = MockDispatcher()
        monitor = PolicyChangeMonitor(service, dispatcher, FakeTenantRepo(), FakeRedis(), bus)
        await bus.publish(
            "workflow.config_updated",
            {
                "tenant_id": 1,
                "workflow_id": "wf-1",
                "workflow_name": "X",
                "has_pii_fields": True,
            },
        )
        signal = dispatcher.dispatched[0][0]
        actions = [a["action"] for a in signal.suggested_actions]
        assert "open_dpia" in actions
