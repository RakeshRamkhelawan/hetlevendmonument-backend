"""Consistency tests for HITLStore wiring across ToolBrokerService construction sites.

AUDIT-TOOL-005: every ToolBrokerService must have a configured HITLStore so that
HIGH-risk tools do not fail with "HITLStore is not configured" outside the
Copilot request flow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Deze tests bouwen een sandbox in een constructor, en die roept `docker.from_env()` aan
# -- een ECHTE verbinding naar de Docker-daemon (ADR-036 OP-214).
from tests.fixtures.docker_sandbox import geen_echte_docker_daemon  # noqa: F401

from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.shared.interfaces import ExecutionResult, SystemEvent, TaskData
from src.core.tool_broker.dependencies import ToolBrokerDependencies, get_tool_broker_service
from src.core.tool_broker.service import ToolBrokerService
from src.core.types import AgentType


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tool_broker_dependencies(monkeypatch: Any) -> Generator[None, None, None]:
    """Reset the ToolBrokerDependencies singleton state between tests."""
    ToolBrokerDependencies._instance = None
    ToolBrokerDependencies._serena_client = None
    ToolBrokerDependencies._seq_thinking_client = None
    ToolBrokerDependencies._local_registry = None
    ToolBrokerDependencies._service = None
    ToolBrokerDependencies._mcp_initialized = False
    yield
    ToolBrokerDependencies._instance = None
    ToolBrokerDependencies._serena_client = None
    ToolBrokerDependencies._seq_thinking_client = None
    ToolBrokerDependencies._local_registry = None
    ToolBrokerDependencies._service = None
    ToolBrokerDependencies._mcp_initialized = False


class _NoopEventEmitter:
    async def __call__(self, event: SystemEvent) -> None:
        return None


def _make_enhanced_agent() -> EnhancedBaseAgent:
    """Create a minimal EnhancedBaseAgent without heavy external deps."""
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.agents.mixins.learning_mixin.get_feature_flag", return_value=True),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return EnhancedBaseAgent(
            agent_id="tool-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            event_emitter=_NoopEventEmitter(),
        )


class _ConcreteSpecialist(BaseSpecialistAgent):
    async def observe(self, signal: Any) -> dict[str, Any]:
        return {}

    async def orient(self, observation: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def decide(self, orientation: dict[str, Any]) -> str:
        return ""

    async def act(self, decision: str) -> ExecutionResult:
        return ExecutionResult(task_id="act", success=True)

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True)


def _make_specialist_agent() -> BaseSpecialistAgent:
    """Create a minimal concrete specialist agent."""
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.agents.mixins.learning_mixin.get_feature_flag", return_value=True),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
        patch("src.core.als.agents.symbiotic_agent.OrganismRegistry"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        config: dict[str, Any] = {
            "agent_id": "specialist-1",
            "technology": "test",
            "name": "Test Specialist",
            "description": "For testing HITLStore wiring.",
            "allowed_tools": [],
        }
        return _ConcreteSpecialist(config=config, tenant_id=1)


# ---------------------------------------------------------------------------
# Construction-site wiring tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLStoreWiringConsistency:
    def test_singleton_get_service_has_hitl_store(self) -> None:
        """ToolBrokerDependencies.get_service() (no db) must provide a HITLStore."""
        service = ToolBrokerDependencies.get_service()
        assert service.hitl_store is not None

    def test_per_request_get_service_has_hitl_store(self) -> None:
        """ToolBrokerDependencies.get_service(db=...) must provide a HITLStore."""
        db = AsyncMock(spec=AsyncSession)
        service = ToolBrokerDependencies.get_service(db=db)
        assert service.hitl_store is not None

    def test_fastapi_dependency_get_tool_broker_service_has_hitl_store(self) -> None:
        """The canonical FastAPI dependency must provide a HITLStore."""
        db = AsyncMock(spec=AsyncSession)
        service = get_tool_broker_service(db=db)
        assert service.hitl_store is not None

    def test_enhanced_base_agent_tool_broker_has_hitl_store(self) -> None:
        """EnhancedBaseAgent._create_tool_broker must configure a HITLStore."""
        agent = _make_enhanced_agent()
        broker = agent.tool_broker
        assert broker is not None
        assert broker.hitl_store is not None

    def test_specialist_agent_tools_has_hitl_store(self) -> None:
        """BaseSpecialistAgent must construct ToolBrokerService with a HITLStore."""
        agent = _make_specialist_agent()
        assert agent.tools.hitl_store is not None

    def test_execution_router_uses_dependency_injected_service(self) -> None:
        """The API execution router must accept ToolBrokerService via Depends.

        Before the fix the router constructed ToolBrokerService inline. After the
        fix it declares a FastAPI dependency, which also means the service has a
        correctly wired HITLStore.
        """
        import inspect

        from src.core.api.v1.tool_broker.execution_router import execute_tool
        from src.core.tool_broker.dependencies import get_tool_broker_service

        sig = inspect.signature(execute_tool)
        assert "service" in sig.parameters, (
            "execute_tool must accept a ToolBrokerService dependency"
        )
        param = sig.parameters["service"]
        assert param.default is not inspect.Parameter.empty
        depends = param.default
        assert hasattr(depends, "dependency"), "service parameter must use Depends(...)"
        assert depends.dependency is get_tool_broker_service


# ---------------------------------------------------------------------------
# Functional test: HIGH-risk tool executes when HITLStore is wired
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLStoreFunctional:
    @pytest.fixture(autouse=True)
    def _allow_all_tools(self) -> Generator[None, None, None]:
        with patch(
            "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
            return_value=True,
        ):
            yield

    @pytest.mark.asyncio
    async def test_high_risk_tool_with_approved_ticket_executes_via_singleton(self) -> None:
        """After wiring, the singleton path can execute a HIGH-risk tool with approval."""
        from src.core.tool_broker.hitl_store import HITLStore

        # Initialize the singleton asynchronously to avoid nested event loops.
        await ToolBrokerDependencies.initialize_async()

        service = ToolBrokerDependencies.get_service()
        # The singleton must have a HITLStore configured.
        assert service.hitl_store is not None

        # Mock the configured HITLStore so we do not need a real database.
        mock_store = AsyncMock(spec=HITLStore)
        # `redeem_approval` en niet `get_approval_status`: sinds ADR-036 OP-63 VERZILVERT de poort
        # de goedkeuring in een enkele UPDATE (tool + parameters + eenmalig) in plaats van alleen
        # de status te lezen. Een mock die de oude methode zet, meet een poort die niet meer bestaat.
        mock_store.redeem_approval = AsyncMock(return_value=True)
        service.hitl_store = mock_store

        # local__run_shell is HIGH risk; with an approved ticket it should pass
        # the HITL gate and then fail only because the local registry is not
        # configured with a real sandbox (acceptable for this wiring test).
        # De tenant hoort in de context: sinds BE-AGT-045 ronde 2 bepaalt de payload hem niet
        # meer (ADR-036 OP-27) en weigert de broker zonder tenant de uitvoering. Zonder deze
        # context zou de test slagen op de verkeerde fout en de HITL-wiring niet meer raken.
        with pytest.raises(Exception) as exc_info:
            await service.execute_tool(
                "local__run_shell",
                payload={"_hitl_ticket_ref": "TOOL-APPROVED"},
                context={"tenant_id": 1},
            )

        detail = str(exc_info.value)
        assert "HITLStore is not configured" not in detail
        mock_store.redeem_approval.assert_awaited_once_with(
            "TOOL-APPROVED",
            tenant_id=1,
            tool_name="local__run_shell",
            payload={"_hitl_ticket_ref": "TOOL-APPROVED", "tenant_id": 1},
        )
