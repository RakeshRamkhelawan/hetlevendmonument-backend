"""
Integration tests for OfficerVerdictCache against real Redis.

Requires Redis running on localhost:6379 (or REDIS_URL env var).
"""

from __future__ import annotations

import pytest

from src.core.copilot.council.cache import (
    CACHE_KEY_PREFIX,
    OfficerVerdictCache,
)
from src.core.copilot.council.cache_invalidator import (
    CacheInvalidator,
    SimpleEventBus,
)
from src.core.copilot.council.types import (
    DataClassification,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)
from tests.integration.copilot.conftest import make_proposal


def _make_verdict(officer_name: str = "ComplianceOfficer") -> OfficerVerdict:
    return OfficerVerdict(
        officer_name=officer_name,
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        confidence=0.95,
        reason_code="OK",
        reason_text="",
        evidence={},
        deliberation_ms=0,
    )


@pytest.mark.integration
@pytest.mark.requires_redis
@pytest.mark.asyncio
async def test_cache_round_trip_with_real_redis(real_redis_client) -> None:
    cache = OfficerVerdictCache(real_redis_client)
    proposal = make_proposal(tenant_id=1, action_type="x")
    verdict = _make_verdict()
    # Clean up any stale key
    fp = cache.fingerprint(proposal)
    key = f"{CACHE_KEY_PREFIX}:1:ComplianceOfficer:{fp}"
    await real_redis_client.delete(key)

    assert await cache.get("ComplianceOfficer", proposal) is None
    await cache.set("ComplianceOfficer", proposal, verdict, ttl_s=60)
    cached = await cache.get("ComplianceOfficer", proposal)
    assert cached is not None
    assert cached.used_cache is True
    assert cached.verdict == VerdictType.APPROVE

    await real_redis_client.delete(key)


@pytest.mark.integration
@pytest.mark.requires_redis
@pytest.mark.security
@pytest.mark.asyncio
async def test_cache_invalidate_tenant_against_real_redis(real_redis_client) -> None:
    cache = OfficerVerdictCache(real_redis_client)
    # Clean up any stale keys
    for tenant_id in (1, 2):
        pattern = f"{CACHE_KEY_PREFIX}:{tenant_id}:*"
        cursor = 0
        while True:
            cursor, keys = await real_redis_client.scan(
                cursor=cursor, match=pattern, count=500
            )
            if keys:
                await real_redis_client.delete(*keys)
            if cursor == 0:
                break

    # Write 5 verdicts for tenant 1, 3 for tenant 2
    for i in range(5):
        p = make_proposal(tenant_id=1, action_type=f"a{i}")
        await cache.set("ComplianceOfficer", p, _make_verdict(), ttl_s=60)
    for i in range(3):
        p = make_proposal(tenant_id=2, action_type=f"b{i}")
        await cache.set("ComplianceOfficer", p, _make_verdict(), ttl_s=60)

    deleted = await cache.invalidate_tenant(1)
    assert deleted == 5

    # Tenant 2 entries remain
    remaining_keys = []
    cursor = 0
    while True:
        cursor, keys = await real_redis_client.scan(
            cursor=cursor, match=f"{CACHE_KEY_PREFIX}:2:*", count=500
        )
        remaining_keys.extend(keys)
        if cursor == 0:
            break
    assert len(remaining_keys) == 3

    # Cleanup tenant 2
    await cache.invalidate_tenant(2)


@pytest.mark.integration
@pytest.mark.requires_redis
@pytest.mark.asyncio
async def test_event_bus_role_change_invalidates_tenant_cache(real_redis_client) -> None:
    """End-to-end: role_changed event -> cache flush for tenant."""
    cache = OfficerVerdictCache(real_redis_client)
    event_bus = SimpleEventBus()
    invalidator = CacheInvalidator(cache)
    event_bus.subscribe("rbac.role_changed", invalidator.on_role_changed)

    # Clean up
    pattern = f"{CACHE_KEY_PREFIX}:99:*"
    cursor = 0
    while True:
        cursor, keys = await real_redis_client.scan(
            cursor=cursor, match=pattern, count=500
        )
        if keys:
            await real_redis_client.delete(*keys)
        if cursor == 0:
            break

    # Fill cache for tenant 99
    p = make_proposal(tenant_id=99, action_type="action")
    await cache.set("ComplianceOfficer", p, _make_verdict(), ttl_s=60)
    assert await cache.get("ComplianceOfficer", p) is not None

    # Fire event
    await event_bus.publish("rbac.role_changed", {"tenant_id": 99, "role": "admin"})

    # Verify empty
    assert await cache.get("ComplianceOfficer", p) is None
