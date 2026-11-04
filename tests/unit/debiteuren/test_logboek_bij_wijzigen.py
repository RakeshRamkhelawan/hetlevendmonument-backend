"""Logboek bij aanmaken en wijzigen van een debiteur -- Keten B dag 1 (besluit 6).

Het echte route-pad (`POST /api/v1/receivables`, `PATCH /api/v1/receivables/{id}`) tegen een
echte SQLite-sessie; de audit-regel wordt teruggelezen uit de tabel `audit_logs`. Niets aan de
auditdienst of de repository is vervangen.

Vervangen zijn alleen de dingen die hier NIET gemeten worden: de ingelogde gebruiker, de
rechtencontrole (RBAC), CSRF en de databasesessie (naar de testsessie). Isolatie van de tenant
komt uit de gebruiker, zoals in productie uit de JWT.

**Wat dit NIET meet.** (1) De hash-keten zelf: `AuditService.log_event` neemt een
advisory lock die alleen PostgreSQL kent; op SQLite degradeert de keten naar een regel zonder
hash (zie `audit_service.py`, `except Exception as hash_exc`). Dat de regel de keten IN gaat,
meet de integratietest tegen Postgres, en die draait hier niet (netwerkpoort 5455 is dicht).
(2) "NA de commit": in dezelfde sessie is een geflushte regel zichtbaar, dus de volgorde is
hier niet te onderscheiden van ervoor. Hier is wel gemeten dat de primaire wijziging blijft
staan en dat er precies een regel bij komt.

AuditService gebruikt `flush()` via `begin_nested()`; daarom wordt er op de rijen in de
sessie getoetst en niet op `commit` van een dubbel.

**Wat de opstelling uitzet, nagelopen.** `_reset_global_state` (autouse, tenantfilter save/
restore), `enforce_testing_env` (TESTING=1; nodig, `_resolve_tenant_id` leest dan de gebruiker).
Geen conftest in `tests/unit/debiteuren/`. Geen patch op de auditdienst.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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

    db_session.add(Tenant(id=TENANT_ID, name="T1", slug="deb-log-1"))
    db_session.add(Tenant(id=2, name="T2", slug="deb-log-2"))
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


async def _zet_factuur(session: AsyncSession, tenant_id: int, status: str = "herinnerd") -> int:
    rij = Receivable(
        tenant_id=tenant_id,
        customer_name="Bakkerij De Korst",
        customer_email="administratie@dekorst.example",
        invoice_number="F-1",
        amount=Decimal("100.00"),
        currency="EUR",
        due_date=date(2026, 9, 1),
        status=status,
        source="handmatig",
    )
    session.add(rij)
    await session.commit()
    return rij.id


async def _regels(session: AsyncSession, tenant_id: int | None = None) -> list[object]:
    from src.core.governance.models import AuditLog

    vraag = select(AuditLog).order_by(AuditLog.id)
    if tenant_id is not None:
        vraag = vraag.where(AuditLog.tenant_id == tenant_id)
    return list((await session.execute(vraag)).scalars().all())


def _tekst(regel: object) -> str:
    """Alles wat een lezer van het logboek ziet, als een doorzoekbare tekst."""
    velden = ("event_type", "action", "resource", "description", "event_metadata", "details")
    return json.dumps({v: getattr(regel, v, None) for v in velden}, default=str).lower()


@pytest.mark.unit
@pytest.mark.asyncio
class TestBetaaldStaatInHetLogboek:
    async def test_betaald_staat_in_het_logboek(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        rid = await _zet_factuur(db_session, TENANT_ID, "herinnerd")
        voor = len(await _regels(db_session, TENANT_ID))

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "betaald"})

        assert antwoord.status_code == 200, antwoord.text
        nieuw = (await _regels(db_session, TENANT_ID))[voor:]
        assert len(nieuw) == 1, f"verwacht precies een logboekregel erbij, kreeg {len(nieuw)}"
        regel = nieuw[0]
        assert regel.user_id == GEBRUIKER_ID and regel.tenant_id == TENANT_ID  # type: ignore[attr-defined]
        assert str(rid) in _tekst(regel) and "betaald" in _tekst(regel), _tekst(regel)

    async def test_de_betaling_blijft_staan_naast_de_logboekregel(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        rid = await _zet_factuur(db_session, TENANT_ID, "herinnerd")

        await api.patch(f"{URL}/{rid}", json={"status": "betaald"})

        db_session.expire_all()
        rij = await db_session.get(Receivable, rid)
        assert rij is not None and rij.status == "betaald" and rij.betaald_op is not None

    async def test_de_regel_noemt_de_oude_en_de_nieuwe_status(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Een logboek dat alleen "betaald" zegt, laat niet zien WAT er veranderde."""
        rid = await _zet_factuur(db_session, TENANT_ID, "herinnerd")
        voor = len(await _regels(db_session, TENANT_ID))

        await api.patch(f"{URL}/{rid}", json={"status": "betaald"})

        regel = (await _regels(db_session, TENANT_ID))[voor]
        assert "herinnerd" in _tekst(regel), _tekst(regel)

    async def test_een_wijziging_zonder_statuswissel_schrijft_geen_statusregel(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Andere kant op: alleen een statuswijziging komt in het logboek, niet elke PATCH."""
        rid = await _zet_factuur(db_session, TENANT_ID, "herinnerd")
        voor = len(await _regels(db_session))

        antwoord = await api.patch(f"{URL}/{rid}", json={"customer_name": "Nieuwe Naam"})

        assert antwoord.status_code == 200, antwoord.text
        assert len(await _regels(db_session)) == voor

    async def test_een_geweigerde_overgang_geeft_geen_serverfout_en_geen_regel(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """`betaald -> open` zonder reden: een nette 4xx, de rij blijft betaald, niets gelogd."""
        rid = await _zet_factuur(db_session, TENANT_ID, "betaald")
        voor = len(await _regels(db_session))

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "open"})

        assert 400 <= antwoord.status_code < 500, (antwoord.status_code, antwoord.text)
        db_session.expire_all()
        rij = await db_session.get(Receivable, rid)
        assert rij is not None and rij.status == "betaald"
        assert len(await _regels(db_session)) == voor

    async def test_een_vreemde_factuur_wijzigen_logt_niets_en_geeft_404(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        rid = await _zet_factuur(db_session, 2, "herinnerd")
        voor = len(await _regels(db_session))

        antwoord = await api.patch(f"{URL}/{rid}", json={"status": "betaald"})

        assert antwoord.status_code == 404
        db_session.expire_all()
        rij = await db_session.get(Receivable, rid)
        assert rij is not None and rij.status == "herinnerd"
        assert len(await _regels(db_session)) == voor


@pytest.mark.unit
@pytest.mark.asyncio
class TestAanmakenStaatInHetLogboek:
    async def test_aanmaken_van_een_factuur_staat_in_het_logboek(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        voor = len(await _regels(db_session, TENANT_ID))

        antwoord = await api.post(
            URL,
            json={
                "customer_name": "Bakkerij De Korst",
                "customer_email": "administratie@dekorst.example",
                "invoice_number": "F-2026-001",
                "amount": "1250.50",
                "currency": "EUR",
                "due_date": "2026-09-01",
            },
        )

        assert antwoord.status_code == 201, antwoord.text
        rid = antwoord.json()["data"]["id"]
        nieuw = (await _regels(db_session, TENANT_ID))[voor:]
        assert len(nieuw) == 1, f"verwacht precies een logboekregel erbij, kreeg {len(nieuw)}"
        assert nieuw[0].user_id == GEBRUIKER_ID  # type: ignore[attr-defined]
        assert str(rid) in _tekst(nieuw[0]), _tekst(nieuw[0])

    async def test_een_afgewezen_aanmaak_logt_niets(
        self, api: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Andere kant op: een 422 (negatief bedrag) laat geen regel achter."""
        voor = len(await _regels(db_session))

        antwoord = await api.post(
            URL,
            json={
                "customer_name": "K",
                "customer_email": "k@klant.example",
                "invoice_number": "F-X",
                "amount": "-5.00",
                "due_date": "2026-09-01",
            },
        )

        assert antwoord.status_code == 422
        assert len(await _regels(db_session)) == voor
