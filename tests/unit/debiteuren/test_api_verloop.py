"""Het verloop van een debiteur in de API -- Keten B dag 3.

Het echte route-pad (`GET`, `PATCH /api/v1/receivables`) tegen een echte SQLite-sessie, in
dezelfde opstelling als `test_logboek_bij_wijzigen.py` (vervangen: de ingelogde gebruiker, de
rechtencontrole, CSRF en de databasesessie; niets aan repository, router of schema).

Wat hier gemeten wordt:
1. `GET` levert `herinnerd_op`, `betaald_op` en de status `geescaleerd` (de pagina heeft ze nodig).
2. Een handmatige `PATCH open -> herinnerd` zet `herinnerd_op` (dag-1-bevinding: alleen het
   toolpad deed dat; de opvolging escaleert op die datum).
3. `PATCH -> betaald` zet `betaald_op`, en `herinnerd -> geescaleerd` door een gebruiker kan niet
   (dat zet alleen de opvolgactor; het schema laat die waarde niet toe).
4. Dag-1-bevinding "valuta of bedrag blijft 422": een ongeldige valuta of een negatief bedrag
   geeft nog steeds 422 en NIET de 409 van een ongeldige statusovergang.

**Wat de opstelling uitzet, nagelopen.** `_reset_global_state` (tenantfilter bewaren/herstellen),
`enforce_testing_env` (TESTING=1; `_resolve_tenant_id` leest dan de gebruiker). Geen conftest in
`tests/unit/debiteuren/`. Geen patch op repository of auditdienst.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.models.rbac_models import Tenant
from src.core.models.receivable_models import Receivable

URL = "/api/v1/receivables"
GEBRUIKER_ID = 7
TENANT_ID = 1


def _alle_dependencies(route: APIRoute) -> list[object]:
    gezien: list[object] = []

    def loop(dependant: object) -> None:
        for sub in dependant.dependencies:  # type: ignore[attr-defined]
            if sub.call is not None:
                gezien.append(sub.call)
            loop(sub)

    loop(route.dependant)
    return gezien


@pytest_asyncio.fixture
async def api(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.receivables.dependencies import (
        ReceivableRepository,
        get_current_user,
        get_receivable_repository,
    )
    from src.core.api.v1.receivables.router import router
    from src.core.database.database import get_db

    db_session.add(Tenant(id=TENANT_ID, name="T1", slug="deb-verloop-1"))
    await db_session.commit()

    app = FastAPI()
    app.include_router(router)

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _geen_csrf() -> None:
        return None

    async def _gebruiker() -> SimpleNamespace:
        return SimpleNamespace(
            id=GEBRUIKER_ID, tenant_id=TENANT_ID, email="admin@test.example", roles=["admin"]
        )

    async def _recht() -> int:
        return GEBRUIKER_ID

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_receivable_repository] = lambda: ReceivableRepository(db_session)
    app.dependency_overrides[get_current_user] = _gebruiker
    app.dependency_overrides[validate_csrf_token] = _geen_csrf
    for route in router.routes:
        if isinstance(route, APIRoute):
            for call in _alle_dependencies(route):
                if getattr(call, "__name__", "") == "permission_checker":
                    app.dependency_overrides[call] = _recht  # type: ignore[index]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _zet_factuur(
    sessie: AsyncSession,
    status: str = "open",
    *,
    herinnerd_op: datetime | None = None,
    betaald_op: datetime | None = None,
) -> int:
    rij = Receivable(
        tenant_id=TENANT_ID,
        customer_name="Bakkerij De Korst",
        customer_email="administratie@dekorst.example",
        invoice_number="F-1",
        amount=Decimal("100.00"),
        currency="EUR",
        due_date=date(2026, 9, 1),
        status=status,
        source="handmatig",
        herinnerd_op=herinnerd_op,
        betaald_op=betaald_op,
    )
    sessie.add(rij)
    await sessie.commit()
    return rij.id


def _moment(tekst: object) -> datetime:
    """Een ISO-tijdstempel uit het antwoord, zonder tijdzone gelezen als UTC (SQLite)."""
    assert isinstance(tekst, str), f"verwacht een tijdstempel, kreeg {tekst!r}"
    moment = datetime.fromisoformat(tekst.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeLijstLevertHetVerloop:
    async def test_de_lijst_levert_herinnerd_op(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        gezet = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        await _zet_factuur(db_session, "herinnerd", herinnerd_op=gezet)

        antwoord = await api.get(URL)

        rij = antwoord.json()["data"][0]
        assert "herinnerd_op" in rij, f"sleutels in het antwoord: {sorted(rij)}"
        assert _moment(rij["herinnerd_op"]) == gezet

    async def test_de_lijst_levert_betaald_op(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        gezet = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        await _zet_factuur(db_session, "betaald", betaald_op=gezet)

        antwoord = await api.get(URL)

        rij = antwoord.json()["data"][0]
        assert "betaald_op" in rij, f"sleutels in het antwoord: {sorted(rij)}"
        assert _moment(rij["betaald_op"]) == gezet

    async def test_de_lijst_toont_de_status_geescaleerd(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _zet_factuur(
            db_session, "geescaleerd", herinnerd_op=datetime(2026, 9, 1, tzinfo=timezone.utc)
        )

        antwoord = await api.get(URL)

        assert antwoord.json()["data"][0]["status"] == "geescaleerd"

    async def test_een_open_factuur_heeft_lege_datums_en_geen_fout(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Andere kant op: zonder datum komt `null`, niet een ontbrekend veld of een 500."""
        await _zet_factuur(db_session, "open")

        antwoord = await api.get(URL)

        rij = antwoord.json()["data"][0]
        assert (
            antwoord.status_code,
            rij.get("herinnerd_op", "ONTBREEKT"),
            rij.get("betaald_op", "ONTBREEKT"),
        ) == (
            200,
            None,
            None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestHandmatigHerinnerdBestaatNietMeer:
    """wfb-dag1 stap 2: `herinnerd` zet alleen de verzendlus. Hier stond dat een handmatige PATCH
    de datum zette; die PATCH geeft nu 422 (test_herinnerd_is_een_feit.py) en raakt niets."""

    async def test_een_geweigerde_patch_naar_herinnerd_laat_de_database_ongemoeid(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        rid = await _zet_factuur(db_session, "open")

        await api.patch(f"{URL}/{rid}", json={"status": "herinnerd"})

        db_session.expire_all()
        rij = await db_session.get(Receivable, rid)
        assert rij is not None and (rij.status, rij.herinnerd_op) == ("open", None)

    async def test_een_wijziging_zonder_statuswissel_laat_de_herinnerdatum_staan(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Andere kant op: een naamswijziging op een herinnerd dossier herstart de termijn niet."""
        oud = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        rid = await _zet_factuur(db_session, "herinnerd", herinnerd_op=oud)

        await api.patch(f"{URL}/{rid}", json={"customer_name": "Nieuwe Naam"})

        db_session.expire_all()
        rij = await db_session.get(Receivable, rid)
        assert rij is not None and rij.herinnerd_op is not None
        assert rij.herinnerd_op.replace(tzinfo=None) == oud.replace(tzinfo=None)

    async def test_betaald_zetten_zet_betaald_op_en_laat_herinnerd_op_staan(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        oud = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        rid = await _zet_factuur(db_session, "herinnerd", herinnerd_op=oud)

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "betaald"})

        data = antwoord.json()["data"]
        assert data.get("betaald_op") is not None and _moment(data.get("herinnerd_op")) == oud


@pytest.mark.unit
@pytest.mark.asyncio
class TestGrenzenVanDeStatusEnDeInvoer:
    async def test_een_gebruiker_kan_niet_zelf_escaleren(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Escaleren is werk van de opvolgactor; het schema laat de waarde niet toe."""
        rid = await _zet_factuur(db_session, "herinnerd", herinnerd_op=datetime.now(timezone.utc))

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "geescaleerd"})

        assert antwoord.status_code == 422, (antwoord.status_code, antwoord.text)

    async def test_een_ongeldige_valuta_blijft_een_422_en_geen_409(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        rid = await _zet_factuur(db_session, "open")

        antwoord = await api.patch(f"{URL}/{rid}", json={"currency": "euro"})

        assert antwoord.status_code == 422, (antwoord.status_code, antwoord.text)

    async def test_een_negatief_bedrag_blijft_een_422_en_geen_409(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        rid = await _zet_factuur(db_session, "open")

        antwoord = await api.patch(f"{URL}/{rid}", json={"amount": "-1.00"})

        assert antwoord.status_code == 422, (antwoord.status_code, antwoord.text)

    async def test_een_ongeldige_statusovergang_blijft_een_409(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Andere kant op: de 409 voor een echte overgangsfout blijft bestaan."""
        rid = await _zet_factuur(db_session, "herinnerd", herinnerd_op=datetime.now(timezone.utc))

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "open"})

        assert antwoord.status_code == 409, (antwoord.status_code, antwoord.text)
