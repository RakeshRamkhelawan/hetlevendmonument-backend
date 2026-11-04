"""De poort bouwt het voorstel dat de officieren daadwerkelijk zien (SP-COUNCIL-GATE-001).

Uit de Gate 2-review, als goedkoopste vals-groene route benoemd: een test die alleen de kwargs
van een gepatchte `request_council_decision_for_agent` inspecteert, is groen zodra de aanroeper
`message=` meestuurt -- ook als de poort dat argument vervolgens niet aan `Proposal(...)`
doorgeeft. De SanityOfficer ziet dan nog steeds een leeg bericht en vetoot, terwijl alles groen
staat.

Deze tests kijken daarom naar het OBJECT dat de raad krijgt voorgelegd, niet naar de aanroep.
`AgentCouncil.deliberate` wordt vervangen door een opnemer; de poort zelf draait echt.

Ook getoetst: de twee eigenschappen die de officieren per stuk beoordelen komen mee -- de
bekendmaking (ComplianceOfficer) en de tenant (SecurityOfficer, via `user_has_scope_for`).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

TENANT = 4401
GEBRUIKER = 4402


@contextlib.asynccontextmanager
async def _geen_sessie() -> AsyncIterator[Any]:
    """De poort opent een databasesessie; die is hier niet nodig en niet beschikbaar."""
    yield AsyncMock()


async def _voorstel_van_de_poort(**overrides: Any) -> Any:
    """Draai de ECHTE poort en geef het `Proposal` terug dat de raad kreeg."""
    from src.core.copilot.council.types import DecisionVerdict, ProposalTrigger

    besluit: Any = AsyncMock()
    besluit.verdict = DecisionVerdict.APPROVED
    besluit.decision_id = "d-1"

    raad = AsyncMock()
    raad.deliberate = AsyncMock(return_value=besluit)

    from src.core.copilot.council import background_gate

    argumenten: dict[str, Any] = {
        "tenant_id": TENANT,
        "agent_id": "skillsgaptraining",
        "user_id": GEBRUIKER,
        "action_type": "query_hr_database",
        "action_params": {"tool": "query_hr_database", "ai_disclosure": "bekendmaking"},
        "reasoning": "reden",
        "message": "Agent skillsgaptraining vraagt toestemming voor query_hr_database.",
        "trigger": ProposalTrigger.USER_REQUEST,
    }
    argumenten.update(overrides)

    with (
        patch.object(background_gate, "get_db_session", _geen_sessie),
        patch.object(background_gate, "build_council", AsyncMock(return_value=raad)),
    ):
        await background_gate.request_council_decision_for_agent(**argumenten)

    assert raad.deliberate.await_count == 1, "De raad heeft geen voorstel gekregen."
    aanroep = raad.deliberate.await_args
    assert aanroep is not None
    return aanroep.args[0]


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheProposalTheCouncilActuallySees:
    async def test_the_message_reaches_the_proposal(self) -> None:
        """Het bericht moet op het VOORSTEL staan, niet alleen in de aanroep van de poort.

        Zonder deze test kan `message` als parameter bestaan en toch nergens landen; de
        SanityOfficer leest `proposal.message` en niets anders.
        """
        voorstel = await _voorstel_van_de_poort()

        assert voorstel.message, (
            "Het voorstel draagt geen bericht. `HallucinationGuard.check()` geeft dan "
            "`empty_suggestion` en de SanityOfficer vetoot -- precies de blokkade die deze dag "
            "oplost."
        )
        assert "query_hr_database" in voorstel.message

    async def test_the_disclosure_reaches_the_proposal(self) -> None:
        voorstel = await _voorstel_van_de_poort()

        assert voorstel.action_params.get("ai_disclosure"), (
            "De bekendmaking staat niet op het voorstel; de ComplianceOfficer vraagt dan een "
            "aanpassing die deze poort niet kan toepassen."
        )

    async def test_the_tenant_reaches_the_proposal(self) -> None:
        """De SecurityOfficer haalt de tenant hiervandaan voor zijn rechtencontrole."""
        voorstel = await _voorstel_van_de_poort()

        assert voorstel.tenant_id == TENANT
        assert voorstel.user_id == GEBRUIKER


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheGateDoesNotInventContent:
    async def test_an_empty_message_stays_empty(self) -> None:
        """De poort mag geen bericht verzinnen als de aanroeper er geen geeft.

        De andere richting: zou de poort zelf een tekst invullen, dan zou elke aanroeper
        automatisch door de SanityOfficer komen en is die officier uitgezet in plaats van
        tevredengesteld door de aanroeper die er verantwoordelijk voor is.
        """
        voorstel = await _voorstel_van_de_poort(message="")

        assert voorstel.message == ""
