"""Een mislukte toolauditregel wordt geteld en de achtergrondtaak wordt vastgehouden.

Bundel logboekketens (brief 2026-10-22, punt 4). De auditregel wordt op de achtergrond
geschreven (`asyncio.create_task`). Gemeten: een fout daarin werd wel gelogd (`best_effort`)
maar nergens geteld, en de taak had geen andere verwijzing dan de zwakke van de gebeurtenislus.
Wat er met de toolactie zelf gebeurt als de auditregel faalt, is niet veranderd: best effort.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.metrics import TOOL_AUDIT_WRITE_FAILURES
from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker import service as service_module
from src.core.tool_broker.business_registry import BusinessToolRegistry
from src.core.tool_broker.service import ToolBrokerService


class _UnusedClient:
    pass


@pytest.fixture(autouse=True)
def _tenant() -> Iterator[None]:
    set_tenant_id(7)
    yield
    set_tenant_id(None)


def _teller(fout: str) -> float:
    return float(TOOL_AUDIT_WRITE_FAILURES.labels(error_type=fout)._value.get())


def _service(audit_repo: AsyncMock) -> ToolBrokerService:
    task_service = AsyncMock()
    task_service.delete = AsyncMock(return_value=True)

    @asynccontextmanager
    async def _sessie() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    registry = BusinessToolRegistry(
        session_factory=_sessie,
        task_service_factory=cast(Any, lambda session, tenant_id: task_service),
    )
    hitl_store = AsyncMock()
    hitl_store.get_approval_status = AsyncMock(return_value="approved")
    return ToolBrokerService(
        serena_client=_UnusedClient(),
        seq_thinking_client=_UnusedClient(),
        business_registry=registry,
        enable_resilience=False,
        audit_repository=audit_repo,
        db_session=cast(Any, AsyncMock()),
        hitl_store=hitl_store,
    )


async def _voer_uit(service: ToolBrokerService) -> None:
    with patch("src.core.governance.audit.AuditService.log_action", new_callable=AsyncMock):
        await service.execute_tool(
            tool_name="delete_task",
            payload={"task_id": str(uuid4()), "_hitl_ticket_ref": "TOOL-approved-007"},
            agent_id="copilot",
            context={"tenant_id": 7},
        )
        await asyncio.sleep(0.1)


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenMislukteAuditregelWordtGeteld:
    async def test_a_failing_write_is_counted_and_the_tool_action_still_succeeds(self) -> None:
        audit_repo = AsyncMock()
        audit_repo.tenant_id = 7  # gebonden aan de klant van de aanroep
        audit_repo.log_execution = AsyncMock(side_effect=RuntimeError("db weg"))
        voor = _teller("RuntimeError")

        await _voer_uit(_service(audit_repo))

        assert _teller("RuntimeError") == voor + 1, "de mislukte auditregel is niet geteld"

    async def test_a_succeeding_write_is_not_counted(self) -> None:
        audit_repo = AsyncMock()
        audit_repo.tenant_id = 7  # gebonden aan de klant van de aanroep
        voor = _teller("RuntimeError")

        await _voer_uit(_service(audit_repo))

        audit_repo.log_execution.assert_awaited()
        assert _teller("RuntimeError") == voor

    async def test_the_background_task_is_held_until_it_is_done(
        self, audittaken_vooraf: None
    ) -> None:
        gate = asyncio.Event()
        audit_repo = AsyncMock()
        audit_repo.tenant_id = 7  # gebonden aan de klant van de aanroep

        async def _wacht(**_: object) -> None:
            await gate.wait()

        audit_repo.log_execution = AsyncMock(side_effect=_wacht)
        service = _service(audit_repo)
        # Gate 2 F7: alleen naar de eigen taak kijken. `_AUDIT_TASKS` is gedeeld op moduleniveau;
        # een taak van een andere test op dezelfde worker mag deze test niet laten omvallen.
        vooraf = set(service_module._AUDIT_TASKS)

        with patch("src.core.governance.audit.AuditService.log_action", new_callable=AsyncMock):
            await service.execute_tool(
                tool_name="delete_task",
                payload={"task_id": str(uuid4()), "_hitl_ticket_ref": "TOOL-approved-007"},
                agent_id="copilot",
                context={"tenant_id": 7},
            )
            await asyncio.sleep(0.05)
            eigen = set(service_module._AUDIT_TASKS) - vooraf
            assert len(eigen) == 1, "de achtergrondtaak wordt niet vastgehouden"
            (taak,) = eigen
            gate.set()
            await asyncio.sleep(0.05)

        assert taak.done(), "de achtergrondtaak is niet afgerond"
        assert taak not in service_module._AUDIT_TASKS, (
            "een klare taak blijft in de verzameling staan"
        )
