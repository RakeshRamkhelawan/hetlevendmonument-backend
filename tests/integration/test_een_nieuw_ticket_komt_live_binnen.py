"""Een HITL-ticket uit het AGENTPAD komt live binnen bij de juiste tenant (meetlat-scenario 5).

**De bevinding (acceptant, 2026-10-05).** Een ticket uit `/debiteuren` kwam niet live op `/hitl`.
`notify_new_ticket` werd alleen aangeroepen in `tool_broker/router.py` (`POST /hitl/request`);
het agentpad -- `specialist_base._council_rejection` -> `HITLTicketRepository.create_hitl_request`
-> eigen sessie + commit -- zond niets uit.

Hier draait de echte keten: de echte `/ws/hitl/{tenant_id}`-route met de echte
`connection_manager`, een echte websocket-client, en een echte PostgreSQL-sessie die het ticket
precies zo aanmaakt en vastlegt als het agentpad. Alleen de JWT-verificatie is vervangen door een
vaste payload. Het aanmaken gebeurt in de event loop van de app (`portal.call`), net als in
productie, waar het verzoek en de websocket in hetzelfde proces draaien.

Vereist `SANSKRITISETU_TEST_DATABASE_URL` (zie `tests/fixtures/testdatabase.py`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.api.v1.websocket_hitl import limiter
from src.core.api.v1.websocket_hitl import router as hitl_router
from tests.fixtures.testdatabase import TestdatabaseNietOpgegeven, testdatabase_url

try:
    _URL: str | None = testdatabase_url()
except TestdatabaseNietOpgegeven:
    _URL = None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_URL is None, reason="SANSKRITISETU_TEST_DATABASE_URL niet gezet"),
]

TENANT = 9101
ANDERE_TENANT = 9102


def _payload(token: str) -> dict[str, object]:
    return {"sub": "user-42", "tenant_id": int(token.split("-")[1]), "roles": ["admin"]}


@pytest.fixture
def ws_client(account_actief_zonder_database: None) -> Iterator[TestClient]:
    """De accountcontrole van de websocket (e19626de, 5248e62c) staat uit: `user-42` bestaat niet in de database.

    Zonder dit sloot de route met 4005 "Account not allowed on a websocket" (gemeten 2026-10-26). Ook de
    intrekkingscontrole staat uit: de vaste payload heeft geen `jti` en een token zonder `jti` telt fail-closed als
    ingetrokken. Deze test meet de melding van een nieuw ticket, niet het account of de intrekking; die worden
    met echte gebruikers gemeten in de tests van de accountcontrole.
    """
    limiter.buckets.clear()
    app = FastAPI()
    app.include_router(hitl_router)
    with (
        patch(
            "src.core.auth.websocket_auth.websocket_auth.jwt_handler.verify_token",
            side_effect=_payload,
        ),
        patch(
            "src.core.auth.account_status.token_is_ingetrokken",
            AsyncMock(return_value=False),
        ),
    ):
        with TestClient(app) as client:
            yield client


async def _ticket_via_het_agentpad(tenant_id: int) -> str:
    """Wat `specialist_base._council_rejection` doet: eigen sessie, create_hitl_request, commit."""
    from src.core.tool_broker.hitl_repository import HITLTicketRepository
    from src.core.tool_broker.models import HITLTicket

    assert _URL is not None
    engine = create_async_engine(_URL)
    sessies = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessies() as db:
            ticket_ref = await HITLTicketRepository(db).create_hitl_request(
                tenant_id=tenant_id,
                user_id=77,
                decision_id="besluit-1",
                reason="Herinnering voor factuur F-1",
                action_type="send_payment_reminder",
                action_params={"receivable_id": 1},
                executing_identity="dunning",
            )
            await db.commit()
        # De melding gaat na de commit als losse taak; geef hem de beurt.
        for _ in range(20):
            await asyncio.sleep(0.01)
        async with sessies() as db:
            await db.execute(delete(HITLTicket).where(HITLTicket.ticket_ref == ticket_ref))
            await db.commit()
        return ticket_ref
    finally:
        await engine.dispose()


def _verbind(client: TestClient, tenant_id: int):  # type: ignore[no-untyped-def]
    return client.websocket_connect(
        f"/ws/hitl/{tenant_id}", headers={"Authorization": f"Bearer tenant-{tenant_id}"}
    )


def test_een_ticket_uit_het_agentpad_komt_live_binnen(ws_client: TestClient) -> None:
    with _verbind(ws_client, TENANT) as ws:
        assert ws.receive_json()["type"] == "connected"
        portal = ws_client.portal
        assert portal is not None

        ticket_ref = portal.call(_ticket_via_het_agentpad, TENANT)

        # Een ping erachteraan: komt de pong als eerste, dan is er niets gemeld.
        ws.send_json({"type": "ping"})
        eerste = ws.receive_json()
        assert (eerste["type"], eerste.get("ticket_ref")) == ("hitl:new", ticket_ref)


def test_een_andere_tenant_ontvangt_niets(ws_client: TestClient) -> None:
    with _verbind(ws_client, ANDERE_TENANT) as ws:
        assert ws.receive_json()["type"] == "connected"
        portal = ws_client.portal
        assert portal is not None

        portal.call(_ticket_via_het_agentpad, TENANT)

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


async def _ticket_teruggedraaid(tenant_id: int) -> None:
    from src.core.tool_broker.hitl_repository import HITLTicketRepository, generate_ticket_ref

    assert _URL is not None
    engine = create_async_engine(_URL)
    try:
        async with async_sessionmaker(engine)() as db:
            await HITLTicketRepository(db).create(
                ticket_ref=generate_ticket_ref(),
                tenant_id=tenant_id,
                tool_name="send_payment_reminder",
                payload={},
                risk_level="HIGH",
            )
            await db.rollback()
        for _ in range(20):
            await asyncio.sleep(0.01)
    finally:
        await engine.dispose()


def test_een_teruggedraaid_ticket_wordt_niet_gemeld(ws_client: TestClient) -> None:
    with _verbind(ws_client, TENANT) as ws:
        assert ws.receive_json()["type"] == "connected"
        portal = ws_client.portal
        assert portal is not None

        portal.call(_ticket_teruggedraaid, TENANT)

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


async def _ticket_terwijl_melden_faalt(tenant_id: int) -> bool:
    from src.core.tool_broker.hitl_repository import HITLTicketRepository
    from src.core.tool_broker.models import HITLTicket

    assert _URL is not None
    engine = create_async_engine(_URL)
    sessies = async_sessionmaker(engine, expire_on_commit=False)
    try:
        with patch(
            "src.core.tool_broker.hitl_notifier.broadcast_new_ticket",
            side_effect=ConnectionError("websocketlaag weg"),
        ):
            async with sessies() as db:
                ticket_ref = await HITLTicketRepository(db).create_hitl_request(
                    tenant_id=tenant_id,
                    user_id=77,
                    decision_id="besluit-2",
                    reason="Herinnering voor factuur F-2",
                    action_type="send_payment_reminder",
                    action_params={"receivable_id": 2},
                    executing_identity="dunning",
                )
                await db.commit()
            for _ in range(20):
                await asyncio.sleep(0.01)
        async with sessies() as db:
            bestaat = await HITLTicketRepository(db).get(ticket_ref, tenant_id) is not None
            await db.execute(delete(HITLTicket).where(HITLTicket.ticket_ref == ticket_ref))
            await db.commit()
        return bestaat
    finally:
        await engine.dispose()


def test_een_mislukte_melding_laat_het_aanmaken_niet_falen(ws_client: TestClient) -> None:
    portal = ws_client.portal
    assert portal is not None
    assert portal.call(_ticket_terwijl_melden_faalt, TENANT) is True
