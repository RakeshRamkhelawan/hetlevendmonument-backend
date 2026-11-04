"""Integration tests for SP-ARCH-ARCH-2: twin consent-profile + council-decisions.

ADR-005: tenant isolation. ADR-033: endpoints exercised as close to their real
call path as practical without requiring full JWT/auth wiring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from src.api.v1.endpoints.digital_twin import get_twin_consent_profile
from src.core.governance.models import HITLRequestModel
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.twin_models import UserBehaviorObservation
from src.core.models.rbac_models import Tenant


def _fake_request() -> Request:
    """Minimal real Starlette Request -- @twin_limiter.limit() needs request.client."""
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/api/v1/learning/twin/consent-profile",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "query_string": b"",
        }
    )


async def _insert_observation(
    db: AsyncSession,
    tenant_id: int,
    hashed_user_id: str,
    behavior_type: str,
    created_at: datetime,
    expires_at: datetime,
) -> None:
    db.add(
        UserBehaviorObservation(
            tenant_id=tenant_id,
            human_user_id=hashed_user_id,
            session_id="sess-1",
            behavior_type=behavior_type,
            context={},
            outcome_metrics={},
            confidence_score=1.0,
            created_at=created_at,
            expires_at=expires_at,
        )
    )
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_twin_consent_profile_aggregates_real_observations(db_session: AsyncSession) -> None:
    """Behavior patterns + retention date come from real UserBehaviorObservation rows."""
    from src.core.learning.privacy.privacy_filter import PrivacyFilter

    tenant_id = 501
    user_id = "twin-profile-user"

    result = await db_session.execute(select(Tenant).where(Tenant.id == tenant_id))
    if result.scalar_one_or_none() is None:
        db_session.add(Tenant(id=tenant_id, name="T501", slug="t501", is_active=True, max_users=10))
        await db_session.commit()

    hashed = PrivacyFilter.hash_user_id(user_id, tenant_id)
    now = datetime.now(timezone.utc)
    await _insert_observation(
        db_session, tenant_id, hashed, "file_edit", now, now + timedelta(days=90)
    )
    await _insert_observation(
        db_session, tenant_id, hashed, "file_edit", now, now + timedelta(days=90)
    )
    await _insert_observation(
        db_session, tenant_id, hashed, "undo_loop", now, now + timedelta(days=90)
    )

    fake_user = SimpleNamespace(id=user_id, tenant_id=tenant_id)
    consent_mgr = TwinConsentManager(db=db_session, cache=None)

    result = await get_twin_consent_profile(
        request=_fake_request(),
        response=Response(),
        current_user=fake_user,  # type: ignore[arg-type]
        consent_mgr=consent_mgr,
        db=db_session,
    )

    assert result.user_id == user_id
    assert result.consent_status == "revoked"  # default DISABLED maps to "revoked"
    patterns_by_name = {p.name: p.frequency for p in result.behavior_patterns}
    assert patterns_by_name == {"file_edit": 2, "undo_loop": 1}
    assert result.data_retained_until is not None
    assert result.avg_cognitive_delay_ms is None
    assert result.context_usage_percent is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_twin_consent_profile_tenant_isolation(db_session: AsyncSession) -> None:
    """Tenant A's observations must not leak into tenant B's aggregate profile."""
    from src.core.learning.privacy.privacy_filter import PrivacyFilter

    for tid in (601, 602):
        result = await db_session.execute(select(Tenant).where(Tenant.id == tid))
        if result.scalar_one_or_none() is None:
            db_session.add(
                Tenant(id=tid, name=f"T{tid}", slug=f"t{tid}", is_active=True, max_users=10)
            )
    await db_session.commit()

    user_id = "shared-user-id"
    now = datetime.now(timezone.utc)
    hashed_a = PrivacyFilter.hash_user_id(user_id, 601)
    await _insert_observation(db_session, 601, hashed_a, "file_edit", now, now + timedelta(days=90))

    fake_user_b = SimpleNamespace(id=user_id, tenant_id=602)
    consent_mgr = TwinConsentManager(db=db_session, cache=None)

    result = await get_twin_consent_profile(
        request=_fake_request(),
        response=Response(),
        current_user=fake_user_b,  # type: ignore[arg-type]
        consent_mgr=consent_mgr,
        db=db_session,
    )

    assert result.behavior_patterns == []
    assert result.data_retained_until is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_council_decisions_lists_pending_hitl_requests(
    client: AsyncClient, db_session: AsyncSession, auth_headers, test_tenant_id: int
) -> None:
    """GET /api/v1/council/decisions surfaces pending hitl_requests for the tenant."""
    hitl = HITLRequestModel(
        request_id="council-req-1",
        tenant_id=test_tenant_id,
        ticket_ref="COUNCIL-TEST-001",
        task_id="task-council-1",
        status="pending",
        reason="High-risk pricing change requires review",
        risk_factors=["HIGH_RISK"],
        agent_id="pricing-agent-1",
    )
    db_session.add(hitl)
    await db_session.commit()

    response = await client.get("/api/v1/council/decisions?status=pending", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    matching = [d for d in data["decisions"] if d["id"] == "COUNCIL-TEST-001"]
    assert len(matching) == 1
    decision = matching[0]
    assert decision["agent_id"] == "pricing-agent-1"
    assert decision["risk_level"] == "high"
    assert decision["description"] == "High-risk pricing change requires review"
    assert decision["timeout_at"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_council_decisions_tenant_isolation(
    client: AsyncClient, db_session: AsyncSession, auth_headers, test_tenant_id: int
) -> None:
    """Council decisions must not leak another tenant's pending HITL requests."""
    other_tenant_id = 999
    hitl = HITLRequestModel(
        request_id="council-req-other",
        tenant_id=other_tenant_id,
        ticket_ref="COUNCIL-OTHER-001",
        task_id="task-other",
        status="pending",
        risk_factors=[],
        agent_id="other-tenant-agent",
    )
    db_session.add(hitl)
    await db_session.commit()

    response = await client.get("/api/v1/council/decisions?status=pending", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    ids = {d["id"] for d in response.json()["decisions"]}
    assert "COUNCIL-OTHER-001" not in ids
