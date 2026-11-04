"""Wat doet de debiteurenagent met `hotl`, en wat met `hitl`? (besluit 4 van dag 1, gemeten dag 2)

Besluit 4 van dag 1 was een HYPOTHESE: met `hotl` en een goedkeurend Council-verdict komt er
geen ticket en blijft de verzendactie hangen. Deze module meet dat EERST, met de echte
`ToolBrokerService` van de skill (geen brokerdubbel in de eerste test), en legt daarna vast wat
`hitl` doet.

Autouse in deze boom (`tests/unit/als/conftest.py` via `tests/fixtures/agent_governance.py`):
`council_gate` geeft APPROVED en `prana_guard` is een stub. Dat is hier precies de opstelling die
de hypothese noemt ("goedkeurend Council-verdict"); de Council zelf wordt niet gemeten.
`hitl_ticket_repository` vervangt `create_hitl_request` en de databasesessie, zodat te zien is
OF en MET WELKE parameters er een ticket wordt aangevraagd.

Het taalmodel is een scriptdubbel: hij geeft een vaste TOOL_CALL terug. Het voorbeeld van de
brief (`preview_payment_reminder`) leest normaal de database; hier een vaste waarde, want het
onderwerp van deze module is de route, niet het sjabloon (dat meet
`tests/unit/tool_broker/test_receivables_registry.py`).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.llm_dubbel import als_async

TENANT = 1
INITIATOR = 42

_VOORBEELD = {
    "success": True,
    "params": {
        "receivable_id": 7,
        "kind": "herinnering",
        "recipient_email": "klant@voorbeeld.example",
        "subject": "Herinnering: factuur F-7",
        "body": "Beste klant, ...",
    },
}

#: Het model probeert zelf een tekst en een ontvanger mee te geven. Die moeten worden
#: overschreven door het sjabloon -- anders keurt de mens een brief van het model goed.
_VERSTUREN = (
    'TOOL_CALL: send_payment_reminder {"receivable_id": 7, "kind": "herinnering", '
    '"body": "BETAAL NU", "recipient_email": "aanvaller@elders.example"}'
)
_LEZEN = 'TOOL_CALL: list_receivables {"status": "open"}'


@pytest.fixture(autouse=True)
def vorderingen_tellen_zonder_database() -> Iterator[AsyncMock]:
    """`execute_with_manifest_prompt` telt na elke run de openstaande vorderingen (`_tel_openstaand`).

    Dat gaat via `ReceivablesToolRegistry.execute_receivables_tool` naar de ECHTE database
    (`db_manager.get_session()` -> `initialize()`), terwijl deze module de route meet en niet de
    telling. Gemeten 2026-10-24: met een databaseadres op poort 5432 (zoals CI) geven vier van de vijf
    tests `EchteVerbindingInUnitTest`; slagen deed het alleen als het adres toevallig nergens heen wees.
    De netwerkblokkade blijft zoals hij is; de database-grens wordt hier vervangen door een lege lijst.
    """
    with patch(
        "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
        "execute_receivables_tool",
        AsyncMock(return_value={"success": True, "receivables": []}),
    ) as dubbel:
        yield dubbel


@pytest.fixture(autouse=True)
def geweigerde_poging_loggen_zonder_database() -> Iterator[AsyncMock]:
    """De broker schrijft een geweigerde poging naar het toollogboek (`_audit_blocked_attempt`).

    Sinds F7 (toolbroker-logboek aangesloten) heeft de broker van de skill een
    `audit_session_factory=db_manager.get_session`, dus de weigering in `TestHotl` opende een ECHTE
    databasesessie en liep tegen `EchteVerbindingInUnitTest` aan (gemeten 2026-11-02, pre-push).
    Deze module meet de route, niet het logboek (dat meet `tests/unit/tool_broker`). De grens wordt
    hier vervangen door een dubbel, zodat ook vast te stellen is DAT de weigering gelogd wordt.
    """
    with patch(
        "src.core.tool_broker.service.ToolBrokerService._audit_blocked_attempt",
        AsyncMock(return_value=None),
    ) as dubbel:
        yield dubbel


def _agent(antwoord: str, **overrides: Any) -> Any:
    from src.core.als.agents.skills.dunning import DunningSkill

    agent = DunningSkill(tenant_id=TENANT, **overrides)
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=antwoord)
    agent._get_llm_service = als_async(llm)  # type: ignore[method-assign]
    return agent


def _voorbeeld_patch() -> Any:
    return patch(
        "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
        "preview_payment_reminder",
        AsyncMock(return_value=_VOORBEELD),
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestHotl:
    async def test_hotl_creates_no_ticket_and_the_broker_refuses_the_send(
        self,
        hitl_ticket_repository: AsyncMock,
        geweigerde_poging_loggen_zonder_database: AsyncMock,
    ) -> None:
        """De meting achter besluit 4: met `hotl` krijgt een mens NOOIT iets te zien.

        De Council keurt goed, er is geen vloer, de skill roept de echte broker aan, en die
        weigert de HIGH-risk tool omdat er geen goedgekeurd ticket is. Er wordt ook geen ticket
        aangemaakt: de actie verdwijnt in een foutmelding in plaats van bij een mens.
        """
        agent = _agent(_VERSTUREN, human_in_the_loop="hotl")
        with _voorbeeld_patch():
            resultaat = await agent.execute_with_manifest_prompt(
                {"task": "herinner de klant"}, initiated_by_user_id=INITIATOR
            )

        fouten = resultaat.result_data["errors"]
        assert hitl_ticket_repository.create_hitl_request.await_count == 0
        assert [f["kind"] for f in fouten] == ["tool_exception"]
        assert "requires human approval" in fouten[0]["error"]
        # De weigering verdwijnt niet spoorloos: er is precies een logboekregel aangevraagd.
        logregel = geweigerde_poging_loggen_zonder_database.await_args.kwargs
        assert geweigerde_poging_loggen_zonder_database.await_count == 1
        assert logregel["tool_name"] == "send_payment_reminder"


@pytest.mark.unit
@pytest.mark.asyncio
class TestHitl:
    async def test_the_manifest_is_hitl(self) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        assert DunningSkill(tenant_id=TENANT).config["human_in_the_loop"] == "hitl"

    async def test_a_send_becomes_a_ticket_with_the_letter_from_the_template(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        agent = _agent(_VERSTUREN)
        with _voorbeeld_patch():
            await agent.execute_with_manifest_prompt(
                {"task": "herinner de klant"}, initiated_by_user_id=INITIATOR
            )

        kwargs = hitl_ticket_repository.create_hitl_request.await_args.kwargs
        assert (kwargs["action_type"], kwargs["executing_identity"], kwargs["action_params"]) == (
            "send_payment_reminder",
            "dunning",
            _VOORBEELD["params"],
        )

    async def test_a_read_needs_no_ticket(self, hitl_ticket_repository: AsyncMock) -> None:
        """Niet-Annex-III: alleen een HIGH-risk actie gaat langs de vloer, lezen niet."""
        agent = _agent(_LEZEN)
        broker = AsyncMock()
        broker.execute_tool = AsyncMock(return_value={"success": True, "receivables": []})
        agent.tools = broker  # type: ignore[attr-defined]

        await agent.execute_with_manifest_prompt(
            {"task": "welke facturen staan open"}, initiated_by_user_id=INITIATOR
        )

        assert hitl_ticket_repository.create_hitl_request.await_count == 0
        broker.execute_tool.assert_awaited_once()

    async def test_an_unknown_receivable_never_reaches_the_council(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        agent = _agent(_VERSTUREN)
        with patch(
            "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
            "preview_payment_reminder",
            AsyncMock(return_value={"success": False, "error": "bestaat niet"}),
        ):
            resultaat = await agent.execute_with_manifest_prompt(
                {"task": "herinner"}, initiated_by_user_id=INITIATOR
            )

        assert council_gate.await_count == 0
        assert resultaat.result_data["errors"][0]["kind"] == "tool_failure"
