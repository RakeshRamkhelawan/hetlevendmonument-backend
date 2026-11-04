"""
C.7 Background Worker for Workflow Execution
============================================

Dramatiq-based worker that processes workflow execution tasks.

Key Features:
- Async task processing with Dramatiq + Redis
- Automatic retries with exponential backoff
- Graceful shutdown handling
- Production provider injection (LLM, Agent, Tool Broker)
- Connection pooling for PostgreSQL

Usage:
    # Start worker
    dramatiq src.workers.workflow_worker -p 4 -t 4

    # Send task to queue
    from src.workers.workflow_worker import execute_workflow_task
    execute_workflow_task.send(execution_id="abc-123")
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, TypeAlias, cast
from collections.abc import AsyncIterator, Awaitable, Callable

# De broker, de actor-decorator en de middleware wonen in `src/core/tasks/dramatiq_broker.py` (ADR-036 OP-13):
# deze module zet geen procesbrede broker meer. Hier opnieuw geexporteerd voor wie ze van de worker haalt.
from src.core.noodstop import model_deur  # noqa: F401  (opstartpunt: meldt de noodstopcontrole van de modeldeur aan)
from src.core.tasks.dramatiq_broker import (  # noqa: F401
    _DRAMATIQ_AVAILABLE as _DRAMATIQ_AVAILABLE,
    AsyncIO as AsyncIO,
    DatabaseInitMiddleware as DatabaseInitMiddleware,
    Middleware as Middleware,
    RedisBroker as RedisBroker,
    dramatiq_module as dramatiq_module,
    workflow_actor as workflow_actor,
    workflow_broker as workflow_broker,
)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import C.7 engine and components
from src.core.database.bypass_session import adopt_tenant
from src.core.governance.governance_helper import apply_governance_check
from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.foutsoort import moet_opnieuw
from src.core.workflow.interfaces import IAgentRuntime, ILLMProvider, IToolBroker
from src.core.workflow.providers import (
    ProductionAgentRuntime,
    ProductionLLMProvider,
    ProductionToolBroker,
)
from src.core.workflow.state_machine import WorkflowStateMachine

logger = logging.getLogger(__name__)


def _sanitize_env_url(value: str | None) -> str:
    """Normalize env URL values to tolerate accidental inline comments in tests."""
    if not value:
        return ""
    return value.split(" #", 1)[0].strip()


# Type aliases
WorkflowTaskResult: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]
HealthStatus: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]

# ============================================================================
# Configuration
# ============================================================================

# FAIL-FAST: Crash if required environment variables are missing
# Environment variables required in ALL environments (no hardcoded defaults)
TESTING_MODE = os.getenv("TESTING") == "1"

# Get database URL (required in all environments)
_db_url = _sanitize_env_url(os.getenv("DATABASE_URL"))
if not _db_url:
    error_msg = (
        "DATABASE_URL environment variable is required. "
        "Set to a PostgreSQL connection string (e.g., postgresql+asyncpg://...)"
    )
    if TESTING_MODE:
        logger.warning(f"WARNING: {error_msg}")
    else:
        raise RuntimeError(f"CRITICAL: {error_msg}")
DATABASE_URL = _db_url

# Get Redis URL (required in all environments)
_redis_url = _sanitize_env_url(os.getenv("REDIS_URL"))
if not _redis_url:
    error_msg = (
        "REDIS_URL environment variable is required. "
        "Set to a Redis connection string (e.g., redis://...)"
    )
    if TESTING_MODE:
        logger.warning(f"WARNING: {error_msg}")
    else:
        raise RuntimeError(f"CRITICAL: {error_msg}")
REDIS_URL = _redis_url

# Optional configuration with sensible defaults
WORKFLOW_TIMEOUT_SECONDS = int(os.environ.get("WORKFLOW_TIMEOUT_SECONDS", "3600"))  # 1 hour default
WORKER_LOG_LEVEL = os.environ.get("WORKER_LOG_LEVEL", "INFO")
MAX_RETRIES = int(os.environ.get("MAX_WORKER_RETRIES", "3"))

# Lazy PostgreSQL engine (P0 fix: defer instantiation)
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_engine_kwargs() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    engine_kwargs: dict[str, Any] = {"echo": False}
    if not DATABASE_URL.startswith("sqlite"):
        engine_kwargs.update(
            {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
            }
        )
    return engine_kwargs


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(DATABASE_URL, **_get_engine_kwargs())
    return _engine


def get_async_session_maker() -> async_sessionmaker[AsyncSession]:
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _async_session_maker


if _DRAMATIQ_AVAILABLE:

    def get_redis_broker() -> Any:  # TODO(TYPE): replace Any with concrete type
        """De workflowbroker. Hij bestaat vanaf het importeren; deze functie hoeft niets meer te "binden".

        Blijft bestaan voor aanroepers die hem nog noemen (scheduler, `workflow_verzending`). Een `.send()` landt
        sinds ADR-036 OP-13 altijd op deze echte RedisBroker, ook zonder deze aanroep.
        """
        return workflow_broker

else:
    # Testing mode: no broker setup needed
    get_redis_broker = None  # type: ignore[assignment]


def __getattr__(name: str) -> Any:
    if name == "async_session_maker":
        return get_async_session_maker()
    if name == "engine":
        return get_engine()
    if name == "redis_broker":
        return get_redis_broker() if get_redis_broker is not None else None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============================================================================
# Production Providers (Integrate with Existing Infrastructure)
# ============================================================================


# `ProductionLLMProvider` en `ProductionToolBroker` waren HIER lokaal gedefinieerd, tegen een
# OUDERE versie van `interfaces.py` (`complete`/`embed` i.p.v. `generate`/`moderate`;
# `list_tools` i.p.v. `list_available_tools`). Beide dus ook een gegarandeerde TypeError bij
# elke echte aanroep, ontdekt bij het repareren van `ProductionAgentRuntime` hierboven (zie
# tests/unit/workers/test_provider_factory_agent_runtime_is_instantiable.py). Vervangen door
# de WEL volledige, actueel-interface-conforme implementaties uit core/workflow/providers.py
# (import bovenaan dit bestand).


# `ProductionAgentRuntime` was gedefinieerd HIER, lokaal, met alleen `__init__` en een
# ongebruikte `invoke_agent()` -- niet de vier abstracte methodes die `IAgentRuntime`
# vereist (`load_agent`, `execute_agent`, `run_agent`, `get_available_agents`). Omdat
# `ProviderFactory.set_providers()` nergens in `src/` wordt aangeroepen, instantieerde
# `create_agent_runtime()` deze kapotte klasse ONGEWIJZIGD bij elke echte aanroep en gaf
# gegarandeerd een TypeError -- gereproduceerd, niet vermoed (zie
# tests/unit/workers/test_provider_factory_agent_runtime_is_instantiable.py). De
# workflow-worker-service in docker-compose.prod.yml (restart: always) draait dit pad
# vanuit execute_workflow_task's hot path.
#
# Vervangen door de WEL volledige implementatie uit core/workflow/providers.py (import
# hierboven), die alle vier methodes heeft EN al agent_router-injectie ondersteunt --
# dezelfde SP-AGT-003-functionaliteit die voorheen alleen in de dode
# core/workflow/worker.py-module zat.


# ============================================================================
# Provider Factory (Dependency Injection)
# ============================================================================


class ProviderFactory:
    """
    Factory for creating providers (Production or Fake for testing)

    This enables testing by injecting FakeProviders instead of ProductionProviders.
    """

    _llm_provider_class: type[ILLMProvider] = ProductionLLMProvider
    _tool_broker_class: type[IToolBroker] = ProductionToolBroker
    _agent_runtime_class: type[IAgentRuntime] = ProductionAgentRuntime

    @classmethod
    def create_llm_provider(cls) -> ILLMProvider:
        """Create LLM provider (override for testing)"""
        return cls._llm_provider_class()

    @classmethod
    def create_tool_broker(cls) -> IToolBroker:
        """Create tool broker (override for testing)"""
        return cls._tool_broker_class()

    @classmethod
    def create_agent_runtime(
        cls,
        agent_router: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> IAgentRuntime:
        """Create agent runtime (override for testing).

        `agent_router` (SP-AGT-003): beide bestaande `IAgentRuntime`-implementaties
        (`ProductionAgentRuntime`, `FakeAgentRuntime` in `core/workflow/providers.py`)
        accepteren deze parameter al.
        """
        return cls._agent_runtime_class(agent_router=agent_router)  # type: ignore[call-arg]

    @classmethod
    def set_providers(
        cls,
        llm_class: type[ILLMProvider],
        tool_class: type[IToolBroker],
        agent_class: type[IAgentRuntime],
    ) -> None:
        """Override providers for testing"""
        cls._llm_provider_class = llm_class
        cls._tool_broker_class = tool_class
        cls._agent_runtime_class = agent_class


_SYSTEM_TENANT_ID = 1  # default if missing


class TenantOnbekend(RuntimeError):
    """De klant van een opdracht kon niet worden vastgesteld of niet worden bevestigd."""


@asynccontextmanager
async def neem_de_klant_van_de_opdracht_aan(
    session: AsyncSession, execution_id: str, geclaimde_tenant: int | None
) -> AsyncIterator[int]:
    """Stel de klant van deze workflow vast, neem hem aan, en bevestig hem (OP-153).

    Deze worker draait buiten elk verzoek, dus de ContextVar is leeg. Tot 2026-09-16
    loste hij dat op door de klant uit het uitvoeringsrecord te LEZEN:

        select(WorkflowExecution.tenant_id).where(WorkflowExecution.id == execution_id)
        tenant_id = gevonden if gevonden is not None else _SYSTEM_TENANT_ID

    (Dat stond ook nog op het verkeerde model: `WorkflowExecution.id` is een geheel getal in de tabel
    `workflow_executions`, terwijl de API en de engine in `c7_workflow_executions` werken, met de tekst-id in
    `execution_id`. Gemeten 2026-10-21: "operator does not exist: integer = character varying". Nu leest deze
    functie `C7WorkflowExecution.execution_id`, net als de routers en `engine.py`.)

    Die lezing werkt alleen omdat de applicatie vandaag als tabeleigenaar verbindt.
    `workflow_executions` heeft een afschermingsregel (gemeten 2026-09-16 op de
    ketendatabase: `relrowsecurity = t`, een policy). Na de omschakeling naar
    `sanskritisetu_app` geeft die SELECT zonder klantcontext NUL rijen -- zonder
    foutmelding -- en valt de code terug op `_SYSTEM_TENANT_ID`, dat 1 is. Elke workflow
    van elke klant zou dan als klant 1 draaien. Dat is geen storing maar een verkeerde
    toeschrijving, en die is stil.

    De opzet nu: de verzender geeft de klant mee als CLAIM, en de database BEVESTIGT
    hem. Na `adopt_tenant` filtert de afschermingsregel elke lezing op die klant, dus
    een verkeerde of vervalste claim levert een onzichtbaar uitvoeringsrecord op en
    daarmee een weigering. De claim hoeft dus niet vertrouwd te worden; hij hoeft alleen
    gecontroleerd te worden. Dat is hetzelfde principe als op het inlogpad: opzoeken,
    aannemen, en pas daarna werken.

    Zonder claim (een opdracht die al in de wachtrij stond voor deze wijziging) wordt de
    oude lezing gedaan. Levert die niets op, dan volgt een weigering en GEEN terugval op
    klant 1: een opdracht waarvan de klant onbekend is, hoort niet te draaien.
    """
    tenant_id = geclaimde_tenant
    if tenant_id is None:
        from sqlalchemy import select

        from src.core.workflow.models import C7WorkflowExecution

        resultaat = await session.execute(
            select(C7WorkflowExecution.tenant_id).where(
                C7WorkflowExecution.execution_id == execution_id
            )
        )
        tenant_id = resultaat.scalar_one_or_none()
        if tenant_id is None:
            raise TenantOnbekend(
                f"Geen klant vast te stellen voor uitvoering {execution_id}: de opdracht "
                "draagt er geen mee en het uitvoeringsrecord is niet zichtbaar."
            )

    async with adopt_tenant(session, tenant_id):
        from sqlalchemy import select

        from src.core.workflow.models import C7WorkflowExecution

        bevestiging = await session.execute(
            select(C7WorkflowExecution.id).where(C7WorkflowExecution.execution_id == execution_id)
        )
        if bevestiging.scalar_one_or_none() is None:
            raise TenantOnbekend(
                f"Uitvoering {execution_id} is niet zichtbaar voor klant {tenant_id}. "
                "De meegegeven klant klopt niet bij deze opdracht."
            )
        yield tenant_id



async def create_workflow_engine(
    db_session: AsyncSession, tenant_id: int = _SYSTEM_TENANT_ID
) -> ProductionWorkflowEngine:
    """
    Create workflow engine with injected dependencies

    This is the main factory function used by workers.

    `agent_router` (SP-AGT-003): geeft `ProductionAgentRuntime.run_agent()` een echte
    `AgentRouterAgent` in plaats van de fallback zonder routering. Geport vanuit de dode
    `core/workflow/worker.py`-module, waar dit al werkte -- dit was voorheen de ENIGE plek
    waar deze functionaliteit zat, en die module draait nooit.
    """
    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator

    from src.core.agents.agent_router_agent import get_agent_router
    from src.core.database.redis import get_redis_client

    @asynccontextmanager
    async def worker_db_session() -> AsyncIterator[AsyncSession]:
        async with get_async_session_maker()() as s:
            yield s

    agent_router = get_agent_router(
        tenant_id=tenant_id,
        async_session_factory=worker_db_session,
        redis_client=await get_redis_client(),
    )

    llm_provider = ProviderFactory.create_llm_provider()
    tool_broker = ProviderFactory.create_tool_broker()
    agent_runtime = ProviderFactory.create_agent_runtime(agent_router=agent_router)
    state_machine = WorkflowStateMachine()

    return ProductionWorkflowEngine(
        db_session=db_session,
        llm_provider=llm_provider,
        tool_broker=tool_broker,
        agent_runtime=agent_runtime,
        state_machine=state_machine,
    )


# ============================================================================
# Dramatiq Tasks
# ============================================================================

if _DRAMATIQ_AVAILABLE:
    if dramatiq_module is None:
        raise ImportError("dramatiq is not available")

    _workflow_actor = cast(
        Callable[
            [Callable[[str, int | None], Awaitable[WorkflowTaskResult]]],
            Callable[[str, int | None], Awaitable[WorkflowTaskResult]],
        ],
        workflow_actor(
            max_retries=MAX_RETRIES,
            # Alleen een tijdelijke fout krijgt een nieuwe poging; dramatiq negeert `max_retries` zodra `retry_when` is gezet.
            retry_when=moet_opnieuw(MAX_RETRIES),
            time_limit=WORKFLOW_TIMEOUT_SECONDS * 1000,
        ),
    )

    async def _execute_workflow_task_impl(
        execution_id: str, tenant_id: int | None = None
    ) -> WorkflowTaskResult:
        """
        Background task to execute a workflow

        Args:
            execution_id: UUID of the workflow execution

        Returns:
            Execution summary dict

        Raises:
            Exception: If workflow execution fails
        """
        logger.info(
            "Worker received task",
            extra={
                "execution_id": execution_id,
                "task_type": "execute_workflow",
                "timeout_seconds": WORKFLOW_TIMEOUT_SECONDS,
            },
        )

        async with get_async_session_maker()() as session:
            try:
                async with neem_de_klant_van_de_opdracht_aan(
                    session, execution_id, tenant_id
                ) as vastgestelde_tenant:
                    engine = await create_workflow_engine(
                        session, tenant_id=vastgestelde_tenant
                    )
                    result: WorkflowTaskResult = await engine.execute_workflow(execution_id)

                logger.info(
                    "Workflow execution completed",
                    extra={
                        "execution_id": execution_id,
                        "status": result["status"],
                        "duration_seconds": result["duration_seconds"],
                    },
                )

                return result

            except Exception as e:
                logger.error(
                    "Workflow execution failed",
                    extra={
                        "execution_id": execution_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                    exc_info=True,
                )
                raise

    execute_workflow_task = _workflow_actor(_execute_workflow_task_impl)

    if dramatiq_module is None:
        raise ImportError("dramatiq is not available")

    _task_actor = cast(
        Callable[
            [Callable[[str, str, int | None], Awaitable[WorkflowTaskResult]]],
            Callable[[str, str, int | None], Awaitable[WorkflowTaskResult]],
        ],
        workflow_actor(max_retries=5, retry_when=moet_opnieuw(5), time_limit=300000),
    )

    async def _execute_task_task_impl(
        execution_id: str, task_ref: str, tenant_id: int | None = None
    ) -> WorkflowTaskResult:
        """
        Background task to execute a single workflow task

        This enables parallel task execution for independent tasks.

        Args:
            execution_id: UUID of the workflow execution
            task_ref: Task reference name

        Returns:
            TaskExecutionResult as dict
        """
        logger.info(f"Worker received task: execute task {task_ref} in {execution_id}")

        async with get_async_session_maker()() as session:
            try:
                async with neem_de_klant_van_de_opdracht_aan(
                    session, execution_id, tenant_id
                ) as vastgestelde_tenant:
                    engine = await create_workflow_engine(
                        session, tenant_id=vastgestelde_tenant
                    )
                    result = await engine.execute_task(execution_id, task_ref)

                status_str = "success" if result.success else "failed"
                logger.info(
                    f"Task {task_ref} completed: "
                    f"status={status_str}, "
                    f"duration={result.execution_time:.1f}s"
                )

                # Convert dataclass to dict
                from dataclasses import asdict

                return asdict(result)

            except Exception as e:
                logger.exception(f"Task {task_ref} failed: {e}")
                raise

    execute_task_task = _task_actor(_execute_task_task_impl)

else:
    # Testing mode: provide dummy tasks that can be mocked
    class _DummySender:
        """Dummy object with .send() method for test patching"""

        def send(self, *args: Any, **kwargs: Any) -> Any:
            logger.debug(f"Dummy task send called with args={args}, kwargs={kwargs}")
            return None

    # Provide dummy senders for testing mode
    execute_workflow_task: Any = _DummySender()  # type: ignore[no-redef]
    execute_task_task: Any = _DummySender()  # type: ignore[no-redef]


# ============================================================================
# Health Check
# ============================================================================


async def check_worker_health() -> HealthStatus:
    """
    Health check for worker (can be exposed via API)

    Returns:
        Health status dict
    """
    health: HealthStatus = {
        "status": "healthy",
        "redis": "unknown",
        "database": "unknown",
    }

    # Check Redis
    try:
        from src.core.typing import create_sync_redis_client

        r = create_sync_redis_client(REDIS_URL)
        r.ping()
        health["redis"] = "connected"
    except Exception as e:
        health["redis"] = f"error: {e}"
        health["status"] = "unhealthy"

    # Check PostgreSQL
    if get_async_session_maker() is not None:
        try:
            async with get_async_session_maker()() as session:
                await session.execute(text("SELECT 1"))
            health["database"] = "connected"
        except Exception as e:
            health["database"] = f"error: {e}"
            health["status"] = "unhealthy"
    else:
        health["database"] = "unavailable"
        health["status"] = "degraded"

    return health


# ============================================================================
# CLI for Testing
# ============================================================================


async def _check_worker_governance(
    execution_id: str,
    agent_name: str = "WorkflowEngine",
    task_action: str = "execute_workflow",
) -> None:
    """Apply governance checkpoint before executing a workflow task.

    Raises:
        PermissionError: if governance blocks execution (fail-closed).
        Any exception raised by apply_governance_check propagates unchanged.
    """
    allowed, reason = await apply_governance_check(
        agent_name=agent_name,
        task_action=task_action,
        agent_department="workflow",
        task_params={"execution_id": execution_id},
    )
    if not allowed:
        raise PermissionError(f"GOVERNANCE_BLOCK: {reason}")


if __name__ == "__main__":
    """
    Test worker locally

    Usage:
        python -m src.workers.workflow_worker
    """
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def test() -> None:
        # Health check
        health: HealthStatus = await check_worker_health()
        logger.info(f"Worker health: {health}")

        # Test execution
        if len(sys.argv) > 1:
            execution_id: str = sys.argv[1]
            logger.info(f"Testing execution: {execution_id}")

            # tenant_id expliciet None: de actor leidt de klant dan af uit het
            # uitvoeringsrecord (OP-153). De cast op regel 448 declareert beide parameters
            # als verplicht, dus weglaten is hier een mypy-fout terwijl de implementatie
            # zelf een default heeft.
            result: WorkflowTaskResult = await execute_workflow_task(execution_id, None)
            logger.info(f"Result: {result}")

    asyncio.run(test())
