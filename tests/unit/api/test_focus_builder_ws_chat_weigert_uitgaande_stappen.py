"""De websocket-chat bewaart geen voorgestelde stap die iets naar buiten stuurt (wfb-dag1 stap 1).

Gate 2 MEDIUM-4: `accept_proposal` voegde de nodes van een AI-voorstel zonder controle aan de
opgeslagen graaf toe. Nu wordt de samengevoegde graaf eerst gecontroleerd; een weigering geeft
een `error`-bericht en er wordt niets bewaard. Opstelling als in test_focus_builder_ws_chat.py:
token, agents en de dienst zijn vervangen; de stappencontrole zelf loopt echt.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.unit.api.test_focus_builder_ws_chat import app_with_overrides  # noqa: F401

ROUTER = "src.core.api.v1.focus_builder.ws_chat_router"


def _accepteer(app: Any, nodes: list[dict[str, Any]]) -> tuple[dict[str, Any], AsyncMock]:
    gebruiker = MagicMock(id=1, tenant_id=1)
    dienst = MagicMock()
    dienst.repository.get = AsyncMock(
        return_value=SimpleNamespace(react_flow_graph={"nodes": [], "edges": []})
    )
    dienst.repository.update = AsyncMock()
    with (
        patch(f"{ROUTER}.validate_ws_token", new=AsyncMock(return_value=gebruiker)),
        # De rolcontrole heeft een eigen meting met echte Postgres
        # (tests/integration/api/test_focus_builder_ws_chat_publicatierecht.py); hier telt de
        # stappencontrole, dus mag deze gebruiker publiceren.
        patch(f"{ROUTER}.mag_flows_publiceren", new=AsyncMock(return_value=True)),
        patch(f"{ROUTER}.FocusBuilderToolAgent") as tool_agent,
        patch(f"{ROUTER}.FocusBuilderChatAgent") as chat_agent,
        patch("src.domains.flows.service.FocusBuilderService", return_value=dienst),
    ):
        tool_agent.return_value.start_session = AsyncMock()
        chat_agent.return_value.start_session = AsyncMock()
        chat_agent.return_value.accept_proposal = AsyncMock(return_value=nodes)
        with TestClient(app) as client:
            client.cookies.set("access_token", "test.jwt.token")
            with client.websocket_connect("/api/v1/focus-builder/ws/chat") as ws:
                ws.send_json({"type": "accept_proposal", "proposal_id": "p1", "flow_id": 7})
                antwoord = ws.receive_json()
    return antwoord, dienst.repository.update


@pytest.mark.unit
def test_een_voorgestelde_mailstap_wordt_geweigerd_en_niet_bewaard(
    app_with_overrides: Any,  # noqa: F811
) -> None:
    mail = [{"id": "m", "type": "action", "position": {}, "data": {"name": "email"}}]

    antwoord, bewaren = _accepteer(app_with_overrides, mail)

    assert (antwoord.get("type"), bewaren.await_count) == ("error", 0), antwoord


@pytest.mark.unit
def test_een_voorgestelde_opmaakstap_wordt_bewaard(
    app_with_overrides: Any,  # noqa: F811
) -> None:
    opmaak = [{"id": "o", "type": "action", "position": {}, "data": {"name": "data_transformer"}}]

    antwoord, bewaren = _accepteer(app_with_overrides, opmaak)

    assert (antwoord.get("type"), bewaren.await_count) == ("proposal_accepted", 1), antwoord
