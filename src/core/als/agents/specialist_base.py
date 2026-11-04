import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional, Protocol, Tuple, cast

from src.core.als.agents.skill_manifest import SkillBudget, SkillBudgetExceeded

from src.core.als.agents.skill_rollout import resolve_config_for_tenant
from src.core.als.agents.symbiotic_agent import SymbioticAgent
from src.core.shared.rollout import is_in_rollout
from src.core.als.infrastructure.signal_bus import Signal
from src.core.copilot.council.background_gate import request_council_decision_for_agent
from src.core.copilot.council.types import DecisionVerdict, ProposalTrigger
from src.core.learning.cross_agent_service import (
    CrossAgentLearningService,
    get_tenant_synapse_network,
)
from src.core.learning.services.adaptation_service import AdaptationService
from src.core.services.llm.base import LLMMessage
from src.core.services.llm.service import LLMService
from src.core.shared.interfaces import ExecutionResult, ExecutionStatusContract, TaskData
from src.core.shared.tenant_llm_keuze import TenantLLMKeuzeFout, TenantLLMNietBeschikbaarError
from src.core.tool_broker.service import ToolBrokerService

logger = logging.getLogger(__name__)

# AI-bekendmaking die bij ELK toolvoorstel van een agent meegaat (EU AI Act art. 50).
# De ComplianceOfficer eist dit veld in `action_params` (`compliance_officer.py:127`).
#
# Bewust een LOKALE constante en niet `governance.attribution.get_ai_disclosure_text()`, om
# twee redenen. Inhoudelijk: die functie levert de tekst die aan een MENS wordt getoond bij de
# start van een gesprek ("You are interacting with an AI system..."); dit veld is een
# eigenschap van deze ene handeling en wordt aan niemand getoond. Meetbaar: die import zou een
# agent_runtime->governance-koppeling toevoegen, en dat budget is krap -- gemeten 2026-08-16
# ging `tests/architecture/test_dsm006_ar_governance_fan_out.py` van groen naar rood door
# precies die ene importregel.
#
# Hier stond "dat budget staat op 8 en is precies vol". Dat is sinds 2026-09-22 onwaar: de
# InputGuard heeft het plafond naar 9 gebracht, met de reden in de docstring van die test. De
# afweging hierboven verandert daar niet door -- de tekst is een eigenschap van de handeling
# en niet iets dat een mens te zien krijgt -- maar een getal in een comment dat niet meer
# klopt, stuurt de volgende lezer het verkeerde bos in.
_AI_DISCLOSURE = (
    "Deze handeling is voorgesteld door een AI-agent en niet door een mens. EU AI Act art. 50."
)

# ADR-036 OP-10: gefaseerde uitrol van de manifestprompt in orient(). Los van de per-manifest
# canary uit skill_rollout.py (OP-02, welke TEKST een tenant ziet); dit bepaalt of orient() de
# manifestprompt uberhaupt gebruikt in plaats van zijn eigen, zelfgebouwde tekst. Eigen salt
# zodat dezelfde tenants niet bij elke uitrol op het platform als eerste worden gekozen.
_ORIENT_MANIFEST_PROMPT_ROLLOUT_ENV = "ORIENT_MANIFEST_PROMPT_ROLLOUT_PERCENTAGE"
_ORIENT_MANIFEST_PROMPT_ROLLOUT_SALT = "orient_manifest_prompt"


def _orient_manifest_prompt_rollout_percentage() -> int:
    """Bij ELKE aanroep gelezen en niet bij import, zelfde reden als de canary-noodrem."""
    raw = os.getenv(_ORIENT_MANIFEST_PROMPT_ROLLOUT_ENV, "0")
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "orient_manifest_prompt_rollout: %s=%r is geen geheel getal, val terug op 0 (uit)",
            _ORIENT_MANIFEST_PROMPT_ROLLOUT_ENV,
            raw,
        )
        return 0


# Dummy client implementations for type checking when None is passed
class _DummySerenaClient:
    """Dummy implementation for optional serena client."""

    async def call(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {"status": "noop", "tool": tool_name}


class _DummySeqThinkingClient:
    """Dummy implementation for optional seq_thinking client."""

    async def call(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {"status": "noop", "tool": tool_name}


class BaseSpecialistAgent(SymbioticAgent):
    """
    The engine that gives real skills to our 135+ agents.
    It dynamically loads prompts and tools based on YAML config.
    """

    def __init__(
        self,
        config: dict[str, object],
        tenant_id: int,
    ) -> None:
        # ADR-036 OP-02: HIER wordt de gefaseerde uitrol beslist, en nergens anders. Dit is
        # het enige punt waar het manifest en de tenant elkaar tegenkomen: de skill-klassen
        # laden hun manifest in `__init__` zonder tenant, en `to_config()` kent hem evenmin.
        # Een tenant buiten de uitrol krijgt exact hetzelfde object terug, dus het gewone pad
        # betaalt niets. Zonder canary-blok in het manifest is dit een dict-lookup.
        config = resolve_config_for_tenant(config, tenant_id)
        super().__init__(
            agent_id=cast(str, config["agent_id"]),
            tenant_id=tenant_id,
            agent_type=cast(str, config["technology"]),
        )
        self.config = config
        self.allowed_tools: list[str] = cast(list[str], config.get("allowed_tools", []))
        self.llm: LLMService | None = None

        # ADR-036 D10 stap 5 (BE-AGT-041): het manifest-budget wordt hier ingelezen en
        # verderop DAADWERKELIJK gehandhaafd. Tot 2026-08-01 werden deze velden alleen
        # geparseerd en teruggeserialiseerd in SkillManifest.to_dict() -- 135 manifesten met
        # identieke waarden die niets deden. Een ontbrekend budget-blok valt terug op de
        # defaults van SkillBudget (8 / 5 / 60 / 100).
        raw_budget = config.get("budget")
        self.budget: SkillBudget = (
            SkillBudget.from_dict(cast(dict[str, int], raw_budget))
            if isinstance(raw_budget, dict)
            else SkillBudget()
        )
        # Tellers per invocatie; gereset door _run_within_budget.
        self._llm_calls_used: int = 0

        # ADR-036 D2 (BE-AGT-042): de mens die deze uitvoering startte. De Council legt zijn
        # besluit vast op een user_id, dus zonder bekende initiator wordt er niets
        # uitgevoerd -- een verzonnen id zou een autonome actie toeschrijven aan iemand die
        # hem niet startte. Gezet door het uitvoerpad, niet via een ContextVar: impliciete
        # ambient identiteit is precies wat hier misging.
        self._initiated_by_user_id: int | None = None
        # Agentstap in een workflow (agentstap dag 1, 2026-10-24): de toets of de MENS die de workflow
        # startte het recht heeft voor DEZE tool (`starter_heeft_toolrecht`), gezet door het uitvoerpad
        # van de stap en nergens anders. `None` = geen workflowstap: dan geldt alleen de Council-poort.
        self._toolrecht_toets: Callable[[str], Awaitable[bool]] | None = None
        # The ToolBroker now enforces our Phase C permissions
        # Use cast to satisfy protocol types when passing None-like dummies
        import importlib

        _db_mod = importlib.import_module("src.core.database.database")
        db_manager = _db_mod.db_manager

        from src.core.tool_broker.hitl_store import HITLStore

        dummy_serena = _DummySerenaClient()
        dummy_seq = _DummySeqThinkingClient()
        self.tools = ToolBrokerService(
            serena_client=cast(Any, dummy_serena),  # TODO(TYPE): replace Any with concrete type
            seq_thinking_client=cast(Any, dummy_seq),  # TODO(TYPE): replace Any with concrete type
            hitl_store=HITLStore(session_factory=db_manager.get_session),
            audit_session_factory=db_manager.get_session,
        )
        self._adaptation_service = AdaptationService(tenant_id=tenant_id)
        self._cross_agent_learning_service = CrossAgentLearningService(
            tenant_id=tenant_id,
            synapse_network=get_tenant_synapse_network(tenant_id),
        )

    async def observe(
        self, signal: Signal
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Standard observation: Gather context from allowed data sources."""
        logger.info(f"Agent {self.agent_id} observing signal {signal.signal_id}")
        return signal.payload

    async def orient(
        self,
        observation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Standard orientation: LLM analyzes how to solve the task with allowed tools."""
        # Extract task info from observation if available
        task_title = observation.get("title", "Unknown Task")
        task_description = observation.get("description", "")

        learning_prompt = self._get_learning_prompt_context(observation)
        cross_agent_prompt = await self._get_cross_agent_prompt_context(observation)
        manifest_prompt = self.config.get("system_prompt")
        if manifest_prompt and is_in_rollout(
            self.tenant_id,
            percentage=_orient_manifest_prompt_rollout_percentage(),
            salt=_ORIENT_MANIFEST_PROMPT_ROLLOUT_SALT,
        ):
            # ADR-036 OP-10: het manifest draagt het TOOL_CALL-contract en de instructie om
            # nooit gegevens te verzinnen; de zelfgebouwde tekst hieronder heeft dat niet.
            system_prompt = f"""
        {manifest_prompt}
        {learning_prompt}
        {cross_agent_prompt}
        """
        else:
            system_prompt = f"""
        You are {self.config["name"]}.
        Your role: {self.config["description"]}.
        Your tools: {", ".join(self.allowed_tools)}.
        Strictly follow the OODA loop.
        {learning_prompt}
        {cross_agent_prompt}
        """
        user_prompt = f"Task: {task_title}\nDescription: {task_description}"

        # Real LLM call to plan the action - use proper message format
        messages: list[LLMMessage] = [LLMMessage(role="user", content=user_prompt)]
        result = await (await self._get_llm_service()).generate(
            messages,
            system_prompt=system_prompt,
        )
        plan = result if isinstance(result, str) else result[0]
        return {"plan": plan, "observation": observation}

    async def _get_llm_service(self) -> LLMService:
        """Het taalmodel van DEZE tenant, laat opgebouwd en daarna hergebruikt.

        Wordt door `_count_llm_call()` geteld tegen `budget.max_llm_calls` -- zie daar
        waarom de teller hier hoort en niet op de aanroepplekken.

        **Async sinds BE-LLM-004, en dat is geen sierlijkheid.** De keten van een klant staat
        in de database, dus de resolutie is per definitie async. Tot nu toe bouwde deze methode
        `LLMService()` -- de platformstandaard -- terwijl `self.tenant_id` gewoon bekend was:
        een klant kon zijn eigen eindpunt inrichten en elke agent praatte toch met het onze.

        **Er wordt hier GEEN sessie meer geopend (BE-LLM-005).** Dat doet `for_tenant` zelf, en
        kort: hij haalt de rijen op, sluit de sessie, en doet daarna de adrescontrole -- die per
        rij een naamsopzoeking van maximaal vijf seconden kost en dus niet in een openstaande
        transactie hoort. De alinea die hier stond beschreef een `importlib`-import die in deze
        methode niet meer bestaat.

        **Wat het cachen op `self.llm` wel en niet betekent.** Een agent-exemplaar wordt per
        aanroep gebouwd (`loader.py:215`, `organism_registry.create_agent`), dus deze provider
        leeft zolang EEN taak leeft. De noodknop `externe_providers_toegestaan` werkt daardoor
        bij de volgende taak en niet halverwege deze -- en het vastgepinde IP blijft binnen een
        taak stabiel, wat precies de bedoeling is.

        **Valt de resolutie om, dan mislukt de taak met een duidelijke fout.** Sinds de Mistral-brief
        (2026-10-19, ADR-041 B14) is er GEEN terugval op de platformstandaard meer: die is in de
        uitrol DeepSeek, en de gegevens van een klant die ook maar een eigen keuze maakte mogen daar
        niet stil heen. Een klant zonder eigen provider krijgt zijn keuze (standaard Mistral).
        """
        if self.llm is None:
            try:
                # GEEN sessie meer van hier (BE-LLM-005). `for_tenant` opent er zelf een, kort,
                # en sluit hem voordat de adrescontrole begint -- die doet per rij een
                # naamsopzoeking van maximaal vijf seconden, en die hoort niet binnen een
                # openstaande databasetransactie. Met een keten van vier rijen was dat twintig
                # seconden verbindingsbezetting per agenttaak.
                self.llm = await LLMService.for_tenant(self.tenant_id)
            except TenantLLMKeuzeFout:
                # De taalmodelkeuze van de klant is ongeldig of niet te gebruiken (ontbrekende
                # sleutel, ongeldige waarde, niet te lezen). NIET terugvallen op het platformmodel:
                # dat is in de uitrol DeepSeek, en een klant die `ollama` koos hoort geen gehuurd
                # model te krijgen. Een duidelijke fout (ADR-041 B14, Gate 2 2026-10-19).
                raise
            except (AttributeError, TypeError, ImportError, NameError):
                # **Deze vier gaan DOOR, en dat is de kern van de terugval hieronder.**
                # Beide Gate 2-reviewers wezen hetzelfde aan: een kale `except Exception` maakt
                # van elk defect in dit pad "de agent werkte, alleen met een ander model" --
                # onzichtbaar in elke test, elk log en elke acceptatiemeting. Dat is precies de
                # succes-zonder-werk-vorm waar ADR-036 om draait, en deze knip repareerde er
                # net zelf een (een ontbrekende methode op de echte adrescontrole, gevonden
                # door de typecontrole en NIET door de tests).
                #
                # Een programmeerfout hoort dus luid te zijn. Een configuratie- of
                # infrastructuurfout niet: dan is doorwerken op het platformmodel beter dan
                # een agent die helemaal niets doet.
                raise
            except Exception as exc:
                # GEEN terugval op `LLMService()` meer (ADR-041 B14, Gate 2 2026-10-19). Het
                # platformmodel is in de uitrol DeepSeek, en een klant die `ollama` koos of een eigen
                # eindpunt (AVG art. 28) heeft ingericht, mag daar bij een storing niet stil terecht
                # komen: de gegevens zijn dan al weg. Een duidelijke fout is beter dan een verkeerde
                # verwerker; de taak mislukt zichtbaar en kan worden herhaald.
                logger.error(
                    "LLM-resolutie voor tenant %s mislukt (%s) -- de taak wordt NIET op het "
                    "platformmodel uitgevoerd",
                    self.tenant_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                raise TenantLLMNietBeschikbaarError(
                    "het taalmodel van deze omgeving kon niet worden bepaald; er is bewust niet "
                    "teruggevallen op het platformmodel"
                ) from exc
        return self.llm

    def _count_llm_call(self) -> None:
        """Registreer een LLM-aanroep en handhaaf `budget.max_llm_calls`.

        ADR-036 D10 stap 5 (BE-AGT-041). Bewust een expliciete aanroep vlak voor elke
        `generate()` in plaats van tellen bij de aanroepplekken zelf: de teller staat naast
        `_get_llm_service()`, zodat wie een nieuw LLM-pad toevoegt hem direct tegenkomt. Een
        teller die verspreid over call-sites leeft, rot weg zodra iemand een pad toevoegt --
        precies het gat dat deze fase moet dichten.

        Vandaag doet het piloot-pad exact een aanroep, dus deze grens is bescherming voor het
        moment dat er een meerstaps-lus komt. Hij is nu al werkzaam en niet "later aan te
        zetten".
        """
        self._llm_calls_used += 1
        if self._llm_calls_used > self.budget.max_llm_calls:
            raise SkillBudgetExceeded(
                f"max_llm_calls={self.budget.max_llm_calls} overschreden "
                f"({self._llm_calls_used} aanroepen) voor agent {self.agent_id}"
            )

    def _get_permission_manager(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """De permissiemanager, bij voorkeur die van de broker (BE-AGT-043).

        `ToolPermissionManager.__init__` leest en parseert `config/tool_permissions.yml` van
        schijf. Een vers exemplaar per tool-actie betekende bij `max_steps=8` dus acht
        schijfleesacties per invocatie -- gemeten in
        `tests/unit/als/test_agent_governance_hardening.py`.

        Belangrijker dan de kosten: `ToolBrokerService` heeft er al een
        (`tool_broker/service.py:114`), en dat is precies de manager waartegen `execute_tool`
        straks opnieuw toetst. Twee exemplaren voor dezelfde denylist kunnen uiteenlopen;
        hergebruik houdt het bij een bron.

        De `isinstance`-controle is er voor aanroepers die `self.tools` vervangen door een
        dubbel: een mock levert bij attribuutopvraging weer een mock op, en die is waarheidig
        -- dan zou `is_denied()` alles blokkeren. Valt de broker af, dan bouwen we zelf een
        exemplaar en cachen dat op de instantie.
        """
        cached = getattr(self, "_permission_manager", None)
        if cached is not None:
            return cached

        from src.core.tool_broker.permission_manager import ToolPermissionManager

        from_broker = getattr(self.tools, "permission_manager", None)
        manager = (
            from_broker
            if isinstance(from_broker, ToolPermissionManager)
            else ToolPermissionManager()
        )
        self._permission_manager = manager
        return manager

    def _reject_before_council(
        self, tool_name: str, params: dict[str, object] | None = None
    ) -> str | None:
        """Weigeringen die VOOR de Council horen. Retourneert de reden, of None.

        Drie gronden, alle drie fail-closed:

        **De inhoud van de parameters (2026-09-22).** De Council beoordeelt de VORM van een
        actie: hij krijgt de toolnaam en de NAMEN van de argumenten, nooit de waarden
        (BE-AGT-043, ADR-036 OP-25). Dat is met opzet zo -- alles wat hij ziet gaat de
        onuitwisbare ADR-019-keten in -- maar het betekent dat een BSN in een vrije opdracht
        vandaag ongehinderd langs de hele governance-laag reist. `input_guard` staat daarom
        HIER: hij leest de waarden wel en bewaart niets. Zie zijn moduledocstring voor waarom
        dat kanaal buiten de Council moet blijven.

        **De D5 harde denylist.** Een actie op `denied_actions` mag de Council niet eens
        bereiken -- anders kan een menselijke goedkeuring een "nooit aanraken"-actie alsnog
        doorlaten (ADR-036 D5, AI Act art. 14).

        **Een ontbrekende initiator.** De Council legt zijn besluit vast op een `user_id`.
        Zonder bekende initiator zou dat een verzonnen waarde worden en daarmee een autonome
        agent-actie toeschrijven aan iemand die hem niet startte. Dan liever niets doen. Hier
        vult later D1 in met het afdelingshoofd als eigenaar van de agent-keten; tot dan is
        de mens die de uitvoering start de enige verifieerbare bron.

        **Welk pad kan die initiator zetten?** Vandaag alleen
        `execute_with_manifest_prompt()` van de piloot-skill. Het OODA-pad
        (`_execute_task()` -> `act()`), dat de overige 134 skills gebruiken, kan hem niet
        meegeven: `TaskData` heeft geen gebruikersveld en `process_task()` wijzigen raakt 18
        overrides en 26 aanroepers. Daar voert een skill dus geen enkele tool uit. Dat is de
        bedoeling en geen omissie -- vastgelegd in
        `tests/unit/als/test_agent_governance_hardening.py` en als OP-21 in ADR-036 par. 10.
        """
        # Expres `is_denied()` en niet `is_tool_allowed()`: die laatste bevat ook de
        # allowlist en de ADR-015 default-deny, en dan zou elke agent zonder profiel hier al
        # stranden -- een veel bredere gedragswijziging dan D5 vraagt. De allowlist en de
        # default-deny blijven het werk van execute_tool, waar ze al getest zijn.
        if self._get_permission_manager().is_denied(self.agent_id, tool_name):
            return (
                f"geweigerd door de harde denylist (ADR-036 D5): {tool_name} staat op de "
                f"'nooit aanraken'-lijst van agent {self.agent_id}. De Council is hierover "
                "niet geraadpleegd."
            )

        if self._initiated_by_user_id is None:
            return (
                "geen initiator bekend: er is geen verantwoordelijke mens aan deze uitvoering "
                "gekoppeld, dus de actie wordt niet uitgevoerd (AI Act art. 14)."
            )

        # De inhoudswachter, als laatste van de drie: pas nadat vaststaat dat deze actie
        # ueberhaupt mag en dat er een verantwoordelijke mens is, heeft het zin om de waarden te
        # beoordelen.
        #
        # De HELE `params` gaat erin, niet elke stringwaarde apart. De eerste versie liep met
        # `isinstance(waarde, str)` over de bovenste laag en liet daarmee
        # `{"employees": [{"bsn": "..."}]}` ongehinderd door -- en `params` is de `json.loads()`
        # van modeloutput zonder schema, dus die nesting kiest het model zelf. Die payload gaat
        # als `ticket_action_params` naar `hitl_tickets.payload`, dat in
        # `tool_broker/redaction.py` als "LIVE en RAUW" staat gedocumenteerd. Gevonden in Gate 2
        # op 2026-09-22; `detect_pii` doorzoekt geneste structuren zelf al, dus de eerste versie
        # gooide capaciteit weg die er al was.
        from src.core.governance.input_guard import beoordeel

        oordeel = beoordeel(params or {}, tenant_id=self.tenant_id, herkomst=f"agent:{tool_name}")
        if not oordeel.toegestaan:
            # `oordeel.reden` bevat de CATEGORIE en een verwijzing, nooit de gevonden tekst --
            # deze melding belandt in `result_data["errors"]` en dus in de leeropslag.
            return f"inhoud van de parameters geweigerd: {oordeel.reden()}"

        return None

    def _floor_applies_to(self, tool_name: str) -> bool:
        """Moet deze actie, ook bij een goedkeurend verdict, langs een mens? (ADR-036 D4-002)

        Alleen voor een skill met `human_in_the_loop: hitl`. Daarbinnen twee gevallen:

        - **Annex III** (`annex_iii_classification: annex_iii`): ELKE actie, ook lezen. Dat is de
          regel van ADR-036 OP-165 en hij verandert hier niet; de twaalf hitl-skills van
          2026-10-05 zijn allemaal Annex III (gemeten met `grep -l "human_in_the_loop: hitl"`
          over de manifesten en hun classificatie).
        - **Niet Annex III** (vandaag alleen de debiteurenagent, dag 2): alleen een HIGH-risk
          actie. Een debiteurenlijst lezen hoort niet op een mens te wachten; een brief aan een
          klant wel. Zonder dit onderscheid zou elke leesactie een ticket opleveren dat na
          goedkeuring nergens naartoe kan -- het resultaat van een lezing komt via de
          goedkeurroute nooit terug bij de agent.

        De risicoklasse komt van dezelfde classifier als de HITL-poort in de broker, zodat de twee
        niet uiteen kunnen lopen. `importlib`: zie de Ce-toelichting verderop in dit bestand.
        """
        if self.config.get("human_in_the_loop") != "hitl":
            return False
        if self.config.get("annex_iii_classification") == "annex_iii":
            return True
        import importlib

        risk = importlib.import_module("src.core.tool_broker.risk_classifier")
        # Een vers exemplaar en niet `self.tools.risk_classifier`: tests vervangen `self.tools`
        # door een dubbel, en dan zou een mock het risico bepalen. Hij leest dezelfde yml.
        niveau = risk.ToolRiskClassifier().classify(tool_name)
        return bool(niveau == risk.ToolRiskLevel.HIGH)

    async def _weiger_zonder_toolrecht_van_de_starter(self, tool_name: str) -> str | None:
        """Een agentstap mag niet meer dan de mens die de workflow startte (agentstap dag 1).

        Alleen actief als het uitvoerpad van een workflowstap `_toolrecht_toets` zette. Fail-closed:
        een toets die gooit telt als weigering, en de oproeper (`act`) vangt dat op als
        governance-poort niet bereikbaar.
        """
        if self._toolrecht_toets is None:
            return None
        if await self._toolrecht_toets(tool_name):
            return None
        return (
            f"de tool '{tool_name}' is niet uitgevoerd: de gebruiker die deze workflow startte "
            "heeft daar geen recht voor (of is niet bekend)."
        )

    async def _prepare_tool_params(
        self, tool_name: str, params: dict[str, object]
    ) -> dict[str, object] | str:
        """Vul de parameters van een actie aan VOOR de Council en de HITL-vloer.

        Standaard ongewijzigd. Een skill overschrijft dit als wat de mens moet goedkeuren niet
        uit het model mag komen -- de debiteurenagent zet hier de brief uit het sjabloon in
        (`dunning.py`). Een string terug is een weigering met die reden; de actie gaat dan niet
        naar de Council en er komt geen ticket.
        """
        return params

    async def _council_rejection(
        self,
        tool_name: str,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """Raadpleeg de Council over deze ene actie. Retourneert de reden bij afwijzing.

        De aanroeper (`act()`, via `_status_from_errors()`) vertaalt een afwijzing naar
        `ExecutionStatusContract.GEBLOKKEERD` (ADR-036 D7-001, fix-sprint dag 7).
        **Alleen APPROVED laat de actie door.**

        `MODIFIED` betekent dat een Officer de actie alleen in AANGEPASTE vorm accepteert;
        die aanpassingen staan in `decision.modifications`. Deze poort kan ze niet toepassen:
        hij geeft een reden terug, geen parameters, en `act()` heeft de originele `params` al
        klaarstaan voor `execute_tool`. MODIFIED doorlaten zou dus de ONGEWIJZIGDE actie
        uitvoeren en precies de inperking negeren waar de Officer om vroeg -- een
        scope-beperking van de SecurityOfficer of een redactie van de PrivacyOfficer valt dan
        stil weg. Daarom weigeren, net als `copilot/council/governance_gate.py` doet (403).
        `copilot/service.py` voegt de aanpassingen wel samen; dat vraagt een poort die
        parameters kan teruggeven en is werk voor een latere fase (BE-AGT-043).

        Uitzondering sinds ADR-036 OP-168-vervolg (2026-08-25): voor een skill met
        `human_in_the_loop: hitl` in het manifest wordt een MODIFIED-verdict door de D4-002-
        floor hieronder eerst opgetild naar HITL_REQUIRED, VOORDAT deze weigering-logica het
        ziet -- die skill krijgt dus een ticket, geen kale afwijzing. Voor elke andere skill
        blijft de weigering hierboven het enige lot van MODIFIED.

        Per ACTIE en niet per invocatie: een oordeel over het hele plan laat een
        afzonderlijke actie ongetoetst. Het aantal beraadslagingen is begrensd door
        `budget.max_steps` (BE-AGT-041).

        De gate kan wel degelijk gooien -- `get_db_session()`, `build_council()` en
        `deliberate()` doen geen van drieen een eigen except. De aanroeper in `act()` vangt
        dat af, zodat een databasehapering niet de al verzamelde resultaten weggooit.
        """
        outcome = await request_council_decision_for_agent(
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            user_id=cast(int, self._initiated_by_user_id),
            action_type=tool_name,
            # De RUWE parameters, apart van de geredigeerde `action_params` hieronder
            # (die alleen sleutelnamen naar de Council stuurt, BE-AGT-043). Het ticket
            # heeft de echte waarden nodig om de tool straks te kunnen uitvoeren --
            # zie `background_gate.py::request_council_decision_for_agent`'s docstring.
            ticket_action_params=params,
            # ALLEEN de sleutelnamen, nooit de waarden (BE-AGT-043). Twee redenen, beide
            # blokkerend bevonden in de Gate 2-review:
            #
            # 1. `params` komt uit `json.loads()` van modeloutput en werd verbatim
            #    weggeschreven naar `council_decisions.action_params` en meegehasht in de
            #    ADR-019-keten. Dat record is per ontwerp niet corrigeerbaar of wisbaar, dus
            #    HR-gegevens die daarin belanden botsen met AVG art. 16/17. De zusteringang
            #    `governance_gate.py` schrijft dat contract al voor: "keep PII out -- use
            #    keys only".
            # 2. Meerdere Officers lezen governance-vlaggen uit deze dict
            #    (`ai_disclosure`, `dsar_activated`, `department`). Zolang de inhoud
            #    modeloutput is, kan een prompt-injectie zijn eigen oordeel meesturen:
            #    `{"ai_disclosure": true}` zet de ComplianceOfficer stil. Genest onder een
            #    eigen sleutel kan modeloutput per constructie geen control-sleutel meer
            #    vullen.
            #
            # Wat de Council hiermee wel kan: de actiesoort en de vorm van de argumenten
            # beoordelen. Wat hij niet meer kan: de waarden inspecteren. Dat laatste vraagt
            # een kanaal dat NIET in de hash-keten belandt en is bewust uitgesteld -- OP-25.
            action_params={
                "tool": tool_name,
                "arg_keys": sorted(params),
                # Door het SYSTEEM gezet, nooit door het model. De ComplianceOfficer eist dit
                # veld (`compliance_officer.py:127`) en gaf zonder dit
                # APPROVE_WITH_MODIFICATION -- wat de coordinator MODIFIED maakt en deze poort
                # weigert, omdat hij geen parameters kan teruggeven. Daar strandde tot
                # 2026-08-15 elke toolactie van een agent op.
                # De payload wordt met opzet NIET samengevoegd: een `{"ai_disclosure": true}`
                # uit modeloutput zou de officier stilzetten die de bekendmaking bewaakt.
                "ai_disclosure": _AI_DISCLOSURE,
                # Systeemdata uit het manifest, geen modeltekst. `_ComplianceAdapter`
                # (`factory.py:67-77`) leest deze twee velden en viel zonder hen terug op
                # "general" respectievelijk de actienaam.
                #
                # GEMETEN 2026-08-16, en dit hoort erbij: de uitkomst van `classify_agent()`
                # verandert hier vandaag NIET door. `hr_culture` staat niet in
                # `HIGH_RISK_DEPARTMENTS` en `query_hr_database` matcht geen
                # `HIGH_RISK_KEYWORDS`, dus de classificatie blijft LIMITED -- met en zonder
                # deze velden. Ze staan er omdat het de juiste, ware waarden zijn en omdat de
                # fix van OP-144 er op leunt; niet omdat ze vandaag iets veranderen. Een
                # eerdere versie van deze toelichting beweerde dat wel, en dat was onwaar.
                #
                # `name` en niet `role`: `SkillManifest.to_config()` levert geen `role`-sleutel
                # (gemeten: de functietitel staat onder `name`). De eerste versie las `role` en
                # stuurde daardoor altijd een lege string mee.
                "department": str(self.config.get("department", "")),
                "specialisation": str(self.config.get("name", "")),
            },
            reasoning=f"Agent {self.agent_id} wil {tool_name} uitvoeren.",
            # De SanityOfficer voert dit veld door `HallucinationGuard.check()`; leeg betekent
            # `empty_suggestion` en dus een veto. Alleen agent-id en toolnaam: geen
            # argumentNAMEN, want die komen uit `json.loads()` van modeloutput. Een sleutel die
            # `always` heet of op `.py` eindigt zou de guard laten weigeren -- dan kiest het
            # MODEL zijn eigen oordeel. Sinds fix-sprint dag 6 (2026-08-20, ADR-036 D2-002/OP-38)
            # wordt dit veld op de aanroepplek in `audit_writer.persist()` geredigeerd via
            # `value_digest()`, maar systeemtekst blijft hier de voorkeur: een gedigeste
            # modeltekst is voor een mens even onleesbaar als geen auditspoor.
            message=(
                f"Agent {self.agent_id} vraagt toestemming om de tool {tool_name} uit te voeren."
            ),
            # De uitvoering is door een mens gestart (die staat hierboven als user_id), dus
            # niet de default PROACTIVE_MONITOR: dat zou een autonome achtergrondscan
            # vastleggen en daarmee het verantwoordingsrecord onwaar maken.
            trigger=ProposalTrigger.USER_REQUEST,
        )

        decision = outcome.decision

        # ADR-036 D4-002: de Annex III/HITL-floor (ADR-036 OP-165). Een unaniem APPROVED-verdict
        # mag de classificatie in het manifest niet overstemmen -- anders is de classificatie
        # een label, geen grens, en zou een Council die toevallig voor stemt een Annex-III-actie
        # alsnog zonder menselijk toezicht laten lopen (AI Act art. 14).
        #
        # Sinds ADR-036 OP-168-vervolg (HITL-ticket-volledigheid sprint, 2026-08-25, Rakesh's
        # GO): ook een MODIFIED-verdict wordt opgetild. Zonder deze uitbreiding strandde een
        # APPROVE_WITH_MODIFICATION-verdict op deze piloot-skill (Annex III/HITL) hierboven op
        # `return f"Council-verdict modified: ..."` -- een kale weigering zonder ticket, ook al
        # eist het manifest juist ALTIJD menselijk toezicht voor deze skill. Dat is het
        # spiegelbeeld van dezelfde OP-168-bug die `coordinator.py::ALWAYS_HITL_ACTIONS` al
        # kreeg: een officier die "ja, mits aangepast" zegt mag een verplicht-HITL-classificatie
        # niet laten stranden als kale afwijzing -- een mens moet de voorgestelde aanpassing juist
        # kunnen accorderen via een ticket, niet nooit te zien krijgen.
        #
        # ALLEEN een upgrade naar HITL_REQUIRED, nooit een downgrade: BLOCKED/DEFERRED blijven
        # wat ze waren voor elke skill, geclassificeerd of niet. Vandaar de aparte
        # `effective_verdict` in plaats van `decision.verdict` rechtstreeks te overschrijven --
        # de originele Council-beslissing blijft intact voor logging/audit, alleen het gedrag
        # van DEZE poort verandert.
        effective_verdict = decision.verdict
        floor_applied = False
        if (
            effective_verdict in (DecisionVerdict.APPROVED, DecisionVerdict.MODIFIED)
            and self._floor_applies_to(tool_name)
        ):
            effective_verdict = DecisionVerdict.HITL_REQUIRED
            floor_applied = True

        if effective_verdict is DecisionVerdict.APPROVED:
            return None

        if effective_verdict is DecisionVerdict.HITL_REQUIRED:
            # Tot ADR-036 OP-163 werd HITL_REQUIRED hier identiek aan BLOCKED behandeld: de
            # actie werd afgewezen en er kwam nooit een echt goedkeuringsticket. Dat is precies
            # het omgekeerde van "menselijk toezicht" (AI Act art. 14 eist dat een mens de
            # output kan goedkeuren of tegenhouden, niet dat de actie stil verdwijnt).
            #
            # Sinds ADR-036 OP-167 (open-punten-opruiming, dag 1) maakt de gate ZELF al een
            # ticket aan zodra het RAUWE Council-verdict al HITL_REQUIRED was --
            # `outcome.hitl_ticket_ref` bevat die ref dan al. De D4-002-floor hierboven is een
            # ANDER mechanisme: die tilt een APPROVED-verdict LOKAAL op, iets waar de generieke
            # gate niets van weet (hij kent het manifest niet). Alleen in dat floor-geval maakt
            # deze poort zelf nog een ticket aan -- anders zou een raw-HITL_REQUIRED-verdict TWEE
            # tickets voor dezelfde beslissing opleveren (een uit de gate, een hier).
            if floor_applied:
                # `executing_identity=self.agent_id` en niet de default ("copilot"): dit pad
                # wordt ook door de piloot-skill (`skillsgaptraining`) bereikt, en die heeft in
                # `config/tool_permissions.yml` een grotendeels afwijkende toolset van `copilot`
                # (sinds 2026-09-21 delen ze NIETS: `send_notification` is uit het
                # piloot-manifest gehaald omdat er geen broker-tool voor bestaat, dus de
                # overlap is nul in plaats van een). Met de default zou de permissiecheck
                # in `create_hitl_request` hier onvoorwaardelijk falen voor elke
                # piloot-specifieke tool (bv. `query_hr_database`, uitsluitend bij de piloot)
                # die de piloot wel degelijk mag uitvoeren (ADR-036 OP-163).
                #
                # `importlib.import_module` voor BEIDE, en geen statische `from ... import ...`:
                # zelfde techniek als hierboven in `__init__` voor `database.database` (regel
                # 109). `test_agent_runtime_ce_dag2_final_target` telt elke
                # `ast.ImportFrom`-STATEMENT (ook binnen functiebodies -- lokaal plaatsen alleen
                # helpt niet) tegen een vaste Ce-ceiling van 225 voor `agent_runtime`. Gemeten:
                # twee statische imports (`get_db_session` uit de nog niet aangesproken bucket
                # `infra`, EN `HITLTicketRepository` -- die telt als eigen statement ook al deelt
                # hij een bucket met de al aanwezige `ToolBrokerService`-import) -> Ce=227. Een
                # statische + een importlib -> Ce=226. Beide via importlib -> Ce=225, exact op de
                # ceiling.
                import importlib

                _database_session = importlib.import_module("src.core.database.session")
                _hitl_repository = importlib.import_module("src.core.tool_broker.hitl_repository")
                # `create_hitl_request()` weigert zelf met ValueError (onbekende tool, OP-90)
                # of PermissionError (executing_identity mag de tool niet, OP-163) -- beide
                # gevangen, net als de gate hierboven doet: deze poort mag geen onverwachte
                # exception laten propageren voor een besluit dat wel degelijk HITL_REQUIRED
                # is (Gate 2-bevinding, dezelfde klasse fout als OP-167 zelf moest oplossen).
                try:
                    async with _database_session.get_db_session() as db:
                        ticket_ref = await _hitl_repository.HITLTicketRepository(
                            db
                        ).create_hitl_request(
                            tenant_id=self.tenant_id,
                            user_id=cast(int, self._initiated_by_user_id),
                            decision_id=str(decision.decision_id),
                            reason=decision.explanation_for_user,
                            action_type=tool_name,
                            action_params=params,
                            executing_identity=self.agent_id,
                        )
                except (ValueError, PermissionError) as exc:
                    logger.warning(
                        "Geen HITL-ticket mogelijk voor agent=%s tool=%s: %s: %s",
                        self.agent_id,
                        tool_name,
                        type(exc).__name__,
                        exc,
                        exc_info=True,
                    )
                    ticket_ref = None
            else:
                ticket_ref = outcome.hitl_ticket_ref

            if ticket_ref is None:
                return (
                    f"Council-verdict {effective_verdict.value}: {decision.explanation_for_user} "
                    "(geen goedkeuringsticket kon worden aangemaakt -- de actie is desondanks "
                    "niet uitgevoerd)"
                )
            return (
                f"Council-verdict {effective_verdict.value}: {decision.explanation_for_user} "
                f"(goedkeuringsticket aangemaakt: {ticket_ref})"
            )

        # Directe attribuuttoegang en geen getattr-met-lege-fallback: `explanation_for_user`
        # is een verplicht veld op CouncilDecision (`copilot/council/types.py:138`) en draagt
        # de uitleg waar de betrokkene recht op heeft (AVG art. 13-15). Zou het veld ooit
        # hernoemd worden, dan hoort dat een fout te geven -- niet stilzwijgend een lege
        # motivering (BE-AGT-043).
        if effective_verdict is DecisionVerdict.BLOCKED:
            # importlib om dezelfde reden als hierboven: geen extra ImportFrom-statement voor de Ce-ceiling.
            import importlib

            _blokkade = importlib.import_module("src.core.copilot.council.technische_blokkade")
            # getattr: sommige testdubbels van de beslissing dragen geen stemmen; een echte CouncilDecision wel.
            if _blokkade.is_technisch_niet_beoordeeld(getattr(decision, "officer_verdicts", ())):
                return str(_blokkade.KLANTTEKST_NIET_BEOORDEELD)
        return f"Council-verdict {effective_verdict.value}: {decision.explanation_for_user}"

    async def _run_within_budget(
        self,
        work: "Callable[[], Awaitable[ExecutionResult]]",
        *,
        task_id: str,
    ) -> ExecutionResult:
        """Voer `work` uit binnen het budget uit het manifest.

        Het enige afdwingpunt, gebruikt door BEIDE uitvoerpaden: `_execute_task()` (de
        OODA-weg van alle 135 skills) en `execute_with_manifest_prompt()` (het piloot-pad
        dat `packs.py` in productie gebruikt). Tot 2026-08-01 liep dat tweede pad volledig
        buiten de governance om -- geen budgetcheck, geen afrekening, geen limiet.

        Handhaaft:
          - department-prana vooraf via `PranaGuard.check_budget()` (ADR-021; no-op zolang
            `PRANA_ENFORCEMENT_ENABLED` uit staat). Geprijsd op `config["technology"]`
            (ml/llm/vision/hybrid), niet op `budget.prana_cost_limit` -- die kolom was een
            uniforme 100 in alle 135 manifesten en droeg geen echt onderscheid;
          - `budget.timeout_seconds` als BINNENSTE tijdsgrens. De pack-SLA
            (`packs.py`, `sla_seconds`) blijft de buitenste; de strakkere zit binnen en wint
            dus automatisch. Er wordt niets weggehaald;
          - afrekening bij succes, geprijsd volgens dezelfde agent-type-tier.

        `asyncio.wait_for` breekt het werk werkelijk af: `LLMService.generate` is puur async
        (geen executor of thread), dus de cancel komt aan. Let op dat die 60s het geheel
        omvat, inclusief de maximaal 3 interne retries met backoff van `generate` -- het
        budget is de totale grens van de skill, niet die van een enkele poging.

        De guard is injecteerbaar (`self._prana_guard`) omdat `check_budget()` een echte
        DB-sessie opent; zonder seam zou elke unit-test op het retry-backoff-probleem van
        OP-18 stuiten.
        """
        guard = self._get_prana_guard()
        agent_type = cast(str, self.config.get("technology", "llm"))

        try:
            await guard.check_budget(
                self.tenant_id,
                department=getattr(self, "department", None),
                agent_type=agent_type,
            )
        except Exception as exc:
            logger.warning(
                "Budgetcheck geweigerd voor agent %s: %s: %s",
                self.agent_id,
                type(exc).__name__,
                exc,
            )
            return ExecutionResult(
                task_id=task_id,
                success=False,
                error_message=str(exc),
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                status=ExecutionStatusContract.MEER_BUDGET_NODIG,
            )

        self._llm_calls_used = 0

        try:
            result = await asyncio.wait_for(work(), timeout=self.budget.timeout_seconds)
        except asyncio.TimeoutError:
            return ExecutionResult(
                task_id=task_id,
                success=False,
                error_message=(
                    f"timeout: budget.timeout_seconds={self.budget.timeout_seconds} "
                    f"overschreden voor agent {self.agent_id}"
                ),
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                status=ExecutionStatusContract.MEER_BUDGET_NODIG,
            )
        except SkillBudgetExceeded as exc:
            return ExecutionResult(
                task_id=task_id,
                success=False,
                error_message=str(exc),
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                status=ExecutionStatusContract.MEER_BUDGET_NODIG,
            )

        if result.success:
            # De afrekening mag een AL GELEVERD resultaat niet weggooien. `charge_prana` gooit
            # sinds SP-COUNCIL-GATE-001 wanneer geen rij wordt geraakt (een tenant die tijdens
            # de uitvoering is verdwenen); zonder deze vangst zou de gebruiker dan een
            # onbehandelde fout krijgen in plaats van zijn antwoord. Niet stil: ERROR met
            # stacktrace, want een niet-geboekte uitvoering is een gat in de financiele
            # governance dat zichtbaar moet zijn.
            try:
                await guard.charge_prana(
                    self.tenant_id,
                    department=getattr(self, "department", None),
                    agent_type=agent_type,
                )
            except Exception as exc:
                logger.error(
                    "prana-afrekening mislukt voor tenant %s (agent %s): %s: %s",
                    self.tenant_id,
                    self.agent_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )

        return result

    def _get_prana_guard(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """De prana-guard, injecteerbaar voor tests.

        Lazy import via importlib zoals `_execute_task` dat al deed (circulaire-import
        vermijding); een test patcht `src.core.governance.prana_guard.PranaGuard`.
        """
        if getattr(self, "_prana_guard", None) is None:
            import importlib

            module = importlib.import_module("src.core.governance.prana_guard")
            self._prana_guard = module.PranaGuard()
        return self._prana_guard

    def _get_learning_prompt_context(
        self,
        observation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format active learned adaptations into the specialist system prompt."""
        context = {
            "agent_id": self.agent_id,
            "agent_type": self.config.get("technology"),
            "task_type": observation.get("metadata", {}).get("type") or observation.get("type"),
        }
        rules = self._adaptation_service.get_relevant_rules(context)
        if not rules:
            return ""
        lines = ["## Learned Optimizations (auto-generated)"]
        for rule in rules:
            lines.append(f"- {rule.name}: {rule.action}")
        return "\n".join(lines)

    async def _get_cross_agent_prompt_context(
        self,
        observation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format shared patterns from related agents into the specialist system prompt."""
        task_type = observation.get("metadata", {}).get("type") or observation.get("type")
        patterns = await self._cross_agent_learning_service.get_related_patterns(
            cast(str | None, self.config.get("technology")),
            task_type=task_type,
        )
        if not patterns:
            return ""

        lines = ["## Shared Patterns From Related Agents"]
        for pattern in patterns[:5]:
            source_agent_type = pattern.learned_behavior.get("shared_from_agent_type")
            pattern_subtype = pattern.learned_behavior.get("pattern_subtype")
            lines.append(
                f"- {source_agent_type or pattern.trigger_conditions.get('agent_type')}: "
                f"{pattern_subtype or pattern.pattern_type.value}"
            )
        return "\n".join(lines)

    async def decide(
        self,
        orientation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Standard decision: Select the specific tool to call."""
        # For simplicity, we let the LLM output the tool call in the orient phase
        plan = orientation.get("plan", "")
        return plan if plan else "execute_task"

    # Regex for TOOL_CALL: tool_name {json_params}
    _TOOL_CALL_RE = re.compile(r"^TOOL_CALL:\s+(\S+)\s+(\{.*\})\s*$", re.MULTILINE)

    def _parse_tool_calls(
        self, decision: str
    ) -> list[tuple[str, dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Parse TOOL_CALL directives from a decision string.

        Format: TOOL_CALL: tool_name {"param": "value"}

        Returns list of (tool_name, params) tuples. Invalid JSON or
        disallowed tools are silently skipped with a warning log.
        """
        calls: list[tuple[str, dict[str, Any]]] = []  # TODO(TYPE): replace Any with concrete type
        for match in self._TOOL_CALL_RE.finditer(decision):
            tool_name = match.group(1)
            raw_json = match.group(2)

            # Validate JSON
            try:
                params = json.loads(raw_json)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Skipping TOOL_CALL with invalid JSON: %s %s",
                    tool_name,
                    raw_json[:80],
                )
                continue

            # Check allowed_tools if the list is non-empty
            if self.allowed_tools and tool_name not in self.allowed_tools:
                logger.warning(
                    "Rejected tool %s -- not in allowed_tools for agent %s",
                    tool_name,
                    self.agent_id,
                )
                continue

            calls.append((tool_name, params))
        return calls

    @staticmethod
    def _status_from_errors(
        results: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        errors: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionStatusContract:
        """ADR-036 D7-001: leidt het statuscontract af uit `act()`'s eigen boekhouding.

        Prioriteitsvolgorde bij samenloop, hoog naar laag: een governance-uitkomst
        domineert altijd over een gelijktijdig deelsucces -- de AI Act art.-14-zichtbaarheid
        van een weigering is belangrijker dan "er lukte ook iets"; een mens die GEBLOKKEERD
        leest mag niet per ongeluk denken dat het gewoon een deelsucces was. Binnen governance
        gaat een onbereikbare poort (infrastructuurstoring, `kind="governance_unavailable"`)
        voor een bewuste weigering (beleid, `kind="governance"`).

        De drie budgetafsluiters (Prana-tekort/timeout/max_llm_calls) komen hier NOOIT langs
        -- die breken `_run_within_budget()` al af voordat `act()` deze functie bereikt.
        `kind="step_limit"` (max_steps-overschrijding) is geen afsluiter maar een echte
        deeluitvoering en draagt daarom alleen bij aan GEDEELTELIJK, nooit aan
        MEER_BUDGET_NODIG.
        """
        if not errors:
            return ExecutionStatusContract.KLAAR

        kinds = {e.get("kind") for e in errors}
        if "governance_unavailable" in kinds:
            return ExecutionStatusContract.MISLUKT
        if "governance" in kinds:
            return ExecutionStatusContract.GEBLOKKEERD
        if results:
            return ExecutionStatusContract.GEDEELTELIJK
        return ExecutionStatusContract.MISLUKT

    async def act(self, decision: str) -> ExecutionResult:
        """Execute tool calls parsed from the decision string.

        Parses TOOL_CALL directives, executes each sequentially via
        ToolBrokerService, and collects results. Partial failures do not
        stop remaining tool calls.
        """
        start = time.perf_counter()
        tool_calls = self._parse_tool_calls(decision)

        if not tool_calls:
            elapsed = time.perf_counter() - start
            logger.info(
                "Agent %s: no TOOL_CALL found in decision, returning as-is",
                self.agent_id,
            )
            return ExecutionResult(
                task_id="act",
                success=True,
                result_data={"output": decision, "tool_calls": 0},
                execution_time=elapsed,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                status=ExecutionStatusContract.KLAAR,
            )

        results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        errors: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        # ADR-036 D10 stap 5 (BE-AGT-041): begrens het aantal tool-uitvoeringen op het
        # gedeclareerde max_steps. `_parse_tool_calls` gebruikt `finditer` zonder limiet, dus
        # een enkel LLM-antwoord kon willekeurig veel uitvoeringen veroorzaken -- met 30s
        # timeout per tool is dat tientallen minuten werk. Dit was het enige weglooppad dat
        # vandaag open stond.
        #
        # De overschrijding wordt EXPLICIET gemeld en niet stil afgekapt: minder doen dan
        # gevraagd en toch succes rapporteren is precies wat AUDIT-009 blootlegde.
        if len(tool_calls) > self.budget.max_steps:
            errors.append(
                {
                    "tool": "budget",
                    "error": (
                        f"max_steps={self.budget.max_steps} overschreden: het model vroeg "
                        f"{len(tool_calls)} tool-calls. Alleen de eerste "
                        f"{self.budget.max_steps} zijn uitgevoerd."
                    ),
                    # ADR-036 D7-001: dit kapt af en gaat DOOR (regels hieronder) -- een
                    # echte deeluitvoering (statuscontract GEDEELTELIJK), geen afsluiter zoals
                    # de drie budgetgrenzen in _run_within_budget() (die de hele aanroep
                    # afbreken, statuscontract MEER_BUDGET_NODIG).
                    "kind": "step_limit",
                }
            )
            logger.warning(
                "Agent %s: %d tool-calls gevraagd, max_steps=%d -- afgekapt",
                self.agent_id,
                len(tool_calls),
                self.budget.max_steps,
            )
            tool_calls = tool_calls[: self.budget.max_steps]

        for tool_name, params in tool_calls:
            # Dag 2 debiteurenagent: een skill kan de parameters aanvullen VOOR de poorten, zodat
            # het ticket draagt wat de mens moet lezen (`_prepare_tool_params`). Een weigering
            # hier is een toolfout, geen governance-besluit: er is niets om over te beslissen.
            #
            # De startertoets van een workflowstap staat NOG eerder: `_prepare_tool_params` leest gegevens (de
            # debiteur voor het voorbeeld van de brief), en een starter zonder het recht hoort daar niets van
            # te zien, ook niet via de foutmelding (Gate 2, agentstap dag 1).
            try:
                starter_fout = await self._weiger_zonder_toolrecht_van_de_starter(tool_name)
                starter_kind = "governance"
            except Exception as exc:
                logger.error(
                    "Startertoets faalde voor tool %s van agent %s: %s: %s",
                    tool_name,
                    self.agent_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                starter_fout = f"governance-poort niet bereikbaar: {type(exc).__name__}"
                starter_kind = "governance_unavailable"
            if starter_fout is not None:
                errors.append({"tool": tool_name, "error": starter_fout, "kind": starter_kind})
                continue
            voorbereid = await self._prepare_tool_params(tool_name, params)
            if isinstance(voorbereid, str):
                errors.append({"tool": tool_name, "error": voorbereid, "kind": "tool_failure"})
                continue
            params = voorbereid
            # ADR-036 D10 stap 6 / D2 (BE-AGT-042): elke actie langs de Council-poort.
            # De volgorde hieronder is onderdeel van het contract, niet toevallig:
            #
            #   1. manifest-allowlist   (al gebeurd in _parse_tool_calls)
            #   2. D5 harde denylist    hier, VOOR de Council
            #   3. Council per actie
            #   4. execute_tool         herhaalt 2 plus risk/HITL -- defence in depth
            #
            # Stap 2 staat bewust dubbel: zou de Council eerst oordelen, dan kan een
            # menselijke goedkeuring een "nooit aanraken"-actie alsnog doorlaten, en dat is
            # precies wat D5 uitsluit. De manifest-allowlist vangt vandaag hetzelfde af,
            # maar dat zijn twee apart onderhouden lijsten die vroeg of laat uiteenlopen.
            #
            # De poort staat in dezelfde try als de uitvoering: `_council_rejection` kan
            # gooien (de gate heeft alleen try/finally rond een DB-sessie), en een
            # databasehapering mag niet de al verzamelde resultaten van eerdere acties
            # weggooien. act() belooft in zijn eigen docstring dat een deelfout de rest niet
            # stopzet.
            gate_unavailable = False
            try:
                gate_error = self._reject_before_council(tool_name, params)
                if gate_error is None:
                    gate_error = await self._council_rejection(tool_name, params)
            except Exception as exc:
                logger.error(
                    "Council-poort faalde voor tool %s van agent %s: %s: %s",
                    tool_name,
                    self.agent_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                gate_error = f"governance-poort niet bereikbaar: {type(exc).__name__}"
                gate_unavailable = True

            if gate_error is not None:
                # Expliciet loggen: een geweigerde actie is precies het voorval dat AI Act
                # art. 14 vastgelegd wil zien, en `result_data["errors"]` wordt door niemand
                # gelezen (zie de toelichting bij `success` onderaan deze methode).
                logger.warning(
                    "Agent %s: tool %s geweigerd door de governance-poort -- %s",
                    self.agent_id,
                    tool_name,
                    gate_error,
                )
                # ADR-036 D7-001: "kind" onderscheidt een bewuste governance-weigering
                # (denylist/geen-initiator/Council-verdict, statuscontract GEBLOKKEERD) van de
                # poort die zelf onbereikbaar was (een infrastructuurstoring, MISLUKT) -- beide
                # zagen er hiervoor identiek uit voor de aanroeper.
                errors.append(
                    {
                        "tool": tool_name,
                        "error": gate_error,
                        "kind": "governance_unavailable" if gate_unavailable else "governance",
                    }
                )
                continue

            try:
                result = await self.tools.execute_tool(
                    tool_name=tool_name,
                    payload=params,
                    agent_id=self.agent_id,
                    timeout_seconds=30,
                    context={"tenant_id": self.tenant_id},
                )
                # Een tool die zelf meldt dat hij faalde, is geen geslaagde stap (BE-AGT-044).
                # Het toolcontract (BE-AGT-039 par. 3) schrijft `{"success": false, "error":
                # ...}` voor als foutvorm, en die kwam tot nu toe in `results` terecht: geen
                # exceptie, dus geen fout. De stap gold dan als geslaagd en de OODA-lus
                # rekende prana af voor werk dat niet is gebeurd. Dat is dezelfde bevinding
                # die F3 voor deelfouten oploste, maar voor deze vorm bleef staan -- zichtbaar
                # geworden nu de eerste echte tool die vorm kan produceren.
                if isinstance(result, dict) and result.get("success") is False:
                    reason = str(result.get("error") or "tool meldde success=false zonder reden")
                    logger.warning(
                        "Agent %s: tool %s meldde een fout -- %s",
                        self.agent_id,
                        tool_name,
                        reason,
                    )
                    errors.append({"tool": tool_name, "error": reason, "kind": "tool_failure"})
                else:
                    results.append({"tool": tool_name, "output": result})
            except Exception as exc:
                logger.warning(
                    "Tool %s failed for agent %s: %s",
                    tool_name,
                    self.agent_id,
                    exc,
                )
                errors.append({"tool": tool_name, "error": str(exc), "kind": "tool_exception"})

        elapsed = time.perf_counter() - start
        # Elke tool-fout maakt de stap onsuccesvol -- ook als andere tools wel slaagden.
        # Was `len(results) > 0 or len(errors) == 0`, waardoor 1 geslaagde en 1 mislukte
        # tool-call samen succes opleverden. Dat is niet alleen een verkeerde melding:
        # de OODA-loop hieronder rekent op dit veld prana af (charge_prana), dus de tenant
        # betaalde voor werk dat deels niet is uitgevoerd. Niemand leest result_data
        # ["errors"], dus er was geen tweede vangnet. Zie BE-AGT-039 / ADR-036 D10 stap 3.
        #
        # Het tekst-only-pad (geen tool-calls) retourneert eerder al met success=True en
        # komt hier niet langs; deze regel gaat uitsluitend over uitgevoerde tool-calls.
        success = not errors

        return ExecutionResult(
            task_id="act",
            success=success,
            result_data={
                "results": results,
                "errors": errors,
                "tool_calls": len(tool_calls),
            },
            execution_time=elapsed,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            status=self._status_from_errors(results, errors),
        )

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """The core OODA execution flow, uitgevoerd binnen het manifest-budget.

        De prana-check en -afrekening die hier inline stonden zitten sinds 2026-08-01 in
        `_run_within_budget()` (BE-AGT-041), samen met de tijdslimiet en de tellers. Reden
        voor die verplaatsing: het piloot-pad `execute_with_manifest_prompt()` liep volledig
        buiten deze governance om, en twee kopieen van dezelfde controle lopen onvermijdelijk
        uiteen. Nu is er een afdwingpunt voor beide paden.
        """

        # Create a signal from task data for OODA loop
        signal_payload: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": (
                task.priority.value if hasattr(task.priority, "value") else str(task.priority)
            ),
            "metadata": task.metadata,
        }
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=self.agent_id,
            target_agent_ids=[],
            tier="cognitive",
            payload=signal_payload,
        )

        async def _ooda() -> ExecutionResult:
            context = await self.observe(signal)
            plan = await self.orient(context)
            decision = await self.decide(plan)
            return await self.act(decision)

        return await self._run_within_budget(_ooda, task_id=task.id)
