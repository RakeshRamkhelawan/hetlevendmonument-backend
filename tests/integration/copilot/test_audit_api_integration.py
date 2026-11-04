"""Integration tests for Co-Pilot audit endpoints against real PostgreSQL."""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow


@pytest.fixture
def csrf_bypass(integration_app):
    """Schakel de CSRF-dependency uit voor tests die iets anders dan CSRF dekken.

    CSRF wordt op de mutaties van audit_router gehandhaafd (SEC-010, Redis-backed
    fetched-token scheme). De handhaving zelf wordt afgedwongen door
    tests/architecture/test_copilot_mission_csrf_enforced.py, die alle POST-routes van
    audit_router scant -- die guard is groen. Zonder deze override gaf
    test_contest_notifies_admin_via_dramatiq 403 "Missing CSRF token": hetzelfde gat dat
    commit fcbb5354 voor de unit-tests dichtte maar in deze integratietest miste
    (OP-11 cluster G).

    De override wordt na de test weer verwijderd, ook als de test faalt, zodat CSRF niet
    stil uitgeschakeld blijft voor andere tests op dezelfde app-fixture.
    """
    from src.core.api.auth.dependencies import validate_csrf_token

    integration_app.dependency_overrides[validate_csrf_token] = lambda: None
    try:
        yield
    finally:
        integration_app.dependency_overrides.pop(validate_csrf_token, None)


@pytest.mark.integration
@pytest.mark.security
async def test_tenant_a_cannot_see_decision_of_tenant_b(
    integration_client: AsyncClient,
    postgres_session: AsyncSession,
    admin_token: str,
):
    """JWT tenant A, request decision from tenant B -> 404 (RLS blocks)."""
    # Create tenant B and a decision belonging to it
    await postgres_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, domain, is_active, "
            "max_users, max_agents, max_storage_gb, data_residency) "
            "VALUES (99999, 'Tenant B', 'tenant-b', 'tenant-b.local', true, "
            "10, 10, 10, 'global') "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    decision_id = uuid.uuid4()
    await postgres_session.execute(
        text(
            """
            INSERT INTO council_decisions (
                decision_id, proposal_id, tenant_id, user_id, timestamp,
                verdict, trigger, confidence, action_type, action_params,
                message, data_classification, model_id, model_version,
                reasoning, explanation_for_user, deliberation_ms,
                officer_verdicts_hash, decision_hash, previous_decision_hash
            ) VALUES (
                :decision_id, :proposal_id, 99999, 1, NOW(),
                'approved', 'user_request', 1.0, 'test', '{}',
                'test message', 'internal', 'm1', 'v1', 'r', 'e', 100,
                'dummy_verdicts_hash', 'h1', NULL
            )
            """
        ),
        {
            "decision_id": str(decision_id),
            "proposal_id": str(uuid.uuid4()),
        },
    )
    await postgres_session.commit()

    # Request with tenant_id=1 token
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await integration_client.get(f"/api/v1/copilot/audit/{decision_id}", headers=headers)
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.gdpr
async def test_full_explanation_flow_with_real_decision(
    integration_client: AsyncClient,
    postgres_session: AsyncSession,
    admin_token: str,
):
    """Write a decision, GET it, assert payload structure."""
    decision_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    await postgres_session.execute(
        text(
            """
            INSERT INTO council_decisions (
                decision_id, proposal_id, tenant_id, user_id, timestamp,
                verdict, trigger, confidence, action_type, action_params,
                message, data_classification, model_id, model_version,
                reasoning, explanation_for_user, deliberation_ms,
                officer_verdicts_hash, decision_hash, previous_decision_hash
            ) VALUES (
                :decision_id, :proposal_id, 1, 1, NOW(),
                'approved', 'user_request', 1.0, 'send_notification', '{}',
                'test message', 'internal', 'deepseek-chat', 'v3.1', 'reasoning text', 'explanation text',
                150, 'dummy_verdicts_hash', 'hash1', NULL
            )
            """
        ),
        {
            "decision_id": str(decision_id),
            "proposal_id": str(proposal_id),
        },
    )
    await postgres_session.execute(
        text(
            """
            INSERT INTO officer_verdicts (
                verdict_id, decision_id, tenant_id, officer_name, officer_version,
                verdict, reason_code, reason_text, evidence, deliberation_ms, confidence, used_cache
            ) VALUES (
                :verdict_id, :decision_id, 1, 'ComplianceOfficer', '1.0',
                'approve', 'OK', 'All checks passed', '{}', 50, 0.95, false
            )
            """
        ),
        {
            "verdict_id": str(uuid.uuid4()),
            "decision_id": str(decision_id),
        },
    )
    await postgres_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await integration_client.get(f"/api/v1/copilot/audit/{decision_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["decision_id"] == str(decision_id)
    assert data["verdict"].lower() == "approved"
    assert data["can_contest"] is True
    assert len(data["officer_verdicts"]) == 1
    assert data["officer_verdicts"][0]["officer_name"] == "ComplianceOfficer"


@pytest.mark.integration
@pytest.mark.gdpr
@patch("src.core.copilot.api.contest_service.notify_tenant_admins_of_contest.send")
async def test_contest_notifies_admin_via_dramatiq(
    mock_send,
    csrf_bypass,
    integration_client: AsyncClient,
    postgres_session: AsyncSession,
    admin_token: str,
):
    """Contest a decision and verify dramatiq send is called."""
    decision_id = uuid.uuid4()
    await postgres_session.execute(
        text(
            """
            INSERT INTO council_decisions (
                decision_id, proposal_id, tenant_id, user_id, timestamp,
                verdict, trigger, confidence, action_type, action_params,
                message, data_classification, model_id, model_version,
                reasoning, explanation_for_user, deliberation_ms,
                officer_verdicts_hash, decision_hash, previous_decision_hash
            ) VALUES (
                :decision_id, :proposal_id, 1, 1, NOW(),
                'approved', 'user_request', 1.0, 'test', '{}',
                'test message', 'internal', 'm1', 'v1', 'r', 'e', 100,
                'dummy_verdicts_hash', 'h1', NULL
            )
            """
        ),
        {
            "decision_id": str(decision_id),
            "proposal_id": str(uuid.uuid4()),
        },
    )
    await postgres_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await integration_client.post(
        f"/api/v1/copilot/audit/{decision_id}/contest",
        headers=headers,
        json={
            "reason_category": "factual_error",
            "reason_text": "This is a detailed reason for contesting the decision",
        },
    )
    assert response.status_code == 201
    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert str(decision_id) in args


@pytest.mark.integration
async def test_verify_endpoint_against_real_chain_of_100_decisions(
    integration_client: AsyncClient,
    postgres_session: AsyncSession,
    admin_token: str,
):
    """Insert 100 decisions with intact chain, verify returns valid."""
    prev_hash = "genesis"
    for i in range(100):
        decision_id = uuid.uuid4()
        decision_hash = f"hash_{i}"
        await postgres_session.execute(
            text(
                """
                INSERT INTO council_decisions (
                    decision_id, proposal_id, tenant_id, user_id, timestamp,
                    verdict, trigger, confidence, action_type, action_params,
                    message, data_classification, model_id, model_version,
                    reasoning, explanation_for_user, deliberation_ms,
                    officer_verdicts_hash, decision_hash, previous_decision_hash
                ) VALUES (
                    :decision_id, :proposal_id, 1, 1, NOW(),
                    'approved', 'user_request', 1.0, 'test', '{}',
                    'test message', 'internal', 'm1', 'v1', 'r', 'e', 100,
                    'dummy_verdicts_hash', :decision_hash, :prev_hash
                )
                """
            ),
            {
                "decision_id": str(decision_id),
                "proposal_id": str(uuid.uuid4()),
                "decision_hash": decision_hash,
                "prev_hash": prev_hash if prev_hash != "genesis" else None,
            },
        )
        prev_hash = decision_hash
    await postgres_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await integration_client.get("/api/v1/copilot/audit/verify", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["chain_valid"] is True
    assert data["decisions_checked"] == 100
    assert data["broken_links"] == []


@pytest.mark.integration
@pytest.mark.slow
async def test_report_pdf_renders_within_30s_for_10k_decisions(
    integration_client: AsyncClient,
    postgres_session: AsyncSession,
    admin_token: str,
):
    """Insert 10k decisions and verify PDF renders under 30s."""
    # Insert in batches to avoid overwhelming the connection
    batch_size = 500
    total = 10_000
    prev_hash = "genesis"
    for batch_start in range(0, total, batch_size):
        values = []
        params = {}
        for i in range(batch_size):
            idx = batch_start + i
            if idx >= total:
                break
            decision_id = str(uuid.uuid4())
            proposal_id = str(uuid.uuid4())
            decision_hash = f"hash_{idx}"
            prev = prev_hash if prev_hash != "genesis" else None
            params[f"d{idx}"] = decision_id
            params[f"p{idx}"] = proposal_id
            params[f"h{idx}"] = decision_hash
            params[f"ph{idx}"] = prev
            values.append(
                f"(:d{idx}, :p{idx}, 1, 1, NOW(), 'approved', 'user_request', 1.0, 'test', "
                f"'{{}}', 'test message', 'internal', 'm1', 'v1', 'r', 'e', 100, 'dummy_verdicts_hash', :h{idx}, :ph{idx})"
            )
            prev_hash = decision_hash

        if not values:
            break

        sql = (
            "INSERT INTO council_decisions ("
            "decision_id, proposal_id, tenant_id, user_id, timestamp, "
            "verdict, trigger, confidence, action_type, action_params, "
            "message, data_classification, model_id, model_version, "
            "reasoning, explanation_for_user, deliberation_ms, "
            "officer_verdicts_hash, decision_hash, previous_decision_hash"
            ") VALUES " + ",".join(values)
        )
        await postgres_session.execute(text(sql), params)
    await postgres_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    start = time.time()
    response = await integration_client.get(
        "/api/v1/copilot/audit/report",
        headers=headers,
        params={
            "from": "2026-01-01T00:00:00+00:00",
            "to": "2026-12-31T00:00:00+00:00",
            "format": "pdf",
        },
    )
    elapsed = time.time() - start
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert elapsed < 30.0, f"PDF render took {elapsed:.1f}s, expected <30s"


@pytest.mark.integration
@pytest.mark.security
async def test_token_in_query_param_is_rejected(
    integration_client: AsyncClient,
):
    """?token= on HTTP endpoint returns 401 per CLAUDE.md §6.2."""
    response = await integration_client.get("/api/v1/copilot/audit/verify?token=fakejwt")
    assert response.status_code == 401
