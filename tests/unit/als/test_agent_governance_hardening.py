"""Herstelpunten uit de onafhankelijke hercontrole van ADR-036 Fase 2 (BE-AGT-043).

Twee losse zaken, gevonden bij het opnieuw meten van dag 2 in plaats van het nalezen van de
eigen documentatie:

**De permissieconfiguratie werd per tool-actie van schijf gelezen.** `_reject_before_council`
bouwde een verse `ToolPermissionManager` in de lus, en diens `__init__` leest en parseert
`config/tool_permissions.yml`. Bij `max_steps=8` zijn dat acht schijfleesacties per invocatie.
Beide bestaande gebruikers houden juist een exemplaar vast (`tool_broker/service.py:114`,
`copilot/council/factory.py:141`); dit week daarvan af zonder reden. Bijkomend probleem: de
configuratie kon tussen twee acties van dezelfde invocatie veranderen.

**Het OODA-pad kan geen initiator meegeven.** `_initiated_by_user_id` wordt op precies een
plek gezet: `execute_with_manifest_prompt()` van de piloot-skill. De andere 134 skills lopen
via `_execute_task()` -> `act()`, en `TaskData` heeft geen gebruikersveld. Daar strandt elke
tool-aanroep dus op de fail-closed-poort. Dat is BEWUST -- geen verantwoordelijke mens
betekent geen actie (AI Act art. 14, ADR-036 D2) -- maar het was nergens vastgelegd, en een
bewuste beperking die je alleen ontdekt door hem tegen te komen is geen ontwerp maar een val.
De test hieronder pint het gedrag vast; D1 (Fase 4) vult het afdelingshoofd in als tweede
verifieerbare bron. Zie OP-21 in ADR-036 par. 10.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from tests.fixtures.llm_dubbel import als_async

PILOT_TENANT = 1
INITIATOR = 42


def _tool_call_lines(count: int, tool: str = "query_hr_database") -> str:
    lines = ["Ik voer de volgende stappen uit."]
    for index in range(count):
        lines.append(f'TOOL_CALL: {tool} {{"employee_id": "e-{index}"}}')
    return "\n".join(lines)


def _build_agent(llm_response: str) -> tuple[Any, AsyncMock]:
    """De echte piloot-skill, met alleen de LLM- en brokergrens gemockt."""
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
    # Sinds ADR-036 D4-002 is de piloot Annex III/HITL: een APPROVED-verdict zou anders een
    # ticket aanmaken in plaats van de tool uit te voeren, en dit bestand toetst
    # governance-hardening ROND uitvoering (permissiecheck, initiator, echte tooldata), niet de
    # HITL-floor zelf. Expliciet terugzetten voor dit test-exemplaar.
    agent.config["human_in_the_loop"] = "hotl"

    llm_service = AsyncMock()
    llm_service.generate = AsyncMock(return_value=llm_response)
    agent._get_llm_service = als_async(llm_service)  # type: ignore[method-assign]

    broker = AsyncMock()
    broker.execute_tool = AsyncMock(return_value={"success": True})
    agent.tools = broker  # type: ignore[attr-defined]
    return agent, broker


def _approved() -> Any:
    from src.core.copilot.council.background_gate import AgentCouncilOutcome
    from src.core.copilot.council.types import DecisionVerdict

    class _Decision:
        verdict = DecisionVerdict.APPROVED
        explanation_for_user = "goedgekeurd"
        decision_id = "d-1"

    # `hitl_ticket_ref=None`: het rauwe verdict is APPROVED, dus de (gemockte) gate zou zelf
    # geen ticket hebben aangemaakt (ADR-036 OP-167). Elke agent in dit bestand zet
    # `human_in_the_loop` expliciet terug naar "hotl" (zie `_build_agent`), dus de D4-002-floor
    # is hier nooit van toepassing en er is nergens een ticket nodig.
    return AgentCouncilOutcome(decision=_Decision(), hitl_ticket_ref=None)  # type: ignore[arg-type]


def _approved_decision_double() -> Any:
    """Een RAUWE CouncilDecision-dubbel, voor het mocken van `council.deliberate()` zelf.

    Anders dan `_approved()` hierboven (dat de RETOURWAARDE van de gate-functie
    `request_council_decision_for_agent()` simuleert, sinds ADR-036 OP-167 een
    `AgentCouncilOutcome`): dit dubbel simuleert wat de RAAD teruggeeft aan de gate, VOORDAT
    die het in een `AgentCouncilOutcome` verpakt. Nooit verwarren -- dat gaf eerder een
    `AttributeError: 'AgentCouncilOutcome' object has no attribute 'verdict'` binnen de
    ECHTE gate-functie zelf, want deze twee waren voorheen dezelfde helper.
    """
    from src.core.copilot.council.types import DecisionVerdict

    class _Decision:
        verdict = DecisionVerdict.APPROVED
        explanation_for_user = "goedgekeurd"
        decision_id = "d-1"

    return _Decision()


async def _count_config_reads(
    monkeypatch: pytest.MonkeyPatch, council_gate: AsyncMock, actions: int
) -> int:
    """Hoe vaak wordt config/tool_permissions.yml van schijf gelezen bij N tool-acties?"""
    from src.core.tool_broker import permission_manager as module

    reads: list[str] = []
    original = module.ToolPermissionManager._load_config

    def counting(self: Any, config_path: str | None = None) -> None:
        reads.append(config_path or "<default>")
        original(self, config_path)

    monkeypatch.setattr(module.ToolPermissionManager, "_load_config", counting)

    agent, broker = _build_agent(_tool_call_lines(actions))
    council_gate.return_value = _approved()

    await agent.execute_with_manifest_prompt(
        {"task": "gap analyse"}, initiated_by_user_id=INITIATOR
    )

    assert broker.execute_tool.await_count == actions, "voorwaarde: alle acties zijn gedaan"
    return len(reads)


@pytest.mark.unit
@pytest.mark.asyncio
class TestPermissionConfigIsNotRePerAction:
    async def test_config_reads_do_not_grow_with_the_number_of_actions(
        self, council_gate: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Het aantal schijfleesacties hoort onafhankelijk te zijn van het aantal tool-calls.

        Bewust een groei-invariant en geen vast getal: de agent bouwt bij constructie al een
        `ToolBrokerService`, die zelf een `ToolPermissionManager` aanmaakt en daarbij een keer
        de YAML leest (`service.py:114`). Dat basisgetal is een implementatiedetail van een
        andere laag; vastpinnen op "precies 1" zou deze test laten omvallen op een wijziging
        die er niets mee te maken heeft. Wat WEL moet gelden: een tweede en derde actie mogen
        niets extra's van schijf lezen.
        """
        one = await _count_config_reads(monkeypatch, council_gate, actions=1)
        three = await _count_config_reads(monkeypatch, council_gate, actions=3)

        assert one == three, (
            f"Bij 1 actie {one} config-lezingen, bij 3 acties {three}. De permissiecheck bouwt "
            "dus een verse ToolPermissionManager per tool-call, en die leest en parseert "
            "config/tool_permissions.yml elke keer opnieuw. Hergebruik de manager die de "
            "broker al heeft (tool_broker/service.py:114) -- dan is het er ook nog eens een "
            "bron in plaats van twee die uiteen kunnen lopen."
        )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("phase_type", ["sequential", "parallel"])
class TestInitiatorSurvivesTheRealEntryPoint:
    async def test_execute_pack_delivers_the_initiator_to_the_step(self, phase_type: str) -> None:
        """`execute_pack` was de productie-ingang (tot OP-09); daar moet de initiator aankomen.

        Sinds OP-09 gebruikt de route `run_pack_by_id`; de initiator daarvan staat in
        `tests/integration/test_packs_execute_route.py`. Deze test bewaakt de oude API.

        Deze test ontbrak bij BE-AGT-042 en dat is precies waarom er een defect doorheen
        glipte: alle tests riepen `_execute_step` of `run_pack` rechtstreeks aan MET de
        parameter er al in, terwijl vier tussenliggende aanroepen in `packs.py` hem lieten
        vallen. De signaturen klopten allemaal; de doorgifte niet. Een test die de keten niet
        vanaf het begin doorloopt, bewijst dus niets over de keten.
        """
        from unittest.mock import MagicMock, patch

        from src.core.als.enterprise.packs import DomainPack, DomainPackOrchestrator
        from src.core.shared.interfaces import ExecutionResult

        seen: list[int | None] = []

        async def capture(
            agent_id: str,
            tenant_id: int,
            params: dict[str, Any],
            *,
            initiated_by_user_id: int | None = None,
        ) -> ExecutionResult:
            seen.append(initiated_by_user_id)
            return ExecutionResult(task_id="t", success=True, tenant_id=tenant_id)

        pack = DomainPack(pack_id="pack.hr.pilot", name="HR pilot", steps=[])
        pack.agent_sequence = [{"type": phase_type, "agents": ["skillsgaptraining"]}]

        orchestrator = DomainPackOrchestrator.__new__(DomainPackOrchestrator)
        orchestrator.catalog = MagicMock()

        with patch.object(orchestrator, "_execute_step", side_effect=capture):
            await orchestrator.execute_pack(pack, tenant_id="1", initiated_by_user_id=INITIATOR)

        assert seen == [INITIATOR], (
            f"De initiator kwam als {seen} aan bij _execute_step in plaats van [{INITIATOR}]. "
            "Ergens tussen execute_pack en _execute_step valt de parameter weg -- controleer "
            "_execute_parallel, _execute_sequential, _execute_with_retry en "
            "_execute_single_agent. Zonder initiator weigert de Council-poort elke actie, dus "
            "elke stap van de pack faalt fail-closed."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestCouncilGateLeavesTheTenantContextIntact:
    async def test_tenant_context_survives_the_gate(self) -> None:
        """De poort mag de tenant-ContextVar van zijn aanroeper niet wissen.

        `request_council_decision_for_agent` is geschreven voor Dramatiq-taken, waar een
        lege begincontext klopt, en zette daarom in zijn `finally` hard `set_tenant_id(None)`.
        Zolang niets hem aanriep was dat onschadelijk. Sinds BE-AGT-042 draait hij per
        tool-actie binnen `act()`, in dezelfde asynctaak als het HTTP-verzoek -- dus die None
        lekte terug. Gevolg: de ADR-004-hook gaf daarna stil nul rijen terug op elke query,
        en een latere `require_tenant_id()` brak af.
        """
        from unittest.mock import MagicMock, patch

        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_cm.__aexit__ = AsyncMock(return_value=None)

        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_approved_decision_double())

        set_tenant_id(7)
        try:
            with (
                patch(
                    "src.core.copilot.council.background_gate.get_db_session",
                    return_value=session_cm,
                ),
                patch(
                    "src.core.copilot.council.background_gate.build_council",
                    AsyncMock(return_value=council),
                ),
                patch("src.core.copilot.council.background_gate.Proposal", MagicMock()),
            ):
                from src.core.copilot.council.background_gate import (
                    request_council_decision_for_agent,
                )

                await request_council_decision_for_agent(
                    tenant_id=7,
                    agent_id="skillsgaptraining",
                    user_id=INITIATOR,
                    action_type="query_hr_database",
                    action_params={"tool": "query_hr_database", "arg_keys": []},
                    reasoning="test",
                )

            assert get_tenant_id() == 7, (
                "De Council-poort heeft de tenant-context van de aanroeper gewist in plaats "
                "van hersteld. Alles wat daarna in dit verzoek een query doet, krijgt stil "
                "nul rijen terug."
            )
        finally:
            set_tenant_id(None)


@pytest.mark.unit
@pytest.mark.asyncio
class TestInitiatorDoesNotLinger:
    async def test_initiator_is_cleared_after_the_run(self, council_gate: AsyncMock) -> None:
        """Na afloop staat er geen gebruiker meer op de instantie.

        Vandaag bouwt de loader per stap een verse skill, dus een achterblijvende waarde
        raakt niemand. Niets legt dat vast: zodra iemand instanties cachet of poolt, wordt
        een volgende actie toegeschreven aan de gebruiker van een eerder verzoek. Dat is
        exact de foutklasse waartegen deze poort bestaat.
        """
        agent, _ = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _approved()

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=INITIATOR
        )

        assert agent._initiated_by_user_id is None, (
            "De initiator staat na afloop nog op de instantie. Bij hergebruik van de agent "
            "krijgt een volgende actie dan de verkeerde verantwoordelijke."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestPilotExecutesARealTool:
    async def test_pilot_gets_real_data_through_the_whole_chain(
        self, council_gate: AsyncMock, db_session: Any
    ) -> None:
        """De piloot doet een tool-aanroep die echt slaagt (ADR-036 D10 stap 3, BE-AGT-044).

        Dit is de test die telt: geen mock-broker, maar de echte `ToolBrokerService` die de
        skill in zijn `__init__` bouwt. De keten die hier wordt afgelegd is
        manifest-allowlist -> D5-denylist -> Council -> permissieprofiel -> risicoclassificatie
        -> `HRToolRegistry` -> tenant-gescoped lezen -> resultaat terug.

        Tot vandaag resolveerde geen van de 27 gedeclareerde tools en eindigde dit pad in
        "Unknown tool category". Op de laag eronder testen zou dat niet hebben laten zien --
        die les kostte bij BE-AGT-042 een hele hersteldag.
        """
        from src.core.models.rbac_models import Role, Tenant, User

        db_session.add(Tenant(id=PILOT_TENANT, name="Pilot", slug="pilot"))
        await db_session.flush()
        role = Role(tenant_id=PILOT_TENANT, name="Finance Analyst")
        db_session.add(role)
        await db_session.flush()
        for index in range(3):
            member = User(
                tenant_id=PILOT_TENANT,
                email=f"m{index}@example.test",
                hashed_password="x",
                is_active=True,
            )
            member.roles.append(role)
            db_session.add(member)
        await db_session.commit()

        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
        # Sinds ADR-036 D4-002 is de piloot Annex III/HITL -- deze test toetst of de tool
        # ECHTE data door de hele keten geeft, niet de HITL-floor. Zie de toelichting bij
        # `_build_agent` hierboven.
        agent.config["human_in_the_loop"] = "hotl"
        llm = AsyncMock()
        llm.generate = AsyncMock(
            return_value='TOOL_CALL: query_hr_database {"role": "Finance Analyst"}'
        )
        agent._get_llm_service = als_async(llm)  # type: ignore[method-assign]
        council_gate.return_value = _approved()

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=INITIATOR
        )

        assert result.success is True, (
            f"De tool-aanroep is niet geslaagd: {result.result_data.get('errors')}. Zolang dit "
            "faalt, is query_hr_database alleen een naam in een manifest."
        )
        output = result.result_data["results"][0]["output"]
        assert output["success"] is True
        assert output["roles"] == [{"role": "Finance Analyst", "user_count": 3, "active_count": 3}]


@pytest.mark.unit
@pytest.mark.asyncio
class TestStructuredToolFailureIsNotSuccess:
    async def test_tool_that_reports_failure_makes_the_step_unsuccessful(
        self, council_gate: AsyncMock
    ) -> None:
        """Een tool die `{"success": false}` teruggeeft, is geen geslaagde stap.

        `act()` telde alleen excepties als fout. Een tool die netjes een gestructureerde
        fout teruggeeft -- precies de vorm die het contract in BE-AGT-039 par. 3
        voorschrijft -- belandde in `results` en dus in een geslaagde stap. Daarmee rekent de
        OODA-lus prana af voor werk dat niet is gebeurd, en dat is exact de bevinding die
        BE-AGT-039 F3 voor deelfouten oploste maar die voor deze vorm bleef staan.

        Gevonden op 2026-08-02 doordat de eerste echte tool (BE-AGT-044) de eerste is die deze
        vorm kan produceren.
        """
        agent, broker = _build_agent(_tool_call_lines(1))
        broker.execute_tool = AsyncMock(
            return_value={"success": False, "error": "filter 'department' wordt niet ondersteund"}
        )
        council_gate.return_value = _approved()

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=INITIATOR
        )

        assert result.success is False, (
            "De tool meldde zelf dat hij faalde, maar de stap geldt als geslaagd. Dan betaalt "
            "de tenant prana voor werk dat niet is gebeurd."
        )
        errors = result.result_data["errors"]
        assert len(errors) == 1
        assert "department" in errors[0]["error"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestOodaPathHasNoInitiator:
    async def test_ooda_path_without_initiator_executes_nothing(
        self, council_gate: AsyncMock
    ) -> None:
        """Het OODA-pad kent geen initiator, dus daar voert een skill geen tool uit.

        Karakteriseringstest: dit gedrag bestaat al en is bewust. De test legt het vast zodat
        het niet per ongeluk verdwijnt EN zodat een volgende ontwikkelaar de beperking
        tegenkomt in een test in plaats van in een onverklaarbare weigering.
        """
        agent, broker = _build_agent("ongebruikt")

        # act() rechtstreeks: precies wat _execute_task() doet aan het einde van de OODA-lus.
        result = await agent.act(_tool_call_lines(1))

        assert broker.execute_tool.await_count == 0, (
            "Er is een tool uitgevoerd zonder dat er een verantwoordelijke mens aan de "
            "uitvoering hing. Dat mag niet (AI Act art. 14, ADR-036 D2)."
        )
        assert council_gate.await_count == 0, (
            "De Council is geraadpleegd zonder initiator. De gate legt zijn besluit op een "
            "user_id vast, dus dan zou daar een verzonnen waarde in terechtkomen."
        )
        assert result.success is False

        errors = result.result_data["errors"]
        assert len(errors) == 1
        assert "geen initiator" in errors[0]["error"], (
            "De melding moet benoemen dat de initiator ontbreekt -- niet een generieke "
            "weigering, want dan is de oorzaak niet te vinden."
        )
