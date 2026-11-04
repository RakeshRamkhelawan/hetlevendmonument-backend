"""
CopilotService -- single entry point for all Co-Pilot interactions.

Consolidates the previously fragmented endpoints into one governed flow that
passes EVERY user-visible action through the Agent Council before execution.

Responsibilities:
    1. Authenticate caller (JWT contextVar)
    2. Rate-limit per user + tenant
    3. Build Proposal from user input + context
    4. Submit to AgentCouncil.deliberate()
    5. Hardened Execution (APPROVED only):
       - Idempotency via ExecutionGuard (Redis NX lock)
       - Scoped execution via ToolBroker
       - Result-Binding to Audit Chain (closes forensic loop)

References:
    - docs/adr/027-copilot-agent-council.md
    - docs/copilot-architecture.md
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from pydantic import ValidationError

from src.core.copilot._refusals import generic_refusal, not_authorized_refusal
from src.core.copilot.council import AgentCouncil, Proposal
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    OfficerVerdict,
    ProposalTrigger,
)
from src.core.copilot.execution.idempotency import ExecutionGuard, ExecutionStatus
from src.core.copilot.llm_handler import LLMHandler
from src.core.copilot.proposal_builder import CONVERSATIONAL_ACTION_TYPES, ProposalBuilder
from src.core.copilot.protocols import (
    IAIContextEngine,
    IAuditWriter,
    IHITLRepository,
    IToolBroker,
    ITwinService,
)
from src.core.copilot.schemas import (
    CopilotAction,
    CopilotTurnResponse,
    ProactiveResponseResponse,
)
from src.core.services.noodstop_toegang import KlantStilgezet, eis_chat_actief

if TYPE_CHECKING:
    # Alleen voor typechecking -- geen runtime-import, dus geen DSM-fan-out en geen
    # ADR-033-laagschending. `from __future__ import annotations` (bovenaan dit bestand)
    # maakt dit veilig: elke annotatie is al een string, ook zonder deze guard.
    from src.core.governance.prana_service import PranaService


logger = logging.getLogger(__name__)


class _FailClosedAudit:
    """Fail-closed audit fallback -- raises if no real audit_writer is injected.

    Per HIGH-1 fix: silently dropping audit events is a compliance violation.
    """

    async def log_user_response(
        self,
        *,
        signal_id: UUID,
        tenant_id: int,
        user_id: int,
        action_type: str,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        raise RuntimeError("audit_writer not configured: cannot log user response")

    async def bind_execution_result(
        self,
        *,
        decision_id: UUID,
        tenant_id: int,
        result_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        status: str = "success",  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        raise RuntimeError("audit_writer not configured: cannot bind execution result")


class DeliberationInProgressError(Exception):
    """Raised when a duplicate request arrives during an active Council deliberation.

    Callers (HTTP endpoints) should translate this to HTTP 429 with Retry-After.
    """


class CopilotService:
    """Unified Co-Pilot service. One instance per app process."""

    def __init__(
        self,
        council: AgentCouncil,
        llm_handler: LLMHandler,
        proposal_builder: ProposalBuilder,
        hitl_repo: IHITLRepository | None = None,
        tool_broker: IToolBroker | None = None,
        twin_service: ITwinService | None = None,
        audit_writer: IAuditWriter | None = None,
        execution_guard: ExecutionGuard | None = None,
        # TODO(TYPE): replace Any with concrete type
        redis: Any
        | None = None,  # redis.asyncio.Redis -- avoids hard import at module level  # TODO(TYPE): replace Any with concrete type
        context_engine: IAIContextEngine | None = None,
        prana_service: "PranaService | None" = None,  # ADR-021 charge on execution
    ) -> None:
        self._council = council
        self._llm_handler = llm_handler
        self._proposal_builder = proposal_builder
        self._hitl_repo = hitl_repo
        self._tool_broker = tool_broker
        self._twin_service = twin_service
        self._audit = audit_writer if audit_writer is not None else _FailClosedAudit()
        self._execution_guard = execution_guard
        self._redis = redis
        self._context_engine = context_engine
        self._prana_service = prana_service

    async def _get_available_agents(
        self, tenant_id: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return available agents from the global SubagentLoader singleton."""
        from src.core.agents.subagent_loader import get_loader

        loader = get_loader()
        return loader.list_available_agents()

    async def _get_allowed_tools(
        self, tenant_id: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return allowed tools catalog.

        Queries ToolPermissionManager for copilot profile allowed tools.
        """
        try:
            # Dynamisch via importlib (i.p.v. statische import) om agent_runtime's
            # tool_broker-koppeling niet op te rekken -- zie test_dsm_008_reclassification.py.
            import importlib

            perm_mod = importlib.import_module("src.core.tool_broker.permission_manager")
            mgr = perm_mod.ToolPermissionManager()
            allowed = mgr.get_allowed_tools("copilot")
            return [{"name": tool, "allowed": True} for tool in allowed]
        except Exception as exc:
            logger.error("Failed to load tool permissions: %s", exc)
        return []

    async def _augment_context(
        self,
        tenant_id: int,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Augment user context with a real platform capability snapshot.

        Injects available agents and allowed tools so the LLM knows what
        actions exist on the platform (prevents hallucination of unknown tools).
        """
        augmented = dict(context)
        agents: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        tools: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        try:
            agents = await self._get_available_agents(tenant_id)
        except Exception as exc:
            logger.warning(
                "augment_context_agents_failed: %s",
                type(exc).__name__,
                extra={"tenant_id": tenant_id},
                exc_info=True,
            )
        try:
            tools = await self._get_allowed_tools(tenant_id)
        except Exception as exc:
            logger.warning(
                "augment_context_tools_failed: %s",
                type(exc).__name__,
                extra={"tenant_id": tenant_id},
                exc_info=True,
            )
        augmented["_platform_capabilities"] = {
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": agents,
            "tools": tools,
        }
        return augmented

    async def handle_turn_stream(
        self,
        tenant_id: int,
        user_id: int,
        message: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        language: str = "nl",
    ) -> Any:
        """Streaming wrapper around handle_turn for the WebSocket endpoint.

        Yields chunk frames while the Council deliberates, then a done frame
        containing the final CopilotTurnResponse payload. This keeps the WS
        contract intact without requiring a true streaming LLM implementation.
        """
        yield {"type": "chunk", "content": "Processing your request..."}
        response = await self.handle_turn(
            tenant_id=tenant_id,
            user_id=user_id,
            message=message,
            context=context,
            language=language,
        )
        yield {"type": "done", "payload": response.model_dump()}

    async def handle_turn(
        self,
        tenant_id: int,
        user_id: int,
        message: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        stream: bool = False,
        language: str = "nl",
    ) -> CopilotTurnResponse:
        """One-shot interaction (Cmd+K, focus-builder)."""
        # NOODSTOP PER KLANT (ADR-036 OP-03, besluit A ronde 2): DE deur van de copilot-chat, voor
        # ALLES wat hieronder kost of klantgegevens verplaatst: de inhoudswachter, de context, het
        # taalmodel, de Council en de Prana-afschrijving. HTTP (`turn_endpoint`) en websocket
        # (`chat_websocket`, via `handle_turn_stream`) komen hier allebei langs. Een stilgezette
        # klant krijgt een geblokkeerd antwoord met de vaste melding; fail-closed bij onbekend.
        try:
            await eis_chat_actief(tenant_id)
        except KlantStilgezet as stop:
            return self._blocked_response(language, message=stop.bericht)

        # DE INHOUDSWACHTER, en met opzet de ALLEREERSTE regel -- voor `_augment_context`, voor
        # de context-engine, voor de LLM-aanroep. Elke stap daarna kopieert het bericht naar een
        # andere plek (verrijkte context, proposal, Council, auditketen), en wat eenmaal is
        # gekopieerd haal je er niet meer uit. Tot 2026-09-22 stond op dit pad GEEN enkele
        # inhoudscontrole -- gemeten: nul treffers op `detect_pii` of een guard in dit bestand.
        #
        # Waarom hier en niet in de Council: die beoordeelt de VORM van een actie en legt alles
        # wat hij ziet onuitwisbaar vast (ADR-036 OP-25). Zie `governance/input_guard.py`.
        # De import staat BINNEN de try, sinds Gate 2. Een kapotte module (een syntaxfout, een
        # ontbrekende afhankelijkheid) zou anders omhoog gooien uit `handle_turn` en een 500 of
        # een stille SSE-foutframe geven in plaats van een weigering -- het enige pad waar
        # fail-closed een stacktrace oplevert in plaats van een antwoord.
        try:
            from src.core.governance.input_guard import beoordeel
        except Exception as exc:  # noqa: BLE001 -- fail-closed, zie hierboven
            logger.error(
                "copilot.handle_turn input_guard_niet_te_laden: %s",
                type(exc).__name__,
                extra={"tenant_id": tenant_id},
                exc_info=True,
            )
            return self._blocked_response(language)

        # `message` EN `context`. De eerste versie beoordeelde alleen `message`, en dat was een
        # gat in dezelfde HTTP-aanvraag: `context` komt rechtstreeks van de client
        # (`api/turn_endpoint.py`), is `dict[str, Any]`, heeft -- anders dan `message`, die op
        # 2000 tekens staat -- GEEN `max_length` in `CopilotTurnRequest` (gemeten 2026-09-22), en
        # gaat via `_augment_context` naar het taalmodel EN naar `proposal.context_snapshot`, dus
        # de Council. Een BSN een JSON-veld verderop zetten was daarmee genoeg om erlangs te
        # komen. Gevonden in Gate 2.
        oordeel = beoordeel(
            {"message": message, "context": context}, tenant_id=tenant_id, herkomst="chat"
        )
        if not oordeel.toegestaan:
            # De gebruiker krijgt de CATEGORIE en een verwijzing te horen, niet zijn eigen tekst
            # terug en ook geen vaag "dat mag niet". Dat is de overrule-route die AI Act art. 14
            # vraagt: hij wordt niet van de dienst uitgesloten, hij weet wat eruit moet en kan
            # het opnieuw stellen. Stil weghalen zou erger zijn -- dan denkt hij dat zijn vraag
            # volledig is beantwoord terwijl de helft eruit is gefilterd.
            return self._blocked_response(language, message=oordeel.reden(language))

        augmented_context = await self._augment_context(tenant_id, context)

        # SP-AGT-003: context_engine is the primary enrichment path (ADR-034)
        if self._context_engine is not None:
            try:
                enriched = await self._context_engine.enrich(
                    agent_id=str(user_id),
                    query=message,
                    surface=context.get("surface", "copilot"),
                )
                augmented_context.update(enriched.context)
                augmented_context["twin_profile"] = enriched.twin_profile
            except Exception as exc:
                logger.warning(
                    "context_engine.enrich failed: %s",
                    type(exc).__name__,
                    extra={"tenant_id": tenant_id},
                    exc_info=True,
                )
        elif self._twin_service:
            try:
                twin_profile = await self._twin_service.get_profile(
                    user_id=str(user_id), tenant_id=tenant_id, db=None
                )
                if twin_profile:
                    augmented_context["twin_profile"] = twin_profile
            except Exception as exc:
                logger.warning(
                    "twin_service.get_profile failed: %s",
                    type(exc).__name__,
                    extra={"tenant_id": tenant_id},
                    exc_info=True,
                )

        capabilities = augmented_context.pop("_platform_capabilities", None)
        try:
            action = await self._llm_handler.get_action(
                message=message,
                context=augmented_context,
                language=language,
                capabilities=capabilities,
            )
        except (ValidationError, Exception) as exc:
            logger.error(
                "copilot.handle_turn llm_error: %s",
                type(exc).__name__,
                extra={"tenant_id": tenant_id},
                exc_info=True,
            )
            return self._blocked_response(language)

        proposal = self._proposal_builder.build(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id=self._llm_handler.model_id,
            model_version=self._llm_handler.model_version,
            context_snapshot=augmented_context,
            capabilities=capabilities,
        )

        # Een actie zonder uitvoerder weigeren VOOR de Council (ADR-036 OP-78). Gemeten
        # 2026-10-04: het taalmodel koos `confirm` (staat in het copilot-profiel, namespace
        # council_action, maar heeft geen uitvoerder), de Council keurde goed en
        # `execute_tool` gooide TB_2002 -- een HTTP 500 na een goedkeuring in de auditketen.
        # Alleen met een broker: zonder broker voert `_execute_decision` niets uit.
        # Gespreksbeurten (noop/clarify/confirm/unknown) zijn geen acties en slaan deze
        # controle over (regressie 23cdc8e8, brief 2026-10-05 A-01).
        if (
            self._tool_broker is not None
            and proposal.action_type
            and proposal.action_type not in CONVERSATIONAL_ACTION_TYPES
            and not self._is_known_tool(proposal.action_type)
        ):
            logger.warning(
                "copilot.handle_turn refused_action_without_executor tenant=%s",
                tenant_id,
                extra={"tenant_id": tenant_id},
            )
            return self._blocked_response(language)

        # Pre-deliberation idempotency lock (WE-003 fix, ADR-027)
        lock_key: str | None = None
        if self._redis is not None:
            request_hash = hashlib.sha256(f"{tenant_id}:{user_id}:{message}".encode()).hexdigest()[
                :16
            ]
            lock_key = f"copilot:deliberation:{tenant_id}:{request_hash}"
            lock_acquired = await self._redis.set(lock_key, "1", nx=True, ex=30)
            if not lock_acquired:
                raise DeliberationInProgressError(
                    "Duplicate request detected while deliberation is in progress."
                )

        try:
            decision = await self._council.deliberate(proposal)
        except DeliberationInProgressError:
            raise
        except Exception as exc:
            logger.error(
                "copilot.handle_turn council_error: %s",
                exc,
                extra={"tenant_id": tenant_id},
                exc_info=True,
            )
            return self._blocked_response(language)
        finally:
            if self._redis is not None and lock_key is not None:
                await self._redis.delete(lock_key)

        # Execute approved actions with idempotency guarding
        await self._execute_decision(proposal, decision)

        return await self._route_verdict(decision, action, proposal, language)

    async def submit_proactive_proposal(self, proposal: Proposal) -> CouncilDecision:
        """Submit a proactive monitor proposal directly to the Council.

        Bypasses the LLM generator, but runs full deliberation and execution.
        """
        try:
            decision = await self._council.deliberate(proposal)
        except Exception as exc:
            logger.error(
                "copilot.submit_proactive_proposal council_error: %s",
                exc,
                extra={"tenant_id": proposal.tenant_id},
                exc_info=True,
            )
            return CouncilDecision(
                proposal_id=proposal.proposal_id,
                tenant_id=proposal.tenant_id,
                user_id=proposal.user_id,
                verdict=DecisionVerdict.BLOCKED,
                officer_verdicts=(),
                explanation_for_user="Een interne fout verhinderde de Co-Pilot om je verzoek te verwerken.",
                decision_hash="FAILED",
                previous_decision_hash=None,
                deliberation_ms=0,
            )

        await self._execute_decision(proposal, decision)

        if decision.verdict == DecisionVerdict.HITL_REQUIRED:
            await self._create_proactive_hitl_ticket(proposal, decision)

        return decision

    @staticmethod
    def _is_known_tool(action_type: str) -> bool:
        """Lazy, GEDEELDE import van `tool_broker.service.is_known_tool` (ADR-036 OP-78).

        Een import-statement voor de TWEE aanroepplekken (`_route_verdict`'s HITL-blok en
        `_create_proactive_hitl_ticket`) in plaats van twee losse: een tweede lokale
        `from ... import is_known_tool` duwde `agent_runtime`'s Ce-coupling-metriek van 227
        naar 228 (`tests/architecture/test_dsm_008_reclassification.py::
        test_agent_runtime_ce_dag2_final_target` -- `src/core/copilot` staat in
        `agent_runtime`'s `SOURCE_DIRS`, empirisch bevestigd, niet aangenomen).
        """
        from src.core.tool_broker.service import is_known_tool

        return is_known_tool(action_type)

    async def _create_proactive_hitl_ticket(
        self, proposal: Proposal, decision: CouncilDecision
    ) -> None:
        """Maak een HITL-ticket voor een proactief voorstel (ADR-036 OP-167).

        Tot deze fix gooide `submit_proactive_proposal` een HITL_REQUIRED-verdict
        ongebruikt weg -- het besluit bereikte nooit een mens (AI Act art. 14).

        **Anders dan `handle_turn`'s HITL-blok: hier LOGGEN we een weigering en stoppen
        we, we gooien geen `ToolExecutionException`.** Gemeten: de ENIGE huidige aanroeper
        (`proactive/monitor.py::propose_to_council`) gebruikt altijd
        `action_type="send_notification"`, en die naam staat NERGENS in
        `BusinessToolRegistry`/`HRToolRegistry` (bevestigd, `is_known_tool()` geeft `False`).
        `handle_turn` mag hier hard op weigeren omdat een HTTP-request de exception netjes
        opvangt; `propose_to_council` heeft geen eigen try/except om deze aanroep, dus een
        exception hier zou de achtergrondtaak van ELKE proactieve melding laten crashen --
        strikt SLECHTER dan de oude bug (een verdict dat stil werd weggegooid). Dit is dus
        een bewuste afwijking van het HTTP-patroon, niet een vergeten poging tot
        consistentie.

        **Tweede weigeringsgrond, apart gevangen (Gate 2-bevinding):** `create_hitl_request`
        gebruikt hier de DEFAULT `executing_identity` ("copilot", geen agent-eigen identiteit
        zoals bij het ALS-pad), en `copilot` is voor sommige tools NIET geautoriseerd
        (`ToolPermissionManager`, ADR-036 OP-163's eigen voorbeeld noemt `local__send_email`
        en `query_hr_database`). Dat geeft een `PermissionError`, niet een `ValueError` --
        de `is_known_tool`-precheck hierboven vangt die niet. Zelfde reden om hem te vangen
        i.p.v. te laten propageren: geen try/except bij de aanroeper.
        """
        if not self._hitl_repo:
            return

        if not self._is_known_tool(proposal.action_type):
            logger.warning(
                "copilot.proactive_hitl_no_ticket_unknown_tool tenant=%s decision=%s "
                "action_type=%s",
                proposal.tenant_id,
                decision.decision_id,
                proposal.action_type,
                extra={"tenant_id": proposal.tenant_id},
            )
            return

        try:
            await self._hitl_repo.create_hitl_request(
                tenant_id=proposal.tenant_id,
                user_id=proposal.user_id,
                decision_id=str(decision.decision_id),
                reason=decision.explanation_for_user,
                action_type=proposal.action_type,
                action_params=dict(proposal.action_params),
            )
        except PermissionError as exc:
            logger.warning(
                "copilot.proactive_hitl_no_ticket_not_authorized tenant=%s decision=%s "
                "action_type=%s: %s: %s",
                proposal.tenant_id,
                decision.decision_id,
                proposal.action_type,
                type(exc).__name__,
                exc,
                extra={"tenant_id": proposal.tenant_id},
                exc_info=True,
            )

    async def handle_proactive_response(
        self,
        *,
        signal_id: UUID,
        tenant_id: int,
        user_id: int,
        action_type: str,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ProactiveResponseResponse:
        KNOWN_ACTIONS = {"confirm", "cancel", "snooze", "dismiss", "navigate"}
        if action_type not in KNOWN_ACTIONS:
            raise ValueError(f"unknown action_type: {action_type}")

        try:
            await self._audit.log_user_response(
                signal_id=signal_id,
                tenant_id=tenant_id,
                user_id=user_id,
                action_type=action_type,
                params=params,
            )
        except Exception as exc:
            logger.warning(
                "proactive_response_audit_failed: %s",
                exc,
                extra={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "signal_id": str(signal_id),
                    "action_type": action_type,
                },
                exc_info=True,
            )

        return ProactiveResponseResponse(
            signal_id=signal_id,
            accepted=True,
            resulting_action=action_type,
            message=f"Response '{action_type}' geregistreerd",
        )

    async def _execute_decision(
        self,
        proposal: Proposal,
        decision: CouncilDecision,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Dispatch execution based on Council verdict with idempotency and result binding."""
        if decision.verdict != DecisionVerdict.APPROVED:
            return None

        if not self._tool_broker or not proposal.action_type:
            return None

        # Een gespreksbeurt heeft niets uit te voeren; voor 23cdc8e8 ging `noop` hier naar
        # `execute_tool` en gaf de echte broker TB_2002 (HTTP 500).
        if proposal.action_type in CONVERSATIONAL_ACTION_TYPES:
            return None

        # 0. Tool validation is performed by ToolBrokerService which checks
        # known prefixes and raises ToolExecutionException for unknown tools.
        # See src/core/tool_broker/service.py lines 173-179.

        # 1. Acquire idempotency lock
        if self._execution_guard:
            acquired = await self._execution_guard.start_execution(decision.decision_id)
            if not acquired:
                logger.info(
                    "copilot.execution_skipped idempotency_lock_active",
                    extra={
                        "tenant_id": proposal.tenant_id,
                        "decision_id": str(decision.decision_id),
                    },
                )
                return None

        # ADR-021 prana charge (flag-guarded) -- the atomic budget gate at execution time,
        # BEFORE the tool runs. Department is the fixed copilot bucket (never the
        # LLM-generated action_params). On InsufficientPrana the tool does NOT run.
        prana_charged = False
        prana_dept: str | None = None
        if self._prana_service is not None:
            # Dynamisch via importlib (i.p.v. losse `from ... import`) om agent_runtime's
            # governance-koppeling niet verder op te rekken -- zie
            # test_dsm006_ar_governance_fan_out.py (plafond, GEEN buffer) en `_get_prana_guard()`
            # in specialist_base.py voor hetzelfde patroon om dezelfde reden.
            import importlib

            prana_config = importlib.import_module("src.core.governance.prana_config")

            if prana_config.prana_enforcement_enabled():
                prana_departments = importlib.import_module("src.core.governance.prana_departments")
                prana_service_mod = importlib.import_module("src.core.governance.prana_service")

                # cast: prana_departments komt uit importlib.import_module() (Any per
                # pyright), dus de aanname dat .value een str is, is niet statisch af te
                # leiden -- zelfde patroon als specialist_base.py elders in deze codebase.
                prana_dept = cast(str, prana_departments.DEFAULT_COPILOT_DEPARTMENT.value)
                try:
                    await self._prana_service.charge(
                        proposal.tenant_id,
                        prana_dept,
                        proposal.action_type,
                        actor_user_id=proposal.user_id,
                    )
                    prana_charged = True
                except prana_service_mod.InsufficientPranaError:
                    logger.info(
                        "copilot.execution_denied prana_budget_exceeded",
                        extra={
                            "tenant_id": proposal.tenant_id,
                            "decision_id": str(decision.decision_id),
                        },
                    )
                    if self._execution_guard:
                        await self._execution_guard.finish_execution(
                            decision.decision_id, ExecutionStatus.FAILED
                        )
                    return None

        try:
            # 2. Execute tool (scoped by user/tenant)
            # AUDIT-001: agent_id is required -- without it, ToolPermissionManager
            # default-denies (agent_id or "" has no profile) and every Council-approved
            # action crashes after the decision is already in the audit hash-chain.
            # "copilot" is the identity already registered in config/tool_permissions.yml
            # and already used by _ToolBrokerAdapter for the deliberation-time check.
            result = await self._tool_broker.execute_tool(
                tool_name=proposal.action_type,
                payload=proposal.action_params,
                agent_id="copilot",
                context={
                    "user_id": proposal.user_id,
                    "tenant_id": proposal.tenant_id,
                    "decision_id": str(decision.decision_id),
                },
            )

            # 3. Bind execution result to Audit Chain (closes the forensic loop)
            await self._audit.bind_execution_result(
                decision_id=decision.decision_id,
                tenant_id=proposal.tenant_id,
                result_data=result or {},
                status="success",
            )

            # 4. Mark success in guard
            if self._execution_guard:
                await self._execution_guard.finish_execution(
                    decision.decision_id, ExecutionStatus.SUCCESS
                )

            return result

        except Exception as exc:
            # Refund the prana charge if we debited but execution failed -- charge-before-
            # execute must not burn budget for an action that did not happen. Best-effort.
            if prana_charged and self._prana_service is not None and prana_dept is not None:
                try:
                    await self._prana_service.refund(
                        proposal.tenant_id,
                        prana_dept,
                        proposal.action_type,
                        actor_user_id=proposal.user_id,
                    )
                except Exception:
                    logger.warning("copilot.prana_refund_failed", exc_info=True)

            logger.error(
                "copilot.execution_failed",
                extra={
                    "tenant_id": proposal.tenant_id,
                    "decision_id": str(decision.decision_id),
                    "error": str(exc),
                },
                exc_info=True,
            )

            await self._audit.bind_execution_result(
                decision_id=decision.decision_id,
                tenant_id=proposal.tenant_id,
                result_data={"error": str(exc)},
                status="failed",
            )

            if self._execution_guard:
                await self._execution_guard.finish_execution(
                    decision.decision_id, ExecutionStatus.FAILED
                )

            raise

    async def _route_verdict(
        self,
        decision: CouncilDecision,
        action: CopilotAction,
        proposal: Proposal,
        language: str,
    ) -> CopilotTurnResponse:
        council_summary = self._build_council_summary(decision.officer_verdicts)

        if decision.verdict == DecisionVerdict.APPROVED:
            return CopilotTurnResponse(
                decision_id=str(decision.decision_id),
                verdict="approved",
                message=action.message,
                action=action.action,
                action_params=dict(action.action_params),
                confidence=action.confidence,
                council_summary=council_summary,
                explanation_url=f"/api/v1/copilot/audit/{decision.decision_id}",
            )

        if decision.verdict == DecisionVerdict.MODIFIED:
            # Apply modifications to action_params
            merged_params = dict(action.action_params)
            if decision.modifications:
                for officer_mods in decision.modifications.values():
                    if isinstance(officer_mods, dict) and "action_params" in officer_mods:
                        merged_params.update(officer_mods["action_params"])
            return CopilotTurnResponse(
                decision_id=str(decision.decision_id),
                verdict="modified",
                message=action.message,
                action=action.action,
                action_params=merged_params,
                confidence=action.confidence,
                council_summary=council_summary,
                explanation_url=f"/api/v1/copilot/audit/{decision.decision_id}",
            )

        if decision.verdict == DecisionVerdict.DEFERRED:
            msg = (
                "Je verzoek is uitgesteld (deferred) voor verdere verwerking."
                if language == "nl"
                else "Your request has been deferred for periodic digest processing."
            )
            return CopilotTurnResponse(
                decision_id=str(decision.decision_id),
                verdict="deferred",
                message=msg,
                action=action.action,
                action_params=dict(action.action_params),
                confidence=action.confidence,
                council_summary=council_summary,
                explanation_url=f"/api/v1/copilot/audit/{decision.decision_id}",
            )

        if decision.verdict == DecisionVerdict.HITL_REQUIRED:
            if self._hitl_repo:
                # DEZELFDE toolvalidatie als op het uitvoerpad (ADR-036 OP-78). Die stond alleen
                # in `ToolBrokerService.execute_tool`, dus een propositie die naar HITL ging werd
                # nooit gecontroleerd -- terwijl `proposal.action_type` uit het taalmodel komt en
                # onbewerkt in `hitl_tickets.tool_name`, in `/hitl/audit` en in de ADR-019
                # hashketen belandt. Die keten is onuitwisbaar.
                #
                # Een ticket voor een onbekende tool was sowieso een doodlopend spoor: de broker
                # weigert hem bij het verzilveren. Hier weigeren faalt luid in plaats van stil.
                from src.core.tool_broker.exceptions import ToolExecutionException

                if not self._is_known_tool(proposal.action_type):
                    logger.warning(
                        "copilot.hitl_refused_unknown_tool tenant=%s decision=%s",
                        proposal.tenant_id,
                        decision.decision_id,
                        extra={"tenant_id": proposal.tenant_id},
                    )
                    raise ToolExecutionException(
                        tool_name=proposal.action_type,
                        error_detail=(
                            "Unknown tool category; no HITL ticket created. The proposed action "
                            "does not match any executable tool."
                        ),
                    )

                # `create_hitl_request` weigert met PermissionError als de identiteit `copilot`
                # de tool niet in zijn profiel heeft (ADR-036 OP-90). Dat is opzet: de copilot
                # krijgt bv. GEEN `send_payment_reminder`, dat loopt via de debiteurenagent.
                # Ongevangen werd het een 500; nu een nette weigering met een logregel zonder
                # payload, zelfde vorm als het proactieve pad.
                try:
                    hitl_id = await self._hitl_repo.create_hitl_request(
                        tenant_id=proposal.tenant_id,
                        user_id=proposal.user_id,
                        decision_id=str(decision.decision_id),
                        reason=decision.explanation_for_user,
                        action_type=proposal.action_type,
                        action_params=dict(proposal.action_params),
                    )
                except PermissionError as exc:
                    logger.warning(
                        "copilot.hitl_no_ticket_not_authorized tenant=%s decision=%s "
                        "action_type=%s: %s: %s",
                        proposal.tenant_id,
                        decision.decision_id,
                        proposal.action_type,
                        type(exc).__name__,
                        exc,
                        extra={"tenant_id": proposal.tenant_id},
                        exc_info=True,
                    )
                    return self._blocked_response(
                        language,
                        message=not_authorized_refusal(language, proposal.action_type or ""),
                    )
                return CopilotTurnResponse(
                    decision_id=str(decision.decision_id),
                    verdict="hitl_required",
                    message=action.message,
                    action=action.action,
                    action_params=dict(action.action_params),
                    confidence=action.confidence,
                    council_summary=council_summary,
                    hitl_request_id=hitl_id,
                    explanation_url=f"/api/v1/copilot/audit/{decision.decision_id}",
                )

        return self._blocked_response(language)

    def _blocked_response(self, language: str, message: str | None = None) -> CopilotTurnResponse:
        """Generate a traceable BLOCKED response with a valid decision_id.

        Per HIGH-2 fix: empty decision_id breaks right-to-explanation.

        `message` overschrijft de generieke weigering (2026-09-22). De inhoudswachter gebruikt
        dat om de CATEGORIE en een verwijzing mee te geven -- nooit de gevonden tekst. Een
        generieke weigering zou daar het verkeerde antwoord zijn: dan weet de gebruiker niet wat
        hij anders moet doen, en dat maakt van de wachter een muur zonder deur (AI Act art. 14).
        De twee bestaande aanroepers laten hem weg en houden dus de generieke tekst, want daar
        is de reden wel degelijk iets dat je niet naar buiten wilt geven (een LLM-fout, een
        Council-storing).
        """
        return CopilotTurnResponse(
            decision_id=str(uuid4()),
            verdict="blocked",
            message=message if message is not None else generic_refusal(language),
            action=None,
            action_params={},
            confidence=0.0,
            council_summary={},
        )

    def _build_council_summary(
        self, officer_verdicts: tuple[OfficerVerdict, ...]
    ) -> dict[str, int]:
        summary = {"approve": 0, "modify": 0, "require_hitl": 0, "defer": 0, "veto": 0}
        for v in officer_verdicts:
            key = v.verdict.value
            if key in summary:
                summary[key] += 1
        return summary
