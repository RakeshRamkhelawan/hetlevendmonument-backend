"""Integration test: all compliance monitors under ProactiveScheduler."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    Severity,
)
from src.core.copilot.proactive.monitors import (
    AuditAnomalyMonitor,
    ConsentExpiryMonitor,
    DSARExportMonitor,
    PolicyChangeMonitor,
    SensitiveWorkflowMonitor,
)
from src.core.copilot.proactive.scheduler import ProactiveScheduler


class FakeTenantRepo:
    async def list_active_ids(self) -> list[int]:
        return [1]

    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1

    async def get_tenant_id_for_user(self, user_id: int) -> int | None:  # noqa: ARG002
        return 1

    async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None:  # noqa: ARG002
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

    def subscribe(self, event_type: str, handler: Any) -> None:
        self._subs.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        if event_type in self._subs:
            self._subs[event_type] = [h for h in self._subs[event_type] if h != handler]

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        for handler in self._subs.get(event_type, []):
            await handler(payload)


class FakeConsentRepo:
    async def list_users_with_expiring_consent(
        self, tenant_id: int, days_before_expiry: int
    ) -> list[dict[str, Any]]:
        return []


class FakeAuditRepo:
    async def count_permission_denied_per_user(
        self, tenant_id: int, hours: int
    ) -> list[dict[str, Any]]:
        return []


class FakeRoleRepo:
    """No roles created recently by default -- grace period inactive."""

    def __init__(self, role_created_recently: bool = False) -> None:
        self._role_created_recently = role_created_recently

    async def was_any_role_created_after(self, tenant_id: int, after: datetime) -> bool:
        return self._role_created_recently


class FakeWorkflow:
    def __init__(self, wf_id: str, name: str) -> None:
        self.id = wf_id
        self.name = name
        self.config: dict[str, Any] = {}


class FakeWorkflowRepo:
    async def list_active(self, tenant_id: int) -> list[Any]:
        return []


class FakePIIScanner:
    def scan(self, config: Any) -> list[str]:
        return []


class FakeDPIARepo:
    async def exists_for_workflow(self, tenant_id: int, workflow_id: Any) -> bool:
        return False


@pytest.fixture
def mock_scheduler() -> Any:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    sched = MagicMock(spec=AsyncIOScheduler)
    sched.add_job = MagicMock()
    return sched


@pytest.mark.integration
class TestComplianceMonitorsRegister:
    def test_interval_monitors_register_under_scheduler(self, mock_scheduler: Any) -> None:
        repo = FakeTenantRepo()
        redis = FakeRedis()

        monitors = [
            ConsentExpiryMonitor(None, None, repo, redis, FakeConsentRepo()),
            AuditAnomalyMonitor(None, None, repo, redis, FakeAuditRepo(), FakeRoleRepo()),
            SensitiveWorkflowMonitor(
                None, None, repo, redis, FakeWorkflowRepo(), FakePIIScanner(), FakeDPIARepo()
            ),
        ]

        ps = ProactiveScheduler(mock_scheduler, repo, monitors)
        ps.start()

        assert mock_scheduler.add_job.call_count == 3
        job_ids = {call.kwargs["id"] for call in mock_scheduler.add_job.call_args_list}
        assert job_ids == {
            "monitor:consent_expiry",
            "monitor:audit_anomaly",
            "monitor:sensitive_workflow",
        }

    def test_event_driven_monitors_skipped_by_scheduler(self, mock_scheduler: Any) -> None:
        repo = FakeTenantRepo()
        redis = FakeRedis()
        event_bus = FakeEventBus()

        monitors = [
            DSARExportMonitor(None, None, repo, redis, event_bus),
            PolicyChangeMonitor(None, None, repo, redis, event_bus),
        ]

        ps = ProactiveScheduler(mock_scheduler, repo, monitors)
        ps.start()

        mock_scheduler.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_scheduler_runs_interval_monitors_without_errors(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        repo = FakeTenantRepo()
        redis = FakeRedis()

        monitors = [
            ConsentExpiryMonitor(None, None, repo, redis, FakeConsentRepo()),
            AuditAnomalyMonitor(None, None, repo, redis, FakeAuditRepo(), FakeRoleRepo()),
            SensitiveWorkflowMonitor(
                None, None, repo, redis, FakeWorkflowRepo(), FakePIIScanner(), FakeDPIARepo()
            ),
        ]

        sched = AsyncIOScheduler()
        ps = ProactiveScheduler(sched, repo, monitors)

        for monitor in monitors:
            await ps._run_for_all_tenants(monitor)

    @pytest.mark.asyncio
    async def test_event_driven_monitors_subscribe_and_handle_events(self) -> None:
        repo = FakeTenantRepo()
        redis = FakeRedis()
        event_bus = FakeEventBus()

        service = AsyncMock()
        decision = CouncilDecision(
            proposal_id=MagicMock(),
            tenant_id=1,
            user_id=42,
            verdict=DecisionVerdict.APPROVED,
            officer_verdicts=(),
            explanation_for_user="ok",
            decision_hash="abc",
            previous_decision_hash=None,
            deliberation_ms=10,
        )
        service.submit_proactive_proposal.return_value = decision
        dispatcher = AsyncMock()

        dsar = DSARExportMonitor(service, dispatcher, repo, redis, event_bus)
        policy = PolicyChangeMonitor(service, dispatcher, repo, redis, event_bus)

        await event_bus.publish(
            "dsar.export_initiated",
            {"tenant_id": 1, "user_id": 99, "export_type": "csv", "contains_pii": True},
        )
        await event_bus.publish(
            "workflow.config_updated",
            {
                "tenant_id": 1,
                "workflow_id": "wf-1",
                "workflow_name": "X",
                "has_pii_fields": True,
            },
        )

        service.submit_proactive_proposal.assert_awaited()
        dispatcher.dispatch.assert_awaited()

        # Suppress unused variable warnings -- monitors registered subscriptions on init
        assert dsar.name == "dsar_export"
        assert policy.name == "policy_change"

    @pytest.mark.asyncio
    async def test_audit_anomaly_grace_period_suppresses_signal(self) -> None:
        """Integration: AuditAnomalyMonitor with recent role returns no signals."""
        repo = FakeTenantRepo()
        redis = FakeRedis()

        class SpikyAuditRepo:
            async def count_permission_denied_per_user(
                self, tenant_id: int, hours: int
            ) -> list[dict[str, Any]]:
                return [
                    {"user_id": 1, "count": 5},
                    {"user_id": 2, "count": 4},
                    {"user_id": 3, "count": 3},
                ]

        monitor = AuditAnomalyMonitor(
            None,
            None,
            repo,
            redis,
            SpikyAuditRepo(),
            FakeRoleRepo(role_created_recently=True),
        )
        signals = await monitor.detect(1)
        assert signals == []

    @pytest.mark.asyncio
    async def test_sensitive_workflow_emits_for_pii_workflow(self) -> None:
        """Integration: SensitiveWorkflowMonitor emits MEDIUM signal for workflow with PII."""
        repo = FakeTenantRepo()
        redis = FakeRedis()

        class SingleWorkflowRepo:
            async def list_active(self, tenant_id: int) -> list[Any]:
                return [FakeWorkflow("wf-hr", "HR Onboarding")]

        class PIIScannerWithFields:
            def scan(self, config: Any) -> list[str]:
                return ["bsn", "email"]

        monitor = SensitiveWorkflowMonitor(
            None,
            None,
            repo,
            redis,
            SingleWorkflowRepo(),
            PIIScannerWithFields(),
            FakeDPIARepo(),
        )
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.MEDIUM
        assert signals[0].data_classification == DataClassification.CONFIDENTIAL
        assert "HR Onboarding" in signals[0].title
