# tests/core/api/v1/focus_builder/test_agents.py
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

# De eerste test in een werkproces importeert de hele focus-builder-router: gemeten 3,9 s op een
# rustige machine, en 30 s en meer als de testpoort naast andere processen draait. De testpoort
# draait met `--timeout=60` en `timeout_method = "thread"` (pyproject.toml): op Windows breekt een
# verlopen time-out dan het hele WERKPROCES af ("worker crashed", "node down: Not properly
# terminated") in plaats van een gewone fout te geven. Dat gebeurde op 2026-10-13 bij beide tests
# hier, terwijl ze los 0,08 s duren. De marker staat op de hele module, zodat ook de fixture-opzet
# (de import) meetelt; een echte hang wordt na 180 s nog steeds afgebroken.
pytestmark = pytest.mark.timeout(180)


@pytest.mark.asyncio
async def test_get_agents_returns_tiers(auth_client: AsyncClient):
    """Endpoint returns live/internal/available tiers."""
    with patch(
        "src.core.api.v1.focus_builder.agents.fetch_live_connections",
        new_callable=AsyncMock,
        return_value=[{"appName": "teams"}],
    ):
        resp = await auth_client.get("/api/v1/focus-builder/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert "live" in body
    assert "internal" in body
    assert "available" in body
    assert "ap_unavailable" in body


@pytest.mark.asyncio
async def test_get_agents_ap_timeout_returns_empty_live(auth_client: AsyncClient):
    """When AP times out, live=[] and ap_unavailable=True, not 500."""
    with patch(
        "src.core.api.v1.focus_builder.agents.fetch_live_connections",
        new_callable=AsyncMock,
        side_effect=TimeoutError("AP timeout"),
    ):
        resp = await auth_client.get("/api/v1/focus-builder/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["live"] == []
    assert body["ap_unavailable"] is True


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over rollen en de middlewareketen, niet over de accountstatus, en hebben geen database.

    De controle zelf (uitgezet = 401 ACCOUNT_DISABLED, database weg = 503) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, tegen een echte database.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import account_status

    with patch.object(
        account_status,
        "haal_account_status",
        AsyncMock(return_value=account_status.AccountStatus.ACTIEF),
    ):
        yield
