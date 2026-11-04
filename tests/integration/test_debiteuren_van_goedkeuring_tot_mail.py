"""Debiteuren van goedkeuring tot mail (2026-10-22): een duidelijke melding bij een ongeldig e-mailadres.

Echte app-stack, echte Postgres op netwerkpoort 5455. Alleen CSRF is vervangen (Redis-gebonden; de controle zelf heeft
eigen tests).

Aanleiding (acceptatie 2026-10-22): een debiteur toevoegen met een e-mailadres op `.test` gaf 422 en het scherm zei alleen
"Toevoegen is niet gelukt. Controleer de velden." De backend gaf de Engelse tekst van de bibliotheek ("value is not a valid
email address: The part after the @-sign is a special-use or reserved name ..."). Nu geeft de backend per fout het veld, een
eigen soort (`ongeldig_email`) en een Nederlandse tekst die zegt waarom; het scherm maakt er een zin van.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

LIJST = "/api/v1/receivables"


def _zet_overrides(app: Any, session: AsyncSession) -> dict[Any, Any]:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _geen_csrf() -> None:
        return None

    overrides: dict[Any, Any] = {get_db: _db, api_get_db: _db, validate_csrf_token: _geen_csrf}
    app.dependency_overrides.update(overrides)
    return overrides


@pytest_asyncio.fixture
async def api(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """De gezaaide beheerder (gebruiker 1, tenant 1)."""
    from tests.integration.conftest import _build_test_token

    overrides = _zet_overrides(integration_app, postgres_session)
    token = _build_test_token(user_id=1, email="admin@integration.test", tenant_id=1)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


def _vordering(email: str) -> dict[str, str]:
    return {
        "customer_name": "Testklant BV",
        "customer_email": email,
        "invoice_number": f"MAIL-{uuid.uuid4().hex[:10]}",
        "amount": "10.00",
        "currency": "EUR",
        "due_date": "2026-11-01",
    }


def _email_fout(antwoord: Any) -> dict[str, Any]:
    """De fout die bij het veld `customer_email` hoort (FastAPI geeft een lijst met `loc`, `msg` en `type`)."""
    fouten = [f for f in antwoord.json()["detail"] if f["loc"][-1] == "customer_email"]
    assert fouten, f"geen fout bij customer_email: {antwoord.json()}"
    return fouten[0]


class TestOngeldigEmailadres:
    async def test_een_gereserveerd_domein_geeft_422(self, api: AsyncClient) -> None:
        antwoord = await api.post(LIJST, json=_vordering("klant@bedrijf.test"))

        assert antwoord.status_code == 422

    async def test_de_fout_heeft_de_eigen_soort(self, api: AsyncClient) -> None:
        antwoord = await api.post(LIJST, json=_vordering("klant@bedrijf.test"))

        assert _email_fout(antwoord)["type"] == "ongeldig_email"

    async def test_de_tekst_is_nederlands_en_noemt_het_e_mailadres(self, api: AsyncClient) -> None:
        antwoord = await api.post(LIJST, json=_vordering("klant@bedrijf.test"))

        assert "e-mailadres" in _email_fout(antwoord)["msg"].lower()

    async def test_de_tekst_zegt_waarom_een_gereserveerd_domein_niet_kan(
        self, api: AsyncClient
    ) -> None:
        antwoord = await api.post(LIJST, json=_vordering("klant@bedrijf.test"))

        assert "gereserveerd" in _email_fout(antwoord)["msg"].lower()

    async def test_de_engelse_tekst_van_de_bibliotheek_komt_er_niet_in(
        self, api: AsyncClient
    ) -> None:
        antwoord = await api.post(LIJST, json=_vordering("klant@bedrijf.test"))

        assert "special-use" not in antwoord.text

    async def test_een_adres_zonder_apenstaart_krijgt_dezelfde_soort(
        self, api: AsyncClient
    ) -> None:
        antwoord = await api.post(LIJST, json=_vordering("geen-apenstaart"))

        assert _email_fout(antwoord)["type"] == "ongeldig_email"

    async def test_een_adres_zonder_apenstaart_krijgt_een_nederlandse_tekst(
        self, api: AsyncClient
    ) -> None:
        antwoord = await api.post(LIJST, json=_vordering("geen-apenstaart"))

        assert "e-mailadres" in _email_fout(antwoord)["msg"].lower()


class TestGeldigEmailadres:
    async def test_een_gewoon_adres_wordt_gewoon_toegevoegd(self, api: AsyncClient) -> None:
        antwoord = await api.post(LIJST, json=_vordering("klant@bedrijf.nl"))

        assert antwoord.status_code == 201

    async def test_het_adres_wordt_genormaliseerd_zoals_voorheen(self, api: AsyncClient) -> None:
        antwoord = await api.post(LIJST, json=_vordering("Klant@Bedrijf.NL"))

        assert antwoord.json()["data"]["customer_email"] == "Klant@bedrijf.nl"


class TestSchemaContract:
    """Het schema blijft zeggen dat het veld een e-mailadres is, en de lengtegrens blijft gelden.

    Zonder deze toets verdween `format: email` uit het OpenAPI-schema toen `EmailStr` door een eigen controle werd vervangen
    (security-review 2026-10-22, LOW).
    """

    def test_het_openapi_schema_noemt_het_veld_een_e_mailadres(self) -> None:
        from src.core.api.v1.receivables.schemas import ReceivableCreate

        veld = ReceivableCreate.model_json_schema()["properties"]["customer_email"]

        assert veld.get("format") == "email"

    def test_het_openapi_schema_noemt_het_veld_ook_bij_een_wijziging_een_e_mailadres(self) -> None:
        from src.core.api.v1.receivables.schemas import ReceivableUpdate

        veld = ReceivableUpdate.model_json_schema()["properties"]["customer_email"]

        assert any(optie.get("format") == "email" for optie in veld["anyOf"])

    def test_het_openapi_schema_houdt_de_lengtegrens(self) -> None:
        from src.core.api.v1.receivables.schemas import ReceivableCreate

        veld = ReceivableCreate.model_json_schema()["properties"]["customer_email"]

        assert veld.get("maxLength") == 320

    def test_een_adres_van_321_tekens_geeft_een_te_lang_fout_en_geen_500(self) -> None:
        import pytest
        from pydantic import ValidationError

        from src.core.api.v1.receivables.schemas import ReceivableCreate

        invoer = _vordering("a" * 316 + "@x.nl")
        with pytest.raises(ValidationError) as fout:
            ReceivableCreate.model_validate(invoer)

        assert [f["type"] for f in fout.value.errors() if f["loc"] == ("customer_email",)] == ["string_too_long"]
