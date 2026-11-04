"""HR-pilot dag 4: elke dag een melding aan HR als een termijn nadert (ADR-039: alleen signaleren).

Echte Postgres op netwerkpoort 5455, de echte rolzaaier en de echte rechtencontrole; de actor
draait via zijn async-kern met de testsessie als sessiefabriek (de tenantcontext zet de actor zelf,
met `adopt_tenant`). Wat dit vaststelt:

1. Een termijn binnen 14 dagen (of al te laat) geeft EEN melding per gebruiker met `hr:read` in die
   tenant; een gewone gebruiker krijgt er geen.
2. De taak twee keer op dezelfde dag geeft nog steeds een melding per termijn en gebruiker.
3. Buiten het venster (15 dagen of verder) en een afgeronde termijn geven niets.
4. Tenant B krijgt niets over tenant A.
5. De melding noemt soort, datum en initialen van de medewerker, NOOIT een omschrijving of het
   e-mailadres, en wijst naar /personeel.
6. De taak verandert niets aan de termijnrijen.
7. De melding staat in de bestaande meldingenlijst van de app (`GET /api/v1/notifications`).

Wat NIET gemeten is: een draaiende worker en planner met scherm.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, User, user_roles
from src.core.services.rbac_service import RBACService

TENANT = 1
ANDERE_TENANT = 2
MEDEWERKER = "anna.jansen-d4@integration.test"
OMSCHRIJVING = "VCA-geheime-omschrijving"


def _dag(delta: int) -> date:
    return date.today() + timedelta(days=delta)


async def _gebruiker(session: AsyncSession, email: str, rol: str, tenant: int = TENANT) -> int:
    gebruiker = User(
        email=email, hashed_password="x", tenant_id=tenant, is_active=True, is_superuser=False
    )
    session.add(gebruiker)
    await session.flush()
    rol_rij = (
        await session.execute(select(Role).where(Role.name == rol, Role.tenant_id == tenant))
    ).scalar_one()
    await session.execute(
        user_roles.insert().values(user_id=gebruiker.id, role_id=rol_rij.id, tenant_id=tenant)
    )
    await session.commit()
    return int(gebruiker.id)


@pytest_asyncio.fixture
async def wereld(postgres_session: AsyncSession) -> dict[str, int]:
    """Gebruikers per rol in tenant 1 (en een HR-medewerker in tenant 2) plus de medewerker."""
    sessie = postgres_session
    await RBACService(sessie).ensure_default_roles(TENANT)
    await RBACService(sessie).ensure_default_roles(ANDERE_TENANT)
    return {
        "medewerker": await _gebruiker(sessie, MEDEWERKER, "user"),
        "hr": await _gebruiker(sessie, "hr-d4@integration.test", "hr_medewerker"),
        "goedkeurder": await _gebruiker(sessie, "gk-d4@integration.test", "goedkeurder_hr"),
        "beheerder": await _gebruiker(sessie, "adm-d4@integration.test", "admin"),
        "gewoon": await _gebruiker(sessie, "usr-d4@integration.test", "user"),
        "hr_b": await _gebruiker(
            sessie, "hr-b-d4@integration.test", "hr_medewerker", tenant=ANDERE_TENANT
        ),
        "medewerker_b": await _gebruiker(
            sessie, "piet.bakker-d4@integration.test", "user", tenant=ANDERE_TENANT
        ),
    }


async def _termijn(
    sessie: AsyncSession,
    user_id: int,
    *,
    kind: str = "certificaat",
    einde_over: int | None = 40,
    start_over: int | None = None,
    omschrijving: str | None = OMSCHRIJVING,
    status: str = "open",
    tenant: int = TENANT,
) -> int:
    rij = (
        await sessie.execute(
            text(
                "INSERT INTO hr_deadlines (tenant_id, user_id, kind, start_date, end_date, "
                "description, status) VALUES (:t, :u, :k, :s, :e, :d, :st) RETURNING id"
            ),
            {
                "t": tenant,
                "u": user_id,
                "k": kind,
                "s": _dag(start_over) if start_over is not None else None,
                "e": _dag(einde_over) if einde_over is not None else None,
                "d": omschrijving if kind != "verzuim" else None,
                "st": status,
            },
        )
    ).scalar_one()
    await sessie.commit()
    return int(rij)


async def _draai(sessie: AsyncSession, nu: datetime | None = None) -> None:
    from src.core.tasks.hr_termijn_tasks import signaleer_hr_termijnen_async

    @asynccontextmanager
    async def _fabriek() -> AsyncGenerator[AsyncSession, None]:
        yield sessie

    await signaleer_hr_termijnen_async(sessie_fabriek=_fabriek, nu=nu or datetime.now(timezone.utc))


async def _meldingen(sessie: AsyncSession, user_id: int) -> list[Any]:
    rijen = await sessie.execute(
        text(
            "SELECT title, body, data FROM notifications "
            "WHERE user_id = :u AND type = 'hr_termijn' ORDER BY id"
        ),
        {"u": user_id},
    )
    return list(rijen.all())


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieKrijgtEenMelding:
    async def test_elke_gebruiker_met_hr_read_krijgt_een_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(
            postgres_session, wereld["medewerker"], einde_over=40
        )  # signaal over 10 dagen

        await _draai(postgres_session)

        aantallen = {
            naam: len(await _meldingen(postgres_session, wereld[naam]))
            for naam in ("hr", "goedkeurder", "beheerder")
        }
        assert aantallen == {"hr": 1, "goedkeurder": 1, "beheerder": 1}

    async def test_een_gewone_gebruiker_krijgt_geen_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["gewoon"]) == []

    async def test_een_hr_medewerker_krijgt_geen_melding_over_zijn_eigen_termijn(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["hr"], einde_over=40)

        await _draai(postgres_session)

        aantallen = {
            naam: len(await _meldingen(postgres_session, wereld[naam]))
            for naam in ("hr", "goedkeurder")
        }
        assert aantallen == {"hr": 0, "goedkeurder": 1}

    async def test_de_betrokken_medewerker_zelf_krijgt_geen_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["medewerker"]) == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetVenster:
    async def test_een_termijn_over_veertien_dagen_geeft_een_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=44)

        await _draai(postgres_session)

        assert len(await _meldingen(postgres_session, wereld["hr"])) == 1

    async def test_een_termijn_over_vijftien_dagen_geeft_geen_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=45)

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["hr"]) == []

    async def test_een_termijn_over_dertig_dagen_geeft_geen_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=60)

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["hr"]) == []

    async def test_een_afgeronde_termijn_geeft_geen_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40, status="afgerond")

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["hr"]) == []

    async def test_een_termijn_die_al_voorbij_is_geeft_een_melding_met_te_laat(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=10)  # 20 dagen geleden

        await _draai(postgres_session)

        (titel, _, data) = (await _meldingen(postgres_session, wereld["hr"]))[0]
        assert ("te laat" in titel.lower(), data["te_laat"]) == (True, True)


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenmaligPerDag:
    async def test_twee_keer_dezelfde_dag_geeft_een_melding_per_termijn(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)
        await _draai(postgres_session)

        assert len(await _meldingen(postgres_session, wereld["hr"])) == 1

    async def test_de_volgende_dag_komt_er_weer_een_melding(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)
        nu = datetime.now(timezone.utc)

        await _draai(postgres_session, nu)
        await _draai(postgres_session, nu + timedelta(days=1))

        assert len(await _meldingen(postgres_session, wereld["hr"])) == 2

    async def test_twee_termijnen_geven_twee_meldingen(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)
        await _termijn(postgres_session, wereld["medewerker"], einde_over=42)

        await _draai(postgres_session)

        assert len(await _meldingen(postgres_session, wereld["hr"])) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestInhoudVanDeMelding:
    async def test_de_melding_noemt_geen_omschrijving_en_geen_e_mailadres(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)

        (titel, tekst, data) = (await _meldingen(postgres_session, wereld["hr"]))[0]
        alles = f"{titel} {tekst} {data}"
        assert OMSCHRIJVING not in alles and MEDEWERKER not in alles

    async def test_de_melding_noemt_soort_datum_en_initialen(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)

        (titel, tekst, _) = (await _meldingen(postgres_session, wereld["hr"]))[0]
        assert "Certificaat verlengen" in titel
        assert _dag(10).strftime("%d-%m-%Y") in tekst
        assert "A.J." in tekst

    async def test_een_verzuimmelding_heeft_geen_omschrijving(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(
            postgres_session,
            wereld["medewerker"],
            kind="verzuim",
            einde_over=None,
            start_over=-30,
        )

        await _draai(postgres_session)

        (titel, tekst, data) = (await _meldingen(postgres_session, wereld["hr"]))[0]
        assert "Probleemanalyse" in titel
        assert "description" not in data and "omschrijving" not in tekst.lower()

    async def test_de_melding_wijst_naar_de_pagina_personeel(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)

        (_, _, data) = (await _meldingen(postgres_session, wereld["hr"]))[0]
        assert data["link"] == "/personeel"


@pytest.mark.integration
@pytest.mark.asyncio
class TestAlleenSignaleren:
    async def test_de_termijnrij_is_na_de_taak_ongewijzigd(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)
        await _termijn(
            postgres_session, wereld["medewerker"], kind="verzuim", einde_over=None, start_over=-30
        )
        vraag = text("SELECT * FROM hr_deadlines ORDER BY id")
        voor = [tuple(r) for r in (await postgres_session.execute(vraag)).all()]

        await _draai(postgres_session)

        na = [tuple(r) for r in (await postgres_session.execute(vraag)).all()]
        assert na == voor


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def test_tenant_b_krijgt_geen_melding_over_tenant_a(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["hr_b"]) == []

    async def test_tenant_a_krijgt_geen_melding_over_tenant_b(
        self, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        await _termijn(
            postgres_session, wereld["medewerker_b"], einde_over=40, tenant=ANDERE_TENANT
        )

        await _draai(postgres_session)

        assert await _meldingen(postgres_session, wereld["hr"]) == []
        assert len(await _meldingen(postgres_session, wereld["hr_b"])) == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestZichtbaarInDeApp:
    async def test_de_melding_staat_in_de_bestaande_meldingenlijst(
        self, integration_app: Any, postgres_session: AsyncSession, wereld: dict[str, int]
    ) -> None:
        from tests.integration.conftest import _build_test_token

        from src.core.api.dependencies import get_db as api_get_db
        from src.core.auth.auth_service import UserResponse
        from src.core.auth.dependencies import get_current_user
        from src.core.database.database import get_db

        await _termijn(postgres_session, wereld["medewerker"], einde_over=40)
        await _draai(postgres_session)

        async def _db() -> AsyncGenerator[AsyncSession, None]:
            yield postgres_session

        gebruiker = UserResponse(
            id=wereld["hr"], email="hr-d4@integration.test", tenant_id=TENANT, roles=["user"]
        )
        overrides: dict[Any, Any] = {
            get_db: _db,
            api_get_db: _db,
            get_current_user: lambda: gebruiker,
        }
        integration_app.dependency_overrides.update(overrides)
        token = _build_test_token(
            user_id=wereld["hr"], email="hr-d4@integration.test", tenant_id=TENANT
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=integration_app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {token}"},
            ) as client:
                antwoord = await client.get("/api/v1/notifications")
        finally:
            for dep in overrides:
                integration_app.dependency_overrides.pop(dep, None)

        assert antwoord.status_code == 200, antwoord.text
        assert [n["type"] for n in antwoord.json()["data"]] == ["hr_termijn"]
