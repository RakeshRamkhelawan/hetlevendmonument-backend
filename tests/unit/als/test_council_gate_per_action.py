"""D10 stap 6 / D2 -- Council-poort verplicht per actie (BE-AGT-042).

`request_council_decision_for_agent()` (`copilot/council/background_gate.py:50`) is de
transport-neutrale Council-ingang voor achtergrondtaken. Hij is compleet, heeft unit- EN
integratietests, en heeft **nul productie-aanroepers**: alleen tests roepen hem aan. Een
tool-aanroep van een skill doorloopt vandaag de manifest-allowlist, `execute_tool`, de
permissie- en categoriecheck, de risk-classificatie en bij HIGH risk de HITL-poort -- de
Council komt daar nergens in voor.

De volgorde is onderdeel van het contract, net als bij D5:

    1. manifest-allowlist-filter   (_parse_tool_calls)
    2. D5 harde denylist           moet VOOR de Council
    3. Council-beraadslaging       per actie
    4. execute_tool                herhaalt 2 plus risk/HITL -- defence in depth

Stap 2 staat er bewust dubbel op. Zou de Council eerst oordelen, dan zou een menselijke
goedkeuring een "nooit aanraken"-actie alsnog kunnen doorlaten -- precies wat D5 uitsluit.

Accountability: de gate vereist een `user_id` en legt het besluit daarop vast. Een verzonnen
waarde zou een autonome agent-actie toeschrijven aan een echt persoon. De initiator komt
daarom van de HTTP-ingang (`_current_user`, die daar vandaag bewust ongebruikt is). Ontbreekt
hij, dan is er geen verantwoordelijke mens en wordt er niets uitgevoerd (AI Act art. 14).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.types import ExecutionStatusContract
from tests.fixtures.llm_dubbel import als_async

PILOT_TENANT = 1
INITIATOR = 42


def _tool_call_lines(count: int, tool: str = "query_hr_database") -> str:
    lines = ["Ik voer de volgende stappen uit."]
    for i in range(count):
        lines.append(f'TOOL_CALL: {tool} {{"employee_id": "e-{i}"}}')
    return "\n".join(lines)


def _build_agent(llm_response: str, *, initiator: int | None = INITIATOR) -> tuple[Any, AsyncMock]:
    """De echte piloot-skill, met alleen de LLM- en brokergrens gemockt."""
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)

    llm_service = AsyncMock()
    llm_service.generate = AsyncMock(return_value=llm_response)
    agent._get_llm_service = als_async(llm_service)  # type: ignore[method-assign]

    broker = AsyncMock()
    broker.execute_tool = AsyncMock(return_value={"success": True})
    agent.tools = broker  # type: ignore[attr-defined]

    # Wordt door de aanroeper meegegeven, net als in productie (packs.py -> skill).
    agent._test_initiator = initiator  # type: ignore[attr-defined]
    return agent, broker


def _decision(verdict_name: str, *, hitl_ticket_ref: str = "TICKET-STUB-OP163") -> Any:
    """Een AgentCouncilOutcome-dubbel met alleen wat de aanroeper leest.

    `decision_id` erbij sinds ADR-036 OP-163: het HITL_REQUIRED-pad geeft dit veld door aan
    `create_hitl_request()` (het ticket moet naar de beraadslaging kunnen terugverwijzen).

    Sinds ADR-036 OP-167 (open-punten-opruiming dag 1) retourneert de ECHTE gate-functie een
    `AgentCouncilOutcome` (decision + hitl_ticket_ref), niet meer de kale CouncilDecision --
    de gate maakt nu zelf een ticket aan zodra het RAUWE verdict al HITL_REQUIRED is. Dit
    dubbel simuleert dat: `hitl_ticket_ref` is alleen relevant als `verdict_name ==
    "HITL_REQUIRED"`, voor elk ander verdict negeert de aanroepende code het toch.
    """
    from src.core.copilot.council.background_gate import AgentCouncilOutcome
    from src.core.copilot.council.types import DecisionVerdict

    class _D:
        verdict = getattr(DecisionVerdict, verdict_name)
        explanation_for_user = f"reden voor {verdict_name}"
        decision_id = f"decision-{verdict_name.lower()}"

    ref = hitl_ticket_ref if verdict_name == "HITL_REQUIRED" else None
    return AgentCouncilOutcome(decision=_D(), hitl_ticket_ref=ref)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
class TestCouncilIsConsultedPerAction:
    async def test_tool_execution_requires_council_decision(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        """Geen enkele tool draait zonder dat de Council is geraadpleegd.

        `hitl_ticket_repository` is nodig sinds ADR-036 D4-002: de piloot-skill (het testvehikel
        van dit bestand) is Annex III/HITL, dus een APPROVED-verdict leidt hier niet meer tot
        directe uitvoering maar tot een ticket -- zie `TestVerdictIsHonoured::
        test_approved_verdict_still_floors_to_a_ticket_for_the_pilot_skill` voor die assertie in
        detail. Deze test blijft toetsen wat hij altijd toetste: dat de Council is geraadpleegd
        voordat er iets met de tool-actie gebeurt, ongeacht wat dat "iets" is.
        """
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision("APPROVED")

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert council_gate.await_count >= 1, (
            "execute_with_manifest_prompt heeft een tool uitgevoerd zonder de Council te "
            "raadplegen. request_council_decision_for_agent bestaat, is getest, en had tot "
            "nu toe nul productie-aanroepers."
        )
        assert broker.execute_tool.await_count == 0, (
            "De tool is direct uitgevoerd. Sinds D4-002 loopt een APPROVED-verdict voor deze "
            "(Annex III/HITL) skill via een goedkeuringsticket, niet via directe uitvoering."
        )
        hitl_ticket_repository.create_hitl_request.assert_awaited_once()

    async def test_council_is_consulted_once_per_tool_call(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        """Per actie, niet per invocatie: drie tool-calls, drie beraadslagingen.

        `hitl_ticket_repository` nodig om dezelfde reden als hierboven (ADR-036 D4-002).
        """
        agent, broker = _build_agent(_tool_call_lines(3))
        council_gate.return_value = _decision("APPROVED")

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert council_gate.await_count == 3, (
            f"De Council is {council_gate.await_count}x geraadpleegd bij 3 tool-calls. D10 "
            "stap 6 vraagt een poort per ACTIE; een oordeel over het hele plan laat een "
            "afzonderlijke actie ongetoetst."
        )
        assert broker.execute_tool.await_count == 0, (
            "De tool is direct uitgevoerd. Sinds D4-002 loopt een APPROVED-verdict voor deze "
            "(Annex III/HITL) skill via een goedkeuringsticket, niet via directe uitvoering."
        )
        assert hitl_ticket_repository.create_hitl_request.await_count == 3, (
            "Per actie, niet per invocatie: drie tool-calls op een Annex III/HITL-skill moeten "
            "drie afzonderlijke tickets opleveren, net zoals ze drie afzonderlijke "
            "beraadslagingen opleveren."
        )

    async def test_text_only_answer_does_not_consult_council(self, council_gate: AsyncMock) -> None:
        """Zonder actie valt er niets te beoordelen."""
        agent, _ = _build_agent("Alleen analyse, geen tool-call.")

        result = await agent.execute_with_manifest_prompt(
            {"task": "adviseer"}, initiated_by_user_id=agent._test_initiator
        )

        assert council_gate.await_count == 0
        assert result.success is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerdictIsHonoured:
    @pytest.mark.parametrize("verdict", ["BLOCKED", "HITL_REQUIRED", "DEFERRED", "MODIFIED"])
    async def test_non_approving_verdict_prevents_execution(
        self,
        council_gate: AsyncMock,
        hitl_ticket_repository: AsyncMock,
        verdict: str,
    ) -> None:
        """Alles wat geen goedkeuring is, houdt de tool tegen.

        `hitl_ticket_repository` wordt hier opgevraagd (niet-autouse, ADR-036 OP-163) omdat de
        HITL_REQUIRED-parametercase het echte `create_hitl_request`-pad raakt en anders op een
        niet-geinitialiseerde databaseverbinding stukloopt; voor de andere drie verdicten wordt
        de stub eenvoudigweg niet aangeroepen.
        """
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision(verdict)

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0, (
            f"Verdict {verdict} heeft de tool niet tegengehouden. Een poort die de uitvoering "
            "niet daadwerkelijk stopt, is geen poort."
        )
        errors = result.result_data.get("errors") or []
        assert any(verdict.lower() in str(e).lower() for e in errors), (
            f"Het verdict {verdict} moet herkenbaar in errors staan, zodat de aanroeper weet "
            "waarom er niets is gebeurd."
        )
        assert result.success is False
        # ADR-036 D7-001: elk van de vier verdicten is een governance-weigering, dus
        # GEBLOKKEERD -- inclusief HITL_REQUIRED (een ticket dat op een mens wacht is
        # precies "mens nodig", niet een variant van geslaagd).
        assert result.status == ExecutionStatusContract.GEBLOKKEERD

    @pytest.mark.parametrize("verdict", ["BLOCKED", "DEFERRED"])
    async def test_a_non_approving_verdict_never_becomes_an_approvable_ticket(
        self,
        council_gate: AsyncMock,
        hitl_ticket_repository: AsyncMock,
        verdict: str,
    ) -> None:
        """ADR-036 D4-002 / OP-165: de floor is een upgrade van APPROVED **of** MODIFIED
        (sinds ADR-036 OP-168-vervolg, 2026-08-25 -- zie
        `test_modified_verdict_also_floors_to_a_ticket_for_the_pilot_skill` hieronder voor die
        assertie), maar NOOIT een downgrade van BLOCKED/DEFERRED naar iets dat een mens kan
        goedkeuren. MODIFIED stond hier tot deze fix ook in deze parametrisatie -- dat was het
        SPIEGELBEELD van de test hieronder en is nu net als bij `test_coordinator.py`
        (coordinator.py's eigen OP-168-fix) verwijderd omdat het de OPPOSITE beweert van wat
        na de fix waar is.

        `test_non_approving_verdict_prevents_execution` kan dit onderscheid niet zien: de
        foutmelding bevat de verdict-naam ("reden voor BLOCKED") ONGEACHT of de actie via het
        originele verdict is afgewezen OF via een ten onrechte aangemaakt HITL_REQUIRED-
        ticket, en `execute_tool` blijft in beide gevallen 0 keer aangeroepen -- die test is
        dus blind voor precies de fout die deze test vangt. Het onderscheidende signaal is of
        er een goedkeuringsticket is aangemaakt: zo ja, dan zou een tenant-admin een
        Council-BLOCK alsnog kunnen goedkeuren via `hitl_router.approve_hitl_request()`,
        precies wat de floor-code in commentaar uitsluit (specialist_base.py:368-377).

        Mutatiebewijs: laat in `_council_rejection()` de conjunct
        `effective_verdict in (DecisionVerdict.APPROVED, DecisionVerdict.MODIFIED)` weg (hou
        alleen `human_in_the_loop == "hitl"` over) -- deze test wordt rood voor elk van de twee
        resterende parameters, terwijl `test_non_approving_verdict_prevents_execution` groen
        blijft.
        """
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision(verdict)

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert hitl_ticket_repository.create_hitl_request.await_count == 0, (
            f"Verdict {verdict} heeft toch een goedkeuringsticket aangemaakt. De floor mag "
            "ALLEEN een APPROVED-verdict optillen naar HITL_REQUIRED, nooit een al afwijzend "
            "Council-verdict omzetten in iets dat een mens kan goedkeuren."
        )

    async def test_approved_verdict_still_floors_to_a_ticket_for_the_pilot_skill(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        """ADR-036 D4-002 / OP-165: Annex III/HITL is een FLOOR, geen label dat de Council kan overstemmen.

        Deze test verving `test_approved_verdict_executes_with_the_original_payload`: tot de
        piloot-skill (`skillsgaptraining`) gereclassificeerd werd naar `annex_iii`/`hitl`, bewees
        die test het OMGEKEERDE -- een unaniem APPROVED-verdict liet de tool direct uit. Sinds de
        classificatie een echte grens is, mag dat niet meer: elke actie van deze skill moet naar
        een goedkeuringsticket, ongeacht hoe de Officers stemden.

        De payload wordt nog steeds expliciet nagelopen (niet alleen het aantal aanroepen), en
        nu in het TICKET in plaats van in een directe uitvoering -- dezelfde regressiebescherming
        als voorheen (MODIFIED mag nooit als goedkeuring gelden), alleen het eindstation
        veranderde.
        """
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision("APPROVED")

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0, (
            "De tool is direct uitgevoerd ondanks de Annex III/HITL-classificatie van deze "
            "skill. Een unaniem APPROVED-verdict mag die classificatie niet overstemmen "
            "(ADR-036 D4-002)."
        )
        assert result.success is False
        # ADR-036 D7-001: een ticket dat op een mens wacht is GEBLOKKEERD, niet KLAAR -- ook
        # al stemde de Council unaniem APPROVED. De floor maakt hier het statuscontract, niet
        # het onderliggende verdict.
        assert result.status == ExecutionStatusContract.GEBLOKKEERD

        hitl_ticket_repository.create_hitl_request.assert_awaited_once()
        kwargs = hitl_ticket_repository.create_hitl_request.await_args.kwargs
        assert kwargs["action_type"] == "query_hr_database"
        assert kwargs["action_params"] == {"employee_id": "e-0"}
        assert kwargs["executing_identity"] == "skillsgaptraining"
        assert kwargs["tenant_id"] == PILOT_TENANT

    async def test_modified_verdict_also_floors_to_a_ticket_for_the_pilot_skill(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        """ADR-036 OP-168-vervolg (HITL-ticket-volledigheid sprint dag 3-vervolg, 2026-08-25,
        Rakesh's GO): het spiegelbeeld van
        `test_approved_verdict_still_floors_to_a_ticket_for_the_pilot_skill` hierboven. Voor
        deze fix eindigde een APPROVE_WITH_MODIFICATION-verdict (de coordinator maakt dat
        MODIFIED) op deze Annex III/HITL-skill in een kale weigering zonder ticket -- exact de
        bug die OP-168 al fixte voor `coordinator.py::ALWAYS_HITL_ACTIONS`, hier voor de
        LOKALE D4-002-floor. Nu moet ook MODIFIED een goedkeuringsticket opleveren, net als
        APPROVED.
        """
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision("MODIFIED")

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0, (
            "De tool is direct uitgevoerd ondanks een MODIFIED-verdict op een Annex III/HITL-"
            "skill. Dat verdict mag de classificatie niet overstemmen (ADR-036 D4-002)."
        )
        assert result.success is False
        assert result.status == ExecutionStatusContract.GEBLOKKEERD

        hitl_ticket_repository.create_hitl_request.assert_awaited_once()
        kwargs = hitl_ticket_repository.create_hitl_request.await_args.kwargs
        assert kwargs["action_type"] == "query_hr_database"
        assert kwargs["action_params"] == {"employee_id": "e-0"}
        assert kwargs["executing_identity"] == "skillsgaptraining"
        assert kwargs["tenant_id"] == PILOT_TENANT

    async def test_the_floor_does_not_raise_when_no_ticket_is_possible(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        """Gate 2-bevinding: `create_hitl_request` weigert zelf met `ValueError`/
        `PermissionError` (OP-90/OP-163). Zonder deze vangst zou de floor-tak een
        onverwachte exception laten propageren voor een verdict dat wel degelijk
        (lokaal opgetild naar) HITL_REQUIRED was -- precies de fout die OP-167 elders al
        moest oplossen, nu voor het pre-existing floor-pad."""
        hitl_ticket_repository.create_hitl_request = AsyncMock(
            side_effect=ValueError("Geen uitvoerder voor tool 'query_hr_database'")
        )
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision("APPROVED")

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0, (
            "Zonder ticket mag de tool alsnog niet direct uitvoeren -- de weigering om een "
            "ticket aan te maken is geen goedkeuring."
        )
        assert result.status == ExecutionStatusContract.GEBLOKKEERD
        errors = result.result_data.get("errors") or []
        assert any("geen goedkeuringsticket" in str(e).lower() for e in errors), (
            "De foutmelding moet eerlijk zeggen dat er GEEN ticket is aangemaakt, niet ten "
            "onrechte een ticketverwijzing tonen (bv. de string 'None')."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestHitlRequiredCreatesATicket:
    """ADR-036 OP-163: HITL_REQUIRED mag geen dood spoor zijn.

    Tot OP-163 behandelde `_council_rejection()` HITL_REQUIRED identiek aan BLOCKED: de
    actie werd afgewezen en er kwam nooit een echt goedkeuringsticket -- precies het
    omgekeerde van menselijk toezicht (AI Act art. 14).

    **Aangepast voor ADR-036 OP-167 (open-punten-opruiming dag 1).** Voor een RAUW
    HITL_REQUIRED-verdict (de Council zelf zegt het, niet de D4-002-floor) maakt de
    gate-functie (`background_gate.py::request_council_decision_for_agent`) het ticket nu
    ZELF aan -- dat is precies het OP-167-gat dat dicht moest: een tweede aanroeper van die
    functie kreeg voorheen geen ticket, want alleen deze skill repliceerde de logica zelf.
    Omdat `council_gate` hier de HELE gate-functie vervangt (fixture-conventie van dit
    bestand), loopt de ECHTE `create_hitl_request()`-aanroep voor DIT scenario niet meer door
    `specialist_base.py` -- die aanroep, met zijn argumenten, wordt bewezen in
    `tests/integration/test_council_background_gate.py` (waar de echte gate-functie draait).
    Deze test bewijst wat er op het ALS-niveau overblijft: de ticketverwijzing die de
    (gemockte) gate teruggeeft, bereikt de agent en zijn foutmelding.
    """

    async def test_the_gates_ticket_ref_reaches_the_agents_error_message(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _decision("HITL_REQUIRED")

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0
        # Geen ticket via DEZE laag: het rauwe verdict was al HITL_REQUIRED, dus de
        # (gemockte) gate had het al aangemaakt. Zou deze skill hier ALSNOG zelf een ticket
        # aanmaken, dan kreeg de mens TWEE tickets voor een enkele beraadslaging.
        assert hitl_ticket_repository.create_hitl_request.await_count == 0, (
            "Deze skill heeft zelf ook een ticket aangemaakt terwijl het rauwe Council-verdict "
            "al HITL_REQUIRED was -- dat levert een DUBBEL ticket op (een uit de gate, een "
            "hier). Alleen de D4-002-floor (APPROVED lokaal opgetild) mag hier zelf een "
            "ticket aanmaken."
        )

        errors = result.result_data.get("errors") or []
        assert any("TICKET-STUB-OP163" in str(e) for e in errors), (
            "De ticketverwijzing die de gate teruggaf, moet in de foutmelding staan, zodat "
            "de agent (en de gebruiker) weet dat er een goedkeuringsticket klaarstaat in "
            "plaats van dat de actie gewoon verdwenen is."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestWhatTheCouncilGetsToSee:
    async def test_raw_tool_values_never_reach_the_council(self, council_gate: AsyncMock) -> None:
        """Alleen sleutelnamen de poort in -- geen waarden, geen modelgestuurde vlaggen.

        Twee blokkerende bevindingen uit de Gate 2-review in een test:

        1. `action_params` wordt verbatim in de ADR-019 hash-keten geschreven. Dat record
           is niet corrigeerbaar of wisbaar, dus HR-waarden erin botsen met AVG art. 16/17.
        2. Meerdere Officers lezen governance-vlaggen (`ai_disclosure`, `dsar_activated`)
           uit diezelfde dict. Zolang de inhoud modeloutput is, kan een prompt-injectie zijn
           eigen oordeel meesturen.
        """
        directive = (
            "TOOL_CALL: query_hr_database "
            '{"employee_id": "burgerservicenummer-123", "ai_disclosure": true}'
        )
        agent, _ = _build_agent(directive)
        council_gate.return_value = _decision("APPROVED")

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        sent = council_gate.await_args.kwargs["action_params"]

        assert "burgerservicenummer-123" not in str(sent), (
            "Een waarde uit de modeloutput is in action_params beland. Die dict gaat "
            "onuitwisbaar de hash-keten in; alleen sleutelnamen horen erin."
        )
        # Sinds SP-COUNCIL-GATE-001 (2026-08-16) zet het SYSTEEM deze vlag altijd zelf; de
        # ComplianceOfficer eiste hem en weigerde daarvoor elke toolactie. De oorspronkelijke
        # assertie ("de sleutel mag er niet zijn") meet daardoor niet meer wat hij bedoelde.
        # Wat hij bedoelde blijft staan en wordt hier scherper getoetst: de WAARDE is die van
        # het systeem, nooit die van het model -- de payload draagt hierboven `true`.
        from src.core.als.agents.specialist_base import _AI_DISCLOSURE

        assert sent.get("ai_disclosure") == _AI_DISCLOSURE, (
            f"De bekendmaking is {sent.get('ai_disclosure')!r} in plaats van de door het "
            "systeem gezette tekst. Kwam de waarde uit de payload, dan stuurt het model zijn "
            "eigen governance-oordeel en zet het de ComplianceOfficer stil."
        )
        assert sent["ai_disclosure"] is not True, (
            "De vlag draagt letterlijk de waarde uit de modeloutput."
        )
        assert sent["arg_keys"] == ["ai_disclosure", "employee_id"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestDenylistPrecedesCouncil:
    async def test_denylist_is_checked_before_council(self, council_gate: AsyncMock) -> None:
        """Een verboden actie bereikt de Council niet eens (D5-volgorde).

        Deze test construeert BEWUST een divergentie tussen manifest en profiel: het
        manifest staat de tool toe, het profiel verbiedt hem via `denied_actions`. In de
        huidige configuratie zijn die twee lijsten disjunct (afgedwongen door BE-AGT-038),
        dus zonder die divergentie zou de manifest-filter de tool al wegvangen en bewees deze
        test niets over de precheck -- een vacuum-test.

        Twee lijsten die apart worden onderhouden lopen vroeg of laat uiteen; dan moet de
        denylist winnen, en wel voordat een mens er via de Council iets van kan vinden.
        """
        from src.core.tool_broker.permission_manager import ToolPermissionManager

        agent, broker = _build_agent(_tool_call_lines(1, tool="update_salary"))
        # Manifest staat hem toe...
        agent.allowed_tools = [*agent.allowed_tools, "update_salary"]
        # ...maar het profiel verbiedt hem. Dat is de divergentie.
        assert (
            ToolPermissionManager().is_tool_allowed(agent.agent_id, "update_salary") is False
        ), "voorwaarde: update_salary staat in denied_actions van het piloot-profiel"

        result = await agent.execute_with_manifest_prompt(
            {"task": "verhoog salaris"}, initiated_by_user_id=agent._test_initiator
        )

        assert council_gate.await_count == 0, (
            "De Council is geraadpleegd over een actie die op de harde denylist staat. Dan "
            "kan een goedkeuring een 'nooit aanraken'-actie alsnog doorlaten -- precies wat "
            "ADR-036 D5 uitsluit."
        )
        assert broker.execute_tool.await_count == 0
        assert result.success is False
        assert result.status == ExecutionStatusContract.GEBLOKKEERD


@pytest.mark.unit
@pytest.mark.asyncio
class TestMissingInitiatorFailsClosed:
    async def test_missing_initiator_prevents_execution(self, council_gate: AsyncMock) -> None:
        """Zonder verantwoordelijke mens wordt er niets uitgevoerd.

        De gate legt het besluit vast op een `user_id`. Zonder initiator zou dat een
        verzonnen waarde worden en daarmee een autonome actie toeschrijven aan iemand die
        hem niet heeft gestart. Dan liever niets doen -- AI Act art. 14, en de ADR zelf:
        "een naam zonder ingreepmacht telt niet".
        """
        agent, broker = _build_agent(_tool_call_lines(1), initiator=None)

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0
        assert council_gate.await_count == 0, (
            "Er is een Council-aanvraag gedaan zonder bekende initiator; dan moet er een "
            "user_id verzonnen zijn."
        )
        errors = result.result_data.get("errors") or []
        assert any("initiator" in str(e).lower() for e in errors)
        assert result.success is False
        assert result.status == ExecutionStatusContract.GEBLOKKEERD


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheFloorOnlyAppliesToAnnexIiiHitlSkills:
    """Regressietest voor ADR-036 D4-002: de floor mag niet overreiken.

    Zonder deze test zou "de floor altijd toepassen, ongeacht classificatie" de vorige klasse
    ook groen laten -- een floor die iedere skill raakt is geen classificatie-afhankelijke
    grens meer, en zou elke skill zonder bekende reden naar HITL_REQUIRED dwingen.
    """

    async def test_a_non_hitl_skill_still_executes_directly_on_approval(
        self, council_gate: AsyncMock
    ) -> None:
        from src.core.als.agents.specialist_base import BaseSpecialistAgent

        config: dict[str, object] = {
            "agent_id": "test-generic-agent",
            "technology": "llm",
            "name": "Generic Test Agent",
            "description": "test",
            "allowed_tools": ["create_task"],
            # Expliciet NIET annex_iii/hitl -- dit is precies het geval dat de floor niet mag
            # raken.
            "annex_iii_classification": "none",
            "human_in_the_loop": "hotl",
        }
        agent = BaseSpecialistAgent(config=config, tenant_id=PILOT_TENANT)
        agent._initiated_by_user_id = INITIATOR  # type: ignore[attr-defined]
        council_gate.return_value = _decision("APPROVED")

        gate_error = await agent._council_rejection("create_task", {"foo": "bar"})

        assert gate_error is None, (
            f"Een niet-Annex-III/HITL-skill kreeg toch de floor toegepast: {gate_error!r}. De "
            "floor mag alleen skills raken waarvan het manifest human_in_the_loop == 'hitl' "
            "declareert."
        )

    async def test_a_non_hitl_skill_with_a_successful_tool_call_reports_klaar(
        self, council_gate: AsyncMock
    ) -> None:
        """ADR-036 D7-001: het tegenovergestelde van de piloot (finding 8 van de dag-7-brief).

        De piloot rapporteert GEBLOKKEERD bij een APPROVED-verdict (de floor tilt hem op naar
        een ticket). Een niet-Annex-III/HITL-skill met dezelfde APPROVED-uitkomst voert de
        tool wel echt uit en moet daadwerkelijk KLAAR kunnen bereiken -- zonder deze test zou
        een fout die GEBLOKKEERD te breed toepast (bijv. op elk APPROVED-verdict, niet alleen
        de floor-tak) hier onopgemerkt blijven.
        """
        from src.core.als.agents.specialist_base import BaseSpecialistAgent

        config: dict[str, object] = {
            "agent_id": "test-generic-agent-2",
            "technology": "llm",
            "name": "Generic Test Agent",
            "description": "test",
            "allowed_tools": ["create_task"],
            "annex_iii_classification": "none",
            "human_in_the_loop": "hotl",
        }
        agent = BaseSpecialistAgent(config=config, tenant_id=PILOT_TENANT)
        agent._initiated_by_user_id = INITIATOR  # type: ignore[attr-defined]
        council_gate.return_value = _decision("APPROVED")
        broker = AsyncMock()
        broker.execute_tool = AsyncMock(return_value={"success": True})
        agent.tools = broker  # type: ignore[attr-defined]

        result = await agent.act('TOOL_CALL: create_task {"title": "x"}')

        assert broker.execute_tool.await_count == 1, (
            "De tool is niet uitgevoerd ondanks een APPROVED-verdict voor een "
            "niet-Annex-III/HITL-skill."
        )
        assert result.success is True
        assert result.status == ExecutionStatusContract.KLAAR

    async def test_a_governance_block_dominates_a_simultaneous_partial_success(
        self, council_gate: AsyncMock
    ) -> None:
        """ADR-036 D7-001 -- prioriteitsbewijs: een governance-weigering domineert over een
        gelijktijdig deelsucces (mappingtabel, dag-7-brief punt 9).

        Twee tool-calls op een niet-Annex-III/HITL-skill: de eerste krijgt APPROVED (voert
        echt uit en slaagt), de tweede BLOCKED. Zonder de prioriteitsregel zou `results`
        niet-leeg zijn en de status GEDEELTELIJK worden -- maar een governance-weigering
        moet zichtbaar blijven als GEBLOKKEERD, ook als er al iets is gelukt."""
        from src.core.als.agents.specialist_base import BaseSpecialistAgent

        config: dict[str, object] = {
            "agent_id": "test-generic-agent-3",
            "technology": "llm",
            "name": "Generic Test Agent",
            "description": "test",
            "allowed_tools": ["create_task", "delete_task"],
            "annex_iii_classification": "none",
            "human_in_the_loop": "hotl",
        }
        agent = BaseSpecialistAgent(config=config, tenant_id=PILOT_TENANT)
        agent._initiated_by_user_id = INITIATOR  # type: ignore[attr-defined]
        council_gate.side_effect = [_decision("APPROVED"), _decision("BLOCKED")]
        broker = AsyncMock()
        broker.execute_tool = AsyncMock(return_value={"success": True})
        agent.tools = broker  # type: ignore[attr-defined]

        decision = (
            'TOOL_CALL: create_task {"title": "x"}\n' 'TOOL_CALL: delete_task {"id": "1"}'
        )
        result = await agent.act(decision)

        assert result.result_data["tool_calls"] == 2
        assert len(result.result_data["results"]) == 1, "voorwaarde: de eerste actie slaagde"
        assert len(result.result_data["errors"]) == 1, "voorwaarde: de tweede werd geblokkeerd"
        assert result.status == ExecutionStatusContract.GEBLOKKEERD, (
            "Een governance-weigering moet domineren over een gelijktijdig deelsucces -- "
            "anders leest een mens GEDEELTELIJK waar in werkelijkheid een actie is "
            "tegengehouden door beleid."
        )

    async def test_a_broken_governance_gate_reports_mislukt(
        self, council_gate: AsyncMock
    ) -> None:
        """ADR-036 D7-001 -- gevonden door Gate 2 (code-reviewer), bewezen met een LIVE
        mutatie: `governance_unavailable` naar `GEBLOKKEERD` laten wijzen liet alle 64
        gerichte tests groen, want geen enkele test raakte deze tak.

        Als de governance-poort ZELF een exception gooit (niet het VERDICT, maar de
        AANROEP ernaartoe), is dat een infrastructuurstoring, geen bewuste weigering --
        `kind="governance_unavailable"` -> MISLUKT, niet GEBLOKKEERD."""
        from src.core.als.agents.specialist_base import BaseSpecialistAgent

        config: dict[str, object] = {
            "agent_id": "test-generic-agent-4",
            "technology": "llm",
            "name": "Generic Test Agent",
            "description": "test",
            "allowed_tools": ["create_task"],
            "annex_iii_classification": "none",
            "human_in_the_loop": "hotl",
        }
        agent = BaseSpecialistAgent(config=config, tenant_id=PILOT_TENANT)
        agent._initiated_by_user_id = INITIATOR  # type: ignore[attr-defined]
        council_gate.side_effect = RuntimeError("database niet bereikbaar")

        result = await agent.act('TOOL_CALL: create_task {"title": "x"}')

        errors = result.result_data.get("errors") or []
        assert any("niet bereikbaar" in str(e).lower() for e in errors)
        assert result.status == ExecutionStatusContract.MISLUKT, (
            "Een onbereikbare governance-poort is een infrastructuurstoring, geen "
            "bewuste weigering -- dat verschil moet zichtbaar blijven in het "
            "statuscontract."
        )

    async def test_governance_unavailable_dominates_a_simultaneous_partial_success(
        self, council_gate: AsyncMock
    ) -> None:
        """Zelfde prioriteitsbewijs als hierboven, maar voor `governance_unavailable`:
        die moet ook domineren over een deelsucces, en over een `governance`-weigering
        (een infrastructuurstoring is minder vertrouwenswaardig dan een bewust
        Council-verdict, dus MISLUKT weegt zwaarder)."""
        from src.core.als.agents.specialist_base import BaseSpecialistAgent

        config: dict[str, object] = {
            "agent_id": "test-generic-agent-5",
            "technology": "llm",
            "name": "Generic Test Agent",
            "description": "test",
            "allowed_tools": ["create_task", "delete_task"],
            "annex_iii_classification": "none",
            "human_in_the_loop": "hotl",
        }
        agent = BaseSpecialistAgent(config=config, tenant_id=PILOT_TENANT)
        agent._initiated_by_user_id = INITIATOR  # type: ignore[attr-defined]
        council_gate.side_effect = [_decision("APPROVED"), RuntimeError("database weg")]
        broker = AsyncMock()
        broker.execute_tool = AsyncMock(return_value={"success": True})
        agent.tools = broker  # type: ignore[attr-defined]

        decision = (
            'TOOL_CALL: create_task {"title": "x"}\n' 'TOOL_CALL: delete_task {"id": "1"}'
        )
        result = await agent.act(decision)

        assert len(result.result_data["results"]) == 1, "voorwaarde: de eerste actie slaagde"
        assert result.status == ExecutionStatusContract.MISLUKT, (
            "Een onbereikbare governance-poort moet ook domineren over een "
            "gelijktijdig deelsucces."
        )
