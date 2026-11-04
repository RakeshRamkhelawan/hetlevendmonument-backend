"""De sinks die bij ronde 1 niet geteld waren (BE-AGT-045 ronde 2, ADR-036 OP-27).

Twee bevindingen uit de tweede Gate 2-ronde:

**Een vijfde sink.** `tool_execution_history` (`api/v1/tool_broker_shared.py`) bewaart payload en
resultaat verbatim in een proces-globale, ongelimiteerde dict en geeft die terug via
`GET /api/v1/tools/history/recent`. Die stond in geen enkele telling: de architectuur-guard
bewaakt AANROEPEN van sinks, en dit is een dict-assignment. Vier sinks waren geteld, vijf waren
er.

**De HITL-koppeling hing aan het overleven van een payload-sleutel.** `log_execution` heeft een
eigen kolom `hitl_ticket_ref`, en de broker vulde die nooit. De koppeling tussen auditregel en
goedkeurend ticket bestond dus alleen zolang `_hitl_ticket_ref` leesbaar in `tool_input` bleef
staan -- wat op zijn beurt de reden was om die sleutelnaam altijd-leesbaar te verklaren. Een
naamgedreven uitzondering in een PII-filter, om een kolom te vervangen die er al was.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker.business_registry import BusinessToolRegistry
from src.core.tool_broker.service import ToolBrokerService

PERSONAL_VALUE = "jan.jansen@acme.nl"


class _UnusedClient:
    """Stub voor de externe clients: deze tests raken alleen business-tools."""

    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"externe client onverwacht aangeroepen voor {tool_name}")


@pytest.fixture(autouse=True)
def _allow_all_tools() -> Iterator[None]:
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


@pytest.fixture(autouse=True)
def _clean_tenant_context() -> Iterator[None]:
    set_tenant_id(None)
    yield
    set_tenant_id(None)


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheAuditRowLinksItsTicketThroughItsOwnColumn:
    async def test_log_execution_receives_the_approved_ticket_reference(self) -> None:
        """De koppeling auditregel-ticket hoort in de kolom die daarvoor bestaat.

        `ToolAuditLog.hitl_ticket_ref` is geindexeerd en bestaat precies hiervoor. Zolang de
        broker hem niet vulde, hing de koppeling aan het leesbaar blijven van een
        payload-sleutel -- en dat was het argument om die sleutelnaam altijd-leesbaar te
        verklaren. Kolom vullen maakt de naamuitzondering overbodig.
        """
        task_service = AsyncMock()
        task_service.delete = AsyncMock(return_value=True)

        @asynccontextmanager
        async def _mock_session() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        registry = BusinessToolRegistry(
            session_factory=_mock_session,
            task_service_factory=cast(Any, lambda session, tenant_id: task_service),
        )

        audit_repo = AsyncMock()
        audit_repo.tenant_id = 7  # gebonden aan de klant van de aanroep
        audit_repo.get_last_audit_hash = AsyncMock(return_value="genesis")

        hitl_store = AsyncMock()
        hitl_store.get_approval_status = AsyncMock(return_value="approved")

        service = ToolBrokerService(
            serena_client=_UnusedClient(),
            seq_thinking_client=_UnusedClient(),
            business_registry=registry,
            enable_resilience=False,
            audit_repository=audit_repo,
            db_session=cast(Any, AsyncMock()),
            hitl_store=hitl_store,
        )

        # `AuditService.log_action` is de ANDERE auditlaag (business-actie, ADR-019
        # audit_logs-tabel) en opent een geneste transactie op de sessie. Die is hier niet het
        # onderwerp; zonder deze patch struikelt de test daarop voordat `log_execution` -- de
        # tool-auditregel waar het hier om gaat -- ooit wordt bereikt.
        with patch(
            "src.core.governance.audit.AuditService.log_action",
            new_callable=AsyncMock,
        ):
            await service.execute_tool(
                tool_name="delete_task",
                payload={"task_id": str(uuid4()), "_hitl_ticket_ref": "TOOL-approved-007"},
                agent_id="copilot",
                context={"tenant_id": 7},
            )
            await asyncio.sleep(0.05)

        audit_repo.log_execution.assert_awaited()
        kwargs = audit_repo.log_execution.await_args.kwargs

        assert kwargs.get("hitl_ticket_ref") == "TOOL-approved-007", (
            "De auditregel legt het goedgekeurde ticket niet vast in zijn eigen kolom. De "
            "koppeling bestaat dan alleen zolang `_hitl_ticket_ref` leesbaar in `tool_input` "
            "overleeft, en dat is precies de naamgedreven uitzondering die dit lek veroorzaakte."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheFifthSink:
    @pytest.fixture(autouse=True)
    def _empty_history(self) -> Iterator[None]:
        """De geschiedenis is proces-globaal; leegmaken voor EN na."""
        from src.core.api.v1.tool_broker_shared import tool_execution_history

        tool_execution_history.clear()
        yield
        tool_execution_history.clear()

    async def test_the_in_memory_history_stores_no_raw_payload(self) -> None:
        """`/api/v1/tools/history/recent` geeft de opgeslagen regel ongefilterd terug.

        Die regel wordt weggeschreven in een `finally` en bevat de payload verbatim. Elke
        gebruiker van dezelfde tenant met `AGENTS_READ` kan hem daarna uitlezen, en de dict is
        proces-globaal en ongelimiteerd: hij leeft tot de worker recyclet (ADR-011).
        """
        from src.core.api.v1.tool_broker import execution_router
        from src.core.api.v1.tool_broker_shared import (
            ToolExecutionRequest,
            tool_execution_history,
        )

        service = AsyncMock()
        service.execute_tool = AsyncMock(return_value={"ok": True})

        current_user = MagicMock()
        current_user.id = 42
        current_user.tenant_id = 1

        await execution_router.execute_tool(
            request=ToolExecutionRequest(tool_name="serena", payload={"note": PERSONAL_VALUE}),
            service=cast(Any, service),
            current_user=cast(Any, current_user),
            _=1,
        )

        stored = list(tool_execution_history.values())
        assert stored, "er is niets vastgelegd -- dan toetst deze test niets"

        assert PERSONAL_VALUE not in str(stored[0].get("payload")), (
            "De payload staat verbatim in de proces-globale geschiedenis en is via "
            "GET /api/v1/tools/history/recent uitleesbaar. Dit is de vijfde bewarende sink; "
            "de architectuur-guard zag hem niet omdat het een dict-assignment is en geen "
            "aanroep."
        )

    async def test_the_error_field_does_not_carry_the_raw_payload(self) -> None:
        """Het `payload`-veld is geredigeerd, maar `error` in DEZELFDE regel was dat niet.

        `clients.py` zet de rauwe payload in de `context` van een `MCPProtocolError`. Die
        exceptie is een `HTTPException`, dus `str(e)` rendert `detail` inclusief die context.
        `execution_router.py` zet dat als `error_msg` in de opgeslagen regel -- de regel waarvan
        het `payload`-veld net geredigeerd is. Uitleesbaar via
        `GET /api/v1/tools/history/recent` voor elke gebruiker van dezelfde tenant met
        `AGENTS_READ`, en het gaat ook mee in het HTTP-500-antwoord.

        Dit viel tussen twee guards door: de OP-29-guard bewaakt `error_detail`, en deze regel
        gebruikt de sleutel `error`. Derde keer in deze reeks dat een sink werd gemist omdat een
        naamlijst een token te kort was.
        """
        from src.core.api.v1.tool_broker import execution_router
        from src.core.api.v1.tool_broker_shared import (
            ToolExecutionRequest,
            tool_execution_history,
        )
        from src.core.tool_broker.exceptions import MCPProtocolError

        def _raise_with_raw_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise MCPProtocolError(
                server_name="serena",
                protocol_error="Unexpected error: boom",
                context={"tool_name": "serena", "payload": {"note": PERSONAL_VALUE}},
            )

        service = AsyncMock()
        service.execute_tool = AsyncMock(side_effect=_raise_with_raw_payload)

        current_user = MagicMock()
        current_user.id = 42
        current_user.tenant_id = 1

        with pytest.raises(Exception):
            await execution_router.execute_tool(
                request=ToolExecutionRequest(tool_name="serena", payload={"note": PERSONAL_VALUE}),
                service=cast(Any, service),
                current_user=cast(Any, current_user),
                _=1,
            )

        stored = list(tool_execution_history.values())
        assert stored, "er is niets vastgelegd -- dan toetst deze test niets"

        assert PERSONAL_VALUE not in str(stored[0].get("error")), (
            "De rauwe payload staat via het `error`-veld alsnog in de proces-globale "
            "geschiedenis, en is daarmee uitleesbaar via de API. Het redigeren van het "
            "`payload`-veld in dezelfde regel is dan een formaliteit."
        )
