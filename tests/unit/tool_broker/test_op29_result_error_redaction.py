"""Gedragsbewijs dat tool-resultaat en foutmelding niet meer rauw naar sinks gaan (ADR-036 OP-29).

Zelfde opzet als `test_pseudonymisation_leaks.py` (de OP-27-tegenhanger, INVOER in plaats van
RESULTAAT/FOUT): op gedragsniveau via `ToolBrokerService.execute_tool`, niet rechtstreeks op
`redaction.digest_result`/`value_digest`, zodat de test onafhankelijk blijft van welke functie
precies de redactie doet.

`test__echo` echoot zijn hele payload terug onder `result["echo"]` (`test_tools.py::test_echo`).
Een PII-waarde die daar nog verbatim in staat, bewijst dat het RESULTAAT ongefilterd naar de
event-bus/leeropslag-sink is gegaan -- exact de OP-29-bevinding.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService

PERSONAL_VALUE = "jan.jansen@acme.nl"


class _UnusedClient:
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
    """Zie test_pseudonymisation_leaks.py: zonder dit lekt de tenant naar latere tests (OP-20)."""
    set_tenant_id(None)
    yield
    set_tenant_id(None)


def _service(publisher: AsyncMock) -> ToolBrokerService:
    return ToolBrokerService(
        serena_client=_UnusedClient(),
        seq_thinking_client=_UnusedClient(),
        local_registry=LocalToolRegistry(),
        event_publisher=publisher,
        enable_resilience=False,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheResultIsNeverPublishedRaw:
    async def test_a_result_that_echoes_the_payload_is_not_readable(self) -> None:
        """`test__echo` zet de PII-waarde in zijn resultaat; die hoort niet leesbaar te blijven."""
        set_tenant_id(1)
        publisher = AsyncMock()
        service = _service(publisher)

        await service.execute_tool("test__echo", {"message": PERSONAL_VALUE}, agent_id="agent-1")
        await asyncio.sleep(0)

        event = publisher.publish.await_args.args[0]
        assert PERSONAL_VALUE not in str(event.data["result"]), (
            "Het resultaat staat leesbaar in de gepubliceerde event-data. `test__echo` echoot "
            "zijn payload in het resultaat, en dat resultaat gaat ongefilterd naar de event bus "
            "en de leeropslag -- exact de OP-29-bevinding."
        )
        assert event.data["result"] != {
            "echo": {"message": PERSONAL_VALUE},
        }, "Het resultaat is structureel gelijk aan de rauwe waarde -- geen digest toegepast."

    async def test_the_result_digest_is_tenant_scoped(self) -> None:
        """Dezelfde bevinding als bij de payload (OP-27): geen gedeelde scope tussen tenants."""
        publisher_a = AsyncMock()
        set_tenant_id(1)
        service_a = _service(publisher_a)
        await service_a.execute_tool("test__echo", {"message": PERSONAL_VALUE}, agent_id="agent-1")
        await asyncio.sleep(0)
        result_a = publisher_a.publish.await_args.args[0].data["result"]

        publisher_b = AsyncMock()
        set_tenant_id(2)
        service_b = _service(publisher_b)
        await service_b.execute_tool("test__echo", {"message": PERSONAL_VALUE}, agent_id="agent-1")
        await asyncio.sleep(0)
        result_b = publisher_b.publish.await_args.args[0].data["result"]

        assert result_a != result_b, (
            "Dezelfde resultaatwaarde geeft in twee tenants dezelfde digest -- correleerbaar "
            "over de tenantgrens, in strijd met ADR-003/004/005."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheErrorIsNeverPublishedRaw:
    async def test_an_unexpected_exception_message_is_not_readable(self) -> None:
        """Het `except Exception as exc: ... str(exc)`-pad, met een PII-waarde in de melding.

        Een `ToolBrokerException` (bv. via `test__fail`) publiceert al een vaste, veilige
        `"tool_broker_error"`-tekst en bewijst dus niets over dit pad; het gaat hier om een
        ONVERWACHTE fout, waarbij `str(exc)` voorheen ongefilterd de event-data in ging.
        """
        set_tenant_id(1)
        publisher = AsyncMock()
        service = _service(publisher)

        with patch.object(
            service.local_registry,
            "execute_local_tool",
            AsyncMock(side_effect=RuntimeError(f"lookup failed for {PERSONAL_VALUE}")),
        ):
            with pytest.raises(Exception):
                await service.execute_tool("test__echo", {"message": "hi"}, agent_id="agent-1")
        await asyncio.sleep(0)

        event = publisher.publish.await_args.args[0]
        assert PERSONAL_VALUE not in str(event.data["error"]), (
            "De foutmelding staat leesbaar in de gepubliceerde event-data. `str(exc)` kan de "
            "waarde echoen die de fout veroorzaakte -- exact de OP-29-bevinding."
        )

    async def test_an_hr_tool_reported_failure_message_is_not_readable(self) -> None:
        """Het HR-registry-pad heeft een EIGEN foutafhandeling (`tool_error`), los van except.

        `hr_registry.execute_hr_tool` kan `{"success": False, "error": "..."}` teruggeven
        zonder een exceptie te gooien; `service.py` zet dat om in `tool_error` en publiceert
        dat apart (Gate 2-review BE-AGT-044, MEDIUM-A).
        """
        set_tenant_id(1)
        publisher = AsyncMock()
        service = _service(publisher)

        with patch.object(
            service,
            "hr_registry",
            AsyncMock(
                execute_hr_tool=AsyncMock(
                    return_value={
                        "success": False,
                        "error": f"denied for {PERSONAL_VALUE}",
                    }
                ),
                known_tool_names=lambda: frozenset({"query_hr_database"}),
            ),
        ):
            with patch(
                "src.core.tool_broker.service.HRToolRegistry.known_tool_names",
                return_value=frozenset({"query_hr_database"}),
            ):
                await service.execute_tool(
                    "query_hr_database",
                    {"role": "Finance Analyst"},
                    agent_id="agent-1",
                    context={"tenant_id": 1},
                )
        await asyncio.sleep(0)

        event = publisher.publish.await_args.args[0]
        assert PERSONAL_VALUE not in str(event.data["error"]), (
            "De door de HR-tool teruggegeven foutmelding staat leesbaar in de event-data."
        )
