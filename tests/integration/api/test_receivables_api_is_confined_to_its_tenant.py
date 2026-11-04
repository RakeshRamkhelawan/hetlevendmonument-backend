"""Handmatige invoer van debiteuren via de API, binnen de eigen tenant (debiteurenagent dag 2).

Echte app-stack (`register_all_routers`), echte Postgres op netwerkpoort 5455, de echte
`require_permission` op het JWT. Alleen CSRF is vervangen (Redis-gebonden token; de controle zelf
heeft eigen tests) en `get_current_user` wijst naar de gezaaide beheerder van tenant 1.

**Isolatie, beide richtingen.** Tenant 1 ziet en wijzigt de debiteur van tenant 2 niet (lijst en
PATCH), en zijn eigen debiteur wel -- zonder die tweede helft is "alles weigeren" een geldige
oplossing. De rij van tenant 2 wordt rechtstreeks in de database gezet, buiten de API om.

Wat NIET gemeten wordt: RLS als laatste verdedigingslinie. De app verbindt hier als eigenaar
(OP-151), dus het is het tenantfilter van de repository dat hier de grens trekt; RLS op
`receivables` meet `tests/integration/security/test_receivables_is_confined_to_its_tenant.py`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

URL = "/api/v1/receivables"

_FACTUUR: dict[str, Any] = {
    "customer_name": "Bakkerij De Korst",
    "customer_email": "administratie@dekorst.example",
    "invoice_number": "F-2026-001",
    "amount": "1250.50",
    "currency": "EUR",
    "due_date": "2026-09-01",
}


@pytest_asyncio.fixture
async def api(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    async def _geen_csrf() -> None:
        return None

    overrides = {get_db: _db, api_get_db: _db, validate_csrf_token: _geen_csrf}
    integration_app.dependency_overrides.update(overrides)
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


async def _rij_van_tenant_2(session: AsyncSession) -> int:
    from src.core.models.receivable_models import Receivable

    rij = Receivable(
        tenant_id=2,
        customer_name="Ander Bedrijf",
        customer_email="geheim@ander.example",
        invoice_number="B-999",
        amount=Decimal("10.00"),
        currency="EUR",
        due_date=date(2026, 9, 1),
        status="open",
        source="handmatig",
    )
    session.add(rij)
    await session.flush()
    return rij.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestInvoer:
    async def test_a_receivable_is_created_as_manual_input(self, api: AsyncClient) -> None:
        antwoord = await api.post(URL, json=_FACTUUR)

        assert antwoord.status_code == 201, antwoord.text
        data = antwoord.json()["data"]
        assert (data["invoice_number"], data["source"], data["status"]) == (
            "F-2026-001",
            "handmatig",
            "open",
        )

    async def test_a_tenant_id_in_the_body_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.post(URL, json={**_FACTUUR, "tenant_id": 2})
        assert antwoord.status_code == 422

    async def test_a_negative_amount_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.post(URL, json={**_FACTUUR, "amount": "-1.00"})
        assert antwoord.status_code == 422

    async def test_a_lowercase_currency_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.post(URL, json={**_FACTUUR, "currency": "eur"})
        assert antwoord.status_code == 422

    async def test_the_list_is_paginated(self, api: AsyncClient) -> None:
        for i in range(3):
            await api.post(URL, json={**_FACTUUR, "invoice_number": f"P-{i}"})

        antwoord = await api.get(URL, params={"limit": 2, "offset": 1})

        body = antwoord.json()
        assert (len(body["data"]), body["limit"], body["offset"]) == (2, 2, 1)


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantgrens:
    async def test_another_tenants_receivable_is_not_listed(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _rij_van_tenant_2(postgres_session)
        await api.post(URL, json=_FACTUUR)

        nummers = {r["invoice_number"] for r in (await api.get(URL)).json()["data"]}

        assert nummers == {"F-2026-001"}

    async def test_another_tenants_receivable_cannot_be_changed(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        vreemd = await _rij_van_tenant_2(postgres_session)

        antwoord = await api.patch(f"{URL}/{vreemd}", json={"status": "betaald"})

        status = (
            await postgres_session.execute(
                text("SELECT status FROM receivables WHERE id = :id"), {"id": vreemd}
            )
        ).scalar_one()
        assert (antwoord.status_code, status) == (404, "open")

    async def test_the_own_receivable_can_be_changed(self, api: AsyncClient) -> None:
        eigen = (await api.post(URL, json=_FACTUUR)).json()["data"]["id"]

        antwoord = await api.patch(f"{URL}/{eigen}", json={"status": "betaald"})

        assert (antwoord.status_code, antwoord.json()["data"]["status"]) == (200, "betaald")


@pytest.mark.integration
@pytest.mark.asyncio
class TestRecht:
    async def test_a_user_without_write_permission_cannot_create(
        self, integration_app: Any, api: AsyncClient
    ) -> None:
        from tests.integration.conftest import _build_test_token

        token = _build_test_token(user_id=2, email="user@integration.test", tenant_id=1)
        antwoord = await api.post(
            URL, json=_FACTUUR, headers={"Authorization": f"Bearer {token}"}
        )

        assert antwoord.status_code == 403
