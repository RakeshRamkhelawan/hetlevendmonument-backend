import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.repositories import (
    ActivePiecesConnectionRepository,
    ActivePiecesFlowRepository,
    ActivePiecesFlowRunRepository,
)


def _serialize_body(payload: dict) -> bytes:
    try:
        import orjson

        return orjson.dumps(payload)
    except ImportError:
        return json.dumps(payload, separators=(",", ":")).encode()


def _sign_payload(payload: dict, secret: str) -> str:
    body_bytes = _serialize_body(payload)
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_activepieces_webhook_endpoint_security(async_client: AsyncClient):
    """
    Integration Test: Verify the actual /webhooks/activepieces endpoint
    enforces signature verification.
    """
    endpoint = "/api/v1/webhooks/activepieces"
    secret = "test-secret"
    payload = {
        "type": "execution.completed",
        "flowId": "flow-test-001",
        "runId": "run-test-001",
        "projectId": "project-test",
        "status": "SUCCESS",
    }

    # 1. Test Missing Header -> 403
    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload)
        response = await async_client.post(
            endpoint, content=body_bytes, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "Missing signature"

    # 2. Test Invalid Signature -> 403
    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload)
        response = await async_client.post(
            endpoint,
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-AP-Signature": "invalid"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "Invalid signature"

    # 3. Test Valid Signature -> 200
    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload)
        signature = _sign_payload(payload, secret)

        response = await async_client.post(
            endpoint,
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-AP-Signature": signature},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_webhook_ignores_spoofed_tenant_id(
    async_client: AsyncClient,
    postgres_session: AsyncSession,
) -> None:
    """
    Integration Test: A signed webhook with a mismatched payload tenant_id
    must resolve to the tenant stored in the first-party flow binding,
    not the spoofed payload value.
    """
    endpoint = "/api/v1/webhooks/activepieces"
    secret = "test-secret"

    flow_repo = ActivePiecesFlowRepository(postgres_session)
    await flow_repo.create(
        tenant_id=1,
        ap_flow_id="flow-legit-123",
        project_id="project-abc",
        name="Legit Flow",
        status="ENABLED",
    )
    await postgres_session.commit()

    payload = {
        "type": "execution.started",
        "flowId": "flow-legit-123",
        "runId": "run-456",
        "projectId": "project-abc",
        "status": "RUNNING",
        "tenant_id": 999,
    }

    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload)
        signature = _sign_payload(payload, secret)
        response = await async_client.post(
            endpoint,
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-AP-Signature": signature},
        )
        assert response.status_code == 200

    run_repo = ActivePiecesFlowRunRepository(postgres_session)
    flow = await flow_repo.get_by_ap_flow_id(1, "flow-legit-123")
    runs = await run_repo.list_by_flow(tenant_id=1, flow_id=flow.id)
    assert len(runs) == 1
    assert runs[0].tenant_id == 1

    runs_spoofed = await run_repo.list_by_tenant(tenant_id=999)
    assert len(runs_spoofed) == 0


@pytest.mark.asyncio
async def test_webhook_rejects_unknown_flow(
    async_client: AsyncClient,
    postgres_session: AsyncSession,
) -> None:
    """
    Integration Test: A webhook referencing an unknown flow/project pair
    must not create any database side-effects.
    """
    endpoint = "/api/v1/webhooks/activepieces"
    secret = "test-secret"

    payload = {
        "type": "execution.started",
        "flowId": "unknown-flow-999",
        "runId": "run-999",
        "projectId": "unknown-project",
        "status": "RUNNING",
    }

    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload)
        signature = _sign_payload(payload, secret)
        response = await async_client.post(
            endpoint,
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-AP-Signature": signature},
        )
        assert response.status_code == 200

    run_repo = ActivePiecesFlowRunRepository(postgres_session)
    all_runs = await run_repo.list_by_tenant(tenant_id=1)
    assert len(all_runs) == 0


@pytest.mark.asyncio
async def test_webhook_resolves_correct_tenant_from_binding(
    async_client: AsyncClient,
    postgres_session: AsyncSession,
) -> None:
    """
    Integration Test: Multiple tenant bindings must resolve independently.
    """
    endpoint = "/api/v1/webhooks/activepieces"
    secret = "test-secret"

    flow_repo = ActivePiecesFlowRepository(postgres_session)
    flow_a = await flow_repo.create(
        tenant_id=1,
        ap_flow_id="flow-tenant-a",
        project_id="project-a",
        name="Flow A",
    )
    flow_b = await flow_repo.create(
        tenant_id=2,
        ap_flow_id="flow-tenant-b",
        project_id="project-b",
        name="Flow B",
    )
    await postgres_session.commit()

    payload_a = {
        "type": "execution.started",
        "flowId": "flow-tenant-a",
        "runId": "run-a-1",
        "projectId": "project-a",
        "status": "RUNNING",
    }

    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload_a)
        sig_a = _sign_payload(payload_a, secret)
        response = await async_client.post(
            endpoint,
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-AP-Signature": sig_a},
        )
        assert response.status_code == 200

    run_repo = ActivePiecesFlowRunRepository(postgres_session)
    runs_a = await run_repo.list_by_flow(tenant_id=1, flow_id=flow_a.id)
    assert len(runs_a) == 1
    assert runs_a[0].ap_run_id == "run-a-1"

    runs_b = await run_repo.list_by_flow(tenant_id=2, flow_id=flow_b.id)
    assert len(runs_b) == 0


@pytest.mark.asyncio
async def test_webhook_connection_event_resolves_tenant(
    async_client: AsyncClient,
    postgres_session: AsyncSession,
) -> None:
    """
    Integration Test: Connection status webhooks must resolve tenant
    from the stored connection binding, not from any payload field.
    """
    endpoint = "/api/v1/webhooks/activepieces"
    secret = "test-secret"

    conn_repo = ActivePiecesConnectionRepository(postgres_session)
    await conn_repo.create(
        tenant_id=1,
        ap_connection_id="conn-001",
        project_id="project-conn",
        app_name="gmail",
        name="Gmail Connection",
    )
    await postgres_session.commit()

    payload = {
        "type": "connection.status_changed",
        "connectionId": "conn-001",
        "appName": "gmail",
        "projectId": "project-conn",
        "status": "error",
        "errorMessage": "OAuth token expired",
    }

    with patch("src.core.config.unified_config.config.activepieces_webhook_secret", secret):
        body_bytes = _serialize_body(payload)
        signature = _sign_payload(payload, secret)
        response = await async_client.post(
            endpoint,
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-AP-Signature": signature},
        )
        assert response.status_code == 200

    conn = await conn_repo.get_by_ap_connection_id(1, "conn-001")
    assert conn.status == "error"
