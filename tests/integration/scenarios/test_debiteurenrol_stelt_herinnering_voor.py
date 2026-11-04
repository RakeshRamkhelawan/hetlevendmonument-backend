"""Acceptant ronde 3, N1: de rol `debiteuren` kan een herinnering VOORSTELLEN, niet goedkeuren.

Live gemeten: `POST /api/v1/receivables/reminder-proposals` als rol `debiteuren` gaf
`niet_gelukt` met "Council-verdict blocked" -- de SecurityOfficer zei `MISSING_SCOPE`, want
`send_payment_reminder` vroeg `write` en de rol had alleen `read` in `ROLE_PERMISSIONS`.

Echt in deze test: Postgres (netwerkpoort 5455), de gebruiker met PRECIES de rol `debiteuren`
uit het echte seedscript, de route, `start_reminder_proposals`, de debiteurenagent, de Council
met de echte SecurityOfficer en `rbac_service.user_has_scope_for` (die de rollen uit de
database leest), de HITL-vloer en `hitl_tickets`. Vervangen: alleen `get_current_user` (wijst
naar de gezaaide gebruiker) en CSRF (Redis-gebonden, eigen tests).

Waarom gecommit en niet in `postgres_session`: de Council en `user_has_scope_for` openen hun
eigen sessie via `db_manager` en zien een terugrollende testtransactie niet.
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
EMAIL = "debiteuren-n1@integration.test"
SCRIPT_PAD = Path(__file__).resolve().parents[3] / "scripts" / "seed_tweede_gebruiker.py"


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


@pytest_asyncio.fixture
async def debiteurenmedewerker() -> AsyncGenerator[int, None]:
    from src.core.database.database import db_manager

    spec = importlib.util.spec_from_file_location("_seed_n1", SCRIPT_PAD)
    assert spec is not None and spec.loader is not None
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)

    async with db_manager.get_session() as session:
        user_id = await seed.maak_tweede_gebruiker(
            session,
            tenant_id=TENANT,
            email=EMAIL,
            password="debiteuren-n1-wachtwoord",
            rol_naam="debiteuren",
        )
    await _sql("UPDATE users SET is_active = true WHERE id = :u", u=user_id)
    yield user_id
    # Niet verwijderen: een voorstel schrijft een auditregel met dit user-id (`audit_logs_user_id_fkey`, 2026-10-20),
    # en een auditregel pas ik niet aan (hashketen). De gebruiker wordt bij een volgende run hergebruikt.
    await _sql("DELETE FROM user_roles WHERE user_id = :u", u=user_id)
    await _sql("UPDATE users SET is_active = false WHERE id = :u", u=user_id)


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
                invoice_number="F-N1-001",
                amount=Decimal("99.95"),
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
    await _sql("DELETE FROM outgoing_messages WHERE tenant_id = :t", t=TENANT)
    await _sql("DELETE FROM receivables WHERE id = :r", r=rid)


async def _als(integration_app: Any, user_id: int, methode: str, pad: str, body: Any) -> Any:
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

    gebruiker = UserResponse(id=user_id, email=EMAIL, tenant_id=TENANT, roles=["debiteuren"])
    overrides: dict[Any, Any] = {
        get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
    }
    token = _build_test_token(user_id=user_id, email=EMAIL, tenant_id=TENANT)
    integration_app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.request(methode, pad, json=body)
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDebiteurenrolStelVoor:
    @pytest.mark.parametrize("soort", ["herinnering", "aanmaning"])
    async def test_proposing_creates_a_ticket_waiting_for_approval(
        self, integration_app: Any, debiteurenmedewerker: int, debiteur: int, soort: str
    ) -> None:
        if soort == "aanmaning":
            # Een aanmaning komt pas na een herinnering (brief 2026-10-24): het dossier is al `herinnerd`.
            await _sql("UPDATE receivables SET status = 'herinnerd' WHERE id = :r", r=debiteur)
        antwoord = await _als(
            integration_app,
            debiteurenmedewerker,
            "POST",
            "/api/v1/receivables/reminder-proposals",
            {"receivable_ids": [debiteur], "kind": soort},
        )

        assert antwoord.status_code == 200, antwoord.text
        uitkomst = antwoord.json()["data"][0]
        assert uitkomst["status"] == "wacht_op_goedkeuring", uitkomst
        rij = (
            await _sql(
                "SELECT status, tool_name FROM hitl_tickets WHERE ticket_ref = :r",
                r=uitkomst["ticket_ref"],
            )
        ).one()
        assert (rij.status, rij.tool_name) == ("pending", "send_payment_reminder")

    async def test_the_role_cannot_approve_its_own_ticket(
        self, integration_app: Any, debiteurenmedewerker: int, debiteur: int
    ) -> None:
        voorstel = await _als(
            integration_app,
            debiteurenmedewerker,
            "POST",
            "/api/v1/receivables/reminder-proposals",
            {"receivable_ids": [debiteur], "kind": "herinnering"},
        )
        ref = voorstel.json()["data"][0]["ticket_ref"]

        antwoord = await _als(
            integration_app,
            debiteurenmedewerker,
            "POST",
            "/api/v1/tools/hitl/approve",
            {"ticket_ref": ref},
        )

        assert antwoord.status_code == 403, antwoord.text
        assert (
            await _sql("SELECT count(*) FROM outgoing_messages WHERE hitl_ticket_ref = :r", r=ref)
        ).scalar_one() == 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeRolBlijftSmal:
    """De oplossing is GEEN algemene `write`: de andere schrijftools blijven dicht."""

    @pytest.mark.parametrize(
        "tool", ["local__write_file", "generate_text", "serena__write_document"]
    )
    async def test_other_write_tools_stay_closed(
        self, debiteurenmedewerker: int, tool: str
    ) -> None:
        from src.core.auth.rbac import rbac_service

        assert not await rbac_service.user_has_scope_for(
            debiteurenmedewerker, tool, tenant_id=TENANT
        )

    async def test_the_proposal_tool_is_open(self, debiteurenmedewerker: int) -> None:
        from src.core.auth.rbac import rbac_service

        assert await rbac_service.user_has_scope_for(
            debiteurenmedewerker, "send_payment_reminder", tenant_id=TENANT
        )
