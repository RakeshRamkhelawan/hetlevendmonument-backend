"""Unit tests for SensitiveWorkflowMonitor."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitors.sensitive_workflow import SensitiveWorkflowMonitor


class FakeTenantRepo:
    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1


class FakeRedis:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True


class FakeWorkflow:
    """Simple workflow object with id, name, config attributes."""

    def __init__(
        self,
        wf_id: str,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.id = wf_id
        self.name = name
        self.config = config or {}


class FakeWorkflowRepo:
    def __init__(self, workflows: list[Any] | None = None) -> None:
        self._workflows = workflows or []

    async def list_active(self, tenant_id: int) -> list[Any]:
        return self._workflows


class FakePIIScanner:
    """Returns pre-configured PII fields for any config."""

    def __init__(self, pii_fields: list[str] | None = None) -> None:
        self._fields = pii_fields if pii_fields is not None else []

    def scan(self, config: Any) -> list[str]:
        return list(self._fields)


class FakeDPIARepo:
    def __init__(self, exists: bool = False) -> None:
        self._exists = exists

    async def exists_for_workflow(self, tenant_id: int, workflow_id: Any) -> bool:
        return self._exists


def _make_monitor(
    workflows: list[Any] | None = None,
    pii_fields: list[str] | None = None,
    dpia_exists: bool = False,
    redis: FakeRedis | None = None,
) -> SensitiveWorkflowMonitor:
    return SensitiveWorkflowMonitor(
        None,
        None,
        FakeTenantRepo(),
        redis or FakeRedis(),
        FakeWorkflowRepo(workflows),
        FakePIIScanner(pii_fields),
        FakeDPIARepo(dpia_exists),
    )


@pytest.mark.unit
class TestSensitiveWorkflowMonitor:
    async def test_no_signal_when_no_active_workflows(self) -> None:
        monitor = _make_monitor(workflows=[], pii_fields=["email"])
        assert await monitor.detect(1) == []

    async def test_no_signal_when_no_pii_fields(self) -> None:
        wf = FakeWorkflow("wf-1", "Onboarding")
        monitor = _make_monitor(workflows=[wf], pii_fields=[])
        assert await monitor.detect(1) == []

    async def test_signal_when_pii_and_no_dpia(self) -> None:
        wf = FakeWorkflow("wf-1", "Onboarding", {"fields": ["email"]})
        monitor = _make_monitor(workflows=[wf], pii_fields=["email"], dpia_exists=False)
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.MEDIUM
        assert "Onboarding" in signals[0].title

    async def test_no_signal_when_dpia_exists(self) -> None:
        wf = FakeWorkflow("wf-1", "Onboarding")
        monitor = _make_monitor(workflows=[wf], pii_fields=["email"], dpia_exists=True)
        assert await monitor.detect(1) == []

    async def test_signal_has_confidential_classification(self) -> None:
        wf = FakeWorkflow("wf-1", "HR Flow")
        monitor = _make_monitor(workflows=[wf], pii_fields=["ssn"])
        signals = await monitor.detect(1)
        assert signals[0].data_classification == DataClassification.CONFIDENTIAL

    async def test_signal_contains_pii_fields_in_context(self) -> None:
        wf = FakeWorkflow("wf-99", "Payroll")
        monitor = _make_monitor(workflows=[wf], pii_fields=["bsn", "salary"])
        signals = await monitor.detect(1)
        assert signals[0].context["pii_fields"] == ["bsn", "salary"]
        assert signals[0].context["workflow_id"] == "wf-99"
        assert signals[0].context["workflow_name"] == "Payroll"

    async def test_dedup_prevents_duplicate_signals(self) -> None:
        wf = FakeWorkflow("wf-1", "X")
        redis = FakeRedis()
        monitor = _make_monitor(workflows=[wf], pii_fields=["email"], redis=redis)
        assert len(await monitor.detect(1)) == 1
        assert len(await monitor.detect(1)) == 0

    async def test_dedup_allows_after_ttl_expires(self) -> None:
        wf = FakeWorkflow("wf-1", "X")
        redis = FakeRedis()
        monitor = _make_monitor(workflows=[wf], pii_fields=["email"], redis=redis)
        assert len(await monitor.detect(1)) == 1
        redis._keys.clear()
        assert len(await monitor.detect(1)) == 1

    async def test_multiple_workflows_emit_separate_signals(self) -> None:
        wf1 = FakeWorkflow("wf-1", "A")
        wf2 = FakeWorkflow("wf-2", "B")
        monitor = _make_monitor(workflows=[wf1, wf2], pii_fields=["email"])
        signals = await monitor.detect(1)
        assert len(signals) == 2
        ids = {s.context["workflow_id"] for s in signals}
        assert ids == {"wf-1", "wf-2"}

    async def test_dedup_is_per_workflow_not_global(self) -> None:
        """Deduplicated wf-1 must not suppress wf-2."""
        wf1 = FakeWorkflow("wf-1", "A")
        wf2 = FakeWorkflow("wf-2", "B")
        redis = FakeRedis()
        monitor = _make_monitor(workflows=[wf1, wf2], pii_fields=["email"], redis=redis)
        first_run = await monitor.detect(1)
        assert len(first_run) == 2
        # Only wf-1 TTL expired
        redis._keys = {k for k in redis._keys if "wf-2" in k}
        second_run = await monitor.detect(1)
        # wf-1 allowed again, wf-2 still deduped
        assert len(second_run) == 1
        assert second_run[0].context["workflow_id"] == "wf-1"

    async def test_interval_is_daily(self) -> None:
        assert SensitiveWorkflowMonitor.interval_seconds == 86_400

    async def test_dedup_ttl_is_24h(self) -> None:
        assert SensitiveWorkflowMonitor.DEDUP_TTL_SECONDS == 86_400

    async def test_suggested_actions_include_dpia_navigate(self) -> None:
        wf = FakeWorkflow("wf-5", "Contract Signing")
        monitor = _make_monitor(workflows=[wf], pii_fields=["name"])
        signals = await monitor.detect(1)
        actions = [a["action"] for a in signals[0].suggested_actions]
        assert "navigate_to" in actions

    async def test_suggested_actions_include_mark_non_pii(self) -> None:
        wf = FakeWorkflow("wf-5", "Contract Signing")
        monitor = _make_monitor(workflows=[wf], pii_fields=["name"])
        signals = await monitor.detect(1)
        actions = [a["action"] for a in signals[0].suggested_actions]
        assert "mark_workflow_non_pii" in actions

    async def test_tenant_isolation(self) -> None:
        """Signals for tenant 1 must not bleed into tenant 2."""
        wf = FakeWorkflow("wf-1", "X")
        redis = FakeRedis()
        monitor = _make_monitor(workflows=[wf], pii_fields=["email"], redis=redis)
        s1 = await monitor.detect(1)
        s2 = await monitor.detect(2)
        assert s1[0].tenant_id == 1
        assert s2[0].tenant_id == 2

    async def test_workflow_missing_id_is_skipped(self) -> None:
        """Workflow without id must be skipped gracefully."""
        wf_bad = {"name": "no-id", "config": {}}  # dict-style, no 'id' key
        wf_good = FakeWorkflow("wf-ok", "Good")
        monitor = _make_monitor(workflows=[wf_bad, wf_good], pii_fields=["email"])
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].context["workflow_id"] == "wf-ok"

    async def test_confidence_is_0_95(self) -> None:
        wf = FakeWorkflow("wf-1", "X")
        monitor = _make_monitor(workflows=[wf], pii_fields=["email"])
        signals = await monitor.detect(1)
        assert signals[0].confidence == 0.95

    async def test_detection_reasoning_contains_workflow_id(self) -> None:
        wf = FakeWorkflow("wf-42", "Billing")
        monitor = _make_monitor(workflows=[wf], pii_fields=["iban"])
        signals = await monitor.detect(1)
        assert "wf-42" in signals[0].detection_reasoning

    async def test_workflow_repo_failure_returns_empty(self) -> None:
        """If workflow_repo raises, detect must return [] and not propagate."""

        class BrokenWorkflowRepo:
            async def list_active(self, tenant_id: int) -> list[Any]:
                raise RuntimeError("db down")

        monitor = SensitiveWorkflowMonitor(
            None,
            None,
            FakeTenantRepo(),
            FakeRedis(),
            BrokenWorkflowRepo(),  # type: ignore[arg-type]
            FakePIIScanner(["email"]),
            FakeDPIARepo(False),
        )
        assert await monitor.detect(1) == []

    async def test_dpia_check_failure_is_fail_open(self) -> None:
        """If dpia_repo raises, signal is still emitted (fail-open)."""

        class BrokenDPIARepo:
            async def exists_for_workflow(self, tenant_id: int, workflow_id: Any) -> bool:
                raise RuntimeError("dpia db down")

        wf = FakeWorkflow("wf-1", "X")
        monitor = SensitiveWorkflowMonitor(
            None,
            None,
            FakeTenantRepo(),
            FakeRedis(),
            FakeWorkflowRepo([wf]),
            FakePIIScanner(["email"]),
            BrokenDPIARepo(),  # type: ignore[arg-type]
        )
        signals = await monitor.detect(1)
        assert len(signals) == 1

    # -- Behavioral test (user perspective) ----------------------------------

    async def test_behavioral_admin_sees_signal_for_pii_workflow_without_dpia(
        self,
    ) -> None:
        """
        User (admin) runs daily scan.
        Workflow 'Employee Onboarding' processes 'bsn' and 'email' fields.
        No DPIA exists.
        Expected: admin receives one MEDIUM signal with 3 actions including DPIA link.
        """
        wf = FakeWorkflow("wf-emp", "Employee Onboarding")
        monitor = _make_monitor(workflows=[wf], pii_fields=["bsn", "email"], dpia_exists=False)
        signals = await monitor.detect(tenant_id=1)

        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == Severity.MEDIUM
        assert "Employee Onboarding" in sig.title
        assert "bsn" in sig.body
        assert len(sig.suggested_actions) == 3
        dpia_routes = [
            a["params"].get("route", "")
            for a in sig.suggested_actions
            if a.get("action") == "navigate_to"
        ]
        assert any("/compliance/dpia/new" in r for r in dpia_routes)
