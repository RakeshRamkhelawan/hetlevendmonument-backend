#!/usr/bin/env python3
"""
Tool Broker Service with Resilience Patterns

Provides:
- Tool execution orchestration between Serena and Sequential Thinking clients
- Circuit breaker pattern for cascading failure prevention
- Automatic retry with exponential backoff
- Health monitoring and service degradation handling
- Comprehensive metrics and tracing
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Protocol, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from src.core.tool_broker.local_registry import LocalToolRegistry
    from src.core.tool_broker.hitl_store import HITLStore
    from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger

from src.core.events.publisher import DomainEvent
from src.core.metrics import (
    TOOL_AUDIT_WRITE_FAILURES,
    TOOL_EXECUTION_COUNT,
    TOOL_EXECUTION_LATENCY,
)

# Expliciet her-geexporteerd: `api/v1/tool_broker/hitl_router.py` haalt ze hier op (een bestand -> module-paar
# minder in de fan-out van `core_api`); zonder `as` meldt mypy "does not explicitly export".
from src.core.noodstop.guard import KlantStilgezet as KlantStilgezet
from src.core.noodstop.guard import eis_klant_actief as eis_klant_actief
from src.core.tool_broker.audit_repository import ToolAuditRepository
from src.core.tool_broker.exceptions import ToolBrokerException, ToolExecutionException
from src.core.tool_broker.health import get_service_health
from src.core.tool_broker.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    RetryConfig,
    async_retry,
    get_circuit_breaker_registry,
    get_resilience_metrics,
)
from src.core.tool_broker.business_registry import BusinessToolRegistry
from src.core.tool_broker.hr_registry import HRToolRegistry
from src.core.tool_broker.payables_registry import PayablesToolRegistry
from src.core.tool_broker.payment_run_registry import BetaalrunToolRegistry
from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry
from src.core.tool_broker.redaction import (
    redact_for_publication,
    safe_digest_result,
    safe_value_digest,
)
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel


#: De lopende achtergrondtaken die een auditregel schrijven. Alleen om ze vast te houden tot ze
#: klaar zijn: `asyncio.create_task` bewaart zelf alleen een zwakke verwijzing.
_AUDIT_TASKS: set["asyncio.Task[None]"] = set()


def _count_audit_write_failure(exc: BaseException) -> None:
    """Tel een mislukte auditregel. De toolactie zelf blijft zoals hij was (best effort).

    Een mislukte regel werd wel gelogd (door `best_effort`) maar nergens geteld, dus een
    structurele storing in de keten was alleen te zien door de logs te lezen. De teller maakt hem
    zichtbaar op een dashboard of in een waarschuwing. Het label is de naam van de fout, nooit de
    tekst: die kan klantgegevens bevatten.
    """
    TOOL_AUDIT_WRITE_FAILURES.labels(error_type=type(exc).__name__).inc()


#: De voorvoegsels waaronder een tool bij een externe uitvoerder hoort.
_KNOWN_TOOL_PREFIXES = ("local__", "test__", "serena__", "sequentialthinking__")


def is_known_tool(tool_name: str) -> bool:
    """Bestaat er een uitvoerder voor deze toolnaam? (ADR-036 OP-78)

    **Waarom dit een functie op moduleniveau is en geen inline-blok.** Deze controle stond alleen
    in `execute_tool`. Gevolg: op het UITVOERPAD werd een toolnaam gevalideerd en op het
    GOEDKEURINGSPAD niet -- dezelfde propositie, een verdict verschil. De naam komt op dat pad uit
    het taalmodel (`CopilotAction.action`) en belandde onbewerkt in `hitl_tickets.tool_name`, in
    `/hitl/audit` en sinds OP-71 in de ADR-019 hashketen, die per ontwerp onuitwisbaar is.

    Nu gebruiken beide paden DEZELFDE definitie. Een tweede lijst zou weer uiteenlopen; daar gaat
    deze bevinding over. `tests/unit/copilot/test_the_action_name_is_not_free_text.py` dwingt met
    de AST af dat `execute_tool` deze functie aanroept en niet opnieuw een eigen lijst opschrijft.

    Een ticket voor een onbekende tool kon sowieso nooit worden uitgevoerd -- de broker weigert hem
    bij het verzilveren. Vroeg weigeren breekt dus niets wat werkte; het faalt luid in plaats van
    stil een doodlopend spoor aan te maken.
    """
    if any(tool_name.startswith(prefix) for prefix in _KNOWN_TOOL_PREFIXES):
        return True
    return (
        tool_name in BusinessToolRegistry.known_tool_names()
        or tool_name in HRToolRegistry.known_tool_names()
        or tool_name in ReceivablesToolRegistry.known_tool_names()
        or tool_name in PayablesToolRegistry.known_tool_names()
        or tool_name in BetaalrunToolRegistry.known_tool_names()
    )


# --- Client Interfaces ---
class ISerenaClient(Protocol):
    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]: ...


class ISequentialThinkingClient(Protocol):
    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]: ...


class IEventPublisher(Protocol):
    async def publish(self, event: DomainEvent, routing_key: str | None = None) -> None: ...


class ToolBrokerService:
    """
    Tool Broker Service with Enterprise Resilience Patterns

    Manages tool execution with automatic resilience features:
    - Circuit breaker protection against cascading failures
    - Automatic retry with exponential backoff
    - Health monitoring and graceful degradation
    - Comprehensive metrics collection
    """

    def __init__(
        self,
        serena_client: ISerenaClient,
        seq_thinking_client: ISequentialThinkingClient,
        local_registry: "LocalToolRegistry | None" = None,
        business_registry: BusinessToolRegistry | None = None,
        hr_registry: HRToolRegistry | None = None,
        receivables_registry: ReceivablesToolRegistry | None = None,
        payables_registry: PayablesToolRegistry | None = None,
        payment_run_registry: BetaalrunToolRegistry | None = None,
        event_publisher: IEventPublisher | None = None,
        enable_resilience: bool = True,
        retry_config: RetryConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        risk_classifier: ToolRiskClassifier | None = None,
        audit_repository: ToolAuditRepository | None = None,
        db_session: "AsyncSession | None" = None,
        audit_session_factory: "Callable[[], AbstractAsyncContextManager[AsyncSession]] | None" = None,
        hitl_store: "HITLStore | None" = None,
        permission_manager: ToolPermissionManager | None = None,
    ) -> None:
        """
        Initialize Tool Broker Service

        Args:
            serena_client: Client for Serena tools
            seq_thinking_client: Client for Sequential Thinking tools
            local_registry: Registry for local/whitelisted tools
            enable_resilience: Enable resilience patterns (default: True)
            retry_config: Custom retry configuration
            circuit_breaker_config: Custom circuit breaker configuration
            risk_classifier: Tool risk level classifier (ADR-015)
            audit_repository: Database repository for audit logging
            db_session: Async database session for audit writes
            audit_session_factory: Opent per auditregel een EIGEN korte sessie (zelfde vorm als
                `HITLStore(session_factory=...)`). De repository wordt dan per regel gebouwd voor de
                klant van DEZE aanroep; een broker die voor meerdere klanten werkt kan geen
                vaste, aan een klant gebonden repository dragen.
            hitl_store: DB-backed store for Human-in-the-Loop tickets
        """
        self.serena_client = serena_client
        self.seq_thinking_client = seq_thinking_client
        self.local_registry = local_registry
        self.business_registry = business_registry or BusinessToolRegistry()
        self.hr_registry = hr_registry or HRToolRegistry()
        self.receivables_registry = receivables_registry or ReceivablesToolRegistry()
        self.payables_registry = payables_registry or PayablesToolRegistry()
        self.payment_run_registry = payment_run_registry or BetaalrunToolRegistry()
        self.event_publisher = event_publisher
        self.enable_resilience = enable_resilience
        self.retry_config = retry_config or RetryConfig(max_attempts=3)
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig(
            failure_threshold=5, failure_window_seconds=60, timeout_seconds=30
        )
        self.risk_classifier = risk_classifier or ToolRiskClassifier()
        self.audit_repository = audit_repository
        self.db_session = db_session
        self.audit_session_factory = audit_session_factory
        self.hitl_store = hitl_store
        self.permission_manager = permission_manager or ToolPermissionManager()

        # Initialize circuit breaker registry
        self.circuit_breaker_registry = get_circuit_breaker_registry()
        self.resilience_metrics = get_resilience_metrics()
        self.service_health = get_service_health()

        # Register circuit breakers for each client
        self.serena_breaker = self.circuit_breaker_registry.get_or_create(
            "serena_client", self.circuit_breaker_config
        )
        self.seq_thinking_breaker = self.circuit_breaker_registry.get_or_create(
            "sequential_thinking_client", self.circuit_breaker_config
        )

        logger.info(
            f"ToolBrokerService initialized "
            f"(resilience={'enabled' if enable_resilience else 'disabled'})"
        )

    async def execute_tool(
        self,
        tool_name: str,
        payload: dict[str, object],
        agent_id: str | None = None,  # Fix: Phase C Permissions
        timeout_seconds: int | None = None,
        context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """
        Execute tool with resilience patterns and permission checks.
        """
        # Inject context into payload for downstream tools. Context always wins
        # over anything supplied by the caller/LLM to prevent cross-tenant spoofing.
        #
        # `broker_keys` legt vast WELKE sleutels hier uit de context zijn gezet. Die zijn per
        # definitie geen modeloutput en mogen daarom leesbaar in een bewarende sink staan. De
        # eerste versie van de redactie gebruikte hiervoor een vaste lijst van acht NAMEN,
        # waarvan de broker er twee zet -- de overige zes kon het model zelf verzinnen, en
        # `_requested_by` is elders letterlijk `current_user.email`. Een naam kan niet
        # onderscheiden wie een sleutel schreef; deze verzameling wel.
        # (Gate 2-review BE-AGT-045 ronde 2, HIGH-2.)
        broker_keys: set[str] = set()
        if context:
            if "tenant_id" in context:
                payload["tenant_id"] = context["tenant_id"]
                broker_keys.add("tenant_id")
            if "user_id" in context:
                payload["user_id"] = context["user_id"]
                broker_keys.add("user_id")

        # OP-35: verplaatst VOOR de permissiecheck/HITL-poort (was na 0a hieronder), zodat elke
        # weigering vanaf hier een tenant heeft om een auditregel mee te scopen. Puur een lezing
        # van context/ContextVar (geen state van eerdere stappen nodig), dus veilig te verplaatsen.
        tenant_id = self._require_tenant_for_execution(tool_name, context)

        # 0-. NOODSTOP PER KLANT (ADR-036 OP-03). Dit is DE deur voor elke toolactie: elke aanroeper
        # (agent, specialist, workflow, uitvoerroute, HITL-goedkeuring, copilot, SOP) komt hier langs.
        # Bewust VOOR de permissiecheck en VOOR het verzilveren van een HITL-ticket: een stilgezette
        # klant verbruikt geen goedkeuring, die blijft staan tot de stop is opgeheven. Fail-closed:
        # ook een stand die niet te lezen is weigert. Een actie die al LOOPT (voorbij deze regel)
        # wordt niet onderbroken; de eerstvolgende wordt hier geweigerd.
        try:
            await eis_klant_actief(tenant_id)
        except KlantStilgezet as stop:
            await self._audit_blocked_attempt(
                tool_name=tool_name,
                tenant_id=tenant_id,
                agent_id=agent_id,
                payload=payload,
                broker_keys=broker_keys,
                error_detail=stop.bericht,
            )
            raise ToolExecutionException(tool_name=tool_name, error_detail=stop.bericht) from stop

        # 0. Permission Check (ADR-015: ToolPermissionManager default-deny allowlist)
        # NOTE: agent_id=None is treated as "" (no profile) -> denied. Fail-secure.
        if not self.permission_manager.is_tool_allowed(agent_id or "", tool_name):
            logger.error(
                "Permission denied: agent %s tried to use tool %s",
                agent_id,
                tool_name,
            )
            refusal_detail = (
                f"Permission denied: Agent '{agent_id}' is not authorized to use tool '{tool_name}'"
            )
            await self._audit_blocked_attempt(
                tool_name=tool_name,
                tenant_id=tenant_id,
                agent_id=agent_id,
                payload=payload,
                broker_keys=broker_keys,
                error_detail=refusal_detail,
            )
            raise ToolExecutionException(tool_name=tool_name, error_detail=refusal_detail)

        # 0a. Validate tool category before risk gating (fail fast for unknown categories).
        # Via `is_known_tool` en niet inline: het goedkeuringspad past nu DEZELFDE controle toe,
        # en twee kopieen van die regel lopen uiteen (ADR-036 OP-78).
        if not is_known_tool(tool_name):
            refusal_detail = f"Unknown tool category for tool: {tool_name}"
            await self._audit_blocked_attempt(
                tool_name=tool_name,
                tenant_id=tenant_id,
                agent_id=agent_id,
                payload=payload,
                broker_keys=broker_keys,
                error_detail=refusal_detail,
            )
            raise ToolExecutionException(tool_name=tool_name, error_detail=refusal_detail)

        # 0c. Risk Classification (ADR-015)
        risk_level = self.risk_classifier.classify(tool_name)
        logger.info(
            "Tool %s classified as %s",
            tool_name,
            risk_level.value,
            extra={"tool_name": tool_name, "risk_level": risk_level.value, "agent_id": agent_id},
        )

        # 0d. HITL-poort (ADR-015)
        #
        # Vuurt bij HIGH risico, EN zodra de aanroeper een ticketverwijzing aanbiedt (ADR-036
        # OP-89). Die tweede voorwaarde is nodig omdat er twee onafhankelijke bronnen van waarheid
        # over risico zijn: `create_hitl_request` zet hardgecodeerd `risk_level="HIGH"` op het
        # ticket, terwijl `ToolRiskClassifier` los daarvan oordeelt. Gemeten: `create_task`,
        # `update_task` en `query_hr_database` zijn medium. Voor precies die tools werd een ticket
        # dus NOOIT verzilverd -- de actie liep, zonder bindingscontrole, en het ticket bleef eeuwig
        # `approved` in plaats van `consumed`.
        #
        # Het invariant is niet "hoog risico wordt bewaakt" maar: WIE EEN TICKET AANBIEDT, MOET EEN
        # GELDIG TICKET AANBIEDEN. Strikt veiliger, want een aanroeper kan zich hiermee niet aan de
        # controle onttrekken door een tool te kiezen die lager is geclassificeerd.
        approved_ticket_ref: str | None = None
        ticket_ref_aangeboden = payload.get("_hitl_ticket_ref")
        if risk_level == ToolRiskLevel.HIGH or ticket_ref_aangeboden is not None:
            ticket_ref = ticket_ref_aangeboden

            if self.hitl_store is None:
                logger.error(
                    "hitl_store not configured in ToolBrokerService",
                    extra={"tool_name": tool_name, "tenant_id": tenant_id},
                )
                refusal_detail = (
                    f"Tool '{tool_name}' requires human approval (HIGH risk) but HITLStore "
                    "is not configured. Inject via ToolBrokerService(hitl_store=...)."
                )
                await self._audit_blocked_attempt(
                    tool_name=tool_name,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    payload=payload,
                    broker_keys=broker_keys,
                    error_detail=refusal_detail,
                )
                raise ToolExecutionException(tool_name=tool_name, error_detail=refusal_detail)

            if isinstance(ticket_ref, str):
                # VERZILVEREN, niet alleen de status lezen (ADR-036 OP-63). Deze poort toetste
                # eerder uitsluitend `status == "approved"`: geen vergelijking met de tool die
                # wordt uitgevoerd, geen vergelijking van de parameters, en het ticket bleef
                # daarna goedgekeurd staan. Omdat `ToolRiskClassifier` onbekende tools standaard
                # op HIGH zet, gold dat voor alles -- een goedgekeurde ticketverwijzing was een
                # permanente volmacht voor de hele tenant. `redeem` doet de vier controles in EEN
                # UPDATE, zodat er geen gat zit tussen controleren en verbruiken.
                ticket_valid = await self.hitl_store.redeem_approval(
                    ticket_ref,
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    payload=payload,
                )
            else:
                ticket_valid = False

            if ticket_valid and self.db_session is not None:
                # DE VERZILVERING VASTLEGGEN VOOR HET NEVENEFFECT (ADR-036 H-1, 2026-08-09).
                #
                # `redeem` zet `approved` -> `consumed` op de request-sessie en die stond hier
                # nog niet vast. Daartussen draait de tool, tot 30 seconden lang
                # (`_UITVOER_TIMEOUT_SECONDEN`). Wordt het verzoek in dat venster afgebroken --
                # werker-recycling per ADR-011, een client die wegklikt, SIGTERM tijdens een
                # deploy -- dan loopt `get_db` (`database.py:490`) zijn `except Exception` NIET,
                # want `CancelledError` erft van `BaseException`. De transactie wordt weggegooid.
                # Uitkomst: de tool IS uitgevoerd, het ticket staat weer op `approved` en is
                # binnen 24 uur opnieuw te verzilveren door de aanvrager, die de ticketverwijzing
                # in zijn eigen antwoord terugkrijgt. Gemeten tegen een echte Postgres.
                #
                # De commit hoort HIER en niet in de router: dit is het enige punt tussen het
                # verzilveren en het neveneffect. `.claude/rules/database.md` zegt bovendien:
                # nooit een transactie openhouden tijdens een externe aanroep -- en dat is
                # precies wat de tooluitvoering is.
                #
                # `db_session is None` in elke andere bedrading (agents, specialisten,
                # singleton). Die hebben de store via `session_factory`/fallback, en
                # `db_manager.get_session()` commit daar zelf bij het verlaten van de context
                # (`database.py:304`) -- daar is de verzilvering dus al duurzaam. De guard is
                # geen "die paden zijn niet gedekt" maar "die paden regelen het zelf".
                #
                # Blast radius, gemeten: `_hitl_ticket_ref` wordt op EEN plek geproduceerd
                # (`hitl_router.py:282`), en op dat pad heeft de sessie hier niets anders
                # openstaan -- de goedkeuring is al vastgelegd op `hitl_router.py:402`.
                # Bewaakt door `tests/architecture/test_hitl_ticket_ref_has_one_producer.py`.
                await self.db_session.commit()

            if ticket_valid and isinstance(ticket_ref, str):
                # De auditregel legt deze koppeling vast in zijn EIGEN kolom
                # (`ToolAuditLog.hitl_ticket_ref`, geindexeerd en precies hiervoor bedoeld).
                # Eerder vulde de broker die kolom niet, waardoor de koppeling alleen bestond
                # zolang `_hitl_ticket_ref` leesbaar in `tool_input` overleefde -- en dat was
                # het argument om die sleutelnaam altijd-leesbaar te verklaren binnen een
                # PII-filter. (Gate 2-review BE-AGT-045 ronde 2, HIGH-2.)
                approved_ticket_ref = ticket_ref

            if not ticket_valid:
                logger.warning(
                    "Tool %s requires HITL approval but no valid approved ticket provided",
                    tool_name,
                    extra={
                        "tool_name": tool_name,
                        "agent_id": agent_id,
                        "ticket_ref": ticket_ref,
                        "tenant_id": tenant_id,
                    },
                )
                hitl_error_detail = (
                    f"Tool '{tool_name}' requires human approval (HIGH risk). "
                    "Create a ticket via POST /v1/tools/hitl/request and obtain approval first."
                )
                await self._audit_blocked_attempt(
                    tool_name=tool_name,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    payload=payload,
                    broker_keys=broker_keys,
                    error_detail=hitl_error_detail,
                )
                raise ToolExecutionException(
                    tool_name=tool_name,
                    error_detail=hitl_error_detail,
                    context={"ticket_ref": ticket_ref} if ticket_ref else None,
                )

        start_time = time.time()
        status_label = "failure"
        result: dict[str, object] | None = None
        error_detail: str | None = None

        # Wat er van de payload vastgelegd MAG worden. Een keer bepaald voor alle takken, zodat
        # ook de twee except-takken en de auditregel hem gebruiken; die publiceerden hem eerder
        # ongefilterd, waardoor de redactie op het succespad niets waard was zodra er iets
        # misging. Binnen de try, want zonder pseudonimiseringssleutel gooit hij en dan hoort
        # die fout geclassificeerd, gepubliceerd en geaudit te worden in plaats van als rauwe
        # RuntimeError langs beide except-takken te glippen.
        publish_payload: dict[str, object] = {}

        try:
            publish_payload = redact_for_publication(
                tool_name,
                payload,
                tenant_id=tenant_id,
                broker_keys=frozenset(broker_keys),
            )
            # 1. Check for Local Tools (Bypasses external resilience for performance)
            if tool_name.startswith("local__") or tool_name.startswith("test__"):
                if not self.local_registry:
                    raise ToolExecutionException(
                        tool_name=tool_name,
                        error_detail="Local tool registry not initialized.",
                    )
                result = await self.local_registry.execute_local_tool(tool_name, payload)
                self._publish_tool_event(
                    event_type="tool.executed",
                    tool_name=tool_name,
                    publish_payload=publish_payload,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    duration_seconds=time.time() - start_time,
                    success=True,
                    publish_result=safe_digest_result(result, tenant_id=tenant_id),
                )
                status_label = "success"
                return result

            # 3. HR-tools (ADR-036 D10 stap 3, BE-AGT-044). Twee leestools met geaggregeerde
            # uitkomsten en sinds 2026-09-21 een schrijftool (`schedule_training`). Geen van de
            # drie geeft persoonsgegevens terug, want het resultaat gaat hieronder de event bus
            # op en wordt door het leersubsysteem gepersisteerd. De schrijftool staat als HIGH in
            # `tool_risk_levels.yml` en komt dus langs de HITL-poort hierboven; deze tak wordt
            # pas bereikt nadat die poort is doorlopen.
            # 3b. Debiteurentools (debiteurenagent dag 2). Zelfde vorm als de HR-tak hieronder,
            # en om dezelfde redenen: de tenant komt uit de EXECUTIECONTEXT en niet uit de
            # payload, en een tool die zelf `success: false` meldt wordt niet als geslaagd
            # gepubliceerd. `send_payment_reminder` is HIGH en komt dus pas hier aan nadat de
            # HITL-poort hierboven een goedgekeurd ticket heeft verzilverd.
            if tool_name in ReceivablesToolRegistry.known_tool_names():
                result = await self.receivables_registry.execute_receivables_tool(
                    tool_name,
                    {k: v for k, v in payload.items() if k != "tenant_id"},
                    tenant_id=self._context_tenant(tool_name, context),
                )
                tool_ok = not (isinstance(result, dict) and result.get("success") is False)
                tool_error = None if tool_ok else str(result.get("error"))
                self._publish_tool_event(
                    event_type="tool.executed" if tool_ok else "tool.failed",
                    tool_name=tool_name,
                    publish_payload=publish_payload,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    duration_seconds=time.time() - start_time,
                    success=tool_ok,
                    publish_result=safe_digest_result(
                        result if tool_ok else None, tenant_id=tenant_id
                    ),
                    publish_error=safe_value_digest(tool_error, tenant_id=tenant_id),
                )
                status_label = "success" if tool_ok else "failure"
                error_detail = tool_error
                return result

            # 3c. Crediteurentools (crediteuren dag 2). Zelfde vorm als de debiteurentak hierboven: de tenant komt
            # uit de EXECUTIECONTEXT, een tool die zelf `success: False` meldt telt niet als geslaagd.
            # `propose_supplier_invoice` is HIGH en komt hier pas aan na een goedgekeurd ticket.
            if tool_name in PayablesToolRegistry.known_tool_names():
                result = await self.payables_registry.execute_payables_tool(
                    tool_name,
                    {k: v for k, v in payload.items() if k != "tenant_id"},
                    tenant_id=self._context_tenant(tool_name, context),
                )
                tool_ok = not (isinstance(result, dict) and result.get("success") is False)
                tool_error = None if tool_ok else str(result.get("error"))
                self._publish_tool_event(
                    event_type="tool.executed" if tool_ok else "tool.failed",
                    tool_name=tool_name,
                    publish_payload=publish_payload,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    duration_seconds=time.time() - start_time,
                    success=tool_ok,
                    publish_result=safe_digest_result(
                        result if tool_ok else None, tenant_id=tenant_id
                    ),
                    publish_error=safe_value_digest(tool_error, tenant_id=tenant_id),
                )
                status_label = "success" if tool_ok else "failure"
                error_detail = tool_error
                return result

            # 3d. Betaalrun (crediteuren dag 3). `propose_payment_run` is HIGH en komt hier pas aan na een goedgekeurd ticket;
            # alle facturen van het voorstel gaan dan atomair naar `goedgekeurd`, of geen enkele.
            if tool_name in BetaalrunToolRegistry.known_tool_names():
                result = await self.payment_run_registry.execute_payment_run_tool(
                    tool_name,
                    {k: v for k, v in payload.items() if k != "tenant_id"},
                    tenant_id=self._context_tenant(tool_name, context),
                )
                tool_ok = not (isinstance(result, dict) and result.get("success") is False)
                tool_error = None if tool_ok else str(result.get("error"))
                self._publish_tool_event(
                    event_type="tool.executed" if tool_ok else "tool.failed",
                    tool_name=tool_name,
                    publish_payload=publish_payload,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    duration_seconds=time.time() - start_time,
                    success=tool_ok,
                    publish_result=safe_digest_result(
                        result if tool_ok else None, tenant_id=tenant_id
                    ),
                    publish_error=safe_value_digest(tool_error, tenant_id=tenant_id),
                )
                status_label = "success" if tool_ok else "failure"
                error_detail = tool_error
                return result

            if tool_name in HRToolRegistry.known_tool_names():
                # De tenant komt uit de EXECUTIECONTEXT en niet uit de payload. De payload is
                # de json.loads van een TOOL_CALL-directive en dus door het model beschreven;
                # zolang de tenant daaruit kwam, hing de isolatie eraan dat elke aanroeper een
                # context meegeeft -- en die parameter is optioneel.
                # (Gate 2-review BE-AGT-044, HIGH-4.)
                #
                # Deze check blijft naast `_require_tenant_for_execution` hierboven staan, en is
                # opzettelijk STRIKTER: die accepteert ook de ADR-003 ContextVar, deze eist een
                # expliciete `context`. Voor een tool die personeelsdata leest is "de aanroeper
                # heeft de tenant bewust meegegeven" een zwaardere eis dan "er stond een tenant
                # in de omgeving", en dat verschil is hier het waard.
                context_tenant = (context or {}).get("tenant_id")
                if not isinstance(context_tenant, (int, str)) or isinstance(context_tenant, bool):
                    raise ToolExecutionException(
                        tool_name=tool_name,
                        error_detail="tenant_id must come from the execution context",
                    )
                try:
                    hr_tenant_id = int(context_tenant)
                except ValueError as exc:
                    raise ToolExecutionException(
                        tool_name=tool_name,
                        error_detail="tenant_id from the execution context must be an integer",
                    ) from exc

                hr_payload = {k: v for k, v in payload.items() if k != "tenant_id"}
                result = await self.hr_registry.execute_hr_tool(
                    tool_name, hr_payload, tenant_id=hr_tenant_id
                )

                # Een tool die zelf meldt dat hij faalde, mag niet als geslaagd de event bus,
                # de leeropslag en de auditketen in. Anders leert het leersubsysteem dat een
                # geweigerde aanroep een goed patroon is, en legt de ADR-019 hash-keten een
                # onwaar record vast dat wel geldig geketend is.
                # (Gate 2-review BE-AGT-044, HIGH-2.)
                tool_ok = not (isinstance(result, dict) and result.get("success") is False)
                tool_error = None if tool_ok else str(result.get("error"))

                self._publish_tool_event(
                    event_type="tool.executed" if tool_ok else "tool.failed",
                    tool_name=tool_name,
                    publish_payload=publish_payload,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    duration_seconds=time.time() - start_time,
                    success=tool_ok,
                    publish_result=safe_digest_result(
                        result if tool_ok else None, tenant_id=tenant_id
                    ),
                    publish_error=safe_value_digest(tool_error, tenant_id=tenant_id),
                )
                status_label = "success" if tool_ok else "failure"
                # Ook de auditregel moet vastleggen WAT er misging, niet alleen DAT er iets
                # misging (Gate 2-review BE-AGT-044, MEDIUM-A).
                error_detail = tool_error
                return result

            # 2. Business tools (governed Task execution)
            if tool_name in BusinessToolRegistry.known_tool_names():
                if not self.business_registry:
                    raise ToolExecutionException(
                        tool_name=tool_name,
                        error_detail="Business tool registry not initialized.",
                    )
                result = await self.business_registry.execute_business_tool(tool_name, payload)
                self._publish_tool_event(
                    event_type="tool.executed",
                    tool_name=tool_name,
                    publish_payload=publish_payload,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    duration_seconds=time.time() - start_time,
                    success=True,
                    publish_result=safe_digest_result(result, tenant_id=tenant_id),
                )
                status_label = "success"
                return result

            # 3. Determine which external client to use
            if tool_name.startswith("serena__"):
                client = self.serena_client
                circuit_breaker = self.serena_breaker
            elif tool_name.startswith("sequentialthinking__"):
                client = self.seq_thinking_client
                circuit_breaker = self.seq_thinking_breaker
            else:
                raise ToolExecutionException(
                    tool_name=tool_name,
                    error_detail=f"Unknown tool category for tool: {tool_name}",
                )

            # 3. Execute with resilience patterns if enabled
            if self.enable_resilience:
                result = await self._execute_with_resilience(
                    client, circuit_breaker, tool_name, payload, timeout_seconds
                )
            else:
                result = await client.call(tool_name, payload)

            status_label = "success"
            self.resilience_metrics.record_call(success=True)
            self._publish_tool_event(
                event_type="tool.executed",
                tool_name=tool_name,
                publish_payload=publish_payload,
                tenant_id=tenant_id,
                agent_id=agent_id,
                duration_seconds=time.time() - start_time,
                success=True,
                publish_result=safe_digest_result(result, tenant_id=tenant_id),
            )
            logger.info(f"Tool executed successfully: {tool_name}")
            return result

        except CircuitBreakerOpenException as e:
            logger.warning(f"Circuit breaker open for {tool_name}: {e}")
            self.resilience_metrics.record_call(success=False)
            self._publish_tool_event(
                event_type="tool.failed",
                tool_name=tool_name,
                publish_payload=publish_payload,
                tenant_id=tenant_id,
                agent_id=agent_id,
                duration_seconds=time.time() - start_time,
                success=False,
                publish_error=safe_value_digest(str(e), tenant_id=tenant_id),
            )
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=f"Service temporarily unavailable (circuit breaker open): {str(e)}",
                original_error=e,
            )

        except ToolBrokerException:
            logger.warning(f"Tool execution failed (ToolBrokerException): {tool_name}")
            self.resilience_metrics.record_call(success=False)
            self._publish_tool_event(
                event_type="tool.failed",
                tool_name=tool_name,
                publish_payload=publish_payload,
                tenant_id=tenant_id,
                agent_id=agent_id,
                duration_seconds=time.time() - start_time,
                success=False,
                publish_error=safe_value_digest("tool_broker_error", tenant_id=tenant_id),
            )
            raise

        except Exception as exc:
            logger.error(
                f"Unexpected error during tool execution for {tool_name}: {exc}",
                exc_info=True,
            )
            self.resilience_metrics.record_call(success=False)
            self._publish_tool_event(
                event_type="tool.failed",
                tool_name=tool_name,
                publish_payload=publish_payload,
                tenant_id=tenant_id,
                agent_id=agent_id,
                duration_seconds=time.time() - start_time,
                success=False,
                publish_error=safe_value_digest(str(exc), tenant_id=tenant_id),
            )
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=f"An unexpected error occurred during tool execution: {str(exc)}",
                original_error=exc,
            ) from exc

        finally:
            duration = time.time() - start_time
            TOOL_EXECUTION_COUNT.labels(tool_name=tool_name, status=status_label).inc()
            TOOL_EXECUTION_LATENCY.labels(tool_name=tool_name).observe(duration)

            # Audit logging via best_effort (never blocks primary operation)
            if self._audit_actief():
                import asyncio

                resultaat_voor_audit = result if status_label == "success" else None

                # OP-29: tool_output/error_detail are unfiltered tool output, same class of risk
                # as tool_input (already redacted into publish_payload above). Redact here, once,
                # so the OP-28 audit hash covers exactly what gets persisted.
                # SYNCHROON, voor het inplannen van de taak (Gate 2 N6): de achtergrondtaak draait
                # pas na het eerstvolgende `await` van de aanroeper, en een in-place mutatie van het
                # resultaat in tussentijd zou anders in het logboek terechtkomen. De digest hoort
                # bij het resultaat zoals de tool het teruggaf. BINNEN een eigen try (Gate 2 S1): een
                # fout hier (bijvoorbeeld een ontbrekende pseudonimiseringssleutel buiten
                # development) wordt geteld en lekt niet uit de `finally` naar de toolaanroeper.
                # Zonder geslaagde redactie wordt er niets geschreven.
                digest_gelukt = False
                publish_result = None
                publish_error = None
                try:
                    publish_result = safe_digest_result(resultaat_voor_audit, tenant_id=tenant_id)
                    publish_error = safe_value_digest(error_detail, tenant_id=tenant_id)
                    digest_gelukt = True
                except Exception as digest_exc:
                    _count_audit_write_failure(digest_exc)
                    logger.warning("Audit log digest failed (non-critical): %s", digest_exc)

                async def _write_audit() -> None:
                    try:
                        async with self._audit_schrijfdoel(
                            tenant_id, "tool audit log"
                        ) as _audit_repo:
                            try:
                                # De repository leest de vorige hash zelf, onder het slot per klant.
                                await _audit_repo.log_execution(
                                    agent_id=agent_id or "unknown",
                                    tool_name=tool_name,
                                    risk_level=self.risk_classifier.classify(tool_name).value,
                                    tool_input=publish_payload,
                                    tool_output=publish_result,
                                    status=(
                                        "success"
                                        if status_label == "success"
                                        else (
                                            "blocked"
                                            if "permission" in (error_detail or "")
                                            else "failed"
                                        )
                                    ),
                                    duration_seconds=duration,
                                    error_detail=publish_error,
                                    hitl_ticket_ref=approved_ticket_ref,
                                )
                            except Exception as write_exc:
                                _count_audit_write_failure(write_exc)
                                raise
                    except asyncio.CancelledError as cancel_exc:
                        # Gate 2 S5: `except Exception` vangt een annulering niet. Een geannuleerde
                        # auditregel is een verloren regel en hoort geteld te worden. Daarna
                        # opnieuw opgooien: een annulering wordt nooit ingeslikt.
                        _count_audit_write_failure(cancel_exc)
                        raise
                    except Exception as audit_exc:
                        # Alles buiten het blok (redactie, digest, sessie openen, commit/sluiten,
                        # context terugzetten, klantcontrole) viel hier nog ongeteld weg. Fouten
                        # BINNEN het blok slikt `best_effort` en zijn hierboven al geteld.
                        _count_audit_write_failure(audit_exc)
                        logger.warning("Audit log write failed (non-critical): %s", audit_exc)

                # Geen `return` in een `finally`: dat zou de uitzondering van de tool inslikken.
                if digest_gelukt:
                    try:
                        # Houd een verwijzing vast tot de taak klaar is: de gebeurtenislus bewaart
                        # alleen een zwakke verwijzing, en een taak zonder andere verwijzing kan
                        # halverwege worden opgeruimd, waarna de auditregel stil ontbreekt.
                        audit_task = asyncio.create_task(_write_audit())
                        _AUDIT_TASKS.add(audit_task)
                        audit_task.add_done_callback(_AUDIT_TASKS.discard)
                    except Exception as sched_exc:
                        _count_audit_write_failure(sched_exc)
                        logger.warning("Failed to schedule audit log write: %s", sched_exc)

    def _audit_actief(self) -> bool:
        """Schrijft deze broker een regel in het toollogboek (ADR-019)? Zo niet, dan is dat bewust.

        Twee vormen: een sessiefabriek (de repository wordt per regel voor de klant van de
        aanroep gebouwd) of het oudere paar `audit_repository` + `db_session`.
        """
        return self.audit_session_factory is not None or bool(
            self.audit_repository and self.db_session
        )

    @asynccontextmanager
    async def _audit_schrijfdoel(
        self, tenant_id: int, operatie: str
    ) -> "AsyncIterator[ToolAuditRepository]":
        """De repository waarmee EEN auditregel voor `tenant_id` wordt geschreven, best effort.

        Een fout binnen het blok wordt door `best_effort` gelogd en teruggedraaid, nooit
        doorgegeven: de toolactie zelf slaagt of faalt zoals hij deed.

        Met een sessiefabriek krijgt elke regel een EIGEN sessie en een repository voor de klant
        van deze aanroep (de klant komt uit de executiecontext, nooit uit de payload). De RLS-
        context volgt de ContextVar; die wordt hier voor de duur van de schrijfactie op deze klant
        gezet en daarna teruggezet, zodat een agent buiten een HTTP-verzoek geen lege context
        schrijft en de aanroeper er niets van overhoudt.

        Met het oudere paar geldt dat de repository aan een klant gebonden is: hoort hij bij een
        andere klant dan deze aanroep, of heeft hij geen bruikbare `tenant_id`, dan wordt er
        NIETS geschreven (geen regel in andermans keten).

        Elke fout buiten het blok (openen, sluiten, terugzetten, klantcontrole) wordt hier
        doorgegeven en door de aanroeper geteld en gelogd; die lekt nooit naar de toolaanroeper.
        """
        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id
        from src.core.utils.best_effort import best_effort

        factory = self.audit_session_factory
        if factory is not None:
            vorige = get_tenant_id()
            try:
                set_tenant_id(tenant_id)
                async with factory() as sessie:
                    async with best_effort(operatie, db_session=sessie):
                        yield ToolAuditRepository(sessie, tenant_id)
            finally:
                set_tenant_id(vorige)
            return

        repo = self.audit_repository
        if repo is None:
            raise RuntimeError("audit_repository ontbreekt")
        # Fail closed: een repository zonder bruikbare klant (attribuut ontbreekt of is geen int)
        # schrijft NIETS. De aanroeper (`_write_audit` / `_audit_blocked_attempt`) telt de fout.
        gebonden = getattr(repo, "tenant_id", None)
        if not isinstance(gebonden, int) or isinstance(gebonden, bool):
            raise RuntimeError("audit_repository heeft geen bruikbare tenant_id")
        if gebonden != tenant_id:
            raise RuntimeError("audit_repository hoort bij een andere klant dan deze aanroep")
        async with best_effort(operatie, db_session=self.db_session):
            yield repo

    async def _audit_blocked_attempt(
        self,
        *,
        tool_name: str,
        tenant_id: int,
        agent_id: str | None,
        payload: dict[str, object],
        broker_keys: set[str],
        error_detail: str,
    ) -> None:
        """Auditregel voor een fail-closed weigering (ADR-036 OP-35).

        De vier weigeringen die aan `execute_tool`'s `try`/`finally` voorafgaan (permissie,
        onbekende toolcategorie, ontbrekende hitl_store, ongeldig/ontbrekend HITL-ticket) kwamen
        nooit in de auditketen terecht: de auditregel-schrijvende `finally` ligt ACHTER ze. Precies
        de gebeurtenissen die het meest waard zijn om te loggen -- een geweigerde poging -- lieten
        daardoor geen spoor achter, en `status="blocked"` was daarmee onschrijfbaar
        (`get_blocked_tools_count()` toonde altijd nul).

        Best-effort en synchroon afgewacht (niet `asyncio.create_task`, in tegenstelling tot de
        auditregel in de `finally`): de aanroeper gaat hierna toch meteen een exception opvangen,
        dus er is geen "blokkeer de primaire operatie niet"-afweging zoals bij een geslaagde
        uitvoering. Een falende redactie/audit-write mag de ORIGINELE weigering niet overschaduwen
        -- vandaar `best_effort`, zelfde patroon als de `finally`-auditregel.
        """
        if not self._audit_actief():
            return

        try:
            # Redactie en digest staan BUITEN `_audit_schrijfdoel` (Gate 2 S1): binnen dat blok
            # slikt `best_effort` een fout in, gelogd maar ongeteld. Hier komt een fout in de
            # buitenste `except`, die telt. Zonder geslaagde redactie wordt er niets geschreven.
            publish_payload = redact_for_publication(
                tool_name, payload, tenant_id=tenant_id, broker_keys=frozenset(broker_keys)
            )
            # `publish_result`/`publish_error`: dezelfde naam-is-het-contract-conventie als
            # de `finally`-auditregel verderop (OP-29's test_tool_results_are_registered_as_
            # open.py scant SPECIFIEK op deze bare namen als bewijs van filtering). Een
            # geweigerde poging heeft nooit een resultaat, vandaar `publish_result = None`
            # in plaats van een aanroep -- maar wel als losse, herkenbare variabele, anders
            # meldt de guard een NIEUWE ongeregistreerde plek.
            publish_result: dict[str, str] | None = None
            publish_error = safe_value_digest(error_detail, tenant_id=tenant_id)
            async with self._audit_schrijfdoel(
                tenant_id, "tool audit log (blocked)"
            ) as audit_repository:
                try:
                    await audit_repository.log_execution(
                        agent_id=agent_id or "unknown",
                        tool_name=tool_name,
                        risk_level=self.risk_classifier.classify(tool_name).value,
                        tool_input=publish_payload,
                        tool_output=publish_result,
                        status="blocked",
                        duration_seconds=0.0,
                        error_detail=publish_error,
                    )
                except Exception as write_exc:
                    _count_audit_write_failure(write_exc)
                    raise
        except asyncio.CancelledError as cancel_exc:
            # Gate 2 N5, gelijk aan S5: `except Exception` vangt een annulering niet. Een
            # geannuleerde weigeringsregel is een verloren regel en hoort geteld te worden. Daarna
            # opnieuw opgooien: een annulering wordt nooit ingeslikt.
            _count_audit_write_failure(cancel_exc)
            raise
        except Exception as audit_exc:
            # Zie `_write_audit`: de fouten buiten het blok worden hier geteld, nooit doorgegeven.
            _count_audit_write_failure(audit_exc)
            logger.warning("Blocked-attempt audit log write failed (non-critical): %s", audit_exc)

    @staticmethod
    def _context_tenant(tool_name: str, context: dict[str, object] | None) -> int:
        """De tenant uit een EXPLICIETE `context`, strikter dan `_require_tenant_for_execution`.

        Dezelfde eis als de HR-tak: voor een tool op bedrijfsdata telt alleen een tenant die de
        aanroeper bewust heeft meegegeven, niet een tenant die toevallig in de omgeving stond.
        """
        context_tenant = (context or {}).get("tenant_id")
        if not isinstance(context_tenant, (int, str)) or isinstance(context_tenant, bool):
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id must come from the execution context",
            )
        try:
            return int(context_tenant)
        except ValueError as exc:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id from the execution context must be an integer",
            ) from exc

    def _require_tenant_for_execution(
        self, tool_name: str, context: dict[str, object] | None
    ) -> int:
        """De tenant van deze uitvoering -- uit de executiecontext, NOOIT uit de payload.

        De payload is bij agent-gedreven uitvoering de `json.loads` van een `TOOL_CALL`-directive
        en dus door een taalmodel geschreven. Zolang de tenant daaruit kwam, koos het model zijn
        eigen pseudonimiseringsscope en kon het zijn digests in de scope van een andere tenant
        laten vallen. Dit is dezelfde fout die in `hr_registry.py` bij BE-AGT-044 HIGH-4 is
        gesloten. (Gate 2-review BE-AGT-045 ronde 2, HIGH-1.)

        Resolutie: expliciete `context` eerst, dan de ADR-003 ContextVar die de
        tenant-middleware op elk HTTP-pad zet. Geen van beide: harde fout.

        Fail-closed en geen terugval, want beide alternatieven zijn erger dan een fout:
        een gedeelde constante ("unscoped") maakt dezelfde persoon in twee tenants
        correleerbaar, en een per-proces willekeurige waarde sloopt STIL de koppelbaarheid
        waarop het AI Act art.-12(2)-argument rust -- exact de reden waarom de sleutel buiten
        development ook hard faalt in plaats van iets te verzinnen.
        """
        from src.core.middleware.tenant_context import get_tenant_id

        candidate: object | None = (context or {}).get("tenant_id")
        if candidate is None:
            candidate = get_tenant_id()

        if isinstance(candidate, bool) or not isinstance(candidate, (int, str)):
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=(
                    "tenant_id must come from the execution context (context={'tenant_id': ...} "
                    "or the tenant ContextVar); it is never read from the payload."
                ),
            )

        try:
            tenant_id = int(candidate)
        except ValueError as exc:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id from the execution context must be an integer",
            ) from exc

        if tenant_id <= 0:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id from the execution context must be a positive integer",
            )

        return tenant_id

    def _publish_tool_event(
        self,
        event_type: str,
        tool_name: str,
        publish_payload: dict[str, object],
        agent_id: str | None,
        duration_seconds: float,
        success: bool,
        tenant_id: int,
        publish_result: dict[str, str] | None = None,
        publish_error: str | None = None,
    ) -> None:
        """Schedule asynchronous tool event publishing without blocking execution.

        De parameters heten `publish_payload`/`publish_result`/`publish_error` en niet
        `payload`/`result`/`error_detail`, en dat is geen stijlkeuze: de architectuur-guard kan
        niet zien of een waarde geredigeerd IS, alleen of hij uit de enige plek komt waar
        redactie gebeurt (`redaction.py::redact_for_publication`/`digest_result`/
        `value_digest`). De naam is dus het contract, en die naam moet ook binnen deze methode
        blijven gelden -- anders is de dict die de event-data opbouwt weer onzichtbaar voor de
        guard. Zo bleef de vierde sink in ronde 1 ongeteld (payload), en resultaat/foutmelding
        (OP-29) volgen sindsdien dezelfde regel: de AANROEPER redigeert, vlak voor de aanroep,
        niet deze methode zelf -- anders is de plek waar redactie gebeurt niet meer EEN plek.

        `tenant_id` komt uit de executiecontext en niet meer uit de gepubliceerde payload. De
        tenant-routing van `pubsub_manager` hing eraan dat die sleutel leesbaar in de payload
        overleefde, en dat was op zijn beurt het argument om de sleutelnaam altijd-leesbaar te
        verklaren. Een expliciete parameter haalt die koppeling weg.
        """
        publisher = self.event_publisher
        if publisher is None:
            return

        event = DomainEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            aggregate_id=agent_id or tool_name,
            aggregate_type="ToolExecution",
            data={
                "tool_name": tool_name,
                "agent_id": agent_id,
                "payload": publish_payload,
                "result": publish_result,
                "duration_seconds": duration_seconds,
                "success": success,
                "error": publish_error,
                "tenant_id": tenant_id,
            },
            timestamp=datetime.now(timezone.utc),
            metadata={"source": "tool_broker"},
        )

        async def _publish() -> None:
            try:
                await publisher.publish(event, routing_key=event_type)
            except Exception as exc:
                logger.warning("Tool event publish failed for %s: %s", tool_name, exc)

        asyncio.create_task(_publish())

    async def _execute_with_resilience(
        self,
        client: ISerenaClient | ISequentialThinkingClient,
        circuit_breaker: CircuitBreaker,
        tool_name: str,
        payload: dict[str, object],
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        """
        Execute tool with retry logic and circuit breaker protection

        Args:
            client: Tool client to call
            circuit_breaker: Circuit breaker for this client
            tool_name: Tool name
            payload: Tool parameters
            timeout_seconds: Execution timeout

        Returns:
            Tool execution result
        """

        async def call_through_breaker() -> dict[str, object]:
            result = await circuit_breaker.call(client.call, tool_name, payload)
            return result

        # Execute with retry logic through circuit breaker
        result = await async_retry(
            call_through_breaker,
            config=self.retry_config,
            on_retry=self._on_retry_attempt,
        )
        return result

    async def _on_retry_attempt(self, attempt_number: int, exception: Exception) -> None:
        """
        Callback for retry attempts

        Args:
            attempt_number: Current retry attempt number
            exception: Exception that triggered the retry
        """
        self.resilience_metrics.record_retry_attempt(success=False)
        logger.warning(f"Retry attempt {attempt_number}: {str(exception)}")

    def get_resilience_status(self) -> dict[str, object]:
        """
        Get detailed resilience status

        Returns: Dictionary with circuit breaker states and metrics
        """
        return {
            "resilience_enabled": self.enable_resilience,
            "circuit_breakers": self.circuit_breaker_registry.get_all_states(),
            "resilience_metrics": self.resilience_metrics.get_metrics(),
            "service_health": self.service_health.get_status(),
        }

    def get_circuit_breaker_state(self, name: str) -> dict[str, object] | None:
        """
        Get state of specific circuit breaker

        Args:
            name: Circuit breaker name ('serena_client' or 'sequential_thinking_client')

        Returns:
            Circuit breaker state or None
        """
        breaker = self.circuit_breaker_registry.get(name)
        if breaker:
            return breaker.get_state()
        return None
