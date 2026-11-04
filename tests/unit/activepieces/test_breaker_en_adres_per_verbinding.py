"""Een storing bij de AP van een tenant raakt de andere tenants niet; en een adres is nooit dubbelzinnig.

Gate 2 security-review dag 2 (2026-10-21): M1 (een gedeelde circuitbreaker), L2 (besturingstekens in
het adres), L3 (het interne adres in het health-antwoord).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.verbinding import ApVerbinding
from src.core.activepieces.verbinding_beheer import OngeldigApAdres, controleer_adres


def _client(tenant_id: int, url: str) -> ActivePiecesClient:
    return ActivePiecesClient(
        ApVerbinding(
            tenant_id=tenant_id,
            base_url=url,
            email="ap@example.test",
            wachtwoord="geheim-voor-de-test",
            project_id=f"proj-{tenant_id}",
        )
    )


def test_twee_adressen_hebben_elk_een_eigen_breaker() -> None:
    a = _client(1, "http://localhost:18091/api/v1")
    b = _client(2, "http://localhost:18092/api/v1")

    assert a.circuit_breaker is not b.circuit_breaker


@pytest.mark.asyncio
async def test_een_storing_bij_het_ene_adres_opent_de_breaker_van_het_andere_niet() -> None:
    a = _client(1, "http://localhost:18093/api/v1")
    b = _client(2, "http://localhost:18094/api/v1")

    async def _faalt() -> None:
        raise ConnectionError("AP weg")

    for _ in range(a.client_config.circuit_failure_threshold):
        with pytest.raises(ConnectionError):
            await a.circuit_breaker.call(_faalt)

    assert (a.is_available(), b.is_available()) == (False, True)


def test_dezelfde_tenant_deelt_zijn_breaker_tussen_verzoeken() -> None:
    eerste = _client(1, "http://localhost:18095/api/v1")
    tweede = _client(1, "http://localhost:18095/api/v1")

    assert eerste.circuit_breaker is tweede.circuit_breaker


@pytest.mark.parametrize("teken", [chr(9), chr(10), chr(13)])
def test_een_adres_met_een_besturingsteken_wordt_geweigerd(teken: str) -> None:
    with pytest.raises(OngeldigApAdres):
        controleer_adres(f"https://ap.example.com{teken}/api")


@pytest.mark.asyncio
async def test_het_health_antwoord_noemt_het_interne_adres_niet() -> None:
    client = _client(1, "http://localhost:18096/api/v1")

    # Geen echt netwerk: de uitkomst van de inlogpoging doet er niet toe, alleen wat er terugkomt.
    with patch.object(client, "_get_token", new=AsyncMock(side_effect=ConnectionError("weg"))):
        antwoord = await client.health_check()

    assert "base_url" not in antwoord and "localhost:18096" not in repr(antwoord)


def test_twee_projecten_op_hetzelfde_adres_hebben_elk_een_eigen_breaker() -> None:
    url = "http://localhost:18097/api/v1"
    a = _client(1, url)
    b = _client(2, url)

    assert a.circuit_breaker is not b.circuit_breaker


@pytest.mark.parametrize(
    ("invoer", "verwacht"),
    [
        ("HTTPS://AP.Example.COM/api/v1", "https://ap.example.com/api/v1"),
        ("https://ap.example.com:443/api/v1", "https://ap.example.com/api/v1"),
        ("https://ap.example.com./api/v1", "https://ap.example.com/api/v1"),
        ("http://LOCALHOST:80/api/v1", "http://localhost/api/v1"),
        ("https://ap.example.com:8443/Api/V1/", "https://ap.example.com:8443/Api/V1"),
    ],
)
def test_een_adres_wordt_genormaliseerd_zodat_de_uniekheid_niet_te_omzeilen_is(
    invoer: str, verwacht: str
) -> None:
    assert controleer_adres(invoer) == verwacht


@pytest.mark.asyncio
async def test_het_foutpad_van_de_health_route_noemt_het_interne_adres_niet() -> None:
    from src.core.api.v1.workflow.workflow_execution_ap_router import activepieces_health

    client = _client(1, "http://localhost:18098/api/v1")
    fout = ConnectionError("Server error for url 'http://localhost:18098/api/v1/pieces'")

    with patch.object(client, "list_pieces", new=AsyncMock(side_effect=fout)):
        antwoord = await activepieces_health(ap_client=client)

    assert "18098" not in repr(antwoord)
