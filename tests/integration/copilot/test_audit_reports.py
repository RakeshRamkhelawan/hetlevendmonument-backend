"""Integration tests for audit report endpoints.

Tests the report generation API for PDF/JSON output, authorization,
and cross-tenant isolation.

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.copilot.audit.models import AuditReportJobRow
from tests.integration.copilot.conftest import seed_tenants

pytestmark = pytest.mark.asyncio


@pytest.fixture
def override_async_threshold():
    import os
    original_val = os.environ.get("AUDIT_REPORT_ASYNC_THRESHOLD")
    os.environ["AUDIT_REPORT_ASYNC_THRESHOLD"] = "5"
    yield
    if original_val is not None:
        os.environ["AUDIT_REPORT_ASYNC_THRESHOLD"] = original_val
    else:
        os.environ.pop("AUDIT_REPORT_ASYNC_THRESHOLD", None)


async def test_audit_report_sync_pdf(
    authenticated_client: AsyncClient,
    db_session: Any,
) -> None:
    """Happy Path: Small PDF report (sync)"""
    tenant_id = 5001
    await seed_tenants(db_session, [tenant_id])

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    response = await authenticated_client.get(
        "/api/v1/copilot/audit/report",
        params={"from": start.isoformat(), "to": end.isoformat(), "format": "pdf"},
        headers={"x-tenant-id": str(tenant_id)},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


async def test_audit_report_async_json(
    authenticated_client: AsyncClient,
    db_session: Any,
    override_async_threshold: Any,
) -> None:
    """Happy Path: Large JSON report (async) -> returns 202"""
    tenant_id = 1

    from src.core.copilot.council.models import CouncilDecisionRow

    for _ in range(6):
        decision = CouncilDecisionRow(
            decision_id=uuid4(),
            proposal_id=uuid4(),
            tenant_id=tenant_id,
            user_id=1,
            timestamp=datetime.now(timezone.utc),
            verdict="approved",
            trigger="user_request",
            confidence=1.0,
            action_type="test",
            action_params={},
            message="test message",
            data_classification="public",
            model_id="test",
            model_version="1.0",
            reasoning="test",
            explanation_for_user="test",
            deliberation_ms=100,
            officer_verdicts_hash="dummy_verdicts_hash",
            decision_hash=str(uuid4()),
        )
        db_session.add(decision)
    await db_session.commit()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    with patch("src.core.copilot.audit.report_jobs.generate_audit_report.send") as mock_send:
        response = await authenticated_client.get(
            "/api/v1/copilot/audit/report",
            params={"from": start.isoformat(), "to": end.isoformat(), "format": "json"},
            headers={"x-tenant-id": str(tenant_id)},
        )

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert mock_send.called


async def test_audit_report_unauthorized(
    unauthenticated_client: AsyncClient,
    db_session: Any,
) -> None:
    """Unhappy Path: Non-admin gets 401/403"""
    tenant_id = 5003
    await seed_tenants(db_session, [tenant_id])

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    response = await unauthenticated_client.get(
        "/api/v1/copilot/audit/report",
        params={"from": start.isoformat(), "to": end.isoformat(), "format": "json"},
        headers={"x-tenant-id": str(tenant_id)},
    )
    assert response.status_code in (401, 403)


async def test_cross_tenant_polling(
    authenticated_client: AsyncClient,
    db_session: Any,
) -> None:
    """Security: Tenant A cannot poll Tenant B's job."""
    tenant_id = 5004
    other_tenant_id = 5005
    await seed_tenants(db_session, [tenant_id, other_tenant_id])

    job_id = uuid4()

    job = AuditReportJobRow(
        job_id=job_id,
        tenant_id=other_tenant_id,
        user_id=1,
        status="pending",
        from_date=datetime.now(timezone.utc),
        to_date=datetime.now(timezone.utc),
        format="json",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    response = await authenticated_client.get(
        f"/api/v1/copilot/audit/report/{job_id}/status",
        headers={"x-tenant-id": str(tenant_id)},
    )
    assert response.status_code == 404
