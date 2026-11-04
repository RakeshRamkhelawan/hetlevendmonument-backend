"""
C.7 Production-Ready Workflow Engine
====================================

This module implements the core workflow orchestration engine with:
- Dependency Injection for testability (ILLMProvider, IToolBroker, IAgentRuntime)
- DAG validation and topological execution
- PostgreSQL persistence via workflow_models
- State machine integration for transition validation
- Idempotent task execution via (execution_id, task_ref)
- Exponential backoff retry strategy
- Observability (Prometheus metrics + OpenTelemetry tracing)
- Multi-tenant isolation

Key Design:
- execute_task() is the seam for testing (accepts injected providers)
- Production uses ProductionLLMProvider/ProductionAgentRuntime
- Tests inject FakeLLMProvider/FakeAgentRuntime
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, TypeAlias, cast

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.observability.logging import configure_logging, structured_logger
from src.core.services.noodstop_toegang import KlantStilgezet, eis_klant_actief

# Import interfaces
from src.core.workflow.interfaces import (
    IAgentRuntime,
    ILLMProvider,
    IStateMachine,
    IToolBroker,
    IUnitOfWork,
    IWorkflowEngine,
    TaskExecutionResult,
)

# Import workflow models
from src.core.workflow.models import C7ExecutionEvent as ExecutionEvent
from src.core.workflow.models import C7ExecutionTask as ExecutionTask
from src.core.workflow.models import C7Workflow as Workflow
from src.core.workflow.models import C7WorkflowExecution as WorkflowExecution
from src.core.workflow.models import C7WorkflowSnapshot as WorkflowSnapshot
from src.core.workflow.models import EventType, TaskStatus, WorkflowStatus

# Import state machine
from src.core.workflow.state_machine import WorkflowStateMachine
from src.core.workflow.foutsoort import is_tijdelijke_fout
from src.core.workflow.tekst_invullen import vul_in

# Type aliases for common types
WorkflowSpecDict: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]
TaskConfigDict: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]
ExecutionContextDict: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]
DependenciesDict: TypeAlias = dict[str, list[str]]
TasksDict: TypeAlias = dict[str, TaskConfigDict]

# Prometheus metrics (optional - graceful degradation if not available)
# Using get_or_create_* functions to prevent duplicate registration in tests
workflow_executions_total: Any = None
workflow_duration_seconds: Any = None
workflow_tasks_total: Any = None
workflow_active_executions: Any = None

try:
    from src.core.monitoring.prometheus_metrics import (
        get_or_create_counter,
        get_or_create_gauge,
        get_or_create_histogram,
    )

    METRICS_AVAILABLE = True

    # Workflow metrics - using safe registration to prevent duplicates
    workflow_executions_total = get_or_create_counter(
        "workflow_executions_total",
        "Total workflow executions",
        labelnames=["tenant_id", "workflow_id", "status"],
    )
    workflow_duration_seconds = get_or_create_histogram(
        "workflow_duration_seconds",
        "Workflow execution duration",
        labelnames=["tenant_id", "workflow_id"],
    )
    workflow_tasks_total = get_or_create_counter(
        "workflow_tasks_total",
        "Total task executions",
        labelnames=["tenant_id", "workflow_id", "task_ref", "status"],
    )
    workflow_active_executions = get_or_create_gauge(
        "workflow_active_executions",
        "Currently active workflow executions",
        labelnames=["tenant_id", "workflow_id"],
    )
except ImportError:
    METRICS_AVAILABLE = False

# OpenTelemetry tracing (optional)
tracer: Any = None
try:
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__, "2.0.0")
    TRACING_AVAILABLE = True
except (ImportError, TypeError):
    TRACING_AVAILABLE = False


configure_logging()
logger = structured_logger


def _begrens(waarde: object, *, standaard: int, onder: int, boven: int) -> int:
    """Een instelling uit de workflowdefinitie binnen vaste grenzen; onleesbaar valt terug op de standaard.

    `max_retries` en het uitstel komen uit de definitie die een medewerker kan schrijven: ongeklemd houdt een grote waarde een
    werker lang bezet en kost elke poging van een agentstap taalmodelgeld (Gate 2 security).
    """
    if isinstance(waarde, bool) or not isinstance(waarde, int):
        return standaard
    return max(onder, min(waarde, boven))


class StapMislukt(RuntimeError):
    """Een stap kon zijn werk niet doen (bijv. een tool die `success: False` meldt). De uitvoering faalt dan.

    `tijdelijk` zegt of een nieuwe poging zin heeft (een dienst die te druk is); standaard is een mislukte stap
    inhoudelijk en wordt hij niet opnieuw geprobeerd (zie `foutsoort`).
    """

    def __init__(self, bericht: str = "", *, tijdelijk: bool = False) -> None:
        super().__init__(bericht)
        self.tijdelijk = tijdelijk


def _taken_als_woordenboek(taken: object) -> TasksDict:
    """`{taak: instellingen}`, ook als de definitie als LIJST is opgeslagen (ADR-036 OP-13).

    De engine werkt met een woordenboek. Een definitie komt er op twee manieren als lijst in: een leeg woordenboek
    dat `C7Workflow.spec_json` met `or []` tot een lijst maakte, en de lijstvorm van de workflowbuilder en
    `workflow_service` (`[{id, type, data}]`). Gemeten 2026-10-22: `'list' object has no attribute 'items'` in een
    echte worker, op elke uitvoering. Bij een node wint de sleutel van de node zelf van dezelfde sleutel in `data`;
    welke sleutels een stap in `data` nodig heeft, bepaalt de builder (niet hier).
    """
    if isinstance(taken, dict):
        return taken
    if not isinstance(taken, list):
        raise ValueError(f"De taken van de workflowdefinitie zijn geen woordenboek of lijst: {taken!r}")
    resultaat: TasksDict = {}
    for node in taken:
        if not isinstance(node, dict) or "id" not in node:
            raise ValueError(f"Een taak in de workflowdefinitie heeft geen id: {node!r}")
        if str(node["id"]) in resultaat:
            raise ValueError(f"Dubbele taak-id in de workflowdefinitie: {node['id']!r}")
        data = node.get("data")
        instellingen = dict(data) if isinstance(data, dict) else {}
        # Het staptype: een expliciet type van de node zelf of uit `data`, mits het een staptype is. De
        # weergavetypen van het canvas (`custom`, `activepieces`) zijn dat niet.
        expliciet = next(
            (
                t
                for t in (node.get("type"), instellingen.get("type"))
                if isinstance(t, str) and t in _STAPTYPEN
            ),
            None,
        )
        instellingen.update({k: v for k, v in node.items() if k != "data"})
        _normaliseer_stap(instellingen, expliciet)
        resultaat[str(node["id"])] = instellingen
    return resultaat


#: De staptypen die de engine uitvoert (`execute_task`).
_STAPTYPEN = ("llm", "tool", "agent")


def _normaliseer_stap(instellingen: TaskConfigDict, expliciet: str | None) -> None:
    """Zet een node uit de builder om naar de sleutels die `execute_task` leest.

    De bron voor het staptype, in deze volgorde (ADR-036 OP-13, gemeten met `WorkflowBuilder.tsx::handleSave`, dat
    alleen `{id, name, agent_id, config}` stuurt):
    1. een expliciet `type` van de stap (`llm`, `tool`, `agent`);
    2. afgeleid: `tool_name` -> `tool`; `agent_id` -> `agent`; `prompt` -> `llm`;
    3. anders blijft het weergavetype staan en faalt de stap zichtbaar met `Unknown task type`, in plaats van stil een
       taalmodelstap met een lege prompt te worden (de standaard van `execute_task`).
    Canvas-namen (`agentId`, `toolName`) worden de namen die de engine leest (`agent_id`, `tool_name`).
    """
    for canvas, engine in (("agentId", "agent_id"), ("toolName", "tool_name")):
        if canvas in instellingen and engine not in instellingen:
            instellingen[engine] = instellingen[canvas]
    if expliciet is not None:
        instellingen["type"] = expliciet
        return
    if instellingen.get("tool_name"):
        instellingen["type"] = "tool"
    elif instellingen.get("agent_id"):
        instellingen["type"] = "agent"
    elif instellingen.get("prompt"):
        instellingen["type"] = "llm"


def _afhankelijkheden_als_woordenboek(afhankelijkheden: object) -> DependenciesDict:
    """`{doel: [bronnen]}`, ook als de edges als lijst `[{source, target}]` zijn opgeslagen."""
    if isinstance(afhankelijkheden, dict):
        return afhankelijkheden
    if not isinstance(afhankelijkheden, list):
        raise ValueError(
            f"De afhankelijkheden van de workflowdefinitie zijn geen woordenboek of lijst: {afhankelijkheden!r}"
        )
    resultaat: DependenciesDict = {}
    for edge in afhankelijkheden:
        # De canvasvorm heet `source`/`target`, de workflowbuilder stuurt `from`/`to` (gemeten met `handleSave`).
        bron = edge.get("source", edge.get("from")) if isinstance(edge, dict) else None
        doel = edge.get("target", edge.get("to")) if isinstance(edge, dict) else None
        if bron is None or doel is None:
            raise ValueError(f"Een verbinding in de workflowdefinitie mist een begin of een eind: {edge!r}")
        resultaat.setdefault(str(doel), []).append(str(bron))
    return resultaat


@dataclass
class WorkflowSpec:
    """Parsed workflow specification (DAG)"""

    workflow_id: str
    version: int
    tasks: TasksDict
    dependencies: DependenciesDict
    timeout_seconds: int = 3600
    max_retries: int = 3
    retry_backoff_seconds: int = 5

    def to_nodes_and_edges(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Convert spec to nodes and edges format for validator"""
        nodes = [
            {"id": task_id, "type": config.get("type", "unknown")}
            for task_id, config in self.tasks.items()
        ]

        edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for task_id, deps in self.dependencies.items():
            for dep in deps:
                # Dependency means dep -> task_id
                edges.append({"source": dep, "target": task_id})

        return nodes, edges


from src.core.workflow.validator import WorkflowValidationError, topological_sort, validate_topology


class DAGValidator:
    """Validates workflow DAGs for cycles and topology issues"""

    @staticmethod
    def validate_dag(workflow_spec: WorkflowSpec) -> tuple[bool, str | None]:
        """
        Validate a workflow DAG for cycles and topology issues.

        Args:
            workflow_spec: The workflow specification to validate

        Returns: Tuple[Any, ...] of (is_valid, error_message)  # TODO(TYPE): replace Any with concrete type
            - is_valid: True if DAG is valid, False otherwise
            - error_message: None if valid, error description if invalid
        """
        try:
            nodes, edges = workflow_spec.to_nodes_and_edges()
            validate_topology(nodes, edges)
            return True, None
        except WorkflowValidationError as e:
            return False, str(e)


class ProductionWorkflowEngine(IWorkflowEngine):
    """
    Production workflow engine with dependency injection

    This is the MAIN implementation that orchestrates workflow execution.
    The execute_task() method is the KEY seam for testing.

    P5 Update: Supports Unit of Work pattern for proper transaction management.
    - Production: Use UnitOfWork for explicit commit control
    - Tests: Use TestUnitOfWork for auto-rollback isolation
    - Legacy: Still accepts db_session for backwards compatibility
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        tool_broker: IToolBroker,
        agent_runtime: IAgentRuntime,
        state_machine: IStateMachine | None = None,
        db_session: AsyncSession | None = None,  # Legacy support
    ) -> None:
        """
        Initialize engine with injected dependencies

        Args:
            llm_provider: LLM provider (Production or Fake)
            tool_broker: Tool broker (Production or Fake)
            agent_runtime: Agent runtime (Production or Fake)
            state_machine: State machine for validation (defaults to WorkflowStateMachine)
            db_session: DEPRECATED - Use UnitOfWork pattern instead.
                        Kept for backwards compatibility.

        Note: For new code, pass session via method parameters using UnitOfWork:
            async with TestUnitOfWork(session) as uow:
                await engine.create_workflow(uow, ...)
        """
        self._legacy_session = db_session  # For backwards compatibility
        self.llm_provider = llm_provider
        self.tool_broker = tool_broker
        self.agent_runtime = agent_runtime
        self.state_machine = state_machine or WorkflowStateMachine()

        logger.info(
            f"Initialized ProductionWorkflowEngine with providers: "
            f"LLM={type(llm_provider).__name__}, "
            f"Tool={type(tool_broker).__name__}, "
            f"Agent={type(agent_runtime).__name__}"
        )

    @property
    def db(self) -> AsyncSession:
        """
        Legacy property for backwards compatibility with internal methods.
        Prefer using _get_session(uow) for new code.

        Raises:
            ValueError: If no legacy session is available
        """
        if self._legacy_session is None:
            raise ValueError(
                "No database session available. Either pass UnitOfWork to method "
                "or provide db_session in constructor."
            )
        return self._legacy_session

    def _get_session(self, uow: IUnitOfWork | None = None) -> AsyncSession:
        """
        Get database session from UnitOfWork or legacy session

        Args:
            uow: Optional UnitOfWork (preferred)

        Returns:
            AsyncSession for database operations

        Raises:
            ValueError: If neither uow nor legacy session is available
        """
        if uow is not None:
            return cast(AsyncSession, uow.session)
        if self._legacy_session is not None:
            return self._legacy_session
        raise ValueError(
            "No database session available. Either pass UnitOfWork to method "
            "or provide db_session in constructor."
        )

    async def create_workflow(
        self,
        workflow_id: str,
        spec_json: WorkflowSpecDict,
        version: int = 1,
        tenant_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        uow: IUnitOfWork | None = None,
    ) -> int:
        """
        Create a new workflow definition

        Args:
            workflow_id: Unique workflow identifier
            spec_json: Workflow specification as JSON dict
            version: Workflow version (default 1)
            tenant_id: Optional tenant identifier for multi-tenancy
            name: Optional human-readable name
            description: Optional description
            uow: Optional Unit of Work for transaction management.
                 If provided, caller controls commit timing.
                 If None, uses legacy self.db with auto-commit.

        Returns: Database ID of created workflow
        """
        # Parse and validate spec
        spec = self._parse_spec(workflow_id, version, spec_json)

        try:
            nodes, edges = spec.to_nodes_and_edges()
            validate_topology(nodes, edges)
        except WorkflowValidationError as e:
            raise ValueError(f"Invalid workflow DAG: {e}")

        # Get session from UoW or legacy db
        session = self._get_session(uow)

        # Create workflow record
        workflow = Workflow(
            workflow_id=workflow_id,
            version=version,
            spec_json=spec_json,
            tenant_id=tenant_id,
            name=name or workflow_id,  # Default to workflow_id if name not provided
            description=description,
            workflow_type="standard",
            trigger_type="manual",
        )

        session.add(workflow)

        # Only auto-commit if using legacy mode (no UoW)
        if uow is None:
            await session.commit()
            await session.refresh(workflow)
        else:
            # With UoW, flush to get ID but don't commit
            await session.flush()

        logger.info(f"Created workflow {workflow_id} v{version} (ID: {workflow.id})")
        return int(workflow.id)

    async def start_execution(
        self,
        workflow_id: str,
        input_data: ExecutionContextDict,
        tenant_id: str | None = None,
        version: int | None = None,
        uow: IUnitOfWork | None = None,
    ) -> str:
        """
        Start a new workflow execution

        Args:
            workflow_id: Workflow to execute
            input_data: Input data for workflow
            tenant_id: Optional tenant identifier
            version: Optional specific version (default: latest)
            uow: Optional Unit of Work for transaction management.
                 If provided, caller controls commit timing.

        Returns: execution_id (UUID string)
        """
        # Get session from UoW or legacy db
        session = self._get_session(uow)

        # Get workflow (latest version if not specified)
        query = select(Workflow).where(Workflow.workflow_id == workflow_id)

        if tenant_id:
            query = query.where(Workflow.tenant_id == tenant_id)

        if version:
            query = query.where(Workflow.version == version)
        else:
            query = query.where(Workflow.is_active).order_by(Workflow.version.desc())

        result = await session.execute(query)
        workflow = result.scalar_one_or_none()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Create execution record
        execution_id = str(uuid.uuid4())

        execution = WorkflowExecution(
            id=execution_id,
            execution_id=execution_id,
            workflow_id=workflow.id,
            status=WorkflowStatus.PENDING,
            input_json=input_data,
            tenant_id=tenant_id,
        )

        session.add(execution)

        # Log event
        event = ExecutionEvent(
            id=str(uuid.uuid4()),
            execution=execution,
            tenant_id=tenant_id,
            event_type="workflow_started",
            payload_json={"workflow_id": workflow_id, "version": workflow.version},
        )
        session.add(event)

        # Only auto-commit if using legacy mode (no UoW)
        if uow is None:
            await session.commit()
        else:
            await session.flush()

        if METRICS_AVAILABLE:
            workflow_active_executions.labels(
                tenant_id=tenant_id or "default", workflow_id=workflow_id
            ).inc()

        logger.info(f"Started execution {execution_id} for workflow {workflow_id}")
        return execution_id

    async def execute_workflow(
        self,
        execution_id: str,
        uow: IUnitOfWork | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute entire workflow (orchestration logic)

        This is typically called by a background worker.

        Args:
            execution_id: UUID of execution to run
            uow: Optional Unit of Work for transaction management.
                 Note: This method has many internal commits for progress tracking.
                 UoW is primarily for test isolation via savepoints.

        Returns: final execution summary dict
        """
        span = tracer.start_span("execute_workflow") if TRACING_AVAILABLE else None
        start_time = time.time()

        try:
            # Load execution with workflow
            execution = await self._get_execution(execution_id)
            workflow = execution.workflow
            tenant_id = execution.tenant_id

            # NOODSTOP PER KLANT (ADR-036 OP-03): geen workflow start voor een stilgezette klant.
            # De uitvoering eindigt hier als mislukt, met de Nederlandse reden in het record; elke
            # taak controleert bovendien zelf (`execute_task`), zodat een stop MIDDEN in een
            # workflow de eerstvolgende taak tegenhoudt.
            await eis_klant_actief(tenant_id)

            # Parse spec
            spec = self._parse_spec(workflow.workflow_id, workflow.version, workflow.spec_json)

            if not spec.tasks:
                raise ValueError("De workflow heeft geen stappen; er valt niets uit te voeren.")

            # Validate DAG
            nodes, edges = spec.to_nodes_and_edges()
            try:
                validate_topology(nodes, edges)
            except WorkflowValidationError as e:
                await self._fail_execution(execution, f"Invalid DAG: {e}")
                raise ValueError(f"Invalid DAG: {e}")

            # Update status to RUNNING. Een HERVATTE uitvoering (na een noodstop of storing, zie de
            # `except KlantStilgezet` hieronder) staat al op RUNNING; de toestandsmachine kent geen
            # RUNNING -> RUNNING, dus alleen een verse uitvoering gaat hier van PENDING naar RUNNING.
            if execution.status == WorkflowStatus.PENDING:
                await self._update_execution_status(execution, WorkflowStatus.RUNNING)

            # Get topological order
            task_order = topological_sort(nodes, edges)
            logger.info(f"Execution {execution_id}: Task order = {task_order}")

            # Initialize task records
            await self._initialize_tasks(execution, spec, task_order)

            # Execute tasks in order
            context = execution.input_json.copy()

            for task_ref in task_order:
                # Check if task already completed (idempotency)
                task_record = await self._get_task(execution.id, task_ref)

                if task_record.status == TaskStatus.SUCCEEDED:
                    logger.info(f"Task {task_ref} already succeeded, skipping")
                    context[task_ref] = task_record.result_json
                    continue

                # Check dependencies
                deps = spec.dependencies.get(task_ref, [])
                deps_ready = await self._check_dependencies(execution.id, deps)

                if not deps_ready:
                    await self._update_task_status(task_record, TaskStatus.SKIPPED)
                    logger.warning(f"Task {task_ref} skipped due to failed dependencies")
                    continue

                # Execute task with retry
                result = await self._execute_task_with_retry(
                    execution_id,
                    task_ref,
                    context,
                    spec.max_retries,
                    spec.retry_backoff_seconds,
                )

                # Update context with result
                context[task_ref] = result.output

                # Check for timeout
                elapsed = time.time() - start_time
                if elapsed > spec.timeout_seconds:
                    await self._timeout_execution(execution)
                    raise TimeoutError(f"Workflow timeout after {elapsed:.1f}s")

            # All tasks completed successfully
            await self._complete_execution(execution, context)

            duration = time.time() - start_time

            if METRICS_AVAILABLE:
                workflow_executions_total.labels(
                    tenant_id=tenant_id or "default",
                    workflow_id=workflow.workflow_id,
                    status="succeeded",
                ).inc()
                workflow_duration_seconds.labels(
                    tenant_id=tenant_id or "default", workflow_id=workflow.workflow_id
                ).observe(duration)
                workflow_active_executions.labels(
                    tenant_id=tenant_id or "default", workflow_id=workflow.workflow_id
                ).dec()

            logger.info(f"Execution {execution_id} completed in {duration:.1f}s")

            return {
                "execution_id": execution_id,
                "status": "succeeded",
                "duration_seconds": duration,
                "output": context,
            }

        except KlantStilgezet as stop:
            # NOODSTOP PER KLANT (ADR-036 OP-03, Gate 2 ronde 2 punt 4): een stop of een
            # onleesbare stand (`stop.onbekend`) is GEEN mislukking van de workflow en wordt dus
            # niet naar het eindstation FAILED gezet (de toestandsmachine kent daar geen weg
            # terug). Bij een stop aan het begin blijft de uitvoering PENDING; midden in de run
            # blijft hij RUNNING met de voltooide taken als SUCCEEDED. In beide gevallen biedt een
            # worker hem opnieuw aan na het opheffen en hervat `execute_workflow` (voltooide taken
            # worden overgeslagen). De prijs: een uitvoering die niemand hervat blijft RUNNING.
            logger.warning(
                "Execution %s niet voltooid: noodstop (onbekend=%s); blijft hervatbaar",
                execution_id,
                stop.onbekend,
            )
            raise

        except Exception as e:
            logger.exception(f"Execution {execution_id} failed: {e}")

            # Is de databasetransactie zelf omgevallen (NOT NULL, deadlock), dan kan de uitvoering zonder rollback niet
            # eens meer worden geladen en blijft hij op `running` staan (Gate 2 ronde 1, M2).
            await self.db.rollback()
            execution = await self._get_execution(execution_id)
            await self._fail_execution(execution, str(e))
            # De uitvoering staat nu op `failed` (eindstation). Een werker die hem opnieuw aanbiedt kan niets meer
            # doen en zou alleen `failed -> running` weigeren; het merk voorkomt die nieuwe poging (zie `foutsoort`).
            e.uitvoering_beeindigd = True  # type: ignore[attr-defined]

            if METRICS_AVAILABLE:
                workflow_executions_total.labels(
                    tenant_id=execution.tenant_id or "default",
                    workflow_id=execution.workflow.workflow_id,
                    status="failed",
                ).inc()
                workflow_active_executions.labels(
                    tenant_id=execution.tenant_id or "default",
                    workflow_id=execution.workflow.workflow_id,
                ).dec()

            raise

        finally:
            if span:
                span.end()

    async def execute_task(self, execution_id: str, task_ref: str) -> TaskExecutionResult:
        """
        Execute a single task (KEY SEAM FOR TESTING)

        This method is called by workers and is the injection point for testing.
        Production: Uses injected ProductionLLMProvider/ProductionAgentRuntime
        Tests: Uses injected FakeLLMProvider/FakeAgentRuntime

        Returns: TaskExecutionResult with output and metadata
        """
        span = tracer.start_span("execute_task") if TRACING_AVAILABLE else None
        start_time = time.time()

        # NOODSTOP PER KLANT (ADR-036 OP-03): DE deur voor elke taak (llm, tool en agent), ook als een
        # worker de taak los start. BUITEN de `try`: een weigering is geen mislukte poging en moet
        # niet door de hertelling hieronder heen. De taak blijft dan onaangeroerd; `execute_workflow`
        # vangt de weigering en laat de uitvoering hervatbaar (niet FAILED), zodat de taak na het
        # opheffen van de stop opnieuw wordt aangeboden.
        await eis_klant_actief((await self._get_execution(execution_id)).tenant_id)

        try:
            # Load execution and task
            execution = await self._get_execution(execution_id)
            task_record = await self._get_task(execution.id, task_ref)
            workflow = execution.workflow
            spec = self._parse_spec(workflow.workflow_id, workflow.version, workflow.spec_json)

            task_config = spec.tasks[task_ref]
            task_type = task_config.get("type", "llm")

            # Update task status to RUNNING
            await self._update_task_status(task_record, TaskStatus.RUNNING)

            # Build context from previous task results
            context = execution.input_json.copy()
            prev_tasks = await self._get_completed_tasks(execution.id)
            for prev_task in prev_tasks:
                context[prev_task.task_ref] = prev_task.result_json

            # Execute based on task type
            if task_type == "llm":
                output = await self._execute_llm_task(
                    task_config, context, tenant_id=execution.tenant_id
                )
            elif task_type == "tool":
                output = await self._execute_tool_task(
                    task_config,
                    context,
                    tenant_id=execution.tenant_id,
                    starter=execution.initiated_by,
                )
            elif task_type == "agent":
                output = await self._execute_agent_task(
                    task_config,
                    context,
                    tenant_id=execution.tenant_id,
                    starter=execution.initiated_by,
                )
            else:
                raise ValueError(f"Unknown task type: {task_type}")

            # Save result
            duration = time.time() - start_time
            # Een tool geeft echte Python-waarden terug (UUID, datum); de kolommen zijn JSON. Zonder dit slaagde
            # `create_task` (de taak bestond) en eindigde de uitvoering toch op `failed` (gemeten 2026-10-22), en
            # hetzelfde bij de uitkomst van de hele uitvoering, die uit `result.output` wordt opgebouwd.
            output = json.loads(json.dumps(output, default=str))
            task_record.result_json = output
            task_record.finished_at = datetime.now(timezone.utc)
            execution.tasks_completed = (execution.tasks_completed or 0) + 1

            await self._update_task_status(task_record, TaskStatus.SUCCEEDED)
            await self.db.commit()

            if METRICS_AVAILABLE:
                workflow_tasks_total.labels(
                    tenant_id=execution.tenant_id or "default",
                    workflow_id=workflow.workflow_id,
                    task_ref=task_ref,
                    status="succeeded",
                ).inc()

            logger.info(f"Task {task_ref} succeeded in {duration:.1f}s")

            return TaskExecutionResult(
                task_id=task_ref,
                success=True,
                output=output,
                execution_time=duration,
                error=None,
            )

        except Exception as e:
            logger.exception(f"Task {task_ref} failed: {e}")

            execution = await self._get_execution(execution_id)
            task_record = await self._get_task(execution.id, task_ref)
            task_record.error_json = {"type": type(e).__name__, "message": str(e)}
            await self._update_task_status(task_record, TaskStatus.FAILED)
            await self.db.commit()

            if METRICS_AVAILABLE:
                workflow_tasks_total.labels(
                    tenant_id=execution.tenant_id or "default",
                    workflow_id=execution.workflow.workflow_id,
                    task_ref=task_ref,
                    status="failed",
                ).inc()

            return TaskExecutionResult(
                task_id=task_ref,
                success=False,
                output={},
                execution_time=time.time() - start_time,
                error=str(e),
                tijdelijk=is_tijdelijke_fout(e),
            )

        finally:
            if span:
                span.end()

    async def register_workflow(
        self,
        workflow_id: str,
        spec_json: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: str | None = None,
    ) -> str:
        """Alias for create_workflow (interface compatibility)"""
        workflow_db_id = await self.create_workflow(
            workflow_id, spec_json, version=1, tenant_id=tenant_id
        )
        return str(workflow_db_id)

    async def validate_workflow(self, workflow_id: str) -> tuple[bool, str | None]:
        """Validate workflow DAG"""
        query = (
            select(Workflow)
            .where(Workflow.workflow_id == workflow_id)
            .order_by(Workflow.version.desc())
        )
        result = await self.db.execute(query)
        workflow = result.scalar_one_or_none()

        if not workflow:
            return False, f"Workflow {workflow_id} not found"

        spec = self._parse_spec(workflow.workflow_id, workflow.version, workflow.spec_json)
        try:
            nodes, edges = spec.to_nodes_and_edges()
            validate_topology(nodes, edges)
            return True, None
        except WorkflowValidationError as e:
            return False, str(e)

    async def get_execution_status(
        self, execution_id: str, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get execution status summary"""
        execution = await self._get_execution(execution_id, tenant_id=tenant_id)
        workflow = execution.workflow

        # Get task statuses
        query = select(ExecutionTask).where(ExecutionTask.execution_id == execution.id)
        result = await self.db.execute(query)
        tasks = result.scalars().all()

        task_summary: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for task in tasks:
            task_summary[task.task_ref] = {
                "status": task.status.value,
                "retries": task.retries,
                "completed_at": task.finished_at.isoformat() if task.finished_at else None,
                "error": (task.error_json or {}).get("message"),
            }

        return {
            "execution_id": execution_id,
            "workflow_id": workflow.workflow_id,
            "version": workflow.version,
            "status": execution.status.value,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.finished_at.isoformat() if execution.finished_at else None,
            "tasks": task_summary,
            "output": execution.output_json,
        }

    async def get_execution(self, execution_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Get execution by ID - Required by IWorkflowEngine interface.

        Args:
            execution_id: The unique execution identifier

        Returns: Dict[str, Any] with execution details or None if not found  # TODO(TYPE): replace Any with concrete type
        """
        try:
            execution = await self._get_execution(execution_id)
            workflow = execution.workflow

            return {
                "execution_id": execution_id,
                "workflow_id": workflow.workflow_id,
                "version": workflow.version,
                "status": execution.status.value,
                "input": execution.input_json,
                "output": execution.output_json,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": (
                    execution.finished_at.isoformat() if execution.finished_at else None
                ),
                "tenant_id": execution.tenant_id,
            }
        except ValueError:
            return None

    async def list_executions(
        self,
        workflow_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """List executions with filters"""
        query = select(WorkflowExecution).options(selectinload(WorkflowExecution.workflow))

        if tenant_id:
            query = query.where(WorkflowExecution.tenant_id == tenant_id)

        if status:
            query = query.where(WorkflowExecution.status == WorkflowStatus(status))

        if workflow_id:
            # Join with workflows table
            query = query.join(Workflow).where(Workflow.workflow_id == workflow_id)

        query = query.order_by(WorkflowExecution.started_at.desc()).limit(limit)

        result = await self.db.execute(query)
        executions = result.scalars().all()

        return [
            {
                "execution_id": exec.execution_id,
                "workflow_id": exec.workflow.workflow_id,
                "status": exec.status.value,
                "started_at": exec.started_at.isoformat() if exec.started_at else None,
                "completed_at": exec.finished_at.isoformat() if exec.finished_at else None,
            }
            for exec in executions
        ]

    async def cancel_execution(self, execution_id: str, tenant_id: str | None = None) -> bool:
        """Cancel running execution"""
        execution = await self._get_execution(execution_id, tenant_id=tenant_id)

        if execution.status not in [WorkflowStatus.PENDING, WorkflowStatus.RUNNING]:
            return False

        await self._update_execution_status(execution, WorkflowStatus.CANCELLED)
        return True

    async def save_snapshot(
        self,
        workflow_id: str,
        content: bytes,
        tenant_id: str | None = None,
        created_by: int | None = None,
        uow: IUnitOfWork | None = None,
    ) -> int:
        """
        Save a binary Yjs snapshot for a workflow

        Args:
            workflow_id: Target workflow ID
            content: Binary content (Yjs state)
            tenant_id: Tenant ID for isolation

        Returns: Snapshot database ID
        """
        session = self._get_session(uow)

        # Verify workflow exists and belongs to tenant
        query = select(Workflow).where(Workflow.workflow_id == workflow_id)
        if tenant_id:
            query = query.where(Workflow.tenant_id == tenant_id)

        result = await session.execute(query)
        workflow = result.scalar_one_or_none()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Create snapshot
        snapshot = WorkflowSnapshot(
            workflow_id=workflow.id,  # Link to internal DB ID
            content=content,
            size_bytes=len(content),
            tenant_id=workflow.tenant_id,  # Use workflow's tenant ID
            created_by=created_by,
        )

        session.add(snapshot)

        if uow is None:
            await session.commit()
            await session.refresh(snapshot)
        else:
            await session.flush()

        logger.info(f"Saved snapshot for workflow {workflow_id} ({len(content)} bytes)")
        return snapshot.id

    async def get_latest_snapshot(
        self,
        workflow_id: str,
        tenant_id: str | None = None,
    ) -> bytes | None:
        """
        Get latest snapshot content for a workflow
        """
        session = self._get_session()

        # We need to join with Workflow to check tenant_id via workflow_id properly
        # OR verify workflow first. Usually checking workflow exists is safer.
        query = select(Workflow).where(Workflow.workflow_id == workflow_id)
        if tenant_id:
            query = query.where(Workflow.tenant_id == tenant_id)

        result = await session.execute(query)
        workflow = result.scalar_one_or_none()

        if not workflow:
            # If workflow doesn't exist, no snapshot exists
            return None

        # Get latest snapshot
        stmt = (
            select(WorkflowSnapshot)
            .where(WorkflowSnapshot.workflow_id == workflow.id)
            .order_by(WorkflowSnapshot.created_at.desc())
            .limit(1)
        )

        result = await session.execute(stmt)
        snapshot = result.scalar_one_or_none()

        return snapshot.content if snapshot else None

    # Private helper methods

    def _parse_spec(
        self, workflow_id: str, version: int, spec_json: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> WorkflowSpec:
        """Parse workflow spec JSON into WorkflowSpec dataclass"""
        return WorkflowSpec(
            workflow_id=workflow_id,
            version=version,
            tasks=_taken_als_woordenboek(spec_json.get("tasks", {})),
            dependencies=_afhankelijkheden_als_woordenboek(spec_json.get("dependencies", {})),
            timeout_seconds=spec_json.get("timeout_seconds", 3600),
            max_retries=_begrens(spec_json.get("max_retries"), standaard=3, onder=0, boven=5),
            retry_backoff_seconds=_begrens(
                spec_json.get("retry_backoff_seconds"), standaard=5, onder=0, boven=60
            ),
        )

    async def _get_execution(
        self, execution_id: str, tenant_id: str | None = None
    ) -> WorkflowExecution:
        """Get execution with workflow loaded (with optional tenant isolation)

        Args:
            execution_id: Execution UUID
            tenant_id: Optional tenant ID for isolation validation

        Returns: WorkflowExecution object

        Raises: ValueError if execution not found OR tenant mismatch (security)
        """
        query = (
            select(WorkflowExecution)
            .where(WorkflowExecution.execution_id == execution_id)
            .options(selectinload(WorkflowExecution.workflow))
        )

        # If tenant_id provided, add security filter (prevent cross-tenant access)
        if tenant_id is not None:
            query = query.where(WorkflowExecution.tenant_id == tenant_id)

        result = await self.db.execute(query)
        execution = result.scalar_one_or_none()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        # Security check: if tenant_id was specified, ensure it matches
        if tenant_id is not None and execution.tenant_id != tenant_id:
            raise ValueError(f"Execution {execution_id} does not belong to tenant {tenant_id}")

        return execution

    async def _get_task(self, execution_db_id: str, task_ref: str) -> ExecutionTask:
        """Get task record"""
        query = select(ExecutionTask).where(
            and_(
                ExecutionTask.execution_id == execution_db_id,
                ExecutionTask.task_ref == task_ref,
            )
        )
        result = await self.db.execute(query)
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError(f"Task {task_ref} not found in execution {execution_db_id}")

        return task

    async def _get_completed_tasks(self, execution_db_id: str) -> list[ExecutionTask]:
        """Get all completed tasks for an execution"""
        query = select(ExecutionTask).where(
            and_(
                ExecutionTask.execution_id == execution_db_id,
                ExecutionTask.status == TaskStatus.SUCCEEDED,
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _initialize_tasks(
        self, execution: WorkflowExecution, spec: WorkflowSpec, task_order: list[str]
    ) -> None:
        """Create task records for all tasks in workflow; a restart does not create them twice"""
        bestaand = set(
            (
                await self.db.execute(
                    select(ExecutionTask.task_ref).where(ExecutionTask.execution_id == execution.id)
                )
            )
            .scalars()
            .all()
        )
        for task_ref in task_order:
            if task_ref in bestaand:
                continue
            # Get task type from spec (default to 'unknown' if not specified)
            task_config = spec.tasks.get(task_ref, {})
            task_type = task_config.get("type", "unknown")

            # `id` en `tenant_id` zijn verplicht (NOT NULL, geen standaardwaarde): zonder deze twee faalde elke
            # uitvoering bij het aanmaken van zijn taken (ADR-036 OP-13, gemeten 2026-10-22).
            task = ExecutionTask(
                id=str(uuid.uuid4()),
                execution_id=execution.id,
                tenant_id=execution.tenant_id,
                task_ref=task_ref,
                task_type=task_type,
                status=TaskStatus.PENDING,
            )
            self.db.add(task)

        await self.db.commit()
        logger.info(f"Initialized {len(task_order)} tasks for execution {execution.execution_id}")

    async def _check_dependencies(self, execution_db_id: str, dependencies: list[str]) -> bool:
        """Check if all dependencies succeeded"""
        if not dependencies:
            return True

        query = select(ExecutionTask).where(
            and_(
                ExecutionTask.execution_id == execution_db_id,
                ExecutionTask.task_ref.in_(dependencies),
            )
        )
        result = await self.db.execute(query)
        dep_tasks = result.scalars().all()

        return all(task.status == TaskStatus.SUCCEEDED for task in dep_tasks)

    async def _execute_task_with_retry(
        self,
        execution_id: str,
        task_ref: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        max_retries: int,
        backoff_seconds: int,
    ) -> TaskExecutionResult:
        """Execute task with exponential backoff retry"""
        execution = await self._get_execution(execution_id)
        task_record = await self._get_task(execution.id, task_ref)

        for attempt in range(max_retries + 1):
            result = await self.execute_task(execution_id, task_ref)

            if result.success:
                return result

            # Een inhoudelijke fout (een weigering, validatie, rechten) verandert niet door het nog eens te proberen en
            # een nieuwe poging van een agent- of taalmodelstap kost geld: alleen een tijdelijke fout krijgt er een.
            if result.tijdelijk and attempt < max_retries:
                # Exponential backoff
                delay = backoff_seconds * (2**attempt)
                logger.warning(
                    f"Task {task_ref} attempt {attempt + 1} failed, "
                    f"retrying in {delay}s: {result.error}"
                )

                task_record.retries = attempt + 1
                await self._update_task_status(task_record, TaskStatus.RETRYING)
                await self.db.commit()

                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Task {task_ref} failed after {attempt} retries (tijdelijk={result.tijdelijk})"
                )
                execution.tasks_failed = (execution.tasks_failed or 0) + 1
                await self.db.commit()
                raise RuntimeError(f"Stap {task_ref} is mislukt: {result.error}")

        raise RuntimeError("Unreachable code")

    async def _execute_llm_task(
        self,
        task_config: TaskConfigDict,
        context: ExecutionContextDict,
        tenant_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute LLM task using injected provider, voor de klant van de uitvoering (de modelkeuze van de klant)"""
        prompt = vul_in(task_config.get("prompt", ""), context)
        model = task_config.get("model", os.getenv("LLM_MODEL", "gemini-2.5-flash"))
        temperature = task_config.get("temperature", 0.7)

        result = await self.llm_provider.generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            tenant_id=tenant_id,
        )

        return result

    async def _execute_tool_task(
        self,
        task_config: TaskConfigDict,
        context: ExecutionContextDict,
        tenant_id: int | None = None,
        starter: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute tool task using injected broker, voor de klant en de starter van de uitvoering"""
        tool_name = task_config.get("tool_name") or ""
        parameters = {
            k: vul_in(v, context) if isinstance(v, str) else v
            for k, v in task_config.get("parameters", {}).items()
        }

        result = await self.tool_broker.execute_tool(
            tool_name=tool_name,
            parameters=parameters,
            tenant_id=tenant_id,
            starter=starter,
        )
        if isinstance(result, dict) and result.get("success") is False:
            # Een toolstap die zegt dat hij mislukt is, IS mislukt. Zonder deze regel ging de uitvoering door en
            # eindigde hij op `succeeded` met een fout in de uitvoer (gemeten 2026-10-22).
            raise StapMislukt(str(result.get("error") or "de tool gaf geen uitkomst"))

        return result

    async def _execute_agent_task(
        self,
        task_config: TaskConfigDict,
        context: ExecutionContextDict,
        tenant_id: int | str | None = None,
        starter: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute agent task using injected runtime, voor de klant en de starter van de uitvoering.

        De GEKOZEN agent draait (`run_agentstap`, geen router-keuze) en elke tool van die agent wordt getoetst op het
        recht van de starter, zoals bij een toolstap.
        """
        agent_id = task_config.get("agent_id") or ""
        instruction = vul_in(task_config.get("instruction", ""), context)

        # De context bevat `input_json`, en die is van de beller. De agent leest de klant uit
        # `metadata["tenant_id"]`; die sleutel komt dus ALTIJD van de uitvoering, nooit uit de invoer.
        agent_context = {**context, "tenant_id": tenant_id}

        result = await self.agent_runtime.run_agentstap(
            agent_id=agent_id,
            instruction=instruction,
            context=agent_context,
            starter=starter,
        )
        if isinstance(result, dict) and result.get("success") is False:
            # Zelfde regel als bij een toolstap: een agent die zegt dat hij mislukte, IS mislukt (gemeten 2026-10-22:
            # `{"success": false, "output": {"error": "Agent ... not found in process"}}` en toch `succeeded`).
            uitvoer = result.get("output")
            reden = uitvoer.get("error") if isinstance(uitvoer, dict) else None
            raise StapMislukt(
                str(reden or result.get("error") or "de agent gaf geen uitkomst"),
                tijdelijk=result.get("tijdelijk") is True,
            )

        return result

    async def _update_execution_status(
        self, execution: WorkflowExecution, new_status: WorkflowStatus
    ) -> None:
        """Update execution status with state machine validation"""
        self.state_machine.validate_transition(execution.status.value, new_status.value, "workflow")

        old_status = execution.status
        execution.status = new_status

        if new_status == WorkflowStatus.RUNNING and execution.started_at is None:
            execution.started_at = datetime.now(timezone.utc)
        if new_status in [
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.TIMEOUT,
        ]:
            execution.finished_at = datetime.now(timezone.utc)
        if new_status == WorkflowStatus.FAILED and isinstance(execution.output_json, dict):
            execution.error_message = str(execution.output_json.get("error") or "")

        event = ExecutionEvent(
            id=str(uuid.uuid4()),
            execution=execution,
            tenant_id=execution.tenant_id,
            event_type=EventType.STATUS_CHANGED,
            payload_json={"from": old_status.value, "to": new_status.value},
        )
        self.db.add(event)
        await self.db.commit()

        logger.info(f"Execution {execution.execution_id}: {old_status.value} -> {new_status.value}")

    async def _update_task_status(self, task: ExecutionTask, new_status: TaskStatus) -> None:
        """Update task status with state machine validation"""
        self.state_machine.validate_transition(task.status.value, new_status.value, "task")

        old_status = task.status
        task.status = new_status

        if new_status == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        if new_status in [TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.TIMEOUT]:
            task.finished_at = datetime.now(timezone.utc)

        await self.db.commit()

        logger.debug(f"Task {task.task_ref}: {old_status.value} -> {new_status.value}")

    async def _complete_execution(
        self, execution: WorkflowExecution, output: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Mark execution as succeeded"""
        execution.output_json = output
        await self._update_execution_status(execution, WorkflowStatus.SUCCEEDED)

    async def _fail_execution(self, execution: WorkflowExecution, error: str) -> None:
        """Mark execution as failed"""
        if execution.status in (
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.TIMEOUT,
        ):
            # Al terminaal: de EERSTE reden blijft staan. De DAG-validatie faalt de uitvoering zelf en gooit daarna een
            # fout die de buitenste `except` opnieuw laat falen; zonder deze regel kwam daar `failed -> failed` bovenop
            # de echte fout (Gate 2 ronde 1, H1).
            logger.info(f"Execution {execution.execution_id} is al {execution.status.value}; geen tweede fout")
            return
        execution.output_json = {"error": error}
        if execution.status == WorkflowStatus.PENDING:
            # De toestandsmachine kent geen `pending -> failed`. Een uitvoering die faalt voordat hij startte (een
            # ongeldige definitie) liet daardoor een TWEEDE fout vallen, verborg de echte reden en bleef voor altijd op
            # `pending` staan (ADR-036 OP-13, gemeten 2026-10-22). Eerst starten, dan falen: beide stappen zijn legaal.
            await self._update_execution_status(execution, WorkflowStatus.RUNNING)
        await self._update_execution_status(execution, WorkflowStatus.FAILED)

    async def _timeout_execution(self, execution: WorkflowExecution) -> None:
        """Mark execution as timed out"""
        await self._update_execution_status(execution, WorkflowStatus.TIMEOUT)
