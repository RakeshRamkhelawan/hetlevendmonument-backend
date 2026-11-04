from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="Workflow endpoint uses local get_db_session (not overridden by integration fixtures)"
)
async def test_workflow_creation_resilience_to_audit_db_failure(
    integration_client: AsyncClient, admin_token: str
):
    """
    CRITICAL SECURITY TEST (Unhappy Path):
    Verifies that a database failure specifically during Audit Logging
    does NOT crash the application or rollback the main business transaction (Workflow Creation).

    The AuditService is designed to "fail open" (log error to system log, but allow operation)
    to prevent logging infrastructure issues from causing denial of service.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "workflow_id": "audit-resilience-test",
        "name": "Audit Resilience Workflow",
        "spec": {"tasks": {}, "dependencies": {}},
        "tenant_id": "1",
    }

    # Patch 'insert' in the audit_service module to simulate a DB error during query construction/execution
    # This simulates a situation where writing to the audit_logs table fails (e.g., locking, constraint violation, downtime)
    with patch(
        "src.core.services.audit_service.insert",
        side_effect=SQLAlchemyError("Simulated Audit DB Crash"),
    ):
        # Action: Try to create a workflow
        response = await integration_client.post("/api/v1/workflows", json=payload, headers=headers)

        # Verification 1: API should still succeed (200 OK)
        if response.status_code != 200:
            pytest.fail(
                f"API crashed due to Audit Log failure! Status: {response.status_code}, Body: {response.text}"
            )

        json_resp = response.json()
        assert json_resp["workflow_id"] == "audit-resilience-test"
        assert json_resp["status"] == "created"

    # Verification 2: Ensure the workflow was ACTUALLY created in the DB (Transaction didn't rollback)
    # We query the API to fetch it
    fetch_response = await integration_client.get(
        "/api/v1/workflows/audit-resilience-test", headers=headers
    )
    assert fetch_response.status_code == 200, (
        "Workflow was not persisted despite 200 OK - Transaction may have rolled back!"
    )

    # Cleanup
    await integration_client.delete("/api/v1/workflows/audit-resilience-test", headers=headers)


@pytest.mark.asyncio
async def test_login_resilience_to_audit_failure(integration_client: AsyncClient):
    """
    Verifies that Login still works if Audit Logging fails.
    """
    # 1. Standard Login Payload
    login_data = {"username": "admin@integration.test", "password": "AdminPass123!"}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # 1.5 Verify Route Exists (Debug)
    debug_resp = await integration_client.post(
        "/api/v1/auth/login", data=login_data, headers=headers
    )
    if debug_resp.status_code != 200:
        pytest.fail(
            f"Route /api/v1/auth/login is unreachable or broken: {debug_resp.status_code} - {debug_resp.text}"
        )

    # 2. Simulate DB Failure during Audit Log
    with patch(
        "src.core.governance.services.audit_service.log_security_event",
        side_effect=SQLAlchemyError("Simulated Login Audit Crash"),
    ):
        response = await integration_client.post(
            "/api/v1/auth/login", data=login_data, headers=headers
        )

    # 3. Verify Login success
    assert response.status_code == 200, f"Login failed due to Audit Crash: {response.text}"
    token_data = response.json()
    assert "access_token" in token_data, "No access token returned"
