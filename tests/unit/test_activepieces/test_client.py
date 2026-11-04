import pytest
from httpx import Response

import respx
from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.verbinding import ApVerbinding

PROJECT_ID = "proj_123"
FLOW_ID = "flow_456"
BASE_URL = "http://activepieces:80/api/v1"


@pytest.fixture
def client():
    """Fixture that provides an ActivePiecesClient with the connection of one tenant."""
    yield ActivePiecesClient(
        ApVerbinding(
            tenant_id=1,
            base_url=BASE_URL,
            email="test@example.com",
            wachtwoord="password",
            project_id=PROJECT_ID,
        )
    )


@pytest.mark.asyncio
async def test_authenticate(client):
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "test-jwt-token"})
        )

        await client._authenticate()
        assert client.token == "test-jwt-token"


@pytest.mark.asyncio
async def test_create_flow(client):
    client.token = "valid-token"  # Pre-authenticate
    flow_data = {"displayName": "Test Flow"}

    with respx.mock(base_url=BASE_URL, assert_all_mocked=False) as respx_mock:
        # Allow any auth calls that might happen
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "valid-token"})
        )
        # Mock flows endpoint
        respx_mock.post("/flows").mock(
            return_value=Response(200, json={"id": FLOW_ID, **flow_data})
        )

        result = await client.create_flow(PROJECT_ID, flow_data)
        assert result["id"] == FLOW_ID
        assert result["displayName"] == "Test Flow"


@pytest.mark.asyncio
async def test_update_flow(client):
    flow_data = {"displayName": "Updated Flow"}

    with respx.mock(base_url=BASE_URL, assert_all_mocked=False) as respx_mock:
        # Mock authentication endpoint
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "valid-token"})
        )
        respx_mock.get(f"/flows/{FLOW_ID}").mock(
            return_value=Response(200, json={"id": FLOW_ID, "projectId": PROJECT_ID})
        )
        respx_mock.post(f"/flows/{FLOW_ID}").mock(
            return_value=Response(200, json={"id": FLOW_ID, **flow_data})
        )

        result = await client.update_flow(FLOW_ID, flow_data)
        assert result["displayName"] == "Updated Flow"


@pytest.mark.asyncio
async def test_delete_flow(client):
    with respx.mock(base_url=BASE_URL, assert_all_mocked=False) as respx_mock:
        # Mock authentication endpoint
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "valid-token"})
        )
        respx_mock.get(f"/flows/{FLOW_ID}").mock(
            return_value=Response(200, json={"id": FLOW_ID, "projectId": PROJECT_ID})
        )
        respx_mock.delete(f"/flows/{FLOW_ID}").mock(
            return_value=Response(204)  # No content response for delete
        )

        result = await client.delete_flow(FLOW_ID)
        # delete_flow catches all exceptions and returns False on failure
        # Returns True on success
        assert result is True


@pytest.mark.asyncio
async def test_list_pieces(client):
    pieces_data = [{"name": "gmail", "version": "0.0.1", "displayName": "Gmail"}]

    with respx.mock(base_url=BASE_URL, assert_all_mocked=False) as respx_mock:
        # Mock authentication in case it's called
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "valid-token"})
        )
        # Mock the pieces endpoint
        respx_mock.get("/pieces").mock(return_value=Response(200, json=pieces_data))

        pieces = await client.list_pieces()
        assert len(pieces) == 1
        assert pieces[0].name == "gmail"


@pytest.mark.asyncio
async def test_auto_auth(client):
    """Test that auth is called if token is missing"""
    client.token = None

    with respx.mock(base_url=BASE_URL) as respx_mock:
        # Expect auth call
        respx_mock.post("/authentication/sign-in").mock(
            return_value=Response(200, json={"token": "new-token"})
        )
        # Uitvoeren leest eerst de flow voor de stappencontrole (wfb-dag1 stap 1)
        respx_mock.get(f"/flows/{FLOW_ID}").mock(
            return_value=Response(
                200,
                json={
                    "projectId": PROJECT_ID,
                    "version": {"trigger": {"name": "t", "type": "EMPTY", "settings": {}}},
                },
            )
        )
        # Expect flow call
        respx_mock.post(f"/flows/{FLOW_ID}/runs").mock(
            return_value=Response(200, json={"id": "run_1"})
        )

        await client.trigger_flow(FLOW_ID, {})
        assert client.token == "new-token"
