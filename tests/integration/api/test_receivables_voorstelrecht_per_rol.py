"""Meting: `POST /api/v1/receivables/reminder-proposals` vraagt `receivables:propose` (wfb-dag1 stap 7).

Hetzelfde recht als de agent-tool `send_payment_reminder` (`receivables_propose`, commit
788612d0). Hier stond `receivables:write`: breder, want daarmee kun je ook een factuur op
`betaald` zetten. Opstelling en fixtures zoals in `test_receivables_schrijfrecht_per_rol.py`
(echte app-stack, echte Postgres, echte rolcontrole; alleen CSRF en `get_current_user` zijn
vervangen).

Per rol: `user` krijgt 403 met precies het gevraagde recht in de melding, `debiteuren` en de
beheerder (`*:*`) komen voorbij de rolcontrole. De tegenproef bij de beheerder sluit uit dat
"alles weigeren" de test haalt.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.api.test_receivables_schrijfrecht_per_rol import (  # noqa: F401 - fixtures
    beheerder,
    debiteuren,
    medewerker,
)

URL = "/api/v1/receivables/reminder-proposals"
SOORTEN: list[dict[str, Any]] = [
    {"receivable_ids": [1], "kind": "herinnering"},
    {"receivable_ids": [1], "kind": "aanmaning"},
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("body", SOORTEN)
async def test_de_gewone_gebruiker_mist_het_voorstelrecht(
    medewerker: AsyncClient,  # noqa: F811
    body: dict[str, Any],
) -> None:
    antwoord = await medewerker.post(URL, json=body)

    assert antwoord.status_code == 403, antwoord.text
    assert antwoord.json().get("detail") == (
        "U mag geen herinneringen of aanmaningen voorstellen. Vraag de beheerder om u de rol "
        "'debiteuren' te geven."
    ), antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("body", SOORTEN)
async def test_de_debiteurenrol_komt_voorbij_de_rolcontrole(
    debiteuren: AsyncClient,  # noqa: F811
    body: dict[str, Any],
) -> None:
    antwoord = await debiteuren.post(URL, json=body)

    assert antwoord.status_code != 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("body", SOORTEN)
async def test_de_beheerder_komt_voorbij_de_rolcontrole(
    beheerder: AsyncClient,  # noqa: F811
    body: dict[str, Any],
) -> None:
    antwoord = await beheerder.post(URL, json=body)

    assert antwoord.status_code != 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_me_geeft_de_debiteurenrol_het_voorstelrecht(
    debiteuren: AsyncClient,  # noqa: F811
) -> None:
    antwoord = await debiteuren.get("/api/v1/auth/me")

    assert "receivables:propose" in antwoord.json()["permissions"], antwoord.text
