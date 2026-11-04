from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from src.core.api.tool_broker_endpoints import available_tools, tool_execution_history
from src.core.auth.scopes import OAuth2Scope


# Reset state before tests
@pytest.fixture(autouse=True)
def reset_broker_state():
    tool_execution_history.clear()
    for tool_name in available_tools:
        available_tools[tool_name]["execution_count"] = 0
        available_tools[tool_name]["last_used"] = None
    yield


@pytest.mark.asyncio
async def test_list_tools_success(test_client, admin_user_with_token):
    """Test listing tools with proper permissions."""
    # Assuming test_user_with_token provides a valid token.
    # We might need to override the dependency if the default user doesn't have scopes.
    # But for now, let's try with default token.

    token = admin_user_with_token["token"]

    response = await test_client.get(
        "/api/v1/tools/list", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert data["total_count"] > 0
    assert isinstance(data["tools"][0]["tool_name"], str)


@pytest.mark.asyncio
async def test_list_tools_unauthorized(test_client):
    """Test listing tools without authentication."""
    response = await test_client.get("/api/v1/tools/list")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_execute_tool_success(test_client, admin_user_with_token):
    """Test executing a tool successfully."""
    token = admin_user_with_token["token"]

    payload = {"tool_name": "code_analyzer", "payload": {"code": "print('hello')"}}

    with patch(
        "src.core.api.tool_broker_endpoints.ToolBrokerService.execute_tool",
        return_value={"analysis": "ok"},
    ):
        response = await test_client.post(
            "/api/v1/tools/execute",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["tool_name"] == "code_analyzer"
    assert "result" in data


@pytest.mark.asyncio
async def test_execute_tool_not_found(test_client, admin_user_with_token):
    """Test executing a non-existent tool."""
    token = admin_user_with_token["token"]

    payload = {"tool_name": "invalid_tool", "payload": {}}

    response = await test_client.post(
        "/api/v1/tools/execute",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_tool_status(test_client, admin_user_with_token):
    """Test getting specific tool status."""
    token = admin_user_with_token["token"]
    tool_name = "serena"

    response = await test_client.get(
        f"/api/v1/tools/{tool_name}/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == tool_name
    assert "available" in data


@pytest.mark.asyncio
async def test_get_history(test_client, admin_user_with_token):
    """Test getting execution history."""
    token = admin_user_with_token["token"]

    # First execute a tool to have some history
    await test_client.post(
        "/api/v1/tools/execute",
        json={"tool_name": "code_analyzer", "payload": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await test_client.get(
        "/api/v1/tools/history", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    history = response.json()
    assert isinstance(history, list)
    assert len(history) > 0
    assert history[0]["tool_name"] == "code_analyzer"


@pytest.mark.asyncio
async def test_enable_tool(test_client, admin_user_with_token):
    """Test enabling a tool (requires admin)."""
    token = admin_user_with_token["token"]
    tool_name = "serena"

    response = await test_client.post(
        f"/api/v1/tools/{tool_name}/enable",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": f"Tool '{tool_name}' has been enabled"}


@pytest.mark.asyncio
async def test_execute_tool_failure_handling(test_client, admin_user_with_token):
    """Test that tool failure is handled and recorded."""
    token = admin_user_with_token["token"]

    # Mocking ToolBrokerService to raise exception
    with patch(
        "src.core.api.tool_broker_endpoints.ToolBrokerService.execute_tool",
        side_effect=Exception("Simulated Failure"),
    ):
        response = await test_client.post(
            "/api/v1/tools/execute",
            json={"tool_name": "serena", "payload": {}},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 500

        # Verify it was recorded in history
        history_response = await test_client.get(
            "/api/v1/tools/history", headers={"Authorization": f"Bearer {token}"}
        )
        history = history_response.json()
        assert len(history) > 0
        assert history[0]["status"] == "failed"
        # Het fouttYPE, niet de fouttekst (ADR-036 OP-29). Deze test eiste eerder letterlijk
        # "Simulated Failure" -- de `str()` van de exception. Die tekst is niet te vertrouwen: hij
        # kan payload-inhoud bevatten, en de historie is uitleesbaar via GET /tools/history.
        # Daarom legt deze assertie de EIGENSCHAP vast in plaats van de oude tekst: het type
        # wordt bewaard, de boodschap niet.
        #
        # Sinds de audit-hash-dekking is uitgebreid (ADR-036 OP-28/OP-29-vervolg): `error_msg`
        # ("Exception", het type) gaat niet meer kaal de historie in, maar via
        # `safe_value_digest(error_msg, tenant_id=...)` -- dezelfde keyed-HMAC-primitief als
        # `payload`/`result` hierboven al kregen (`execution_router.py:138`). Reconstrueer het
        # verwachte digest met dezelfde functie i.p.v. de kale tekst te verwachten.
        from src.core.tool_broker.redaction import safe_value_digest

        expected_error_digest = safe_value_digest("Exception", tenant_id=1)
        assert history[0]["error"] == expected_error_digest
        assert "Simulated Failure" not in str(history[0]), (
            "De rauwe fouttekst staat weer in de uitleesbare historie. Die kan payload-inhoud "
            "bevatten; alleen het fouttype hoort bewaard te blijven."
        )
        assert "Exception" not in str(history[0]["error"]), (
            "Het fouttype staat weer kaal in de uitleesbare historie i.p.v. gedigest."
        )
