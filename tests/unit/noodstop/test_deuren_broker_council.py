"""De deuren weigeren een stilgezette klant: broker en Council (noodstop per klant, ADR-036 OP-03).

Klant 1 staat stil, klant 2 is actief. De lezer van de stand is de enige vervanging (de grens).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.types import (
    DataClassification,
    DecisionVerdict,
    Proposal,
    ProposalTrigger,
)
from src.core.noodstop import guard
from src.core.noodstop.guard import MELDING_ONBEKEND, MELDING_STIL
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.service import ToolBrokerService

STIL, ACTIEF = 1, 2


@pytest.fixture
def klant_1_staat_stil(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    gevraagd: list[int] = []

    async def lezer(tenant_id: int) -> bool:
        gevraagd.append(tenant_id)
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)
    return gevraagd


class _Client:
    async def call(self, tool_name: str, payload: dict) -> dict:
        return {"result": "ok"}


def _broker() -> ToolBrokerService:
    return ToolBrokerService(
        serena_client=_Client(), seq_thinking_client=_Client(), enable_resilience=False
    )


@pytest.mark.asyncio
async def test_broker_weigert_de_stilgezette_klant_met_een_nederlandse_melding(
    klant_1_staat_stil: list[int],
) -> None:
    with pytest.raises(ToolExecutionException) as fout:
        await _broker().execute_tool(
            tool_name="create_task",
            payload={"title": "x"},
            agent_id="copilot",
            context={"tenant_id": STIL},
        )
    assert MELDING_STIL in str(fout.value.detail)


@pytest.mark.asyncio
async def test_broker_weigert_fail_closed_als_de_stand_niet_te_lezen_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def kapot(tenant_id: int) -> bool:
        raise ConnectionError("database weg")

    monkeypatch.setattr(guard, "_lees_stand", kapot)
    with pytest.raises(ToolExecutionException) as fout:
        await _broker().execute_tool(
            tool_name="create_task",
            payload={"title": "x"},
            agent_id="copilot",
            context={"tenant_id": ACTIEF},
        )
    assert MELDING_ONBEKEND in str(fout.value.detail)


@pytest.mark.asyncio
async def test_broker_vraagt_de_stand_van_de_klant_uit_de_context(
    klant_1_staat_stil: list[int],
) -> None:
    with pytest.raises(ToolExecutionException):
        await _broker().execute_tool(
            tool_name="create_task",
            payload={"tenant_id": ACTIEF, "title": "x"},
            agent_id="copilot",
            context={"tenant_id": STIL},
        )
    assert klant_1_staat_stil == [STIL]


def _voorstel(tenant_id: int) -> Proposal:
    return Proposal(
        tenant_id=tenant_id,
        user_id=7,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="navigate_to",
        action_params={"route": "/dashboard"},
        reasoning="test",
        data_classification=DataClassification.INTERNAL,
        confidence=0.9,
        model_id="m",
        model_version="1",
        context_snapshot={},
        timestamp=datetime.now(timezone.utc),
    )


def _raad() -> tuple[AgentCouncil, dict[str, MagicMock]]:
    namen = ["compliance", "privacy", "security", "risk", "ethics", "resource", "sanity", "audit"]
    officers = {
        n: MagicMock(
            deliberate=AsyncMock(), can_cache=MagicMock(return_value=False), timeout_ms=500
        )
        for n in namen
    }
    for o in officers.values():
        o.version = "1.0.0"
        o.health_check = MagicMock(return_value=True)
    return AgentCouncil(**officers), officers


@pytest.mark.asyncio
async def test_council_blokkeert_de_stilgezette_klant_zonder_te_beraadslagen(
    klant_1_staat_stil: list[int],
) -> None:
    raad, officers = _raad()
    besluit = await raad.deliberate(_voorstel(STIL))
    assert besluit.verdict == DecisionVerdict.BLOCKED
    assert besluit.explanation_for_user == MELDING_STIL
    assert all(o.deliberate.await_count == 0 for o in officers.values())


@pytest.mark.asyncio
async def test_council_laat_een_andere_klant_beraadslagen(klant_1_staat_stil: list[int]) -> None:
    raad, _ = _raad()
    besluit = await raad.deliberate(_voorstel(ACTIEF))
    assert besluit.decision_hash != "NOODSTOP"


def _geweigerd(deur: str) -> float:
    from src.core.noodstop.metrics import NOODSTOP_GEWEIGERD

    return NOODSTOP_GEWEIGERD.labels(deur=deur)._value.get()


@pytest.mark.asyncio
async def test_een_noodstopweigering_door_de_council_wordt_geteld_en_gelogd(
    klant_1_staat_stil: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    raad, _ = _raad()
    voor = _geweigerd("council")
    with caplog.at_level("WARNING"):
        await raad.deliberate(_voorstel(STIL))
    assert _geweigerd("council") == voor + 1
    regels = [
        r for r in caplog.records if "council" in r.getMessage() and "noodstop" in r.getMessage()
    ]
    assert regels, "de Council logt zijn noodstopweigering niet"
    assert getattr(regels[0], "tenant_id", None) == STIL


@pytest.mark.asyncio
async def test_een_beraadslaging_van_een_actieve_klant_telt_niet(
    klant_1_staat_stil: list[int],
) -> None:
    raad, _ = _raad()
    voor = _geweigerd("council")
    await raad.deliberate(_voorstel(ACTIEF))
    assert _geweigerd("council") == voor
