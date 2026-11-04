"""D10 stap 5 -- het manifest-budget wordt echt afgedwongen (BE-AGT-041).

`SkillBudget` (als/agents/skill_manifest.py) parseert `max_steps`, `max_llm_calls`,
`timeout_seconds` en `prana_cost_limit`, maar die velden komen alleen terug in `to_dict()`.
Alle 135 manifesten declareren dezelfde waarden (8 / 5 / 60 / 100) en geen enkele wordt
gehandhaafd.

Het belangrijkste gat is niet theoretisch. `_parse_tool_calls()` gebruikt `finditer` ZONDER
limiet op het LLM-antwoord, en `act()` voert elke gevonden directive sequentieel uit met 30s
timeout per tool. Een antwoord met 50 `TOOL_CALL`-regels betekent 50 uitvoeringen en tot ~25
minuten werk. `max_steps=8` hoort daar precies op.

Daarnaast omzeilt het piloot-pad de bestaande governance: `_execute_task()` doet
`PranaGuard.check_budget()` en `charge_prana()`, maar `execute_with_manifest_prompt()` -- het
pad dat `packs.py:337` in productie gebruikt -- roept `_execute_task` niet aan. Dus geen
budgetcheck, geen afrekening, geen limiet.

De prana-guard wordt in deze tests gestubd. Dat is geen luxe: `check_budget()` opent een
echte DB-sessie, en zonder stub krijgt elke test de retry-backoff die vandaag als OP-18 is
opgeruimd (56,8s per test).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.types import ExecutionStatusContract
from tests.fixtures.llm_dubbel import als_async

PILOT_TENANT = 1

# BE-AGT-042: elke uitvoering heeft een verantwoordelijke mens. Zonder initiator is de
# uitvoering fail-closed, dus tests geven hem expliciet mee -- net als de HTTP-ingang.
TEST_INITIATOR = 42


# Het manifest van de piloot declareert max_steps=8.
MANIFEST_MAX_STEPS = 8


def _tool_call_lines(count: int) -> str:
    """Een LLM-antwoord met `count` geldige TOOL_CALL-directives."""
    lines = ["Ik voer de volgende stappen uit."]
    for i in range(count):
        lines.append(f'TOOL_CALL: query_hr_database {{"employee_id": "e-{i}"}}')
    return "\n".join(lines)


def _build_agent(llm_response: str) -> tuple[Any, AsyncMock]:
    """De echte piloot-skill, met alleen de LLM- en brokergrens gemockt."""
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
    # Sinds ADR-036 D4-002 is de piloot Annex III/HITL: een APPROVED-verdict zou anders een
    # ticket aanmaken in plaats van de tool uit te voeren, en dit bestand test budgetgrenzen op
    # UITVOERING, niet de HITL-floor. Expliciet terugzetten voor dit test-exemplaar.
    agent.config["human_in_the_loop"] = "hotl"

    llm_service = AsyncMock()
    llm_service.generate = AsyncMock(return_value=llm_response)
    agent._get_llm_service = als_async(llm_service)  # type: ignore[method-assign]
    # Het dubbel ook rechtstreeks bereikbaar: sinds BE-LLM-004 is `_get_llm_service()` async,
    # dus `agent._get_llm_service().generate` levert een coroutine op in plaats van het dubbel.
    # Een test die daarop asserteert meet dan niets.
    agent._test_llm = llm_service  # type: ignore[attr-defined]

    broker = AsyncMock()
    broker.execute_tool = AsyncMock(return_value={"success": True})
    agent.tools = broker  # type: ignore[attr-defined]

    return agent, broker


# De `prana_guard`-fixture staat in tests/unit/als/conftest.py: autouse, zodat geen enkele
# ALS-unittest per ongeluk een databaseverbinding opent, en tegelijk opvraagbaar op naam
# voor tests die op de aanroepen willen asserteren.


@pytest.mark.unit
@pytest.mark.asyncio
class TestMaxStepsCapsToolCalls:
    """De onbegrensde tool-call-lus is het echte weglooppad van vandaag."""

    async def test_tool_calls_capped_at_max_steps(self, prana_guard: Any) -> None:
        """Twintig directives mogen niet twintig tool-uitvoeringen opleveren."""
        agent, broker = _build_agent(_tool_call_lines(20))

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert broker.execute_tool.await_count == MANIFEST_MAX_STEPS, (
            f"Er zijn {broker.execute_tool.await_count} tools uitgevoerd terwijl het "
            f"manifest max_steps={MANIFEST_MAX_STEPS} declareert. Zonder deze grens kan "
            "een enkel LLM-antwoord willekeurig veel uitvoeringen veroorzaken -- met 30s "
            "timeout per tool is dat tientallen minuten werk."
        )

    async def test_exceeding_max_steps_is_reported_not_silently_truncated(
        self, prana_guard: Any
    ) -> None:
        """Afkappen mag niet stil: de overschrijding hoort in het resultaat te staan."""
        agent, _ = _build_agent(_tool_call_lines(20))

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        errors = result.result_data.get("errors") or []
        assert any("max_steps" in str(e) for e in errors), (
            "Een overschrijding van max_steps moet expliciet gemeld worden. Stil afkappen "
            "is precies het patroon dat AUDIT-009 blootlegde: minder doen dan gevraagd en "
            "toch succes rapporteren."
        )
        # ADR-036 D7-001: dit kapt af en gaat DOOR met de eerste max_steps calls (die hier
        # allemaal slagen) -- een echte deeluitvoering, GEEN budgetafsluiter. De drie ECHTE
        # afsluiters (Prana/timeout/max_llm_calls) breken _run_within_budget() al af voordat
        # act() ooit begint en geven MEER_BUDGET_NODIG -- zie de klassen hieronder.
        assert result.status == ExecutionStatusContract.GEDEELTELIJK

    async def test_within_max_steps_is_unchanged(self, prana_guard: Any) -> None:
        """Regressiebescherming: onder de grens verandert er niets."""
        agent, broker = _build_agent(_tool_call_lines(3))

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert broker.execute_tool.await_count == 3
        assert result.success is True
        assert result.status == ExecutionStatusContract.KLAAR


@pytest.mark.unit
@pytest.mark.asyncio
class TestTimeoutFromManifest:
    async def test_slow_execution_aborts_with_explicit_budget_error(self, prana_guard: Any) -> None:
        """Werk dat langer duurt dan timeout_seconds breekt af, en zegt waarom."""
        agent, _ = _build_agent("Alleen tekst, geen tool-call.")

        async def _too_slow(*_a: Any, **_k: Any) -> str:
            await asyncio.sleep(5)
            return "te laat"

        agent._test_llm.generate = AsyncMock(side_effect=_too_slow)  # type: ignore[attr-defined]

        # Het echte manifest zegt 60s; die willen we niet afwachten in een unit-test.
        agent.budget.timeout_seconds = 0.05
        result = await agent.execute_with_manifest_prompt(
            {"task": "traag"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert result.success is False
        assert "timeout" in str(result.error_message).lower(), (
            "De foutmelding moet benoemen dat de tijdslimiet is geraakt -- anders is een "
            "budgetafbreking niet te onderscheiden van een echte hang."
        )
        assert result.status == ExecutionStatusContract.MEER_BUDGET_NODIG


@pytest.mark.unit
@pytest.mark.asyncio
class TestLlmCallLimit:
    async def test_more_llm_calls_than_budget_aborts(self, prana_guard: Any) -> None:
        """Meer LLM-aanroepen dan max_llm_calls breekt af.

        Vandaag doet het piloot-pad er precies een, dus deze grens beschermt het moment
        dat er een meerstaps-lus komt. De teller zit daarom op `_get_llm_service()` en niet
        op de aanroepplekken: elke toekomstige aanroeper wordt zo automatisch geteld.
        """
        from src.core.als.agents.skill_manifest import SkillBudgetExceeded

        agent, _ = _build_agent("Alleen tekst.")
        agent._llm_calls_used = 0

        # De eerste vijf mogen (manifest: max_llm_calls=5), de zesde niet.
        for _ in range(agent.budget.max_llm_calls):
            agent._count_llm_call()

        with pytest.raises(SkillBudgetExceeded) as excinfo:
            agent._count_llm_call()

        assert "max_llm_calls" in str(excinfo.value), (
            "De foutmelding moet benoemen WELKE limiet is geraakt; anders is een "
            "budgetafbreking niet te onderscheiden van een andere storing."
        )

    async def test_llm_call_limit_reached_through_the_full_flow_reports_meer_budget_nodig(
        self, prana_guard: Any
    ) -> None:
        """ADR-036 D7-001: dezelfde limiet, maar via `_run_within_budget()` in plaats van een
        directe `_count_llm_call()`-aanroep -- dit is het pad dat een productie-invocatie
        daadwerkelijk volgt."""
        agent, _ = _build_agent("Alleen tekst.")
        agent.budget.max_llm_calls = 0

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert result.success is False
        assert result.status == ExecutionStatusContract.MEER_BUDGET_NODIG

    async def test_llm_call_counter_resets_per_invocation(self, prana_guard: Any) -> None:
        """Twee opeenvolgende invocaties mogen elkaars teller niet opeten."""
        agent, _ = _build_agent("Alleen tekst.")

        await agent.execute_with_manifest_prompt(
            {"task": "eerste"}, initiated_by_user_id=TEST_INITIATOR
        )
        first = agent._llm_calls_used
        await agent.execute_with_manifest_prompt(
            {"task": "tweede"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert first == 1 and agent._llm_calls_used == 1, (
            f"De teller stond na twee invocaties op {agent._llm_calls_used}. Zonder reset "
            "per invocatie zou een langlevende agent na vijf taken vastlopen op zijn "
            "eigen budget."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestPranaGovernanceOnThePilotPath:
    async def test_manifest_prompt_path_checks_tenant_budget(self, prana_guard: Any) -> None:
        """Het piloot-pad moet dezelfde budgetcheck doen als elke andere skill."""
        agent, _ = _build_agent("Alleen tekst.")

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert prana_guard.check_budget.await_count >= 1, (
            "execute_with_manifest_prompt slaat PranaGuard.check_budget over, terwijl "
            "_execute_task die wel doet. Het productiepad van de piloot (packs.py:337) "
            "loopt dus buiten de financiele governance om."
        )

    async def test_insufficient_prana_reports_meer_budget_nodig(self, prana_guard: Any) -> None:
        """ADR-036 D7-001: een tenant-Prana-tekort breekt af VOORDAT act() start."""
        agent, broker = _build_agent(_tool_call_lines(1))
        prana_guard.check_budget = AsyncMock(
            side_effect=Exception("Tenant heeft onvoldoende Prana-budget.")
        )

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        assert result.success is False
        assert result.status == ExecutionStatusContract.MEER_BUDGET_NODIG
        broker.execute_tool.assert_not_awaited()

    async def test_prana_charged_uses_the_manifests_technology_tier(self, prana_guard: Any) -> None:
        """De afrekening prijst op `config['technology']` (ADR-021-tier), niet een hardcoded
        waarde. Sinds `iter/prana-economy` bepaalt de tier de kosten (ml/llm/vision/hybrid via
        `prana_costs.cost_for_tier`), niet meer `budget.prana_cost_limit` -- dat manifestveld
        was in alle 135 manifesten dezelfde 100 en droeg geen onderscheid."""
        agent, _ = _build_agent("Alleen tekst.")

        agent.config["technology"] = "vision"
        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
        )

        charged_tiers = [
            c.kwargs.get("agent_type") for c in prana_guard.charge_prana.await_args_list
        ]
        assert "vision" in charged_tiers, (
            f"Afgerekend met tier(s) {charged_tiers} in plaats van de gedeclareerde 'vision'. "
            "De technology uit het manifest bereikt charge_prana niet."
        )
