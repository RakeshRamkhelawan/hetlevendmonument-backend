"""De lijst van uitvoerbare agents is begrensd per medewerker (agentstap nazorg, Gate 2 security bevinding 3).

Elke aanroep opent per agent een databasesessie voor de pakketcontrole; zonder limiet kan een ingelogde medewerker de
verbindingen van het bedrijf leegtrekken. Het leespatroon van het project is 60 per minuut (`consent_read_limit`).

Mutatiebewijs (2026-10-25): zie de eindmelding van de sessie.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request

from src.core.api.v1.workflow import workflow_generation_router as router_module
from src.core.shared.rate_limiter import _rate_limiter


def _verzoek(gebruiker: int, klant: int = 1) -> SimpleNamespace:
    # De limiet haalt het verzoek uit de argumenten op type; een echt Request-object is dus nodig.
    from starlette.requests import Request

    verzoek = Request(
        {"type": "http", "method": "GET", "path": "/api/v1/vibe/agents/uitvoerbaar", "headers": [], "query_string": b""}
    )
    verzoek.state.user = SimpleNamespace(id=gebruiker, tenant_id=klant)
    return verzoek  # type: ignore[return-value]


def _lijst() -> AsyncMock:
    return AsyncMock(return_value=[])


@pytest.fixture(autouse=True)
def _schone_teller() -> None:
    _rate_limiter._requests.clear()


@pytest.mark.asyncio
async def test_de_eenenzestigste_aanroep_in_een_minuut_wordt_geweigerd() -> None:
    gebruiker = SimpleNamespace(tenant_id=1)
    with patch("src.core.als.agents.workflow_stap.uitvoerbare_agents_voor_klant", _lijst()):
        for _ in range(60):
            await router_module.list_executable_agents(request=_verzoek(7), current_user=gebruiker)  # type: ignore[arg-type]
        with pytest.raises(HTTPException) as fout:
            await router_module.list_executable_agents(request=_verzoek(7), current_user=gebruiker)  # type: ignore[arg-type]

    assert fout.value.status_code == 429


@pytest.mark.asyncio
async def test_een_andere_medewerker_heeft_een_eigen_teller() -> None:
    gebruiker = SimpleNamespace(tenant_id=1)
    with patch("src.core.als.agents.workflow_stap.uitvoerbare_agents_voor_klant", _lijst()):
        for _ in range(60):
            await router_module.list_executable_agents(request=_verzoek(7), current_user=gebruiker)  # type: ignore[arg-type]
        antwoord = await router_module.list_executable_agents(request=_verzoek(8), current_user=gebruiker)  # type: ignore[arg-type]

    assert antwoord["agents"] == []


def test_de_geregistreerde_route_is_de_begrensde_functie() -> None:
    """Een limiet die BOVEN `@router.get` staat laat de router de ongewikkelde functie registreren: dan doet hij niets."""
    route = next(
        r for r in router_module.router.routes if getattr(r, "path", "") == "/api/v1/vibe/agents/uitvoerbaar"
    )

    assert hasattr(route.endpoint, "__wrapped__")  # type: ignore[attr-defined]


class TestDeLimietOpDeEchteRoute:
    """Over de echte route met twee gebruikers vanaf HETZELFDE adres.

    De eerste versie van deze toets zette `request.state.user` met de hand, en liet daardoor niet zien dat de route dat
    zelf niet doet: de sleutel viel terug op het IP-adres, dat achter de proxy voor iedereen gelijk is. Eén medewerker
    kon zo het hele bedrijf (en elk ander bedrijf) op 429 zetten (Gate 2 security, nazorg).
    """

    @staticmethod
    def _client() -> object:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.core.auth.api_deps import get_current_user_dependency

        app = FastAPI()
        app.include_router(router_module.router)

        async def _wie(request: Request) -> SimpleNamespace:
            kop = request.headers.get("x-testgebruiker", "1:1")
            klant, gebruiker = kop.split(":")
            return SimpleNamespace(id=int(gebruiker), tenant_id=int(klant))

        app.dependency_overrides[get_current_user_dependency] = _wie
        return TestClient(app)

    def _vraag(self, client: object, kop: str) -> int:
        with patch("src.core.als.agents.workflow_stap.uitvoerbare_agents_voor_klant", _lijst()):
            return client.get(  # type: ignore[attr-defined]
                "/api/v1/vibe/agents/uitvoerbaar", headers={"x-testgebruiker": kop}
            ).status_code

    def test_de_eenenzestigste_aanroep_van_een_medewerker_geeft_429(self) -> None:
        client = self._client()
        for _ in range(60):
            self._vraag(client, "1:7")

        assert self._vraag(client, "1:7") == 429

    def test_een_andere_medewerker_van_hetzelfde_bedrijf_blijft_bediend(self) -> None:
        client = self._client()
        for _ in range(61):
            self._vraag(client, "1:7")

        assert self._vraag(client, "1:8") == 200

    def test_een_medewerker_van_een_ander_bedrijf_blijft_bediend(self) -> None:
        client = self._client()
        for _ in range(61):
            self._vraag(client, "1:7")

        assert self._vraag(client, "2:7") == 200
