"""Eigen validatieteksten blijven zichtbaar op de pilotschermen; vreemde teksten niet.

Brief 2026-10-22 (validatieteksten op pilotschermen). BE-API-046 maakte van elke 4xx op een
`ValueError` een vaste tekst, ook waar de repository bewust een Nederlandse reden gaf. Hier staan
beide kanten: een eigen `ValidatieFout` geeft zijn tekst door, elke andere `ValueError` geeft de
vaste tekst.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.exceptions import ValidatieFout

INTERN = "db-intern.example:5432"


def _patch_endpoint() -> Any:
    from src.core.api.v1.receivables.router import router

    for route in router.routes:
        if getattr(route, "path", "").endswith("/{receivable_id}") and "PATCH" in getattr(
            route, "methods", set()
        ):
            return inspect.unwrap(getattr(route, "endpoint"))
    raise AssertionError("geen PATCH-route op een debiteur")


async def _patch_met_fout(fout: Exception) -> HTTPException:
    from src.core.api.v1.receivables.schemas import ReceivableUpdate

    repo = MagicMock()
    repo.get = AsyncMock(return_value=SimpleNamespace(status="herinnerd"))
    repo.update = AsyncMock(side_effect=fout)
    with pytest.raises(HTTPException) as uitkomst:
        await _patch_endpoint()(
            request=MagicMock(),
            receivable_id=1,
            body=ReceivableUpdate(status="open"),
            repo=repo,
            current_user=SimpleNamespace(id=1, tenant_id=1),
            user_id=1,
            _csrf=None,
        )
    return uitkomst.value


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_niet_toegestane_statusovergang_geeft_de_nederlandse_reden() -> None:
    from src.core.repositories.receivable_repository import _controleer_overgang

    with pytest.raises(ValidatieFout) as echt:
        _controleer_overgang("herinnerd", "open", None)

    fout = await _patch_met_fout(echt.value)

    assert fout.status_code == 409 and fout.detail == str(echt.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_de_repositoryteksten_zijn_deze_nederlandse_zinnen() -> None:
    from decimal import Decimal

    from src.core.repositories.receivable_repository import (
        _controleer_bedrag,
        _controleer_overgang,
        _controleer_valuta,
    )

    teksten: list[str] = []
    for aanroep in (
        lambda: _controleer_bedrag(Decimal("-1")),
        lambda: _controleer_valuta("eur"),
        lambda: _controleer_overgang("betaald", "open", None),
    ):
        with pytest.raises(ValidatieFout) as fout:
            aanroep()
        teksten.append(str(fout.value))

    assert teksten == [
        "Het bedrag mag niet negatief zijn.",
        "De valuta moet uit drie hoofdletters bestaan, bijvoorbeeld EUR.",
        "Een betaalde factuur terugzetten vraagt een reden.",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_vreemde_valueerror_op_een_debiteur_geeft_de_vaste_tekst() -> None:
    fout = await _patch_met_fout(ValueError(f"bad connection {INTERN}"))

    assert fout.status_code == 409 and INTERN not in str(fout.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_verbinding_met_een_eigen_validatietekst_geeft_die_tekst() -> None:
    from src.core.activepieces.schemas import ConnectionCreate
    from src.core.api.v1.activepieces.connections_router import router

    maak = None
    for route in router.routes:
        if getattr(route, "path", "").endswith("/connections") and "POST" in getattr(
            route, "methods", set()
        ):
            maak = inspect.unwrap(getattr(route, "endpoint"))
    assert maak is not None
    dienst = MagicMock()
    dienst.create_connection = AsyncMock(side_effect=ValidatieFout("Naam ontbreekt."))
    verzoek = ConnectionCreate(name="n", app_name="slack", project_id=None, value={"token": "x"})

    with pytest.raises(HTTPException) as fout:
        await maak(
            request=verzoek,
            http_request=MagicMock(),
            service=dienst,
            _current_user=SimpleNamespace(id=1),
            audit=MagicMock(),
        )

    assert fout.value.status_code == 400 and fout.value.detail == "Naam ontbreekt."


@pytest.mark.unit
def test_de_gegevens_van_een_ap_verbinding_zijn_een_eigen_validatiefout() -> None:
    from src.core.activepieces.verbinding_beheer import OngeldigApAdres, OngeldigeApGegevens

    assert issubclass(OngeldigeApGegevens, ValidatieFout) and issubclass(
        OngeldigApAdres, OngeldigeApGegevens
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_geweigerd_providers_adres_geeft_een_vaste_tekst_zonder_de_ssrf_reden() -> None:
    from src.core.services.tenant_llm_provider_service import TenantLLMProviderService

    repo = MagicMock()
    repo.mag_extern = AsyncMock(return_value=True)
    protector = MagicMock()
    protector.validate_url = MagicMock(side_effect=Exception(f"resolves to 10.1.2.3 {INTERN}"))
    dienst = TenantLLMProviderService(repo, MagicMock(), protector)

    with pytest.raises(ValidatieFout) as fout:
        await dienst.configureer(
            1, volgorde=1, naam="x", base_url="https://x.example", model="m", api_key=None
        )

    assert INTERN not in str(fout.value) and "10.1.2.3" not in str(fout.value)


async def _leg_ap_verbinding_vast(fout: Exception) -> HTTPException:
    from unittest.mock import patch

    from src.core.api.v1.admin import ap_verbinding_router as module

    beheer = MagicMock()
    beheer.leg_vast = AsyncMock(side_effect=fout)
    verzoek = SimpleNamespace(
        base_url="https://ap.example", email="a@b.nl", wachtwoord="w", project_id="p"
    )
    db = MagicMock()
    db.flush = AsyncMock()
    with (
        patch.object(module, "bouw_ap_verbinding_beheer", return_value=beheer),
        patch.object(module, "schrijf_ap_verbinding_audit", new=AsyncMock()),
        pytest.raises(HTTPException) as uitkomst,
    ):
        await inspect.unwrap(module.leg_ap_verbinding_vast)(
            tenant_id=1,
            payload=verzoek,
            request=SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
            beheerder=SimpleNamespace(id=1),
            db=db,
        )
    return uitkomst.value


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_ongeldig_ap_adres_geeft_de_eigen_tekst_aan_de_beheerder() -> None:
    from src.core.activepieces.verbinding_beheer import OngeldigApAdres

    fout = await _leg_ap_verbinding_vast(OngeldigApAdres("Het adres moet beginnen met https://."))

    assert fout.status_code == 400 and fout.detail == "Het adres moet beginnen met https://."
