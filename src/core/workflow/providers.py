"""
Concrete Provider Implementations for Production
Implements interfaces.py abstractions with real integrations

Production Stack:
- LLM: OpenAI/Anthropic via existing base_agent.py
- Tools: Existing tool_broker_client.py
- Agents: Existing subagent_loader.py
"""

import logging
import time
import types
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from src.core.agents.agent_router_agent import AgentRouterAgent
    from src.core.agents.subagent_loader import AgentDefinition, SubagentLoader

from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.tool_broker import workflow_identiteit
from src.core.workflow.interfaces import (
    IAgentRuntime,
    ILLMProvider,
    IToolBroker,
    TaskExecutionRequest,
    TaskExecutionResult,
)

logger = logging.getLogger(__name__)

# Type aliases
LLMResponse: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]
ToolResult: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]
AgentResponse: TypeAlias = dict[str, Any]  # type: ignore[misc, unused-ignore]


# ============================================================================
# PRODUCTION LLM PROVIDER
# ============================================================================


class ProductionLLMProvider(ILLMProvider):
    """
    Production LLM provider: het taalmodel van DE KLANT via de deur per tenant (ADR-041 B14).

    Een taalmodelstap gaat naar `TenantTaalmodel(tenant_id)`, dus naar het model dat de klant koos
    (`LLMService.for_tenant`), niet naar een model dat de workflow of het platform kiest. De klant komt van de
    ENGINE (de klant van de uitvoering), nooit uit de definitie van de workflow. De `model`-instelling van de stap
    wordt genegeerd: die kwam uit een omgevingsvariabele of uit de definitie en zou de keuze van de klant
    overrulen.

    Tot 2026-10-22 bouwde deze klasse een `BaseAgent`, een abstracte klasse: elke taalmodelstap faalde met
    `Can't instantiate abstract class BaseAgent` (gemeten met een echte worker).
    """

    @bewaakt_model_aanroep
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Genereer via het taalmodel van de klant; een storing komt als uitzondering bij de engine."""
        tenant_id = kwargs.get("tenant_id")
        if not isinstance(tenant_id, int):
            # Geen klant, geen antwoord: de deur kent een platformstandaard voor `None`, en die hoort een klantstap
            # niet stilletjes te bedienen.
            raise ValueError("Een taalmodelstap heeft de klant van de uitvoering nodig; die ontbreekt.")

        deur = TenantTaalmodel(tenant_id)
        tekst, tokens_in, tokens_uit = await deur.tekst_met_gebruik(
            prompt, systeem=system_prompt, temperature=temperature, max_tokens=max_tokens
        )
        label = deur.model_label or ""
        return {
            "content": tekst,
            "provider": label.split(":", 1)[0] if label else "onbekend",
            "model": label,
            "tokens": tokens_in + tokens_uit,
            "finish_reason": "stop",
        }

    async def embed(self, text: str, model: str = "text-embedding-ada-002") -> list[float]:
        """Generate embedding (placeholder - implement if needed)"""
        # TODO: Implement via the tenant door or direct OpenAI API
        logger.warning("embed() not yet implemented, returning empty embedding")
        return []

    async def moderate(self, text: str) -> LLMResponse:
        """Content moderation (placeholder - implement if needed)"""
        # TODO: Implement via OpenAI moderation API
        logger.warning("moderate() not yet implemented, returning safe result")
        return {"flagged": False, "categories": {}}


# ============================================================================
# PRODUCTION TOOL BROKER
# ============================================================================


class ProductionToolBroker(IToolBroker):
    """
    Production tool broker: de echte `ToolBrokerService` (ADR-015), onder de identiteit `workflow_engine`.

    Tot 2026-10-22 importeerde deze klasse een `ToolBrokerClient` die niet bestaat en gaf elke toolstap
    `success: False`, waarna de uitvoering toch op `succeeded` eindigde. Nu: de klant van de uitvoering gaat mee in
    de context, het permissieprofiel bepaalt WELKE tools een workflow mag, en een weigering of fout is een
    mislukte stap met een Nederlandse reden. Een tool met hoog risico (HITL) wordt geweigerd: een workflowstap kan
    geen goedkeuring afwachten, dus hij faalt zichtbaar in plaats van te blijven hangen.
    """

    def __init__(self) -> None:
        self._dienst: Any = None  # TODO(TYPE): replace Any with concrete type

    def _broker(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        if self._dienst is None:
            self._dienst = workflow_identiteit.bouw_workflow_broker()
        return self._dienst

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout: int = 60,
        tenant_id: int | None = None,
        starter: str | None = None,
    ) -> ToolResult:
        """Voer de tool uit via de echte broker; een weigering of fout is `success: False` met een reden."""
        if not isinstance(tenant_id, int):
            return {
                "success": False,
                "result": None,
                "error": "De tool kon niet worden uitgevoerd: de klant van de uitvoering ontbreekt.",
                "execution_time": 0.0,
            }
        # De stap mag niet meer dan de mens die de workflow startte: het profiel van `workflow_engine` is de
        # bovengrens, het recht van de starter (nu, niet bij het starten) de tweede grens.
        if not await workflow_identiteit.starter_heeft_toolrecht(starter, tool_name, tenant_id):
            return {
                "success": False,
                "result": None,
                "error": (
                    f"De tool '{tool_name}' is niet uitgevoerd: de gebruiker die deze workflow startte "
                    "heeft daar geen recht voor (of is niet bekend)."
                ),
                "execution_time": 0.0,
            }
        start_time = time.perf_counter()
        try:
            resultaat = await self._broker().execute_tool(
                tool_name=tool_name,
                payload=dict(parameters),
                agent_id=workflow_identiteit.WORKFLOW_IDENTITEIT,
                timeout_seconds=timeout,
                context={"tenant_id": tenant_id},
            )
        except Exception as e:
            logger.error(
                "Workflowstap: tool %s mislukt: %s: %s", tool_name, type(e).__name__, e, exc_info=True
            )
            return {
                "success": False,
                "result": None,
                "error": f"De tool '{tool_name}' is niet uitgevoerd: {workflow_identiteit.reden_in_gewone_taal(e)}",
                "execution_time": time.perf_counter() - start_time,
            }
        return {
            "success": True,
            "result": resultaat,
            "error": None,
            "execution_time": time.perf_counter() - start_time,
        }

    async def list_available_tools(self) -> list[str]:
        """De tools die de identiteit `workflow_engine` mag gebruiken."""
        return workflow_identiteit.toegestane_workflowtools()


# ============================================================================
# PRODUCTION AGENT RUNTIME
# ============================================================================


class ProductionAgentRuntime(IAgentRuntime):
    """
    Production agent runtime using existing subagent_loader.py

    Integration: core.agents.subagent_loader.get_subagent_loader()
    """

    # Sentinel: distinguishes "override not set" from "override explicitly set to None"
    _LOADER_SENTINEL: object = object()

    def __init__(self, agent_router: "AgentRouterAgent | None" = None) -> None:
        self._agent_router: Any = agent_router  # TODO(TYPE): replace Any with concrete type
        # Import from src path
        try:
            from src.core.agents.base_agent import BaseAgent

            self.base_agent_class: Any = BaseAgent  # NOTE: class reference -- genuinely polymorphic  # TODO(TYPE): replace Any with concrete type
        except ImportError as e:
            logger.warning(f"SubAgent loader not available: {e}")
            self.base_agent_class = None
        # Sentinel means "use the real singleton"; set via setter to override
        self._subagent_loader_override: SubagentLoader | None | object = (
            ProductionAgentRuntime._LOADER_SENTINEL
        )

    @property
    def subagent_loader(self) -> "SubagentLoader | None":
        """Lazy accessor -- returns a test override if set, else the real singleton."""
        # Handle __new__ construction (no __init__ called -- attribute may not exist)
        override = getattr(
            self, "_subagent_loader_override", ProductionAgentRuntime._LOADER_SENTINEL
        )
        if override is not ProductionAgentRuntime._LOADER_SENTINEL:
            return override  # type: ignore[return-value]
        try:
            from src.core.agents.subagent_loader import get_subagent_loader

            return get_subagent_loader()
        except ImportError:
            return None

    @subagent_loader.setter
    def subagent_loader(self, value: "SubagentLoader | None") -> None:
        """Allow tests (and dependency injection) to override the singleton."""
        self._subagent_loader_override = value

    async def load_agent(self, agent_type: str) -> "AgentDefinition | None":
        """Load subagent by type"""
        try:
            loader = self.subagent_loader
            if loader is None:
                return None
            # Get subagents for category
            subagents = loader.get_subagents_by_category(agent_type)

            if not subagents:
                # Fallback: search all subagents
                all_subagents = loader.get_all_subagents()
                matching = [s for s in all_subagents if agent_type.lower() in s.name.lower()]
                subagents = matching[:1]

            return subagents[0] if subagents else None

        except Exception as e:
            logger.error(f"Failed to load agent {agent_type}: {e}")
            return None

    async def execute_agent(
        self,
        agent: "AgentDefinition",
        task_request: TaskExecutionRequest,
    ) -> TaskExecutionResult:
        """Execute agent with task (real LLM execution)"""
        start_time = time.perf_counter()

        try:
            # Build TaskData for BaseAgent
            from src.core.shared.interfaces import TaskData

            task_data = TaskData(
                id=task_request.task_id,
                title=f"Workflow Task: {task_request.task_id}",
                description=task_request.parameters.get("description", ""),
                priority=task_request.parameters.get("priority", "MEDIUM"),
                metadata={
                    "task_type": task_request.task_type,
                    "user_id": task_request.tenant_id or "workflow_engine",
                    "subagent_name": agent.name,
                    "subagent_model": agent.model.value,  # type: ignore[attr-defined]
                    "subagent_capabilities": agent.capabilities,
                    "subagent_system_prompt": agent.system_prompt,  # type: ignore[attr-defined]
                    "workflow_context": task_request.context,
                    "task_parameters": task_request.parameters,
                    "agent_type": task_request.agent_type,
                },
            )

            # Execute with real BaseAgent
            base_agent = self.base_agent_class(f"workflow_{agent.name.lower().replace(' ', '_')}")
            result = await base_agent.process_task(task_data)

            execution_time = time.perf_counter() - start_time

            if result and result.success:
                return TaskExecutionResult(
                    task_id=task_request.task_id,
                    success=True,
                    output={
                        "agent": agent.name,
                        "real_output": result.result_data,
                        "execution_type": "REAL_LLM_EXECUTION",
                        "is_mock": False,
                    },
                    error=None,
                    execution_time=execution_time,
                    provider_used=result.result_data.get("provider_used", "unknown"),
                    tokens_used=result.result_data.get("tokens_used", 0),
                )
            else:
                return TaskExecutionResult(
                    task_id=task_request.task_id,
                    success=False,
                    output=None,
                    error=result.error_message if result else "Execution failed",
                    execution_time=execution_time,
                )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return TaskExecutionResult(
                task_id=task_request.task_id,
                success=False,
                output=None,
                error=str(e),
                execution_time=time.perf_counter() - start_time,
            )

    async def get_available_agents(self) -> list[str]:
        """Get available agent types"""
        try:
            all_agents = self.subagent_loader.get_all_subagents()  # type: ignore[union-attr]
            return [agent.name for agent in all_agents]
        except Exception as e:
            logger.error(f"Failed to list agents: {e}")
            return []

    async def run_agentstap(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, object],
        starter: str | None = None,
    ) -> dict[str, object]:
        """Een agentstap: de GEKOZEN agent draait, zonder router-keuze, met alleen de rechten van de starter.

        Zie `src/core/als/agents/workflow_stap.py`. De klant komt uit `context["tenant_id"]`, dat de engine uit de
        uitvoering zet en nooit uit de stapdefinitie of de invoer.
        """
        import importlib

        stap = importlib.import_module("src.core.als.agents.workflow_stap")
        return await stap.voer_agentstap_uit(  # type: ignore[no-any-return]
            agent_id, instruction, tenant_id=context.get("tenant_id"), starter=starter
        )

    async def run_agent(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> AgentResponse:
        """
        Run agent with instruction (simplified interface for workflow engine)

        Delegates to AgentRouterAgent when injected (SP-AGT-003); otherwise
        falls back to the subagent_loader for naive category matching.
        """
        # NOTE: guard against __new__ construction (no __init__ called), same pattern as subagent_loader.
        if getattr(self, "_agent_router", None) is not None:
            return await self._agent_router.run_agent(  # type: ignore[no-any-return]
                agent_id=agent_id,
                instruction=instruction,
                context=context,
            )
        try:
            # Load the agent
            agent = await self.load_agent(agent_id)
            if not agent:
                return {"error": f"Agent {agent_id} not found", "success": False}

            # Build a TaskExecutionRequest
            task_request = TaskExecutionRequest(
                task_id=f"run_{agent_id}_{id(instruction)}",
                task_type="agent",
                agent_type=agent_id,
                parameters={"instruction": instruction},
                context=context,
            )

            # Execute and convert result
            result = await self.execute_agent(agent, task_request)

            if result.success:
                return {
                    "output": result.output,
                    "agent_id": agent_id,
                    "success": True,
                    "execution_time": result.execution_time,
                }
            else:
                return {
                    "error": result.error,
                    "agent_id": agent_id,
                    "success": False,
                }

        except Exception as e:
            logger.error(f"run_agent failed for {agent_id}: {e}")
            return {"error": str(e), "agent_id": agent_id, "success": False}


# ============================================================================
# FAKE PROVIDERS FOR TESTING
# ============================================================================


class FakeLLMProvider(ILLMProvider):
    """Deterministic fake for testing"""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.default_response = "Fake LLM response for testing"

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return predetermined response"""
        content = self.responses.get(prompt, self.default_response)
        return {
            "content": content,
            "provider": "fake",
            "model": model,
            "tokens": len(content.split()),
            "finish_reason": "stop",
        }

    async def embed(self, text: str, model: str = "text-embedding-ada-002") -> list[float]:
        return [0.1, 0.2, 0.3]  # Fake embedding

    async def moderate(self, text: str) -> LLMResponse:
        return {"flagged": False, "categories": {}}


class FakeToolBroker(IToolBroker):
    """Deterministic fake for testing"""

    def __init__(
        self,
        tool_results: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.tool_results = tool_results or {}

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout: int = 60,
        tenant_id: int | None = None,
        starter: str | None = None,
    ) -> ToolResult:
        """Return predetermined result"""
        result = self.tool_results.get(tool_name, {"status": "success", "data": "fake_result"})
        return {"success": True, "result": result, "error": None, "execution_time": 0.1}

    async def list_available_tools(self) -> list[str]:
        return list(self.tool_results.keys())


class FakeAgentRuntime(IAgentRuntime):
    """Deterministic fake for testing"""

    def __init__(
        self,
        agent_results: dict[str, dict[str, object]] | None = None,
        agent_router: Any = None,
    ) -> None:
        self.agent_results = agent_results or {}
        self._agent_router: Any = agent_router  # TODO(TYPE): replace Any with concrete type
        self.agents: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    async def load_agent(
        self, agent_type: str
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Return fake agent"""
        from dataclasses import dataclass

        @dataclass
        class FakeAgent:
            name: str = agent_type
            model: Any = None
            capabilities: list[str] | None = None
            system_prompt: str = ""

        agent = FakeAgent()
        agent.model = type("obj", (object,), {"value": "fake-model"})
        agent.capabilities = ["test"]
        self.agents[agent_type] = agent
        return agent

    async def execute_agent(
        self,
        agent: Any,  # TODO(TYPE): replace Any with concrete type
        task_request: TaskExecutionRequest,
    ) -> TaskExecutionResult:
        """Return predetermined result"""
        result = self.agent_results.get(
            task_request.agent_type, {"output": "fake_agent_output", "success": True}
        )

        return TaskExecutionResult(
            task_id=task_request.task_id,
            success=cast(bool, result.get("success", True)),
            output=result.get("output"),  # type: ignore[arg-type]
            error=cast(str | None, result.get("error")),
            execution_time=0.1,
            provider_used="fake",
            tokens_used=10,
        )

    async def run_agentstap(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, object],
        starter: str | None = None,
    ) -> dict[str, object]:
        """Voor tests: dezelfde voorgeprogrammeerde uitkomst als `run_agent`."""
        return dict(await self.run_agent(agent_id, instruction, context))

    async def run_agent(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> AgentResponse:
        """
        Run agent with instruction (simplified interface for workflow engine)
        Returns predetermined results based on agent_id
        """
        # Look up by agent_id or use default response
        result = self.agent_results.get(
            agent_id,
            {
                "output": f"Fake agent {agent_id} completed: {instruction[:50]}...",
                "success": True,
            },
        )
        return {
            "output": result.get("output", "fake_agent_output"),
            "agent_id": agent_id,
            "success": result.get("success", True),
        }

    async def get_available_agents(self) -> list[str]:
        return list(self.agent_results.keys())


# ============================================================================
# UNIT OF WORK IMPLEMENTATIONS (P5 - Futureproof Transaction Management)
# ============================================================================

from src.core.workflow.interfaces import IUnitOfWork


class ProductionUnitOfWork(IUnitOfWork):
    """
    Production Unit of Work - creates new session per transaction

    Usage:
        async with ProductionUnitOfWork(session_maker) as uow:
            uow.session.add(entity)
            await uow.session.execute(query)
            await uow.commit()  # Explicit commit required

    Behavior:
    - Creates fresh session on __aenter__
    - Auto-rollback on exception in __aexit__
    - Closes session on __aexit__
    - Supports nested transactions via begin_nested()
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        """
        Args:
            session_maker: async_sessionmaker instance
        """
        self._session_maker = session_maker
        self._session: AsyncSession | None = None
        self._committed: bool = False

    async def __aenter__(self) -> "ProductionUnitOfWork":
        """Create new session and start transaction"""
        self._session = self._session_maker()
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """
        Cleanup session:
        - Rollback if exception occurred
        - Rollback if not committed (safety net)
        - Always close session
        """
        try:
            if exc_type is not None:
                # Exception occurred - rollback
                await self._session.rollback()  # type: ignore[union-attr]
                logger.debug("UoW: Rolled back due to exception")
            elif not self._committed:
                # No exception but not committed - rollback uncommitted changes
                await self._session.rollback()  # type: ignore[union-attr]
                logger.debug("UoW: Rolled back uncommitted changes")
        finally:
            await self._session.close()  # type: ignore[union-attr]
            self._session = None

    async def commit(self) -> None:
        """Commit all changes"""
        if self._session is None:
            raise RuntimeError("Cannot commit - no active session")
        await self._session.commit()
        self._committed = True
        logger.debug("UoW: Committed transaction")

    async def rollback(self) -> None:
        """Rollback all changes"""
        if self._session is None:
            raise RuntimeError("Cannot rollback - no active session")
        await self._session.rollback()
        logger.debug("UoW: Rolled back transaction")

    @property
    def session(self) -> AsyncSession:
        """Access underlying session"""
        if self._session is None:
            raise RuntimeError("No active session - use within 'async with' context")
        return self._session


class TestUnitOfWork(IUnitOfWork):
    """
    Test Unit of Work - reuses existing session, auto-rollback

    Usage:
        async with TestUnitOfWork(test_session) as uow:
            uow.session.add(entity)
            # No commit needed - auto-rollback at end

    Behavior:
    - Reuses existing test session (from fixture)
    - Uses savepoint for nested transaction isolation
    - Auto-rollback to savepoint on __aexit__ (regardless of exception)
    - Does NOT close session (test fixture manages lifecycle)

    This ensures:
    - Each test gets isolated transaction
    - No data persists between tests
    - Parallel tests don't interfere (each has own savepoint)
    """

    def __init__(
        self,
        session: AsyncSession,
        auto_rollback: bool = True,
    ) -> None:
        """
        Args:
            session: Existing AsyncSession from test fixture
            auto_rollback: If True, always rollback on exit (default for tests)
        """
        self._session = session
        self._auto_rollback = auto_rollback
        self._savepoint: Any = None  # NOTE: AsyncSessionTransaction -- no public type export
        self._committed: bool = False

    async def __aenter__(self) -> "TestUnitOfWork":
        """Start nested transaction (savepoint) for test isolation"""
        # Begin nested transaction - this creates a savepoint
        self._savepoint = await self._session.begin_nested()
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """
        Cleanup:
        - Always rollback to savepoint in tests (clean slate)
        - Exception or not, we want isolation
        """
        try:
            if self._auto_rollback or exc_type is not None:
                # Rollback to savepoint - removes all changes from this test
                if self._savepoint and self._savepoint.is_active:
                    await self._savepoint.rollback()
                    logger.debug("TestUoW: Rolled back to savepoint")
            elif self._committed and self._savepoint and self._savepoint.is_active:
                # Committed and not auto-rollback - commit savepoint
                await self._savepoint.commit()
                logger.debug("TestUoW: Committed savepoint")
        except Exception as e:
            logger.warning(f"TestUoW cleanup error: {e}")
        # Note: Do NOT close session - test fixture owns it

    async def commit(self) -> None:
        """
        Mark as committed (actual commit happens in __aexit__ if auto_rollback=False)

        In most tests, you don't need to call this - data is visible
        within the same session even without commit.
        """
        self._committed = True
        # Flush to make changes visible in same session
        await self._session.flush()
        logger.debug("TestUoW: Flushed changes (not committed)")

    async def rollback(self) -> None:
        """Rollback to savepoint"""
        if self._savepoint and self._savepoint.is_active:
            await self._savepoint.rollback()
            # Start new savepoint for continued use
            self._savepoint = await self._session.begin_nested()
        logger.debug("TestUoW: Rolled back to savepoint")

    @property
    def session(self) -> AsyncSession:
        """Access underlying session"""
        return self._session
