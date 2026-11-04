"""Unit tests for ConsentExpiryMonitor."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitors.consent_expiry import ConsentExpiryMonitor


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


class FakeConsentRepo:
    def __init__(self, users: list[dict[str, Any]] | None = None) -> None:
        self._users = users or []

    async def list_users_with_expiring_consent(
        self, tenant_id: int, days_before_expiry: int
    ) -> list[dict[str, Any]]:
        return self._users


@pytest.mark.unit
class TestConsentExpiryMonitor:
    async def test_no_signal_when_no_expiring_consents(self) -> None:
        monitor = ConsentExpiryMonitor(
            None, None, FakeTenantRepo(), FakeRedis(), FakeConsentRepo([])
        )
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_emitted_for_expiring_consent(self) -> None:
        repo = FakeConsentRepo([{"user_id": "user-1"}])
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), FakeRedis(), repo)
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.LOW  # ADR-027 §8.2: consent expiry = LOW
        assert "user-1" in signals[0].title
        assert signals[0].affected_user_id == 42

    async def test_multiple_users_emit_multiple_signals(self) -> None:
        repo = FakeConsentRepo([{"user_id": "u1"}, {"user_id": "u2"}])
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), FakeRedis(), repo)
        signals = await monitor.detect(1)
        assert len(signals) == 2
        user_ids = {s.context["user_id"] for s in signals}
        assert user_ids == {"u1", "u2"}

    async def test_dedup_prevents_duplicate_signals(self) -> None:
        repo = FakeConsentRepo([{"user_id": "user-1"}])
        redis = FakeRedis()
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), redis, repo)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        signals2 = await monitor.detect(1)
        assert len(signals2) == 0

    async def test_dedup_allows_after_ttl_expires(self) -> None:
        repo = FakeConsentRepo([{"user_id": "user-1"}])
        redis = FakeRedis()
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), redis, repo)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        redis._keys.clear()
        signals2 = await monitor.detect(1)
        assert len(signals2) == 1

    async def test_detection_reasoning_contains_threshold(self) -> None:
        repo = FakeConsentRepo([{"user_id": "user-1"}])
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), FakeRedis(), repo)
        signals = await monitor.detect(1)
        assert "7 days" in signals[0].detection_reasoning

    async def test_signal_has_restricted_classification(self) -> None:
        # Consent records contain PII (user_id + consent type) -- RESTRICTED per ADR-019.
        repo = FakeConsentRepo([{"user_id": "user-1"}])
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), FakeRedis(), repo)
        signals = await monitor.detect(1)
        assert signals[0].data_classification == DataClassification.RESTRICTED

    async def test_interval_is_daily(self) -> None:
        assert ConsentExpiryMonitor.interval_seconds == 86400

    async def test_suggested_actions_include_reminder(self) -> None:
        repo = FakeConsentRepo([{"user_id": "user-1"}])
        monitor = ConsentExpiryMonitor(None, None, FakeTenantRepo(), FakeRedis(), repo)
        signals = await monitor.detect(1)
        actions = [a["action"] for a in signals[0].suggested_actions]
        assert "send_reminder" in actions
