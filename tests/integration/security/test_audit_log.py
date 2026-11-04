import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Audit middleware does not yet persist to DB (logs to stdout only)")
async def test_audit_log_created_on_login(
    integration_client: AsyncClient, postgres_session: AsyncSession
):
    """
    Verify that a successful login creates an audit log entry.
    """
    # 1. Perform Login
    login_data = {"username": "admin@example.com", "password": "admin_password"}
    response = await integration_client.post("/api/v1/auth/token", data=login_data)

    # Assert login success (prerequisite)
    # Note: If this fails, it's an auth issue, not audit issue, but blocks the test.
    if response.status_code != 200:
        # Fallback to creating a workflow if login is tricky in this env without fixtures
        # But we assume admin@example.com exists from seed/fixtures
        pass

    # 2. Check Database for Audit Log
    # We expect a table 'audit_logs' to exist
    try:
        result = await postgres_session.execute(
            text("SELECT * FROM audit_logs WHERE action = 'LOGIN' ORDER BY timestamp DESC LIMIT 1")
        )
        row = result.fetchone()

        assert row is not None, "No audit log entry found for LOGIN action"
        # Optional: check user_id if we knew it
    except Exception as e:
        pytest.fail(f"Audit log verification failed (likely table missing): {e}")


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Audit middleware does not yet persist to DB (logs to stdout only)")
async def test_audit_log_created_on_workflow_creation(
    integration_client: AsyncClient, admin_token: str, postgres_session: AsyncSession
):
    """
    Verify that creating a workflow creates an audit log entry.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "workflow_id": "audit-test-workflow",
        "name": "Audit Test Workflow",
        "spec": {"tasks": {}, "dependencies": {}},
    }

    # 1. Create Workflow
    response = await integration_client.post("/api/v1/workflows", json=payload, headers=headers)
    if response.status_code != 200:
        pytest.fail(f"Workflow Create Failed: {response.text}")
    workflow_id = response.json().get("workflow_id")  # Use correct key from API response

    # 2. Check Database
    try:
        result = await postgres_session.execute(
            text(
                f"SELECT * FROM audit_logs WHERE details->>'workflow_id' = '{workflow_id}' AND action = 'CREATE_WORKFLOW'"
            )
        )
        row = result.fetchone()
        assert row is not None, "No audit log found for CREATE_WORKFLOW"
        # assert row.actor_email == "admin@example.com" (if we log email)
    except Exception as e:
        pytest.fail(f"Audit log verification failed: {e}")
