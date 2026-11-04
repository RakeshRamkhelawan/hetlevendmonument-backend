"""Meting: de focus-builder-chat-websocket vraagt `workflows:publish` voor `accept_proposal` (bevinding A).

`accept_proposal` schreef de nodes van een AI-voorstel in een opgeslagen flow zonder rolcontrole;
elke andere ingang die een flow wijzigt vraagt `workflows:publish`.

Echt: Postgres op netwerkpoort 5455, de gebruikers uit `scripts/seed_tweede_gebruiker.py`
(`medewerker` met precies de rol `user`, `*:read`; de gezaaide beheerder met `admin`, `*:*`), een
echt JWT in de `access_token`-cookie dat de handler zelf valideert, de echte rolcontrole en de
echte FlowRepository. Vervangen: de websocket zelf (een nep-socket die berichten aanreikt en
antwoorden verzamelt -- een TestClient-websocket draait in een eigen event loop en kan de
testsessie niet delen) en de chat-agent (geen LLM; hij geeft vaste nodes terug).

Wat NIET gemeten wordt: het websocket-transport en de frontend-afhandeling van het foutbericht.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.api.test_receivables_schrijfrecht_per_rol import _seed

ROUTER = "src.core.api.v1.focus_builder.ws_chat_router"
OPMAAK: list[dict[str, Any]] = [
    {"id": "o", "type": "action", "position": {}, "data": {"name": "data_transformer"}}
]
LEGE_GRAAF: dict[str, Any] = {"nodes": [], "edges": []}


class NepSocket:
    """Reikt berichten aan; na het laatste volgt een disconnect. Verzamelt de antwoorden."""

    def __init__(self, token: str, berichten: list[dict[str, Any]]) -> None:
        self.cookies = {"access_token": token}
        self._berichten = list(berichten)
        self.verzonden: list[dict[str, Any]] = []
        self.gesloten: int | None = None

    async def accept(self) -> None:
        return None

    async def receive_json(self) -> dict[str, Any]:
        if not self._berichten:
            raise WebSocketDisconnect(code=1000)
        return self._berichten.pop(0)

    async def send_json(self, data: dict[str, Any]) -> None:
        self.verzonden.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.gesloten = code


async def _flow(session: AsyncSession) -> int:
    from src.domains.flows.repository import FlowRepository

    flow = await FlowRepository(session, 1).create(
        {"name": "ws-recht", "react_flow_graph": LEGE_GRAAF}
    )
    return int(flow.id)


async def _graaf(session: AsyncSession, flow_id: int) -> dict[str, Any]:
    from src.domains.flows.models import Flow

    session.expire_all()
    flow = (await session.execute(select(Flow).where(Flow.id == flow_id))).scalar_one()
    return dict(flow.react_flow_graph or {})


async def _accepteer(
    session: AsyncSession, *, user_id: int, email: str, flow_id: int
) -> tuple[NepSocket, AsyncMock]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.v1.focus_builder.ws_chat_router import focus_builder_ws_chat

    token = _build_test_token(user_id=user_id, email=email, tenant_id=1)
    socket = NepSocket(
        token, [{"type": "accept_proposal", "proposal_id": "p1", "flow_id": flow_id}]
    )
    with (
        patch(f"{ROUTER}.FocusBuilderToolAgent") as tool_agent,
        patch(f"{ROUTER}.FocusBuilderChatAgent") as chat_agent,
    ):
        for agent in (tool_agent.return_value, chat_agent.return_value):
            agent.start_session = AsyncMock()
            agent.accept_proposal = AsyncMock(return_value=list(OPMAAK))
        await focus_builder_ws_chat(websocket=socket, conversation_id=None, db=session)  # type: ignore[arg-type]
    gebruikt = tool_agent.return_value.accept_proposal
    if not gebruikt.await_count:
        gebruikt = chat_agent.return_value.accept_proposal
    return socket, gebruikt


@pytest.mark.integration
@pytest.mark.asyncio
async def test_de_gewone_gebruiker_krijgt_een_fout_en_de_flow_blijft_gelijk(
    postgres_session: AsyncSession,
) -> None:
    email = "ws-medewerker@integration.test"
    user_id = await _seed().maak_tweede_gebruiker(
        postgres_session, tenant_id=1, email=email, password="ws-medewerker-wachtwoord"
    )
    flow_id = await _flow(postgres_session)

    socket, accept = await _accepteer(postgres_session, user_id=user_id, email=email, flow_id=flow_id)

    assert socket.gesloten is None, socket.verzonden
    assert socket.verzonden == [
        {
            "type": "error",
            "code": "PERMISSION_DENIED",
            "message": "Missing permission: workflows:publish",
        }
    ]
    assert accept.await_count == 0, "het voorstel werd toch door de agent opgeslagen"
    assert await _graaf(postgres_session, flow_id) == LEGE_GRAAF


@pytest.mark.integration
@pytest.mark.asyncio
async def test_de_beheerder_schrijft_de_flow_weg(postgres_session: AsyncSession) -> None:
    """Tegenproef: anders is "altijd weigeren" een geldige uitkomst."""
    flow_id = await _flow(postgres_session)

    socket, accept = await _accepteer(
        postgres_session, user_id=1, email="admin@integration.test", flow_id=flow_id
    )

    assert socket.verzonden == [{"type": "proposal_accepted", "proposal_id": "p1"}]
    assert accept.await_count == 1
    assert await _graaf(postgres_session, flow_id) == {"nodes": OPMAAK, "edges": []}
