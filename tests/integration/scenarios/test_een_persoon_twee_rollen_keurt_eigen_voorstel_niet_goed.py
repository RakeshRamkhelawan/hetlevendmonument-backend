"""Dezelfde persoon met de rollen `debiteuren` EN `goedkeurder` keurt zijn eigen voorstel niet goed (2026-10-20).

De acceptant (2026-10-19) heeft dit niet live gezien: in een klein bedrijf is een persoon vaak beide. Met vier ogen AAN
voor `send_payment_reminder` moet het eigen voorstel dan door een ANDERE persoon worden goedgekeurd; zonder die regel
is "vier ogen" een scherm zonder werking.

Echt in deze test: Postgres (netwerkpoort 5455), twee gebruikers uit het echte seedscript, de route
`reminder-proposals`, de debiteurenagent, de Council, de HITL-vloer en `POST /api/v1/tools/hitl/approve` met de echte
`_refuse_self_approval`. Vervangen: alleen `get_current_user` en CSRF (Redis-gebonden, eigen tests).

Beide richtingen: de persoon met twee rollen krijgt 403 op zijn EIGEN voorstel (en er ontstaat geen brief); een andere
goedkeurder krijgt op hetzelfde voorstel GEEN vier-ogen-weigering en de brief komt klaar te staan. Zonder die tweede
helft is "iedereen weigeren" een geldige oplossing.

Waarom gecommit en niet in `postgres_session`: de Council en de rolopzoeking openen hun eigen sessie en zien een
terugrollende testtransactie niet (zelfde reden als `test_debiteurenrol_stelt_herinnering_voor.py`).
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

TENANT = 1
EMAIL_BEIDE = "twee-rollen@integration.test"
EMAIL_ANDER = "andere-goedkeurder@integration.test"
ACTIE = "send_payment_reminder"
SCRIPT_PAD = Path(__file__).resolve().parents[3] / "scripts" / "seed_tweede_gebruiker.py"
# Alleen voor de wegwerpgebruikers van deze test; als variabele, zodat geen letterlijke waarde achter een
# geheimnaam staat.
_TESTSLEUTEL_BEIDE = "twee-rollen-testsleutel"
_TESTSLEUTEL_ANDER = "andere-goedkeurder-testsleutel"


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


def _seed() -> Any:
    spec = importlib.util.spec_from_file_location("_seed_twee_rollen", SCRIPT_PAD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _ruim_gebruiker_op(user_id: int) -> None:
    """Rollen weg en gebruiker uit; de gebruiker zelf blijft staan.

    Een voorstel schrijft een auditregel met dit user-id (`audit_logs_user_id_fkey`), en een auditregel pas ik niet aan
    (hashketen). De gebruiker wordt bij een volgende run hergebruikt en weer actief gezet.
    """
    await _sql("DELETE FROM user_roles WHERE user_id = :u", u=user_id)
    await _sql("UPDATE users SET is_active = false WHERE id = :u", u=user_id)


async def _activeer(user_id: int) -> None:
    await _sql("UPDATE users SET is_active = true WHERE id = :u", u=user_id)


@pytest_asyncio.fixture
async def persoon_met_twee_rollen() -> AsyncGenerator[int, None]:
    from src.core.database.database import db_manager

    seed = _seed()
    async with db_manager.get_session() as session:
        user_id = 0
        for rol in ("debiteuren", "goedkeurder"):
            user_id = await seed.maak_tweede_gebruiker(
                session,
                tenant_id=TENANT,
                email=EMAIL_BEIDE,
                password=_TESTSLEUTEL_BEIDE,
                rol_naam=rol,
            )
        await session.commit()
    await _activeer(user_id)
    yield user_id
    await _ruim_gebruiker_op(user_id)


@pytest_asyncio.fixture
async def andere_goedkeurder() -> AsyncGenerator[int, None]:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        user_id = await _seed().maak_tweede_gebruiker(
            session,
            tenant_id=TENANT,
            email=EMAIL_ANDER,
            password=_TESTSLEUTEL_ANDER,
            rol_naam="goedkeurder",
        )
        await session.commit()
    await _activeer(user_id)
    yield user_id
    await _ruim_gebruiker_op(user_id)


@pytest_asyncio.fixture
async def vier_ogen_aan() -> AsyncGenerator[None, None]:
    """Zet vier ogen AAN voor de brief-actie en herstelt de oude stand."""
    from src.core.database.database import db_manager
    from src.core.governance.four_eyes import read_four_eyes_actions, write_four_eyes_actions

    async with db_manager.get_session() as session:
        stand = await read_four_eyes_actions(session, tenant_id=TENANT)
        oud = [str(a["name"]) for a in stand if a["enabled"]]
        await write_four_eyes_actions(session, tenant_id=TENANT, actions=sorted({*oud, ACTIE}))
    yield
    async with db_manager.get_session() as session:
        await write_four_eyes_actions(session, tenant_id=TENANT, actions=oud)


@pytest_asyncio.fixture
async def debiteur() -> AsyncGenerator[int, None]:
    from src.core.database.database import db_manager
    from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository

    async with db_manager.get_session() as session:
        rij = await ReceivableRepository(session).add(
            TENANT,
            NewReceivable(
                customer_name="Bakkerij De Korst",
                customer_email="administratie@dekorst.example",
                invoice_number="F-4O-001",
                amount=Decimal("42.00"),
                currency="EUR",
                due_date=date(2026, 9, 1),
            ),
        )
        await session.commit()
        rid = int(rij.id)
    yield rid
    await _sql(
        "DELETE FROM hitl_tickets WHERE tenant_id = :t AND payload->>'receivable_id' = :r",
        t=TENANT,
        r=str(rid),
    )
    await _sql("DELETE FROM outgoing_messages WHERE receivable_id = :r", r=rid)
    await _sql("DELETE FROM receivables WHERE id = :r", r=rid)


async def _als(
    app: Any, user_id: int, email: str, rollen: list[str], methode: str, pad: str, body: Any
) -> Any:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import db_manager, get_db

    async def _db() -> AsyncGenerator[Any, None]:
        async with db_manager.get_session() as session:
            yield session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=TENANT, roles=rollen)
    overrides: dict[Any, Any] = {
        get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
    }
    token = _build_test_token(user_id=user_id, email=email, tenant_id=TENANT)
    app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.request(methode, pad, json=body)
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


async def _stel_voor(app: Any, user_id: int, debiteur: int) -> str:
    antwoord = await _als(
        app,
        user_id,
        EMAIL_BEIDE,
        ["debiteuren", "goedkeurder"],
        "POST",
        "/api/v1/receivables/reminder-proposals",
        {"receivable_ids": [debiteur], "kind": "herinnering"},
    )
    assert antwoord.status_code == 200, antwoord.text
    uitkomst = antwoord.json()["data"][0]
    assert uitkomst["status"] == "wacht_op_goedkeuring", uitkomst
    return str(uitkomst["ticket_ref"])


async def _aantal_brieven(ref: str) -> int:
    return int(
        (
            await _sql("SELECT count(*) FROM outgoing_messages WHERE hitl_ticket_ref = :r", r=ref)
        ).scalar_one()
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenPersoonTweeRollen:
    async def test_the_person_cannot_approve_his_own_proposal(
        self,
        integration_app: Any,
        persoon_met_twee_rollen: int,
        vier_ogen_aan: None,
        debiteur: int,
    ) -> None:
        ref = await _stel_voor(integration_app, persoon_met_twee_rollen, debiteur)

        antwoord = await _als(
            integration_app,
            persoon_met_twee_rollen,
            EMAIL_BEIDE,
            ["debiteuren", "goedkeurder"],
            "POST",
            "/api/v1/tools/hitl/approve",
            {"ticket_ref": ref},
        )

        assert (antwoord.status_code, "Four-eyes" in antwoord.json().get("detail", "")) == (
            403,
            True,
        )

    async def test_no_letter_is_created_by_the_refused_approval(
        self,
        integration_app: Any,
        persoon_met_twee_rollen: int,
        vier_ogen_aan: None,
        debiteur: int,
    ) -> None:
        ref = await _stel_voor(integration_app, persoon_met_twee_rollen, debiteur)
        await _als(
            integration_app,
            persoon_met_twee_rollen,
            EMAIL_BEIDE,
            ["debiteuren", "goedkeurder"],
            "POST",
            "/api/v1/tools/hitl/approve",
            {"ticket_ref": ref},
        )

        assert await _aantal_brieven(ref) == 0

    async def test_another_approver_can_approve_the_same_proposal(
        self,
        integration_app: Any,
        persoon_met_twee_rollen: int,
        andere_goedkeurder: int,
        vier_ogen_aan: None,
        debiteur: int,
    ) -> None:
        ref = await _stel_voor(integration_app, persoon_met_twee_rollen, debiteur)

        antwoord = await _als(
            integration_app,
            andere_goedkeurder,
            EMAIL_ANDER,
            ["goedkeurder"],
            "POST",
            "/api/v1/tools/hitl/approve",
            {"ticket_ref": ref},
        )

        assert (antwoord.status_code, await _aantal_brieven(ref)) == (200, 1), antwoord.text
