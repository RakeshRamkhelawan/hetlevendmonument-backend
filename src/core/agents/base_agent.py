from __future__ import annotations

import asyncio
import importlib
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional
from collections.abc import Awaitable, Callable

from src.core.agents.mixins.learning_mixin import LearningMixin
from src.core.learning.auto_learning import auto_learn
from src.core.shared.config import get_feature_flag, get_settings
from src.core.shared.interfaces import (
    AgentCapability,
    AgentStatus,
    BaseAgent,
    ExecutionResult,
    SystemEvent,
    TaskData,
)
from src.core.types import AgentType, ExecutionStatusContract
from src.core.ai.prompt_guard import PromptGuard
from src.core.ai.output_validator import OutputValidator
from src.core.exceptions import PromptInjectionError
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.shared.ai_act_types import AIActRiskLevel

__all__ = [
    "BaseAgent",
    "AgentCapability",
    "AgentType",
    "ExecutionResult",
    "TaskData",
    "AgentStatus",
    "EnhancedBaseAgent",
    "create_agent_with_dependencies",
]

# Deferred import to avoid circular dependency: core.agents -> core.ai -> core.learning -> core.ai
if TYPE_CHECKING:
    from src.core.agents.config import AgentConfig
    from src.core.governance.governance_contract import GovernanceContract
    from src.core.shared.llm_client import ChatTaalmodel
    from src.core.tool_broker.permission_manager import ToolPermissionManager
    from src.core.tool_broker.service import ToolBrokerService

from src.domains.memory.schemas import MemoryItemWrite
from src.domains.memory.services.context_packer_service import ContextPackerService
from src.domains.memory.services.memory_write_service import MemoryWriteService

logger = logging.getLogger(__name__)


class _NoopToolClient:
    """Fallback client for local tool execution only."""

    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": False, "tool": tool_name, "payload": payload, "noop": True}


class EnhancedBaseAgent(LearningMixin, BaseAgent):
    """Enhanced base agent with dependency injection, event handling, and tenant isolation.

    CRITICAL SECURITY: All agents MUST provide a valid tenant_id.
    This ensures strict tenant isolation across all agent operations.
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        tenant_id: int | None = None,
        llm_client: ChatTaalmodel | None = None,
        memory_store: object | None = None,
        event_emitter: Callable[[SystemEvent], Awaitable[None]] | None = None,
        department: str | None = None,
        function: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(agent_id, agent_type)

        if not tenant_id or tenant_id <= 0:
            raise ValueError(
                f"invalid tenant_id for agent {agent_id}: {tenant_id}. "
                f"All agents MUST have a valid tenant_id for security isolation."
            )

        self.tenant_id = tenant_id
        # ADR-036 OP-24: analoog aan BaseSpecialistAgent._initiated_by_user_id
        # (specialist_base.py:104). Gezet door de aanroeper voordat execute_tool()
        # wordt aangeroepen, nooit door de agent zelf verzonnen.
        self._initiated_by_user_id: int | None = None
        self.department = department
        self.function = function

        # Dependency injection
        self.llm_client = llm_client
        self.memory_store = memory_store
        self.event_emitter = event_emitter or self._default_event_emitter
        self._tool_broker: ToolBrokerService | None = None
        self.__init_learning__(tenant_id)

        # AI Router for model selection (lazy import to avoid circular dependency)
        from src.core.ai.router import AIRouter

        self.ai_router = AIRouter()

        # LLM Harness guards (stateless, instantiated once per agent)
        self._prompt_guard = PromptGuard()
        self._output_validator = OutputValidator()

        # Explainability: Reasoning trace
        from src.core.ai.explainability import ReasoningTrace

        self.reasoning_trace: ReasoningTrace | None = None

        # Agent state
        self._tasks_processed = 0
        self._total_execution_time = 0.0
        self._errors_count = 0
        self._last_error: str | None = None
        self._initialization_time: datetime | None = None
        # NOTE: GDPR-009 profiling opt-out -- False = user has not opted out (profiling permitted).
        # SP-DLP-003: replace with per-request ConsentRepository.has_profiling_consent(user_id, tenant_id)
        # inside process_task(). This instance-level bool is NOT per-user -- it is a tenant-level default.
        self._profiling_opted_out: bool = False

        # Configuration
        self.settings = get_settings()
        self._max_concurrent_tasks = self.settings.max_concurrent_tasks

        # Task management
        self._current_tasks: dict[str, TaskData] = {}
        self._task_lock = asyncio.Lock()

        # Load YAML configuration if available
        self.yaml_config: Optional["AgentConfig"] = None
        self._load_yaml_config()

        # Consolidate department: parameter > YAML > default
        # Immutable after construction (stored as frozen attribute)
        extracted_department = self._extract_department_from_yaml()
        self.department = self.department or extracted_department or "unassigned"
        # Similarly for function (optional in Phase 1)
        self.function = self.function or None

        # EU-AI-006: mandatory governance contract per ADR-031 (AUDIT-FIX-001 Dag 4).
        # GOV-002/003/005 (AUDIT-ARCH-2026-07-02 Groep 3): autonomy_level/risk_category
        # are derived per agent-type via ai_act_classifier.classify_agent() (Art. 9 risk
        # management) instead of a single hardcoded value for every agent. Classified
        # AFTER department/function are consolidated (parameter > YAML > default) so a
        # YAML-configured department is visible to the classifier, not just the raw
        # constructor parameter.
        # TODO(SP-GOV-ARCH-6): subclasses (DepartmentAgent, generated agents) set their
        # real capability list via self.department_capabilities AFTER super().__init__()
        # returns, so it is not yet visible here -- classification for those ~120 agent
        # classes still falls back to [agent_type]. See
        # tests/architecture/test_autonomy_ladder_uses_real_agent_capabilities.py.
        _gc_mod = importlib.import_module("src.core.governance.governance_contract")
        _classifier_mod = importlib.import_module("src.core.governance.ai_act_classifier")
        # agent_type is typed AgentType but some callers pass a plain str (AgentType is
        # a str-Enum, duck-typed interchangeably elsewhere) -- getattr guards .value access.
        _agent_type_value = getattr(agent_type, "value", agent_type)
        _risk_category: AIActRiskLevel = _classifier_mod.classify_agent(
            name=agent_id,
            department=self.department,
            specialisation=self.function or _agent_type_value,
            capabilities=list(kwargs.get("capabilities") or [_agent_type_value]),
        )
        # AI Act Art. 14 human oversight: HIGH_RISK/UNACCEPTABLE require explicit
        # per-action approval (HUMAN_IN_LOOP); LIMITED/MINIMAL keep the existing
        # HUMAN_ON_LOOP default (agent executes, governance can review/intervene).
        _risk_to_autonomy = {
            AIActRiskLevel.UNACCEPTABLE: _gc_mod.AutonomyLevel.HUMAN_IN_LOOP,
            AIActRiskLevel.HIGH_RISK: _gc_mod.AutonomyLevel.HUMAN_IN_LOOP,
            AIActRiskLevel.LIMITED: _gc_mod.AutonomyLevel.HUMAN_ON_LOOP,
            AIActRiskLevel.MINIMAL: _gc_mod.AutonomyLevel.HUMAN_ON_LOOP,
        }
        _autonomy_level = _risk_to_autonomy.get(_risk_category, _gc_mod.AutonomyLevel.HUMAN_ON_LOOP)

        self._governance_contract: GovernanceContract | None = (
            _gc_mod.GovernanceContract(
                agent_id=agent_id,
                tenant_id=tenant_id,
                autonomy_level=_autonomy_level,
                risk_category=_risk_category,
            )
            if tenant_id is not None and tenant_id > 0
            else None
        )
        if self._governance_contract is not None:
            # Audit trail (Art. 9 risk management): record which classification and
            # autonomy level this agent was assigned, and why.
            self._governance_contract.record_evidence(
                "ai_act_classification",
                {
                    "risk_category": _risk_category.value,
                    "autonomy_level": _autonomy_level.value,
                    "department": self.department,
                    "specialisation": self.function or _agent_type_value,
                    "classified_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Security: Log agent initialization with tenant context
        logger.info(
            f"Initialized agent {self.agent_id} of type {self.agent_type}",
            extra={
                "agent_id": agent_id,
                "agent_type": agent_type.value if hasattr(agent_type, "value") else str(agent_type),
                "tenant_id": tenant_id,
                "department": self.department,
                "function": self.function,
                "event": "agent_init",
                "security_context": "tenant_isolated",
                "yaml_config_loaded": self.yaml_config is not None,
            },
        )

    def _create_tool_broker(self) -> "ToolBrokerService":
        """Create a local-first tool broker instance for agents."""
        import importlib

        _db_mod = importlib.import_module("src.core.database.database")
        db_manager = _db_mod.db_manager

        from src.core.tool_broker.hitl_store import HITLStore
        from src.core.tool_broker.local_registry import LocalToolRegistry
        from src.core.tool_broker.service import ToolBrokerService

        return ToolBrokerService(
            serena_client=_NoopToolClient(),
            seq_thinking_client=_NoopToolClient(),
            local_registry=LocalToolRegistry(),
            enable_resilience=False,
            hitl_store=HITLStore(session_factory=db_manager.get_session),
            audit_session_factory=db_manager.get_session,
        )

    @property
    def tool_broker(
        self,
    ) -> "ToolBrokerService | None":  # NOTE: deferred import avoids circular dep
        """Lazily create the tool broker to avoid overhead for non-tool agents."""
        if self._tool_broker is None:
            self._tool_broker = self._create_tool_broker()
        return self._tool_broker

    def _load_yaml_config(self) -> None:
        """
        Load YAML configuration for this agent if available.

        This method attempts to load agent configuration from a YAML file
        based on the agent's class name. Configuration is validated before
        being applied.
        """
        try:
            # Lazy import to avoid circular dependencies
            from src.core.agents.config.loader import get_config_loader
            from src.core.agents.config.validator import PromptValidator

            # Get the agent class name (e.g., "PythonProAgent")
            agent_name = self.__class__.__name__

            # Load config
            loader = get_config_loader()
            config = loader.load(agent_name)

            if config:
                # Validate prompts before applying
                validator = PromptValidator()
                is_valid, errors = validator.validate_config(config)

                if is_valid:
                    self.yaml_config = config

                    # Apply configuration values if not already set
                    if hasattr(self, "system_prompt") and not getattr(self, "system_prompt", None):
                        setattr(self, "system_prompt", config.prompts.system_prompt)

                    logger.debug(
                        f"Loaded YAML config for {agent_name}",
                        extra={
                            "agent_name": agent_name,
                            "config_version": config.agent.version,
                            "capabilities_count": len(config.capabilities),
                        },
                    )
                else:
                    logger.warning(
                        f"Invalid YAML config for {agent_name}: {errors}. Using defaults."
                    )

        except Exception as e:
            # YAML config is optional - agents work without it
            logger.debug(f"Could not load YAML config for {self.__class__.__name__}: {e}")

    def _extract_department_from_yaml(self) -> str | None:
        """
        Extract department from loaded YAML configuration.

        Attempts to retrieve the department from the classification section
        of the agent's YAML config. Returns None if config not loaded or
        department field is unavailable.

        Returns:
            Department string from config, or None if not available
        """
        if not self.yaml_config:
            return None

        try:
            # Access department from classification section
            if hasattr(self.yaml_config, "classification") and self.yaml_config.classification:
                department: str | None = getattr(
                    self.yaml_config.classification, "department", None
                )
                if department and isinstance(department, str) and department.strip():
                    logger.debug(
                        f"Extracted department from YAML for {self.agent_id}",
                        extra={"agent_id": self.agent_id, "department": department},
                    )
                    return department.strip()
        except (AttributeError, TypeError) as e:
            logger.debug(f"Could not extract department from YAML for {self.agent_id}: {e}")

        return None

    def _get_execute_tool_permission_manager(self, broker: object) -> "ToolPermissionManager":
        """Hergebruikt de broker's `ToolPermissionManager` i.p.v. een nieuwe te bouwen (ADR036-
        ADR015-001/OP-24, analoog aan `BaseSpecialistAgent._get_permission_manager()`).

        De `isinstance`-controle is er voor aanroepers die de broker vervangen door een mock:
        een mock levert bij attribuutopvraging weer een mock op, en die is waarheidig -- dan
        zou `is_denied()` alles blokkeren. Valt de broker af, dan bouwen we zelf een exemplaar
        en cachen dat op de instantie.

        De cache-check gebruikt bewust dezelfde `isinstance`-toets als de fallback hieronder
        (i.p.v. kaal `is not None`) -- dat narrowt het type voor mypy zonder de retourwaarde
        naar `Any` te moeten verzwakken (gevonden door de verplichte blinde eindreview: de
        oorspronkelijke `is not None`-vorm liet een `Any` weglekken uit een functie die
        `ToolPermissionManager` belooft)."""
        from src.core.tool_broker.permission_manager import ToolPermissionManager

        cached = getattr(self, "_execute_tool_permission_manager", None)
        if isinstance(cached, ToolPermissionManager):
            return cached

        from_broker = getattr(broker, "permission_manager", None)
        manager = (
            from_broker
            if isinstance(from_broker, ToolPermissionManager)
            else ToolPermissionManager()
        )
        self._execute_tool_permission_manager = manager
        return manager

    @auto_learn()
    async def execute_tool(
        self,
        tool_name: str,
        payload: dict[str, object],
        timeout: int = 30,
    ) -> dict[str, object]:
        """Execute a tool through the shared ToolBroker service."""
        broker = self.tool_broker
        if broker is None:
            raise RuntimeError("ToolBroker not available")

        started_at = time.perf_counter()
        try:
            # ADR036-ADR015-001/OP-24: defense-in-depth-precheck op de D5-harde-denylist,
            # analoog aan specialist_base.py::_reject_before_council(). Het runtimegedrag
            # voor een geweigerde tool verandert niet (broker.execute_tool() blokkeert hem
            # via is_tool_allowed() toch al) -- de winst is een vroegere afwijzing, zonder
            # de broker-round-trip en de bijwerkingen daarvan, en architecturale consistentie
            # met het ALS-pad. Geen Council- of initiator-check hier: die twee blijven de
            # echte, nog open OP-24-gaten (Fase D, geen equivalent-veld voor initiator hier).
            if self._get_execute_tool_permission_manager(broker).is_denied(
                self.agent_id, tool_name
            ):
                raise ToolExecutionException(
                    tool_name=tool_name,
                    error_detail=(
                        f"Denylist-geweigerd (ADR-036 D5): agent '{self.agent_id}' mag tool "
                        f"'{tool_name}' niet gebruiken."
                    ),
                )

            # ADR-036 OP-24 (BE-SEC-048): initiator-eis EN Council-raadpleging, analoog
            # aan specialist_base.py::_reject_before_council(). Achter een feature-flag
            # (default False) -- Taak 0-impact-analyse (2026-08-26) vond geen levende
            # aanroeper van execute_tool() op de ~20 EnhancedBaseAgent/SymbioticAgent-
            # subklassen buiten de ALS-boom, dus dit is architecturale consistentie
            # zodra dit pad ooit live gaat, geen fix van een actief lek.
            if get_feature_flag("enhanced_base_agent_initiator_check"):
                if self._initiated_by_user_id is None:
                    raise ToolExecutionException(
                        tool_name=tool_name,
                        error_detail="geen initiator bekend (AI Act art. 14)",
                    )

                from src.core.copilot.council.background_gate import (
                    request_council_decision_for_agent,
                )
                from src.core.copilot.council.types import (
                    DecisionVerdict,
                    ProposalTrigger,
                )

                outcome = await request_council_decision_for_agent(
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    user_id=self._initiated_by_user_id,
                    action_type=tool_name,
                    # Alleen sleutelnamen naar de Council (BE-AGT-043-patroon) --
                    # payload kan modelgegenereerde waarden bevatten.
                    action_params={"tool": tool_name, "arg_keys": sorted(payload)},
                    ticket_action_params=payload,
                    reasoning=f"Agent {self.agent_id} wil {tool_name} uitvoeren.",
                    message=(
                        f"Agent {self.agent_id} vraagt toestemming om de tool "
                        f"{tool_name} uit te voeren."
                    ),
                    trigger=ProposalTrigger.USER_REQUEST,
                )
                decision = outcome.decision

                # Zelfde patroon als specialist_base.py::_council_rejection() (regel
                # 411-497, niet _reject_before_council() -- die laatste checkt alleen
                # de D5-denylist en de initiator-null-check, geen DecisionVerdict):
                # alleen APPROVED gaat door. HITL_REQUIRED heeft al een ticket van de
                # gate zelf (ADR-036 OP-167) -- geen eigen ticket-logica hier nodig.
                # Elk ander verdict (BLOCKED/DEFERRED/MODIFIED) wordt geweigerd, niet
                # stilzwijgend uitgevoerd met aangepaste parameters: een MODIFIED-
                # verdict zonder menselijke review van de aanpassing zelf uitvoeren
                # zou de Council-controle juist omzeilen.
                if decision.verdict is not DecisionVerdict.APPROVED:
                    detail = (
                        f"Council-verdict {decision.verdict.value}: {decision.explanation_for_user}"
                    )
                    if decision.verdict is DecisionVerdict.BLOCKED:
                        from src.core.copilot.council.technische_blokkade import (
                            KLANTTEKST_NIET_BEOORDEELD,
                            is_technisch_niet_beoordeeld,
                        )

                        if is_technisch_niet_beoordeeld(getattr(decision, "officer_verdicts", ())):
                            detail = KLANTTEKST_NIET_BEOORDEELD
                    if (
                        decision.verdict is DecisionVerdict.HITL_REQUIRED
                        and outcome.hitl_ticket_ref is not None
                    ):
                        detail += f" (goedkeuringsticket aangemaakt: {outcome.hitl_ticket_ref})"
                    raise ToolExecutionException(tool_name=tool_name, error_detail=detail)

            result = await broker.execute_tool(
                tool_name=tool_name,
                payload=payload,
                agent_id=self.agent_id,
                timeout_seconds=timeout,
                context={"tenant_id": self.tenant_id},
            )
            await self.emit_event(
                "tool_executed",
                {
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "duration_seconds": time.perf_counter() - started_at,
                    "success": True,
                },
            )
            return result
        except Exception as exc:
            await self.emit_event(
                "tool_failed",
                {
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "duration_seconds": time.perf_counter() - started_at,
                    "success": False,
                    "error": str(exc),
                },
            )
            raise

    async def _load_persisted_governance_contract(self) -> None:
        """SP-GOV-ARCH-8: read back a HITL-approved GovernanceContract, if any.

        __init__ only builds a fresh in-memory contract via classify_agent().
        A HITL approval recorded via /hitl/approve persists evidence
        (approved_actions/hitl_approval) through GovernanceContractRepository
        -- without this read-back, an approved HUMAN_IN_LOOP action stays
        blocked forever on the next agent construction. The fresh
        autonomy_level/risk_category stay authoritative (they reflect the
        agent's current classification); only the approval-evidence keys are
        merged in from the persisted record. Always saves afterward so an
        agent that has never been approved still has a row for a future
        approval to attach to.

        Fail-open on read errors: if repo.load() itself fails, the
        conservative in-memory default (built in __init__) keeps blocking as
        before -- a missed refresh this cycle is not a security bypass, just
        a delayed approval pickup. If load() succeeds but the follow-up
        repo.save() then fails, the successfully-read approval evidence is
        still kept in memory (the approval was real; only the redundant
        re-persist failed) -- intentional, not a bug.

        Skips entirely if the DB engine was never set up (db_manager is not
        initialized) -- agent construction must not bootstrap the DB engine
        itself (that is app-startup's job, with its own multi-attempt retry
        loop); this also keeps unit tests that never configure a DB fast
        instead of paying that retry loop's cost.
        """
        if self._governance_contract is None:
            return
        try:
            _db_mod = importlib.import_module("src.core.database.database")
            if not _db_mod.db_manager.is_initialized():
                return
            _repo_mod = importlib.import_module(
                "src.core.governance.governance_contract_repository"
            )
            async with _db_mod.db_manager.get_session() as db:
                repo = _repo_mod.GovernanceContractRepository(
                    db, self._governance_contract.tenant_id
                )
                persisted = await repo.load(self._governance_contract.agent_id)
                if persisted is not None:
                    for key in ("approved_actions", "hitl_approval"):
                        if key in persisted.evidence:
                            self._governance_contract.evidence[key] = persisted.evidence[key]
                await repo.save(self._governance_contract)
        except Exception as e:
            logger.warning(
                "Could not load persisted governance contract for %s: %s: %s",
                self.agent_id,
                type(e).__name__,
                e,
            )

    async def initialize(self) -> bool:
        """Initialize the agent - base implementation"""
        try:
            self._initialization_time = datetime.now(timezone.utc)

            await self._load_persisted_governance_contract()

            # Initialize capabilities
            await self._initialize_capabilities()

            # Set up event handling
            await self.emit_event(
                "agent_initialized",
                {
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type.value,
                    "capabilities_count": len(self._capabilities),
                },
            )

            logger.info(f"Agent {self.agent_id} initialized successfully")
            return True

        except Exception as e:
            logger.error(
                "Failed to initialize agent %s: %s: %s",
                self.agent_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            self._last_error = str(e)
            return False

    def _sanitize_task_payload(self, task: TaskData) -> TaskData:
        """Sanitize all user-controllable task fields against prompt injection."""
        sanitized_fields: dict[str, object] = {
            "description": self._prompt_guard.sanitize(task.description, self.tenant_id),
            "title": self._prompt_guard.sanitize(task.title, self.tenant_id),
        }

        # Sanitize optional code field if present
        if task.code:
            sanitized_fields["code"] = self._prompt_guard.sanitize(task.code, self.tenant_id)

        # Sanitize metadata dict values if present
        if task.metadata:
            sanitized_fields["metadata"] = {
                k: self._prompt_guard.sanitize(str(v), self.tenant_id)
                for k, v in task.metadata.items()
            }

        # Sanitize tags list if present
        if task.tags:
            sanitized_fields["tags"] = [
                self._prompt_guard.sanitize(tag, self.tenant_id) for tag in task.tags
            ]

        return task.model_copy(update=sanitized_fields)

    @auto_learn()
    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Process a task with error handling and metrics"""
        logger.info(
            f"[DEBUG_BASE_PROCESS_TASK] Starting process_task for agent {self.agent_id}, task {task.id}"
        )
        start_time = time.perf_counter()

        # Initialize reasoning trace for explainability
        from src.core.ai.explainability import ReasoningStepType, ReasoningTrace

        self.reasoning_trace = ReasoningTrace(agent_name=self.agent_id, task_id=task.id)
        self.reasoning_trace.add_step(
            ReasoningStepType.INPUT_RECEIVED,
            f"Task received: {task.title}",
            {"task_id": task.id, "metadata": task.metadata},
        )

        # Load memory boot context if available
        boot_context = None
        if self.memory_store and isinstance(self.memory_store, dict):
            try:
                session_factory = self.memory_store.get("session_factory")
                mem_tenant_id: int = int(self.memory_store.get("tenant_id", self.tenant_id))
                if session_factory:
                    async with session_factory() as db:
                        packer = ContextPackerService(db=db, tenant_id=mem_tenant_id)
                        boot_context = await packer.build(
                            agent_id=self.agent_id,
                            session_id=None,  # session_id is Optional[int], task.id is str
                            token_budget=2000,
                        )
                    self.reasoning_trace.add_step(
                        ReasoningStepType.INPUT_RECEIVED,
                        "Memory boot context loaded",
                        {"context_keys": list(boot_context.keys()) if boot_context else []},
                    )
            except Exception as e:
                logger.warning(f"Failed to load boot context for {self.agent_id}: {e}")

        try:
            # Validate task
            logger.info(f"[DEBUG_BASE_PROCESS_TASK] Validating task {task.id}")
            if not await self.validate_task(task):
                logger.info(f"[DEBUG_BASE_PROCESS_TASK] Task validation FAILED for {task.id}")
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Task validation failed for agent {self.agent_id}",
                    status=ExecutionStatusContract.MISLUKT,
                )
            logger.info(f"[DEBUG_BASE_PROCESS_TASK] Task validation PASSED for {task.id}")

            # GDPR Art. 21: per-request profiling opt-out check.
            # Fail-closed on DB error (True = opted out = block).
            # Fail-open when no user_id in metadata or no session (False = allow).
            _user_id_profiling = str(task.metadata.get("user_id", "")) if task.metadata else ""
            self._profiling_opted_out = False  # reset per-request
            if _user_id_profiling and self.memory_store and isinstance(self.memory_store, dict):
                _sf = self.memory_store.get("session_factory")
                if _sf is not None:
                    try:
                        async with _sf() as _db:
                            _at_mod = importlib.import_module(
                                "src.core.governance.ai_transparency_service"
                            )
                            self._profiling_opted_out = await _at_mod.AITransparencyService(
                                db=_db
                            ).check_profiling_opt_out(
                                user_id=_user_id_profiling,
                                tenant_id=self.tenant_id,
                                profiling_type=_at_mod.ProfilingType.BEHAVIORAL,
                            )
                    except Exception as _e:
                        logger.warning(
                            "Profiling opt-out check failed (fail-closed): %s: %s",
                            type(_e).__name__,
                            _e,
                            exc_info=True,
                        )
                        self._profiling_opted_out = True

            if self._profiling_opted_out:
                logger.info(
                    "Agent %s: profiling opted-out, rejecting task %s",
                    self.agent_id,
                    task.id,
                )
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message="Profiling has been disabled for this user (GDPR Art. 21)",
                    status=ExecutionStatusContract.GEBLOKKEERD,
                )

            # Check concurrent task limit
            async with self._task_lock:
                if len(self._current_tasks) >= self._max_concurrent_tasks:
                    logger.info(f"[DEBUG_BASE_PROCESS_TASK] Agent at capacity, rejecting {task.id}")
                    return ExecutionResult(
                        task_id=task.id,
                        success=False,
                        error_message=f"Agent {self.agent_id} at capacity ({self._max_concurrent_tasks} tasks)",
                        status=ExecutionStatusContract.MEER_BUDGET_NODIG,
                    )

                self._current_tasks[task.id] = task
                logger.info(f"[DEBUG_BASE_PROCESS_TASK] Task {task.id} added to current tasks")

            # Update current load
            self._current_load = len(self._current_tasks) / self._max_concurrent_tasks

            # Emit task started event
            await self.emit_event(
                "task_started",
                {
                    "agent_id": self.agent_id,
                    "task_id": task.id,
                    "current_load": self._current_load,
                },
            )
            logger.info(f"[DEBUG_BASE_PROCESS_TASK] About to call _execute_task for {task.id}")

            # LLM Harness: Prompt injection prevention (sanitize all task fields)
            try:
                task = self._sanitize_task_payload(task)
            except PromptInjectionError as e:
                logger.warning(
                    "Prompt injection blocked in task input",
                    extra={
                        "tenant_id": self.tenant_id,
                        "agent_id": self.agent_id,
                        "task_id": task.id,
                        "event": "prompt_injection_detected",
                    },
                )
                execution_time = time.perf_counter() - start_time
                # MEDIUM-2: Return generic error message to client (log real details server-side)
                result = ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message="Invalid input format",  # Generic message -- real error logged above
                    execution_time=execution_time,
                    status=ExecutionStatusContract.MISLUKT,
                )
                self._current_tasks.pop(task.id, None)
                return result

            # EU-AI-006: governance contract permission check (ADR-031)
            action = task.code or "execute"
            _gc = self._governance_contract
            if _gc is not None and not _gc.is_action_permitted(action):
                logger.warning(
                    "Governance contract blocked action %s for agent %s",
                    action,
                    self.agent_id,
                )
                self._current_tasks.pop(task.id, None)
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Action '{action}' not permitted by governance contract",
                    status=ExecutionStatusContract.GEBLOKKEERD,
                )

            # Execute the actual task
            result = await self._execute_task(task)
            logger.info(f"[DEBUG_BASE_PROCESS_TASK] _execute_task completed for {task.id}")

            # EU-AI-003: log AI decision for transparency (best_effort -- non-blocking)
            if self.memory_store and isinstance(self.memory_store, dict):
                _sf_transparency = self.memory_store.get("session_factory")
                if _sf_transparency is not None:
                    from src.core.utils.best_effort import best_effort  # noqa: PLC0415

                    async with best_effort("ai_transparency_log"):
                        _at_mod2 = importlib.import_module(
                            "src.core.governance.ai_transparency_service"
                        )
                        async with _sf_transparency() as _db_transparency:
                            await _at_mod2.AITransparencyService(
                                db=_db_transparency
                            ).log_ai_decision(
                                user_id=str(task.metadata.get("user_id", self.agent_id))
                                if task.metadata
                                else self.agent_id,
                                tenant_id=self.tenant_id,
                                agent_id=self.agent_id,
                                decision_type=task.code or "execute",
                                explanation=f"Agent {self.agent_id} executed task {task.id}",
                            )

            # LLM Harness: Output validation and PII masking
            if result.output:
                cleaned_output, issues = self._output_validator.validate(
                    result.output,
                    context={"tenant_id": self.tenant_id, "agent_id": self.agent_id},
                )
                result = result.model_copy(update={"output": cleaned_output})

            # Update metrics
            execution_time = time.perf_counter() - start_time
            self._tasks_processed += 1
            self._total_execution_time += execution_time

            result.execution_time = execution_time

            # Finalize reasoning trace and persist to audit log
            if self.reasoning_trace:
                reasoning_data = self.reasoning_trace.finalize()
                self.reasoning_trace.add_step(
                    ReasoningStepType.OUTPUT_GENERATED,
                    f"Task completed: {result.success}",
                    {"result": result.result_data, "execution_time": execution_time},
                )

                # NOTE: reasoning-trace audit persistence removed (SP-AGT-002 Dag 3).
                # The previous deferred db_manager import was already a no-op in
                # production: audit_service.log_action() requires a session; without
                # one it silently returns None. Trace data is kept in self.reasoning_trace.

            # Persist task result as memory candidate
            if self.memory_store and isinstance(self.memory_store, dict) and result.success:
                try:
                    session_factory = self.memory_store.get("session_factory")
                    mem_tenant_id = int(self.memory_store.get("tenant_id", self.tenant_id))
                    if session_factory:
                        async with session_factory() as db:
                            writer = MemoryWriteService(db=db, tenant_id=mem_tenant_id)
                            payload = MemoryItemWrite(
                                content=f"Task '{task.title}' completed: {result.output[:500] if result.output else 'no output'}",
                                memory_type="episodic",
                                agent_id=self.agent_id,
                                source_type="workflow",
                                confidence=0.8,
                            )
                            await writer.write(payload)
                except Exception as e:
                    logger.warning(f"Failed to write memory for {self.agent_id}: {e}")

            # Emit task completed event
            await self.emit_event(
                "task_completed",
                {
                    "agent_id": self.agent_id,
                    "task_id": task.id,
                    "success": result.success,
                    "execution_time": execution_time,
                },
            )

            return result

        except Exception as e:
            execution_time = time.perf_counter() - start_time
            self._errors_count += 1
            self._last_error = str(e)

            logger.error(
                "Error processing task %s in agent %s: %s: %s",
                task.id,
                self.agent_id,
                type(e).__name__,
                e,
                exc_info=True,
            )

            await self.emit_event(
                "task_failed",
                {
                    "agent_id": self.agent_id,
                    "task_id": task.id,
                    "error": str(e),
                    "execution_time": execution_time,
                },
            )

            failed_result = ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=str(e),
                execution_time=execution_time,
                status=ExecutionStatusContract.MISLUKT,
            )

            return failed_result

        finally:
            # Clean up task tracking
            async with self._task_lock:
                self._current_tasks.pop(task.id, None)
                self._current_load = len(self._current_tasks) / self._max_concurrent_tasks

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Execute the actual task - must be implemented by subclasses."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _execute_task")

    async def _initialize_capabilities(self) -> None:
        """Initialize agent capabilities - can be overridden by subclasses"""
        # Default capabilities - subclasses should override this
        self._capabilities = [
            AgentCapability(
                name="basic_processing",
                description="Basic task processing capability",
                input_types=["text"],
                output_types=["text"],
                resource_requirements={"memory": "128MB", "cpu": "0.1"},
            )
        ]

    async def validate_task(self, task: TaskData) -> bool:
        """Validate if this agent can handle the task"""
        # Basic validation - check if task type is supported
        task_type = task.metadata.get("type", "general")

        for capability in self._capabilities:
            if task_type in capability.input_types:
                return True

        # If no specific capability matches, allow general tasks
        return task_type in ["general", "text"]

    async def get_status(self) -> AgentStatus:
        """Get enhanced agent status with metrics"""
        base_status = await super().get_status()

        # Add enhanced metrics
        base_status.metrics = {
            "tasks_processed": self._tasks_processed,
            "total_execution_time": self._total_execution_time,
            "average_execution_time": (
                self._total_execution_time / self._tasks_processed
                if self._tasks_processed > 0
                else 0.0
            ),
            "errors_count": self._errors_count,
            "error_rate": (
                self._errors_count / self._tasks_processed if self._tasks_processed > 0 else 0.0
            ),
            "last_error": self._last_error,
            "current_tasks_count": len(self._current_tasks),
            "initialization_time": (
                self._initialization_time.isoformat() if self._initialization_time else None
            ),
            "uptime_seconds": (
                (datetime.now(timezone.utc) - self._initialization_time).total_seconds()
                if self._initialization_time
                else 0
            ),
        }

        return base_status

    async def emit_event(self, event_type: str, data: dict[str, object]) -> None:
        """Emit system event"""
        try:
            if self.event_emitter is not None:
                event = SystemEvent(event_type=event_type, source=self.agent_id, data=data)
                await self.event_emitter(event)
        except Exception as e:
            logger.warning(f"Failed to emit event {event_type}: {e}")

    async def _default_event_emitter(self, event: SystemEvent) -> None:
        """Default event emitter - logs events"""
        logger.info(f"Event: {event.event_type} from {event.source}")

    async def shutdown(self) -> None:
        """Gracefully shutdown the agent"""
        try:
            # Wait for current tasks to complete (with timeout)
            max_wait = 30  # 30 seconds
            wait_start = time.time()

            while self._current_tasks and (time.time() - wait_start) < max_wait:
                logger.info(f"Waiting for {len(self._current_tasks)} tasks to complete...")
                await asyncio.sleep(1)

            if self._current_tasks:
                logger.warning(f"Shutting down with {len(self._current_tasks)} tasks still running")

            await self.emit_event(
                "agent_shutdown",
                {
                    "agent_id": self.agent_id,
                    "tasks_processed": self._tasks_processed,
                    "uptime_seconds": (
                        (datetime.now(timezone.utc) - self._initialization_time).total_seconds()
                        if self._initialization_time
                        else 0
                    ),
                },
            )

            logger.info(f"Agent {self.agent_id} shutdown completed")

        except Exception as e:
            logger.error("Error during agent shutdown: %s: %s", type(e).__name__, e, exc_info=True)

    def get_performance_metrics(
        self,
    ) -> dict[str, object]:
        """Get detailed performance metrics"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "tasks_processed": self._tasks_processed,
            "total_execution_time": self._total_execution_time,
            "average_execution_time": (
                self._total_execution_time / self._tasks_processed
                if self._tasks_processed > 0
                else 0.0
            ),
            "errors_count": self._errors_count,
            "error_rate": (
                self._errors_count / self._tasks_processed if self._tasks_processed > 0 else 0.0
            ),
            "current_load": self._current_load,
            "max_concurrent_tasks": self._max_concurrent_tasks,
            "current_tasks_count": len(self._current_tasks),
            "capabilities_count": len(self._capabilities),
            "is_active": self._is_active,
            "initialization_time": (
                self._initialization_time.isoformat() if self._initialization_time else None
            ),
        }


# Utility functions for agent management
async def create_agent_with_dependencies(
    agent_class: type[EnhancedBaseAgent],
    agent_id: str,
    agent_type: AgentType,
    **kwargs: Any,
) -> EnhancedBaseAgent:
    """Factory function to create agents with proper dependency injection"""

    tenant_id = kwargs.get("tenant_id")
    if not tenant_id or tenant_id <= 0:
        raise ValueError(
            f"invalid tenant_id for agent {agent_id}: {tenant_id}. "
            f"All agents MUST have a valid tenant_id for security isolation."
        )

    # Set up LLM client based on configuration
    llm_client = None
    if get_feature_flag("llm_integration"):
        llm_client = await _setup_llm_client(tenant_id)

    # Set up memory store
    memory_store = None
    if get_feature_flag("agent_memory"):
        memory_store = await _setup_memory_store(tenant_id=tenant_id)

    # Set up event emitter
    event_emitter = await _setup_event_emitter()

    # Create agent (department and function can be passed via kwargs)
    agent = agent_class(
        agent_id=agent_id,
        agent_type=agent_type,
        llm_client=llm_client,
        memory_store=memory_store,
        event_emitter=event_emitter,
        **kwargs,
    )

    # Initialize
    if not await agent.initialize():
        raise RuntimeError(f"Failed to initialize agent {agent_id}")

    return agent


async def _setup_llm_client(tenant_id: int) -> ChatTaalmodel | None:
    """Het taalmodel van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14).

    Hier stond `get_default_llm_config()`: het platformmodel (Ollama of Google) voor elke klant, en bij
    een fout stil `None`. Het model wordt pas bij het eerste gebruik opgevraagd; een storing is dan een fout
    bij de aanroeper.
    """
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    return TenantTaalmodel(tenant_id)


async def _setup_memory_store(
    tenant_id: int,
) -> dict[str, object] | None:
    """Set up memory store with session factory for the memory domain.

    Returns a dict with session_factory and tenant_id so that services
    can be instantiated per-request inside process_task(). This avoids
    the session-lifecycle bug of creating services with a session that
    gets closed before they're used.

    Returns None if memory domain is not available.
    """
    if tenant_id <= 0:
        raise ValueError(f"invalid tenant_id for memory store: {tenant_id}")

    try:
        from src.core.container import get_container

        container = get_container()
        session_factory = container.session_factory()

        # Verify memory domain is importable (module-level imports exist at top of file)
        _ = ContextPackerService
        _ = MemoryWriteService
        _ = MemoryItemWrite

        return {
            "session_factory": session_factory,
            "tenant_id": tenant_id,
        }
    except Exception as e:
        logger.warning(f"Memory store setup failed, agents will run without memory: {e}")
        return None


async def _setup_event_emitter() -> Callable[[SystemEvent], Awaitable[None]]:
    """Set up event emitter system"""

    # Simple logging-based emitter for Week 1
    async def log_emitter(event: SystemEvent) -> None:
        logger.info(f"System Event: {event.event_type} from {event.source} - {event.data}")

    return log_emitter
