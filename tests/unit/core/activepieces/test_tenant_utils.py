"""Unit tests for src.core.activepieces.tenant_utils."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.activepieces.tenant_utils import fetch_live_connections, get_tenant_ap_project
from src.core.activepieces.verbinding import ApVerbinding, ApVerbindingOntbreektError

_VERBINDING_PAD = "src.core.activepieces.tenant_utils.ap_verbinding_voor"
_CLIENT_VOOR_PAD = "src.core.activepieces.client.ap_client_voor"


def _verbinding(project_id: str = "proj-abc123") -> ApVerbinding:
    return ApVerbinding(
        tenant_id=42,
        base_url="http://ap.example.test/api/v1",
        email="ap@example.test",
        wachtwoord="geheim-voor-de-test",
        project_id=project_id,
    )


@pytest.mark.asyncio
async def test_get_tenant_ap_project_happy_path() -> None:
    """Geeft het project uit de verbinding van de tenant."""
    with patch(_VERBINDING_PAD, return_value=_verbinding()) as voor:
        result = await get_tenant_ap_project(42)

    assert result == "proj-abc123"
    voor.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_get_tenant_ap_project_without_connection_does_not_fall_back_to_the_tenant_id() -> None:
    """Een tenant zonder verbinding krijgt een fout, niet `str(tenant_id)`."""
    with patch(_VERBINDING_PAD, side_effect=ApVerbindingOntbreektError("geen verbinding.")):
        with pytest.raises(ApVerbindingOntbreektError):
            await get_tenant_ap_project(7)


@pytest.mark.asyncio
async def test_fetch_live_connections_uses_the_client_of_the_tenant() -> None:
    client = MagicMock()
    client.list_app_connections = AsyncMock(return_value=[{"appName": "slack"}])

    with patch(_CLIENT_VOOR_PAD, return_value=client) as voor:
        result = await fetch_live_connections(42)

    voor.assert_called_once_with(42)
    assert result == [{"appName": "slack"}]


@pytest.mark.asyncio
async def test_fetch_live_connections_without_connection_raises_instead_of_returning_empty() -> None:
    """Een lege lijst zou niet te onderscheiden zijn van "deze klant heeft geen verbindingen"."""
    with patch(_CLIENT_VOOR_PAD, side_effect=ApVerbindingOntbreektError("geen verbinding.")):
        with pytest.raises(ApVerbindingOntbreektError):
            await fetch_live_connections(7)


@pytest.mark.asyncio
async def test_fetch_live_connections_with_unreachable_server_raises() -> None:
    client = MagicMock()
    client.list_app_connections = AsyncMock(side_effect=ConnectionError("unreachable"))

    with patch(_CLIENT_VOOR_PAD, return_value=client):
        with pytest.raises(ConnectionError):
            await fetch_live_connections(42)
