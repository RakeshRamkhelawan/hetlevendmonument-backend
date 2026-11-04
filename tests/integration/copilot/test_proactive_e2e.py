"""E2E test: AgentHealthMonitor -> Council (real 7 Officers) -> Dispatcher -> WS push.

Behavioral: admin user sees a WS notification when an agent's error rate
exceeds the critical threshold.

Security: cross-tenant signals are never visible to other tenants.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.als.health_monitor import ERROR_RATE_CRITICAL
from src.core.copilot.council.types import CouncilDecision, DecisionVerdict
from src.core.copilot.notification.budget import NotificationBudgetTracker
from src.core.copilot.notification.digest import DigestQueue
from src.core.copilot.notification.dispatcher import NotificationDispatcher
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.copilot.proactive.monitors import AgentHealthMonitor
from src.core.copilot.service import CopilotService
from tests.integration.copilot.conftest import seed_tenants

logger = logging.getLogger(__name__)


class _MockWSPusher:
    """Captures WS push calls without hitting Redis Pub/Sub."""

    def __init__(self) -> None:
        self.pushed: list[dict[str, Any]] = []

    async def push(self, user_id: int, payload: dict[str, Any]) -> None:
        self.pushed.append(payload)


class _MockHealthService:
    def __init__(self, metrics: list[Any]) -> None:
        self._metrics = metrics

    def get_health_report(self) -> list[Any]:
        return self._metrics


class _MockHealthRegistry:
    def __init__(self) -> None:
        self._services: dict[int, Any] = {}

    def set(self, tenant_id: int, service: Any) -> None:
        self._services[tenant_id] = service

    def get_for_tenant(self, tenant_id: int) -> Any:
        return self._services.get(tenant_id)


class _MockTenantRepo:
    def __init__(self) -> None:
        self._admins: dict[int, int] = {}

    def set_primary_admin(self, tenant_id: int, user_id: int) -> None:
        self._admins[tenant_id] = user_id

    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return self._admins[tenant_id]

    async def get_platform_admin_tenant_id(self) -> int:
        return next(iter(self._admins.keys()), 1)

    async def list_active_ids(self) -> list[int]:
        return list(self._admins.keys())


def _make_unhealthy_metrics(agent_id: str, error_count: int, total_tasks: int) -> Any:
    m = MagicMock()
    m.agent_id = agent_id
    m.error_count = error_count
    m.total_tasks = total_tasks
    m.error_rate = error_count / total_tasks
    return m


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
async def test_agent_health_monitor_to_user_notification(
    real_council: Any,
    db_session: Any,
    real_redis_client: Any,
) -> None:
    """Failing agent -> AgentHealthMonitor -> Council APPROVED -> WS push to admin."""
    tenant_id = 10001
    admin_user_id = 10042

    logger.info(
        "e2e_start",
        extra={
            "test_name": "test_agent_health_monitor_to_user_notification",
            "tenant_id": tenant_id,
        },
    )

    await seed_tenants(db_session, [tenant_id])

    # donor-router: 27/50 calls fail (error_rate=0.54 > ERROR_RATE_CRITICAL=0.50)
    metrics = _make_unhealthy_metrics("donor-router", error_count=27, total_tasks=50)
    assert metrics.error_rate >= ERROR_RATE_CRITICAL

    health_registry = _MockHealthRegistry()
    health_registry.set(tenant_id, _MockHealthService([metrics]))

    tenant_repo = _MockTenantRepo()
    tenant_repo.set_primary_admin(tenant_id, admin_user_id)

    ws_mock = _MockWSPusher()
    prefs_repo = UserNotificationPreferencesRepo(db_session)
    budget_tracker = NotificationBudgetTracker(real_redis_client)
    digest_queue = DigestQueue(real_redis_client)

    dispatcher = NotificationDispatcher(
        budget_tracker=budget_tracker,
        preferences_repo=prefs_repo,
        ws_pusher=ws_mock,  # type: ignore[arg-type]
        digest_queue=digest_queue,
    )
    copilot_service = CopilotService(
        council=real_council,
        llm_handler=AsyncMock(),
        proposal_builder=MagicMock(),
    )
    monitor = AgentHealthMonitor(
        copilot_service=copilot_service,
        dispatcher=dispatcher,
        health_registry=health_registry,
        tenant_repo=tenant_repo,
        redis=real_redis_client,
    )

    # Clean dedup key to prevent interference from previous runs
    dedup_key = f"monitor_dedup:agent_health:{tenant_id}:donor-router"
    await real_redis_client.delete(dedup_key)

    try:
        # Step 1 -- detect
        signals = await monitor.detect(tenant_id=tenant_id)
        assert len(signals) >= 1, "Monitor must emit signal for unhealthy agent"
        assert signals[0].affected_user_id == admin_user_id
        assert signals[0].tenant_id == tenant_id

        # Step 2 -- propose to council (real 7-Officer deliberation)
        decision = await monitor.propose_to_council(signals[0])

        assert isinstance(decision, CouncilDecision)
        # Platform monitor (internal data, no user PII) -> APPROVED
        assert decision.verdict == DecisionVerdict.APPROVED, (
            f"Expected APPROVED but got {decision.verdict}"
        )

        # Step 3 -- dispatcher pushed to WS (27 errors >= HIGH threshold 25)
        assert len(ws_mock.pushed) == 1, f"Expected 1 WS push, got {len(ws_mock.pushed)}"
        msg = ws_mock.pushed[0]
        assert msg["type"] == "signal"
        assert "agent" in msg["title"].lower() or "Agent" in msg["title"]
        assert msg["severity"] == "high"

        logger.info(
            "e2e_complete",
            extra={
                "test_name": "test_agent_health_monitor_to_user_notification",
                "tenant_id": tenant_id,
                "verdict": decision.verdict.value,
            },
        )
    finally:
        from datetime import datetime, timezone

        budget_key = (
            f"copilot:notif:{tenant_id}:{admin_user_id}:"
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        )
        await real_redis_client.delete(dedup_key)
        await real_redis_client.delete(budget_key)


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
@pytest.mark.multi_tenant
async def test_agent_health_signal_not_visible_across_tenants(
    real_council: Any,
    db_session: Any,
    real_redis_client: Any,
) -> None:
    """Cross-tenant isolation: tenant_1 detect() returns empty when only tenant_2 is unhealthy."""
    tenant_1_id = 201
    tenant_2_id = 202
    admin_1_id = 2001
    admin_2_id = 2002

    await seed_tenants(db_session, [tenant_1_id, tenant_2_id])

    metrics = _make_unhealthy_metrics("failing-agent", error_count=30, total_tasks=50)

    health_registry = _MockHealthRegistry()
    health_registry.set(tenant_2_id, _MockHealthService([metrics]))
    # tenant_1 has NO health service registered

    tenant_repo = _MockTenantRepo()
    tenant_repo.set_primary_admin(tenant_1_id, admin_1_id)
    tenant_repo.set_primary_admin(tenant_2_id, admin_2_id)

    ws_mock = _MockWSPusher()
    prefs_repo = UserNotificationPreferencesRepo(db_session)
    dispatcher = NotificationDispatcher(
        budget_tracker=NotificationBudgetTracker(real_redis_client),
        preferences_repo=prefs_repo,
        ws_pusher=ws_mock,  # type: ignore[arg-type]
        digest_queue=DigestQueue(real_redis_client),
    )
    copilot_service = CopilotService(
        council=real_council,
        llm_handler=AsyncMock(),
        proposal_builder=MagicMock(),
    )
    monitor = AgentHealthMonitor(
        copilot_service=copilot_service,
        dispatcher=dispatcher,
        health_registry=health_registry,
        tenant_repo=tenant_repo,
        redis=real_redis_client,
    )

    dedup_key = f"monitor_dedup:agent_health:{tenant_2_id}:failing-agent"
    await real_redis_client.delete(dedup_key)

    try:
        # tenant_1 has no health service -> no signals (isolation check)
        signals_t1 = await monitor.detect(tenant_id=tenant_1_id)
        assert len(signals_t1) == 0, "tenant_1 must not receive tenant_2 signals"

        # tenant_2 has unhealthy agent -> 1 signal for its admin
        signals_t2 = await monitor.detect(tenant_id=tenant_2_id)
        assert len(signals_t2) >= 1
        assert signals_t2[0].affected_user_id == admin_2_id
        assert signals_t2[0].affected_user_id != admin_1_id
        assert signals_t2[0].tenant_id == tenant_2_id
    finally:
        await real_redis_client.delete(dedup_key)
