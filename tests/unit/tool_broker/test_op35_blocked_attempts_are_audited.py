"""Een geweigerde tool-aanroep laat een auditspoor achter (ADR-036 OP-35).

`execute_tool` had 4 fail-closed weigeringen (permissie, onbekende toolcategorie, ontbrekende
`hitl_store`, ongeldig/ontbrekend HITL-ticket) die VOOR de audit-schrijvende `try`/`finally`
lagen. Precies de gebeurtenissen die het meest waard zijn om te loggen -- een geweigerde poging
-- lieten daardoor geen spoor achter: `ToolAuditRepository.log_execution` werd nooit met
`status="blocked"` aangeroepen, en `get_blocked_tools_count()` toonde daardoor altijd nul.

Op GEDRAGSNIVEAU geschreven, via `ToolBrokerService.execute_tool` en een gemockte
`ToolAuditRepository` -- niet via `_audit_blocked_attempt` rechtstreeks -- zodat de test blijft
gelden als de interne opbouw van de methode verandert. Elke test dekt EEN van de vier
weigeringspunten (project-conventie: een genoemde verzameling van vier plekken vereist een
mutatiebewijs per element, niet een enkele steekproef die als representatief wordt aangenomen).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService


class _UnusedClient:
    """Stub voor de externe clients: geen van deze paden voert een tool daadwerkelijk uit."""

    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError(f"externe client onverwacht aangeroepen voor {tool_name}")


@pytest.fixture(autouse=True)
def _clean_tenant_context() -> Iterator[None]:
    """De tenant-ContextVar opruimen voor EN na (zie OP-20)."""
    from src.core.middleware.tenant_context import set_tenant_id

    set_tenant_id(None)
    yield
    set_tenant_id(None)


def _make_service(
    *,
    permission_allowed: bool,
    hitl_store: Any | None = None,
) -> tuple[ToolBrokerService, AsyncMock]:
    audit_repository = AsyncMock()
    audit_repository.tenant_id = 1  # gebonden aan de klant van de aanroep
    audit_repository.get_last_audit_hash = AsyncMock(return_value=None)
    permission_manager = AsyncMock()
    permission_manager.is_tool_allowed = lambda *_args, **_kwargs: permission_allowed
    service = ToolBrokerService(
        serena_client=_UnusedClient(),
        seq_thinking_client=_UnusedClient(),
        local_registry=LocalToolRegistry(),
        event_publisher=AsyncMock(),
        enable_resilience=False,
        audit_repository=audit_repository,
        db_session=AsyncMock(),
        hitl_store=hitl_store,
        permission_manager=permission_manager,
    )
    return service, audit_repository


@pytest.mark.unit
@pytest.mark.asyncio
class TestAPermissionDenialIsAudited:
    async def test_a_permission_denial_writes_a_blocked_audit_row(self) -> None:
        service, audit_repository = _make_service(permission_allowed=False)

        with pytest.raises(ToolExecutionException):
            await service.execute_tool(
                "test__echo",
                {"message": "hallo"},
                agent_id="agent-1",
                context={"tenant_id": 1},
            )

        audit_repository.log_execution.assert_awaited_once()
        assert audit_repository.log_execution.await_args.kwargs["status"] == "blocked"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAnUnknownToolCategoryIsAudited:
    async def test_an_unknown_tool_category_writes_a_blocked_audit_row(self) -> None:
        service, audit_repository = _make_service(permission_allowed=True)

        with pytest.raises(ToolExecutionException):
            await service.execute_tool(
                "totally_unknown_tool_category",
                {"message": "hallo"},
                agent_id="agent-1",
                context={"tenant_id": 1},
            )

        audit_repository.log_execution.assert_awaited_once()
        assert audit_repository.log_execution.await_args.kwargs["status"] == "blocked"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAMissingHitlStoreIsAudited:
    async def test_a_missing_hitl_store_writes_a_blocked_audit_row(self) -> None:
        # "test__echo" zelf is LOW risico (tool_risk_levels.yml), maar de HITL-poort vuurt ook
        # zodra de aanroeper zelf een ticketverwijzing aanbiedt (ADR-036 OP-89) -- ongeacht het
        # risiconiveau. Dat is genoeg om deze weigering te bereiken zonder een HIGH-risico-tool
        # nodig te hebben.
        service, audit_repository = _make_service(permission_allowed=True, hitl_store=None)

        with pytest.raises(ToolExecutionException):
            await service.execute_tool(
                "test__echo",
                {"message": "hallo", "_hitl_ticket_ref": "any-ticket-ref"},
                agent_id="agent-1",
                context={"tenant_id": 1},
            )

        audit_repository.log_execution.assert_awaited_once()
        assert audit_repository.log_execution.await_args.kwargs["status"] == "blocked"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAnInvalidHitlTicketIsAudited:
    async def test_an_invalid_hitl_ticket_writes_a_blocked_audit_row(self) -> None:
        hitl_store = AsyncMock()
        hitl_store.redeem_approval = AsyncMock(return_value=False)
        service, audit_repository = _make_service(permission_allowed=True, hitl_store=hitl_store)

        with pytest.raises(ToolExecutionException):
            await service.execute_tool(
                "test__echo",
                {"message": "hallo", "_hitl_ticket_ref": "not-a-real-ticket"},
                agent_id="agent-1",
                context={"tenant_id": 1},
            )

        audit_repository.log_execution.assert_awaited_once()
        assert audit_repository.log_execution.await_args.kwargs["status"] == "blocked"
