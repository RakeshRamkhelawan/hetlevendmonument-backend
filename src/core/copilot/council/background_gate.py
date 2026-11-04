"""Transport-neutral Council-ingang voor achtergrondtaken (ADR-036 D2).

De bestaande HTTP-gebonden Council-code (governance_gate.py, factory.py,
coordinator.py) blijft VOLLEDIG ONGEWIJZIGD. Drie harde koppelpunten maakten
platformbreed hergebruik van die code onveilig:

  1. governance_gate.require_council_approval() communiceert via HTTPException
     -- niet bruikbaar buiten een FastAPI-requestcontext.
  2. factory.build_council() leest require_tenant_id() -- een ContextVar die
     normaal alleen door HTTP-middleware gezet wordt.
  3. _ToolBrokerAdapter.is_allowed hardcodeerde de agent-identiteit "copilot"
     (OPGELOST in AUDIT-007: build_council() accepteert nu een agent_id-parameter
     en deze ingang geeft die door, zodat elke achtergrondagent tegen zijn eigen
     ToolBroker-profiel wordt gecheckt -- ADR-015. Agents zonder profiel vallen
     op de ADR-015 default-deny -- fail-secure, nooit stilletjes toegestaan).

Deze module lost (1) en (2) op met een aparte, additieve ingang en geeft voor
(3) de agent_id door aan build_council(). Ze hergebruikt
build_council()/AgentCouncil.deliberate() ONGEWIJZIGD -- geen doublure van de
8-Officer-bedrading, om te garanderen dat deze weg nooit uit de pas kan lopen
met de HTTP-weg.

Tenant-context-volgorde volgt het GECORRIGEERDE patroon (zie AUDIT-003 in
docs/agent-briefs/generated/2026-07-03-audit-to-fix.md): het try-blok begint
direct na set_tenant_id(), zonder tussenliggende code die kan falen voordat de
finally-garantie actief is -- de referentie-implementatie in workflow_tasks.py
had hier zelf een cleanup-gat.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.factory import build_council
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    Proposal,
    ProposalTrigger,
)
from src.core.database.session import get_db_session
from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

logger = logging.getLogger(__name__)


class AgentCouncilOutcome(NamedTuple):
    """Result of `request_council_decision_for_agent()` (ADR-036 OP-167).

    `hitl_ticket_ref` is None unless `decision.verdict` is HITL_REQUIRED, in which case
    the gate function itself has already created the ticket -- the caller does not need
    to know how to do that (that used to be the gap: only `specialist_base.py` replicated
    this logic, so a second caller would have gotten no ticket at all).
    """

    decision: CouncilDecision
    hitl_ticket_ref: str | None


async def request_council_decision_for_agent(
    *,
    tenant_id: int,
    agent_id: str,
    user_id: int,
    action_type: str,
    action_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    reasoning: str,
    message: str = "",
    trigger: ProposalTrigger = ProposalTrigger.PROACTIVE_MONITOR,
    data_classification: DataClassification = DataClassification.INTERNAL,
    confidence: float = 1.0,
    model_id: str = "unknown",
    model_version: str = "1.0",
    context_snapshot: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ticket_action_params: dict[str, object] | None = None,
) -> AgentCouncilOutcome:
    """Vraag een Council-beslissing aan vanuit een Dramatiq-achtergrondtaak.

    In tegenstelling tot require_council_approval() (governance_gate.py:49) gooit
    dit GEEN HTTPException -- het retourneert altijd een AgentCouncilOutcome, ook bij
    een BLOCKED/HITL_REQUIRED-verdict. De aanroeper vertaalt een niet-APPROVED verdict
    zelf naar zijn eigen statuscontract (bv. `specialist_base.py::_council_rejection()`
    naar `ExecutionStatusContract.GEBLOKKEERD`, ADR-036 D7-001, fix-sprint dag 7).

    **ADR-036 OP-167 (fix-sprint dag 1 van het HITL-ticket-volledigheidsproject):** deze
    functie maakt nu ZELF een HITL-ticket aan zodra `decision.verdict` HITL_REQUIRED is --
    voorheen deed alleen de enige aanroeper (`specialist_base.py`) dat, met eigen
    gerepliceerde logica. Een tweede aanroeper zou daardoor stilzwijgend GEEN ticket
    hebben gekregen. Nu is de garantie onderdeel van de gate zelf.

    **Kan geen ticket aanmaken? Dan wordt `hitl_ticket_ref` None, er wordt NOOIT
    gegooid.** `HITLTicketRepository.create_hitl_request()` weigert zelf met `ValueError`
    (onbekende tool, OP-90) of `PermissionError` (`executing_identity` mag de tool niet,
    OP-163) -- terecht bij een aanroeper met een eigen requestgrens
    (`copilot/service.py::handle_turn`), maar deze functie kan niet garanderen dat ELKE
    aanroeper zo'n grens heeft. Beide worden hier gevangen en gelogd; de aanroeper krijgt
    een `AgentCouncilOutcome` met `hitl_ticket_ref=None` terug in plaats van een onverwachte
    exception voor een besluit dat wel degelijk HITL_REQUIRED was.

    `ticket_action_params`: de RUWE tool-parameters voor het ticket (nodig om de actie
    later daadwerkelijk te kunnen verzilveren). Standaard `None`, in welk geval
    `action_params` zelf wordt gebruikt (het patroon van `copilot/service.py::handle_turn`,
    dat geen aparte redactie-laag heeft). `specialist_base.py` geeft hier WEL een apart,
    ongeredigeerd dict door: zijn `action_params` bevat uit veiligheidsoverwegingen
    (BE-AGT-043) alleen sleutelnamen voor de Council, nooit de waarden -- het ticket heeft
    de echte waarden nodig om de tool straks te kunnen uitvoeren.

    agent_id wordt gebruikt voor logging/traceerbaarheid EN wordt doorgegeven
    aan build_council(agent_id=...), zodat de ToolBroker-permissiecheck van de
    SecurityOfficer het profiel van deze agent gebruikt in plaats van het
    hardcoded "copilot"-profiel (AUDIT-007, ADR-015). Heeft de agent nog geen
    permissieprofiel (AUDIT-008), dan geldt de ADR-015 default-deny.

    trigger: kies de waarde die de daadwerkelijke context weergeeft --
    PROACTIVE_MONITOR (default) voor een autonome achtergrondscan,
    SCHEDULED voor een terugkerende taak, ESCALATION voor een lateraal
    A2A-verzoek van een andere agent (ADR-036 D6).

    message: de tekst die de SanityOfficer beoordeelt via `HallucinationGuard.check()`. Leeg
    betekent `empty_suggestion` en dus een VETO -- daar strandde tot 2026-08-15 elke
    toolactie van een agent op, want deze parameter bestond niet eens.
    **Uitsluitend SYSTEEMTEKST meegeven blijft de aanbevolen praktijk.** Sinds fix-sprint dag 6
    (2026-08-20, ADR-036 D2-002/OP-38) wordt dit veld op de aanroepplek in
    `audit_writer.persist()` geredigeerd via `value_digest()` voordat het de ADR-019-hashketen
    ingaat -- net als `action_params` via `redact_for_publication()`. De opgeslagen waarde is
    daarmee voor een mens onleesbaar: modeltekst hier neerzetten levert dus geen leesbaar
    auditspoor op, systeemtekst wel.
    """
    logger.info(
        "Council-aanvraag via achtergrondingang: tenant=%s agent=%s action=%s trigger=%s",
        tenant_id,
        agent_id,
        action_type,
        trigger.value,
    )

    # Herstellen en niet wissen (BE-AGT-043). Zolang deze functie geen productie-aanroepers
    # had, was `set_tenant_id(None)` in de finally onschadelijk. Sinds BE-AGT-042 wordt hij
    # per tool-actie vanuit `act()` aangeroepen, in dezelfde asynctaak als de aanroeper --
    # dus die None lekte terug. Gevolg: `execute_tool` en alles eronder draaide zonder
    # tenant in de ContextVar, waardoor de ADR-004 `do_orm_execute`-hook stil nul rijen
    # teruggeeft, en een latere `require_tenant_id()` in hetzelfde verzoek afbrak.
    previous_tenant_id = get_tenant_id()
    set_tenant_id(tenant_id)
    try:
        async with get_db_session() as db:
            council: AgentCouncil = await build_council(db, agent_id=agent_id)
            proposal = Proposal(
                tenant_id=tenant_id,
                user_id=user_id,
                trigger=trigger,
                action_type=action_type,
                action_params=action_params,
                reasoning=reasoning,
                message=message,
                data_classification=data_classification,
                confidence=confidence,
                model_id=model_id,
                model_version=model_version,
                context_snapshot=context_snapshot or {},
            )
            decision = await council.deliberate(proposal)
            logger.info(
                "Council-beslissing (achtergrond): tenant=%s agent=%s verdict=%s decision_id=%s",
                tenant_id,
                agent_id,
                decision.verdict.value,
                decision.decision_id,
            )

            hitl_ticket_ref: str | None = None
            if decision.verdict is DecisionVerdict.HITL_REQUIRED:
                # Lazy import, geen statische `from ... import ...`: `src/core/copilot` staat
                # ZELF in `agent_runtime`'s `SOURCE_DIRS` (empirisch bevestigd via
                # `test_agent_runtime_ce_dag2_final_target`, niet aangenomen -- een eerdere
                # versie van deze toelichting beweerde het omgekeerde en dat was onwaar). Een
                # statische import hier zou dus rechtstreeks de Ce-ceiling raken, net als bij
                # `specialist_base.py` hieronder in de keten.
                import importlib

                hitl_repository = importlib.import_module("src.core.tool_broker.hitl_repository")
                # `create_hitl_request()` weigert zelf, luid, met ValueError (onbekende tool,
                # OP-90) of PermissionError (executing_identity mag de tool niet, OP-163) --
                # BEIDE gemeten aan de bron (`hitl_repository.py::create_hitl_request`), niet
                # aangenomen. Die weigering is juist bedoeld voor de HTTP-aanroeper
                # (`handle_turn`), die de exception netjes kan omzetten. Deze functie heeft
                # geen enkele garantie dat AL zijn aanroepers zo'n grens hebben (dat is precies
                # het OP-167-probleem dat deze functie moet oplossen) -- dus vangen we hier,
                # loggen we, en blijft `hitl_ticket_ref` None in plaats van de aanroeper een
                # onverwachte exception te geven voor een besluit dat wel degelijk
                # HITL_REQUIRED was.
                try:
                    hitl_ticket_ref = await hitl_repository.HITLTicketRepository(
                        db
                    ).create_hitl_request(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        decision_id=str(decision.decision_id),
                        reason=decision.explanation_for_user,
                        action_type=action_type,
                        action_params=(
                            ticket_action_params
                            if ticket_action_params is not None
                            else action_params
                        ),
                        executing_identity=agent_id,
                    )
                except (ValueError, PermissionError) as exc:
                    logger.warning(
                        "Geen HITL-ticket mogelijk voor tenant=%s agent=%s action=%s: %s: %s",
                        tenant_id,
                        agent_id,
                        action_type,
                        type(exc).__name__,
                        exc,
                        exc_info=True,
                    )
                    hitl_ticket_ref = None

            return AgentCouncilOutcome(decision=decision, hitl_ticket_ref=hitl_ticket_ref)
    finally:
        set_tenant_id(previous_tenant_id)


def is_irreversible_verdict_blocked(decision: CouncilDecision) -> bool:
    """Kleine helper: vertaalt een DecisionVerdict naar een simpele ja/nee voor
    aanroepers die geen zin hebben de volledige verdict-enum te importeren.
    Bewust NIET de enum zelf verbergen -- aanroepers die HITL/DEFERRED/MODIFIED
    apart willen afhandelen (bijna altijd het geval, zie D4/D7) moeten
    decision.verdict rechtstreeks inspecteren, niet deze helper."""

    return decision.verdict in (DecisionVerdict.BLOCKED, DecisionVerdict.HITL_REQUIRED)
