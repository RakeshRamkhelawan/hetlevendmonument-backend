"""
C.7 Unit Tests with Fake Providers
===================================

Tests WorkflowEngine using FakeLLMProvider/FakeAgentRuntime for deterministic testing.
No external dependencies (LLM APIs, real agents) required.

Run:
    pytest src/tests/unit/test_c7_workflow.py -v
"""

from typing import Any, Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Import engine and providers
from src.core.workflow.engine import DAGValidator, ProductionWorkflowEngine, WorkflowSpec
from src.core.workflow.interfaces import IAgentRuntime, ILLMProvider, IToolBroker

# Import models - use src package imports
from src.core.workflow.models import Base
from src.core.workflow.state_machine import WorkflowStateMachine

# ============================================================================
# Fake Providers for Testing
# ============================================================================


class FakeLLMProvider(ILLMProvider):
    """Deterministic fake for testing"""

    def __init__(self, responses: dict[str, str] = None):
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
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return predetermined response"""
        content = self.responses.get(prompt, self.default_response)
        return {
            "content": content,
            "provider": "fake",
            "model": model,
            "tokens": len(content.split()),
            "finish_reason": "stop",
        }

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return predetermined response (legacy)"""
        prompt = " ".join(
            [msg.get("content", "") for msg in messages if isinstance(messages, list)]
        )
        content = self.responses.get(prompt, self.default_response)
        return {
            "content": content,
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": len(content.split())},
        }

    async def embed(self, text: str, model: str = "text-embedding-ada-002") -> list[float]:
        return [0.1, 0.2, 0.3]

    async def moderate(self, text: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {"flagged": False, "categories": {}}


class FakeToolBroker(IToolBroker):
    """Deterministic fake for testing"""

    def __init__(self, responses: dict[str, Any] = None):  # TODO(TYPE): replace Any with concrete type
        self.responses = responses or {}

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout: float | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return predetermined result"""
        result = self.responses.get(tool_name, {"status": "success", "data": "fake_result"})
        return {
            "status": "success",
            "result": result,
            "execution_time": 0.1,
        }

    async def list_tools(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        return [{"name": k} for k in self.responses.keys()]

    async def list_available_tools(self) -> list[str]:
        return list(self.responses.keys())


class FakeAgentRuntime(IAgentRuntime):
    """Deterministic fake for testing"""

    def __init__(self, responses: dict[str, Any] = None):  # TODO(TYPE): replace Any with concrete type
        self.responses = responses or {}

    async def load_agent(self, agent_type: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        return {"agent_type": agent_type, "loaded": True}

    async def execute_agent(self, agent: Any, task_request: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        return {"status": "success", "output": "fake_execution"}

    async def run_agent(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        result = self.responses.get(agent_id, {"output": "fake_agent_output"})
        return {"status": "success", "output": result, "execution_time": 0.1}

    async def get_available_agents(self) -> list[str]:
        return list(self.responses.keys())

    async def invoke_agent(
        self,
        agent_id: str,
        input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout: float | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return predetermined result (legacy)"""
        result = self.responses.get(agent_id, {"output": "fake_agent_output"})
        return {"status": "success", "output": result, "execution_time": 0.1}


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
async def db_session():
    """Create in-memory SQLite database for testing"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session: sessionmaker[AsyncSession] = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def fake_providers():
    """Create fake providers for testing"""
    llm_responses = {
        "Generate a summary": "This is a fake summary",
        "Translate to Spanish": "Esta es una traduccion falsa",
    }

    tool_responses = {
        "search_database": {"results": ["item1", "item2"]},
        "send_email": {"status": "sent"},
    }

    agent_responses = {
        "customer_support_agent": {"response": "How can I help you?"},
    }

    return {
        "llm": FakeLLMProvider(responses=llm_responses),
        "tool": FakeToolBroker(responses=tool_responses),
        "agent": FakeAgentRuntime(responses=agent_responses),
    }


@pytest.fixture
async def workflow_engine(db_session, fake_providers):
    """Create workflow engine with fake providers"""
    return ProductionWorkflowEngine(
        db_session=db_session,
        llm_provider=fake_providers["llm"],
        tool_broker=fake_providers["tool"],
        agent_runtime=fake_providers["agent"],
        state_machine=WorkflowStateMachine(),
    )


# ============================================================================
# DAG Validation Tests
# ============================================================================


def test_dag_validator_valid():
    """Test DAG validation with valid workflow"""
    spec = WorkflowSpec(
        workflow_id="test_workflow",
        version=1,
        tasks={
            "task_a": {"type": "llm", "prompt": "Hello"},
            "task_b": {"type": "llm", "prompt": "World"},
        },
        dependencies={
            "task_b": ["task_a"],
        },
    )

    is_valid, error = DAGValidator.validate_dag(spec)
    assert is_valid is True
    assert error is None


def test_dag_validator_cycle():
    """Test DAG validation detects cycles"""
    spec = WorkflowSpec(
        workflow_id="cyclic_workflow",
        version=1,
        tasks={
            "task_a": {"type": "llm"},
            "task_b": {"type": "llm"},
            "task_c": {"type": "llm"},
        },
        dependencies={
            "task_a": ["task_c"],
            "task_b": ["task_a"],
            "task_c": ["task_b"],
        },
    )

    is_valid, error = DAGValidator.validate_dag(spec)
    assert is_valid is False
    assert "cycle" in error.lower()


def test_dag_validator_missing_dependency():
    """Test DAG validation detects missing dependencies"""
    spec = WorkflowSpec(
        workflow_id="bad_workflow",
        version=1,
        tasks={
            "task_a": {"type": "llm"},
        },
        dependencies={
            "task_a": ["task_b"],  # task_b doesn't exist
        },
    )

    is_valid, error = DAGValidator.validate_dag(spec)
    assert is_valid is False
    assert "not found" in error.lower()


def test_topological_sort():
    """Test topological sorting"""
    spec = WorkflowSpec(
        workflow_id="test",
        version=1,
        tasks={
            "A": {"type": "llm"},
            "B": {"type": "llm"},
            "C": {"type": "llm"},
            "D": {"type": "llm"},
        },
        dependencies={
            "B": ["A"],
            "C": ["A"],
            "D": ["B", "C"],
        },
    )

    sorted_tasks = DAGValidator.topological_sort(spec)

    # A must come before B, C
    assert sorted_tasks.index("A") < sorted_tasks.index("B")
    assert sorted_tasks.index("A") < sorted_tasks.index("C")

    # B and C must come before D
    assert sorted_tasks.index("B") < sorted_tasks.index("D")
    assert sorted_tasks.index("C") < sorted_tasks.index("D")


# ============================================================================
# Workflow Engine Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_workflow(workflow_engine):
    """Test creating a workflow"""
    spec = {
        "tasks": {
            "task1": {"type": "llm", "prompt": "Hello"},
        },
        "dependencies": {},
    }

    workflow_id = await workflow_engine.create_workflow(
        workflow_id="test_workflow",
        spec_json=spec,
        version=1,
    )

    assert workflow_id > 0


@pytest.mark.asyncio
async def test_start_execution(workflow_engine):
    """Test starting a workflow execution"""
    spec = {
        "tasks": {
            "task1": {"type": "llm", "prompt": "Hello"},
        },
        "dependencies": {},
    }

    await workflow_engine.create_workflow(
        workflow_id="test_workflow",
        spec_json=spec,
    )

    execution_id = await workflow_engine.start_execution(
        workflow_id="test_workflow",
        input_data={"user_input": "test"},
    )

    assert execution_id is not None
    assert len(execution_id) > 0


@pytest.mark.asyncio
async def test_execute_simple_workflow(workflow_engine):
    """Test executing a simple single-task workflow"""
    spec = {
        "tasks": {
            "summarize": {
                "type": "llm",
                "prompt": "Generate a summary",
                "model": "gpt-4",
            },
        },
        "dependencies": {},
    }

    await workflow_engine.create_workflow(
        workflow_id="simple_workflow",
        spec_json=spec,
    )

    execution_id = await workflow_engine.start_execution(
        workflow_id="simple_workflow",
        input_data={},
    )

    result = await workflow_engine.execute_workflow(execution_id)

    assert result["status"] == "succeeded"
    assert "summarize" in result["output"]
    assert result["output"]["summarize"]["content"] == "This is a fake summary"


@pytest.mark.asyncio
async def test_execute_multi_task_workflow(workflow_engine):
    """Test executing a multi-task workflow with dependencies"""
    spec = {
        "tasks": {
            "task_a": {
                "type": "llm",
                "prompt": "Generate a summary",
            },
            "task_b": {
                "type": "llm",
                "prompt": "Translate to Spanish",
            },
            "task_c": {
                "type": "tool",
                "tool_name": "search_database",
                "parameters": {},
            },
        },
        "dependencies": {
            "task_b": ["task_a"],
            "task_c": ["task_a", "task_b"],
        },
    }

    await workflow_engine.create_workflow(
        workflow_id="multi_task_workflow",
        spec_json=spec,
    )

    execution_id = await workflow_engine.start_execution(
        workflow_id="multi_task_workflow",
        input_data={},
    )

    result = await workflow_engine.execute_workflow(execution_id)

    assert result["status"] == "succeeded"
    assert "task_a" in result["output"]
    assert "task_b" in result["output"]
    assert "task_c" in result["output"]


@pytest.mark.asyncio
async def test_task_failure_skips_dependents(workflow_engine):
    """Test that when a task fails, dependent tasks are skipped"""
    # Configure fake provider to fail on specific task
    workflow_engine.llm_provider.responses["failing_task"] = None  # Trigger error

    spec = {
        "tasks": {
            "task_a": {
                "type": "llm",
                "prompt": "failing_task",  # Will fail
            },
            "task_b": {
                "type": "llm",
                "prompt": "Generate a summary",
            },
        },
        "dependencies": {
            "task_b": ["task_a"],
        },
        "max_retries": 0,  # Disable retries
    }

    await workflow_engine.create_workflow(
        workflow_id="failing_workflow",
        spec_json=spec,
    )

    execution_id = await workflow_engine.start_execution(
        workflow_id="failing_workflow",
        input_data={},
    )

    with pytest.raises(RuntimeError):
        await workflow_engine.execute_workflow(execution_id)


@pytest.mark.asyncio
async def test_get_execution_status(workflow_engine):
    """Test retrieving execution status"""
    spec = {
        "tasks": {
            "task1": {"type": "llm", "prompt": "Generate a summary"},
        },
        "dependencies": {},
    }

    await workflow_engine.create_workflow(
        workflow_id="status_test_workflow",
        spec_json=spec,
    )

    execution_id = await workflow_engine.start_execution(
        workflow_id="status_test_workflow",
        input_data={},
    )

    await workflow_engine.execute_workflow(execution_id)

    status = await workflow_engine.get_execution_status(execution_id)

    assert status["execution_id"] == execution_id
    assert status["status"] == "succeeded"
    assert "task1" in status["tasks"]
    assert status["tasks"]["task1"]["status"] == "succeeded"


# ============================================================================
# State Machine Tests
# ============================================================================


def test_workflow_state_transitions():
    """Test valid workflow state transitions"""
    sm = WorkflowStateMachine()

    # Valid transitions
    assert sm.can_transition("pending", "running", "workflow") is True
    assert sm.can_transition("running", "succeeded", "workflow") is True
    assert sm.can_transition("running", "failed", "workflow") is True

    # Invalid transitions
    assert sm.can_transition("succeeded", "running", "workflow") is False
    assert sm.can_transition("pending", "succeeded", "workflow") is False


def test_task_state_transitions():
    """Test valid task state transitions"""
    sm = WorkflowStateMachine()

    # Valid transitions
    assert sm.can_transition("pending", "running", "task") is True
    assert sm.can_transition("running", "succeeded", "task") is True
    assert sm.can_transition("running", "retrying", "task") is True
    assert sm.can_transition("retrying", "running", "task") is True

    # Invalid transitions
    assert sm.can_transition("succeeded", "running", "task") is False


def test_validate_transition_raises():
    """Test that validate_transition raises on invalid transition"""
    sm = WorkflowStateMachine()

    with pytest.raises(ValueError, match="Invalid.*state transition"):
        sm.validate_transition("succeeded", "running", "workflow")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
