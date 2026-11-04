# tests/agents/test_tool_broker_client.py

import httpx
import pytest

from respx import MockRouter
from src.core.agents.tool_broker_client import AgentToolBrokerClient

TOOL_BROKER_URL = "http://test-toolbroker.sanskritisetu.org"


@pytest.mark.asyncio
async def test_execute_tool_success(respx_mock: MockRouter) -> None:
    """
    Test een succesvolle aanroep naar de Tool Broker.
    """
    # Mock de API response
    respx_mock.post(f"{TOOL_BROKER_URL}/v1/tools/execute").mock(
        return_value=httpx.Response(200, json={"result": {"status": "completed"}})
    )

    client = AgentToolBrokerClient(base_url=TOOL_BROKER_URL, auth_token="fake-token")
    result = await client.execute_tool("serena__diagnose", {"input": "data"})

    assert result == {"status": "completed"}
    assert "Authorization" in respx_mock.calls.last.request.headers
    assert respx_mock.calls.last.request.headers["Authorization"] == "Bearer fake-token"


@pytest.mark.asyncio
async def test_execute_tool_connection_error(respx_mock: MockRouter) -> None:
    """
    Test de foutafhandeling bij een connectiefout.
    """
    respx_mock.post(f"{TOOL_BROKER_URL}/v1/tools/execute").mock(
        side_effect=httpx.ConnectError("Connection failed")
    )

    client = AgentToolBrokerClient(base_url=TOOL_BROKER_URL)
    with pytest.raises(ConnectionError, match="Tool Broker service onbereikbaar"):
        await client.execute_tool("serena__diagnose", {})


@pytest.mark.asyncio
async def test_execute_tool_api_error(respx_mock: MockRouter) -> None:
    """
    Test de foutafhandeling bij een API-fout (bv. 403 Forbidden).
    """
    error_detail = "Niet geautoriseerd voor deze tool"
    respx_mock.post(f"{TOOL_BROKER_URL}/v1/tools/execute").mock(
        return_value=httpx.Response(403, json={"detail": error_detail})
    )

    client = AgentToolBrokerClient(base_url=TOOL_BROKER_URL)
    with pytest.raises(
        ValueError, match=f"Fout bij aanroepen Tool Broker (status 403): {error_detail}"
    ):
        await client.execute_tool("serena__diagnose", {})


@pytest.mark.asyncio
async def test_client_initialization_no_token() -> None:
    """Test dat de client correct werkt zonder authenticatie token."""
    client = AgentToolBrokerClient(base_url=TOOL_BROKER_URL)
    assert "Authorization" not in client.client.headers
