"""Meting: flows maken, wijzigen, publiceren, aanzetten en uitvoeren vraagt `workflows:publish` (wfb-dag1 stap 1).

Echte app-stack, echte Postgres, echte rolcontrole (`require_resource_permission`). Fixtures uit
test_receivables_schrijfrecht_per_rol.py: `medewerker` heeft precies de rol `user` (`*:read`),
`beheerder` de rol `admin` (`*:*`). Alleen CSRF en `get_current_user` zijn vervangen.

De gewone gebruiker krijgt op ELKE schrijvende flowroute 403 met precies dit recht in de
melding; de beheerder komt op dezelfde routes voorbij de rolcontrole (tegenproef: anders is
"alles weigeren" een geldige uitkomst). Wat de beheerder daarna krijgt (ActivePieces draait hier
niet) wordt niet gemeten -- alleen dat het geen 403 is.

De route `/api/v1/workflows/ap/{id}/execute` (tenant uit de query, gaf altijd 501) bestaat niet
meer.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.api.test_receivables_schrijfrecht_per_rol import (  # noqa: F401 - fixtures
    beheerder,
    medewerker,
)

GRAAF: dict[str, Any] = {
    "nodes": [
        {
            "id": "s1",
            "type": "action",
            "position": {"x": 0, "y": 0},
            "data": {"name": "data_transformer"},
        },
    ],
    "edges": [],
}

ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    (
        "POST",
        "/api/v1/integrations/flows",
        {"name": "x", "project_id": "p", "react_flow_data": GRAAF},
    ),
    ("PUT", "/api/v1/integrations/flows/f1", {"name": "y"}),
    ("DELETE", "/api/v1/integrations/flows/f1", None),
    ("POST", "/api/v1/integrations/flows/f1/toggle", None),
    ("POST", "/api/v1/integrations/flows/f1/execute", {"payload": {}}),
    ("POST", "/api/v1/integrations/flows/f1/runs/r1/retry", None),
    ("POST", "/api/v1/integrations/flows/f1/runs/r1/cancel", None),
    ("POST", "/api/v1/focus-builder/flows", {"name": "x", "react_flow_graph": GRAAF}),
    ("PUT", "/api/v1/focus-builder/flows/1", {"is_published": True}),
    ("DELETE", "/api/v1/focus-builder/flows/1", None),
    ("POST", "/api/v1/focus-builder/flows/1/execute", {}),
    ("POST", "/api/v1/workflows/execute", {"name": "x", "nodes": [{"id": "s1"}], "edges": []}),
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(("methode", "pad", "body"), ROUTES)
async def test_de_gewone_gebruiker_mist_het_publicatierecht(
    medewerker: AsyncClient,  # noqa: F811
    methode: str,
    pad: str,
    body: dict[str, Any] | None,
) -> None:
    antwoord = await medewerker.request(methode, pad, json=body)

    assert antwoord.status_code == 403, antwoord.text
    assert antwoord.json().get("detail") == "Missing permission: workflows:publish", antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(("methode", "pad", "body"), ROUTES)
async def test_de_beheerder_komt_voorbij_de_rolcontrole(
    beheerder: AsyncClient,  # noqa: F811
    methode: str,
    pad: str,
    body: dict[str, Any] | None,
) -> None:
    """Geen 403 VAN DE ROLCONTROLE. Een latere 403 mag: focus-builder-execute vraagt daarna nog
    de Council, en die blokkeert zonder agents (`FLOW_BLOCKED_BY_COUNCIL`)."""
    antwoord = await beheerder.request(methode, pad, json=body)

    assert "Missing permission" not in antwoord.text, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lezen_blijft_open_voor_de_gewone_gebruiker(
    medewerker: AsyncClient,  # noqa: F811
) -> None:
    """Andere kant op: alleen schrijven vraagt het recht; de lijst lezen niet."""
    antwoord = await medewerker.get("/api/v1/focus-builder/flows")

    assert antwoord.status_code != 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_de_route_met_de_tenant_uit_de_query_bestaat_niet_meer(
    beheerder: AsyncClient,  # noqa: F811
) -> None:
    antwoord = await beheerder.post("/api/v1/workflows/ap/1/execute?tenant_id=2")

    assert antwoord.status_code in (404, 405), antwoord.text
