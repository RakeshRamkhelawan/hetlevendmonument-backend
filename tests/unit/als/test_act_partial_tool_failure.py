"""F3 -- een gedeeltelijk mislukte tool-reeks mag geen succes rapporteren (BE-AGT-039).

`BaseSpecialistAgent.act()` bepaalt succes met (`specialist_base.py`, aan het einde van
`act()`):

    success = not errors

Was `len(results) > 0 or len(errors) == 0`: bij twee tool-calls waarvan een slaagt en een
faalt gold `results=1, errors=1`, dus `success=True`. De ExecutionResult meldde succes terwijl
er een actie was mislukt.

Waarom dit meer is dan een rapportagekwestie: `_run_within_budget()` (`specialist_base.py:
512-520`) rekent na `act()` af op precies dat veld --

    if result.success:
        await guard.charge_prana(self.tenant_id, self.budget.prana_cost_limit)

-- dus de tenant betaalde voor werk dat deels niet is uitgevoerd. Niemand in `src/` leest
`result_data["errors"]`, dus er was geen tweede vangnet.

ADR-036 D7-001 (fix-sprint dag 7) voegt hier `result.status` aan toe: dezelfde boekhouding
(`results`/`errors`) bepaalt nu ook een van de vijf statuscontract-waarden, zie de losse
`assert result.status == ...` per test hieronder.

Randgevallen die NIET mogen veranderen:
  - geen tool-calls (tekst-only-tak): success blijft True -- dat is de normale weg voor een
    adviserende skill en het merendeel van de evaluatieset van dag 1;
  - alle tool-calls slagen: success blijft True;
  - alle tool-calls falen: was al False en blijft False.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.types import ExecutionStatusContract
from tests.fixtures.llm_dubbel import als_async

PILOT_TENANT = 1

# BE-AGT-042: elke uitvoering heeft een verantwoordelijke mens. Zonder initiator is de
# uitvoering fail-closed, dus tests geven hem expliciet mee -- net als de HTTP-ingang.
TEST_INITIATOR = 42


def _build_agent(llm_response: str) -> tuple[object, AsyncMock]:
    """De echte piloot-skill, met alleen de LLM- en brokergrens gemockt."""
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
    # Sinds ADR-036 D4-002 is de piloot Annex III/HITL: een APPROVED-verdict zou anders een
    # ticket aanmaken in plaats van de tool uit te voeren, en dit bestand test succes-/
    # foutboekhouding NA uitvoering, niet de HITL-floor. Expliciet terugzetten naar de
    # oorspronkelijke classificatie voor dit test-exemplaar.
    agent.config["human_in_the_loop"] = "hotl"

    llm_service = AsyncMock()
    llm_service.generate = AsyncMock(return_value=llm_response)
    agent._get_llm_service = als_async(llm_service)  # type: ignore[method-assign]

    broker = AsyncMock()
    agent.tools = broker  # type: ignore[attr-defined]

    return agent, broker


# Twee tools die de piloot ECHT mag aanroepen EN die zijn broker echt kan uitvoeren.
# Hier stond `send_notification`, op 2026-09-21 uit het manifest gehaald omdat er geen
# broker-tool voor bestaat; de manifest-filter in `act()` weigerde hem daarna voordat de
# broker hem zag, waardoor deze opstelling niet meer twee tool-calls opleverde en de
# assertie op de foutboekhouding niets meer meette. Daarna stond er kort
# `local__llm_generate`; die is er ook uit, want `BaseSpecialistAgent` wiret geen
# `local_registry` (gemeten: `None`). De payloads zijn die van de echte tools.
TWO_CALLS = (
    "Ik kijk naar de bezetting en plan de training.\n"
    'TOOL_CALL: query_hr_database {"role": "Engineer"}\n'
    'TOOL_CALL: schedule_training {"user_email": "j.jansen@klant.test", '
    '"training_name": "IFRS basis"}'
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestPartialToolFailureIsNotSuccess:
    async def test_one_of_two_tools_fails_means_not_successful(self) -> None:
        """De kern: een mislukte actie tussen geslaagde acties maakt het geheel niet goed."""
        agent, broker = _build_agent(TWO_CALLS)
        broker.execute_tool = AsyncMock(
            side_effect=[
                {"success": True},
                ToolExecutionException(tool_name="schedule_training", error_detail="boem"),
            ]
        )

        result = await agent.execute_with_manifest_prompt({"task": "plan training"}, initiated_by_user_id=TEST_INITIATOR)  # type: ignore[attr-defined]

        assert result.result_data["tool_calls"] == 2, "voorwaarde: er zijn twee tool-calls"
        assert len(result.result_data["errors"]) == 1, "voorwaarde: precies een fout"
        assert result.success is False, (
            "Een van de twee tools is mislukt, dus act() mag geen succes rapporteren. "
            "Anders rekent _run_within_budget() prana af voor werk dat deels niet is "
            "uitgevoerd, en niemand leest result_data['errors'] om dat te corrigeren."
        )
        assert result.status == ExecutionStatusContract.GEDEELTELIJK

    async def test_all_tools_failing_stays_unsuccessful(self) -> None:
        """Bestaand gedrag: alles mislukt was al False en blijft False."""
        agent, broker = _build_agent(TWO_CALLS)
        broker.execute_tool = AsyncMock(
            side_effect=ToolExecutionException(tool_name="x", error_detail="boem")
        )

        result = await agent.execute_with_manifest_prompt({"task": "plan training"}, initiated_by_user_id=TEST_INITIATOR)  # type: ignore[attr-defined]

        assert result.result_data["tool_calls"] == 2
        assert result.success is False
        assert result.status == ExecutionStatusContract.MISLUKT

    async def test_all_tools_succeeding_stays_successful(self) -> None:
        """Bestaand gedrag: alles slaagt blijft True."""
        agent, broker = _build_agent(TWO_CALLS)
        broker.execute_tool = AsyncMock(return_value={"success": True})

        result = await agent.execute_with_manifest_prompt({"task": "plan training"}, initiated_by_user_id=TEST_INITIATOR)  # type: ignore[attr-defined]

        assert result.result_data["tool_calls"] == 2
        assert not result.result_data["errors"]
        assert result.success is True
        assert result.status == ExecutionStatusContract.KLAAR

    async def test_text_only_answer_stays_successful(self) -> None:
        """De tekst-only-tak mag niet geraakt worden door de fix.

        Dit is de normale weg voor een adviserende skill: geen tool-calls, alleen analyse.
        Het merendeel van de evaluatieset van dag 1 loopt hier langs.
        """
        agent, broker = _build_agent("Op basis van de gegevens adviseer ik cursus X.")
        broker.execute_tool = AsyncMock()

        result = await agent.execute_with_manifest_prompt({"task": "adviseer"}, initiated_by_user_id=TEST_INITIATOR)  # type: ignore[attr-defined]

        assert result.result_data["tool_calls"] == 0
        assert result.success is True
        assert result.status == ExecutionStatusContract.KLAAR
        broker.execute_tool.assert_not_awaited()
