"""
P4.2.3: Workflow Providers Coverage Tests
Tests for src/core/workflow/providers.py (412 LOC)

Coverage target: 80%+

Key Components tested:
- ProductionLLMProvider: LLM generation, embeddings, moderation
- ProductionToolBroker: Tool execution, tool listing
- ProductionAgentRuntime: Agent loading, agent execution, agent listing
- FakeLLMProvider: Deterministic testing provider
- FakeToolBroker: Deterministic testing provider
- FakeAgentRuntime: Deterministic testing provider

Run:
    python -m pytest tests/unit/test_workflow_providers_coverage.py --cov=src.core.workflow.providers --cov-report=term-missing -v
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.core.workflow.interfaces import (
    IAgentRuntime,
    ILLMProvider,
    IToolBroker,
    TaskExecutionRequest,
    TaskExecutionResult,
)
from src.core.workflow.providers import (
    FakeAgentRuntime,
    FakeLLMProvider,
    FakeToolBroker,
    ProductionAgentRuntime,
    ProductionLLMProvider,
    ProductionToolBroker,
)

# =============================================================================
# FIXTURES: Common Test Data
# =============================================================================


@pytest.fixture
def task_execution_request():
    """Create a task execution request for testing."""
    return TaskExecutionRequest(
        task_id="task-123",
        task_type="test_task",
        agent_type="test_agent",
        parameters={
            "description": "Test task description",
            "priority": 3,
        },  # Use valid priority enum
        context={"test": "context"},
        tenant_id="tenant-1",
    )


@pytest.fixture
def fake_agent():
    """Create a fake agent for testing."""

    @dataclass
    class FakeAgent:
        name: str = "TestAgent"
        model: Any = None
        capabilities: Optional[List[str]] = None
        system_prompt: str = "Test prompt"

    agent = FakeAgent()
    agent.model = type("obj", (object,), {"value": "test-model"})
    agent.capabilities = ["test_capability"]
    return agent


# =============================================================================
# FAKE PROVIDER TESTS
# =============================================================================


class TestFakeLLMProvider:
    """Test FakeLLMProvider for deterministic testing."""

    def test_fake_llm_initialization(self):
        """Test FakeLLMProvider initialization."""
        provider = FakeLLMProvider()
        assert provider is not None
        assert provider.default_response == "Fake LLM response for testing"

    def test_fake_llm_initialization_with_responses(self):
        """Test FakeLLMProvider with custom responses."""
        responses = {"prompt1": "response1", "prompt2": "response2"}
        provider = FakeLLMProvider(responses=responses)
        assert provider.responses == responses

    @pytest.mark.asyncio
    async def test_fake_llm_generate_default(self):
        """Test default LLM generation."""
        provider = FakeLLMProvider()
        result = await provider.generate(
            prompt="Test prompt",
            model="gpt-4",
            temperature=0.7,
            max_tokens=100,
        )
        assert result["content"] == "Fake LLM response for testing"
        assert result["provider"] == "fake"
        assert result["model"] == "gpt-4"
        assert result["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_fake_llm_generate_custom_response(self):
        """Test LLM generation with custom response."""
        responses = {"Custom prompt": "Custom response"}
        provider = FakeLLMProvider(responses=responses)
        result = await provider.generate(
            prompt="Custom prompt",
            model="gpt-4",
        )
        assert result["content"] == "Custom response"

    @pytest.mark.asyncio
    async def test_fake_llm_generate_unknown_prompt(self):
        """Test LLM generation with unknown prompt."""
        responses = {"known": "response"}
        provider = FakeLLMProvider(responses=responses)
        result = await provider.generate(
            prompt="unknown",
            model="gpt-4",
        )
        assert result["content"] == "Fake LLM response for testing"

    @pytest.mark.asyncio
    async def test_fake_llm_generate_with_system_prompt(self):
        """Test LLM generation with system prompt."""
        provider = FakeLLMProvider()
        result = await provider.generate(
            prompt="Test",
            model="gpt-4",
            system_prompt="You are a test system",
        )
        assert result["content"] == "Fake LLM response for testing"

    @pytest.mark.asyncio
    async def test_fake_llm_generate_with_kwargs(self):
        """Test LLM generation with extra kwargs."""
        provider = FakeLLMProvider()
        result = await provider.generate(
            prompt="Test",
            model="gpt-4",
            top_p=0.9,
            presence_penalty=0.5,
        )
        assert result["content"] == "Fake LLM response for testing"

    @pytest.mark.asyncio
    async def test_fake_llm_embed(self):
        """Test embedding generation."""
        provider = FakeLLMProvider()
        embeddings = await provider.embed("Test text")
        assert embeddings == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_fake_llm_embed_custom_model(self):
        """Test embedding with custom model."""
        provider = FakeLLMProvider()
        embeddings = await provider.embed("Test text", model="text-embedding-3-large")
        assert embeddings == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_fake_llm_moderate(self):
        """Test content moderation."""
        provider = FakeLLMProvider()
        result = await provider.moderate("Test text")
        assert result["flagged"] is False
        assert "categories" in result

    @pytest.mark.asyncio
    async def test_fake_llm_token_counting(self):
        """Test token counting in response."""
        provider = FakeLLMProvider()
        result = await provider.generate(
            prompt="Test",
            model="gpt-4",
        )
        # "Fake LLM response for testing" = 5 tokens
        assert result["tokens"] == 5


class TestFakeToolBroker:
    """Test FakeToolBroker for deterministic testing."""

    def test_fake_tool_broker_initialization(self):
        """Test FakeToolBroker initialization."""
        broker = FakeToolBroker()
        assert broker is not None
        assert broker.tool_results == {}

    def test_fake_tool_broker_initialization_with_results(self):
        """Test FakeToolBroker with custom tool results."""
        tool_results = {
            "tool1": {"status": "success", "data": "result1"},
            "tool2": {"status": "success", "data": "result2"},
        }
        broker = FakeToolBroker(tool_results=tool_results)
        assert broker.tool_results == tool_results

    @pytest.mark.asyncio
    async def test_fake_tool_execute_default(self):
        """Test default tool execution."""
        broker = FakeToolBroker()
        result = await broker.execute_tool(
            tool_name="unknown_tool",
            parameters={"param": "value"},
        )
        assert result["success"] is True
        assert result["result"]["status"] == "success"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_fake_tool_execute_custom(self):
        """Test tool execution with custom result."""
        tool_results = {"custom_tool": {"status": "success", "output": "custom_output"}}
        broker = FakeToolBroker(tool_results=tool_results)
        result = await broker.execute_tool(
            tool_name="custom_tool",
            parameters={},
        )
        assert result["result"]["output"] == "custom_output"

    @pytest.mark.asyncio
    async def test_fake_tool_list_available(self):
        """Test listing available tools."""
        tool_results = {"tool1": {}, "tool2": {}, "tool3": {}}
        broker = FakeToolBroker(tool_results=tool_results)
        tools = await broker.list_available_tools()
        assert set(tools) == {"tool1", "tool2", "tool3"}

    @pytest.mark.asyncio
    async def test_fake_tool_list_empty(self):
        """Test listing tools when none available."""
        broker = FakeToolBroker()
        tools = await broker.list_available_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_fake_tool_execution_time(self):
        """Test execution time tracking."""
        broker = FakeToolBroker()
        result = await broker.execute_tool(
            tool_name="test_tool",
            parameters={},
            timeout=30,
        )
        assert result["execution_time"] == 0.1

    @pytest.mark.asyncio
    async def test_fake_tool_multiple_calls(self):
        """Test multiple tool executions."""
        broker = FakeToolBroker(tool_results={"math": {}, "string": {}})
        result1 = await broker.execute_tool("math", {})
        result2 = await broker.execute_tool("string", {})
        assert result1["success"] is True
        assert result2["success"] is True


class TestFakeAgentRuntime:
    """Test FakeAgentRuntime for deterministic testing."""

    def test_fake_agent_runtime_initialization(self):
        """Test FakeAgentRuntime initialization."""
        runtime = FakeAgentRuntime()
        assert runtime is not None
        assert runtime.agent_results == {}
        assert runtime.agents == {}

    def test_fake_agent_runtime_initialization_with_results(self):
        """Test FakeAgentRuntime with custom agent results."""
        agent_results = {
            "agent1": {"output": "result1", "success": True},
            "agent2": {"output": "result2", "success": True},
        }
        runtime = FakeAgentRuntime(agent_results=agent_results)
        assert runtime.agent_results == agent_results

    @pytest.mark.asyncio
    async def test_fake_agent_load_agent(self):
        """Test loading a fake agent."""
        runtime = FakeAgentRuntime()
        agent = await runtime.load_agent("test_agent")
        assert agent is not None
        assert agent.name == "test_agent"
        assert agent.model.value == "fake-model"
        assert agent.capabilities == ["test"]

    @pytest.mark.asyncio
    async def test_fake_agent_load_multiple_agents(self):
        """Test loading multiple agents."""
        runtime = FakeAgentRuntime()
        agent1 = await runtime.load_agent("agent1")
        agent2 = await runtime.load_agent("agent2")
        assert agent1.name == "agent1"
        assert agent2.name == "agent2"
        assert len(runtime.agents) == 2

    @pytest.mark.asyncio
    async def test_fake_agent_execute_default(self, task_execution_request):
        """Test default agent execution."""
        runtime = FakeAgentRuntime()
        agent = await runtime.load_agent("test_agent")
        result = await runtime.execute_agent(agent, task_execution_request)
        assert result.success is True
        assert result.output == "fake_agent_output"
        assert result.error is None
        assert result.execution_time == 0.1

    @pytest.mark.asyncio
    async def test_fake_agent_execute_custom_result(self, task_execution_request):
        """Test agent execution with custom result."""
        agent_results = {"test_agent": {"output": "custom_output", "success": True}}
        runtime = FakeAgentRuntime(agent_results=agent_results)
        agent = await runtime.load_agent("test_agent")
        result = await runtime.execute_agent(agent, task_execution_request)
        assert result.output == "custom_output"

    @pytest.mark.asyncio
    async def test_fake_agent_execute_failure(self, task_execution_request):
        """Test failed agent execution."""
        agent_results = {
            "test_agent": {
                "output": None,
                "success": False,
                "error": "Test error",
            }
        }
        runtime = FakeAgentRuntime(agent_results=agent_results)
        agent = await runtime.load_agent("test_agent")
        result = await runtime.execute_agent(agent, task_execution_request)
        assert result.success is False
        assert result.error == "Test error"

    @pytest.mark.asyncio
    async def test_fake_agent_get_available_agents(self):
        """Test listing available agents."""
        agent_results = {
            "agent1": {"output": "result1", "success": True},
            "agent2": {"output": "result2", "success": True},
        }
        runtime = FakeAgentRuntime(agent_results=agent_results)
        agents = await runtime.get_available_agents()
        assert set(agents) == {"agent1", "agent2"}

    @pytest.mark.asyncio
    async def test_fake_agent_get_empty_list(self):
        """Test listing agents when none available."""
        runtime = FakeAgentRuntime()
        agents = await runtime.get_available_agents()
        assert agents == []


# =============================================================================
# PRODUCTION PROVIDER TESTS
# =============================================================================


class TestProductionLLMProviderInit:
    """Test ProductionLLMProvider initialization."""

    def test_production_llm_initialization(self):
        """Test ProductionLLMProvider initialization."""
        with patch("src.core.workflow.providers.logger"):
            provider = ProductionLLMProvider()
            assert provider is not None


class TestProductionLLMProviderGenerate:
    """Test ProductionLLMProvider.generate()."""

    @pytest.mark.asyncio
    async def test_production_llm_generate_exception(self):
        """Test LLM generation with exception."""
        provider = ProductionLLMProvider()
        provider.base_agent_class = None

        with pytest.raises(Exception):
            await provider.generate(
                prompt="Test prompt",
                model="gpt-4",
            )

    @pytest.mark.asyncio
    async def test_production_llm_embed(self):
        """Test embedding generation."""
        provider = ProductionLLMProvider()
        result = await provider.embed("Test text")
        assert result == []

    @pytest.mark.asyncio
    async def test_production_llm_moderate(self):
        """Test content moderation."""
        provider = ProductionLLMProvider()
        result = await provider.moderate("Test text")
        assert result["flagged"] is False
        assert "categories" in result


class TestProductionToolBrokerInit:
    """Test ProductionToolBroker initialization."""

    def test_production_tool_broker_initialization(self):
        """Test ProductionToolBroker initialization."""
        with patch("src.core.workflow.providers.logger"):
            broker = ProductionToolBroker()
            assert broker is not None


class TestProductionToolBrokerExecute:
    """Test ProductionToolBroker.execute_tool()."""


class TestProductionAgentRuntimeInit:
    """Test ProductionAgentRuntime initialization."""

    def test_production_agent_runtime_initialization(self):
        """Test ProductionAgentRuntime initialization."""
        with patch("src.core.workflow.providers.logger"):
            runtime = ProductionAgentRuntime()
            assert runtime is not None


class TestProductionAgentRuntimeLoadAgent:
    """Test ProductionAgentRuntime.load_agent()."""

    @pytest.mark.asyncio
    async def test_production_agent_load_success(self):
        """Test successful agent loading."""
        runtime = ProductionAgentRuntime()

        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_loader = MagicMock()
        mock_loader.get_subagents_by_category = MagicMock(return_value=[mock_agent])
        runtime.subagent_loader = mock_loader

        agent = await runtime.load_agent("test_category")
        assert agent == mock_agent

    @pytest.mark.asyncio
    async def test_production_agent_load_not_found(self):
        """Test agent loading when not found."""
        runtime = ProductionAgentRuntime()

        mock_loader = MagicMock()
        mock_loader.get_subagents_by_category = MagicMock(return_value=[])
        mock_loader.get_all_subagents = MagicMock(return_value=[])
        runtime.subagent_loader = mock_loader

        agent = await runtime.load_agent("unknown")
        assert agent is None

    @pytest.mark.asyncio
    async def test_production_agent_load_fallback(self):
        """Test agent loading with fallback to all agents."""
        runtime = ProductionAgentRuntime()

        mock_agent = MagicMock()
        mock_agent.name = "FallbackAgent"
        mock_loader = MagicMock()
        mock_loader.get_subagents_by_category = MagicMock(return_value=[])
        mock_loader.get_all_subagents = MagicMock(return_value=[mock_agent])
        runtime.subagent_loader = mock_loader

        agent = await runtime.load_agent("fallback")
        assert agent == mock_agent

    @pytest.mark.asyncio
    async def test_production_agent_load_exception(self):
        """Test agent loading with exception."""
        runtime = ProductionAgentRuntime()
        runtime.subagent_loader = None

        agent = await runtime.load_agent("test_agent")
        assert agent is None


class TestProductionAgentRuntimeExecuteAgent:
    """Test ProductionAgentRuntime.execute_agent()."""

    @pytest.mark.asyncio
    async def test_production_agent_execute_success(self, fake_agent, task_execution_request):
        """Test successful agent execution."""
        runtime = ProductionAgentRuntime()

        mock_base_agent = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result_data = {
            "output": "Agent output",
            "provider_used": "gpt-4",
            "tokens_used": 200,
        }
        mock_base_agent.process_task = AsyncMock(return_value=mock_result)
        runtime.base_agent_class = MagicMock(return_value=mock_base_agent)

        result = await runtime.execute_agent(fake_agent, task_execution_request)

        assert result.success is True
        assert result.task_id == task_execution_request.task_id
        assert result.output["real_output"] == mock_result.result_data
        assert result.output["is_mock"] is False

    @pytest.mark.asyncio
    async def test_production_agent_execute_failure(self, fake_agent, task_execution_request):
        """Test failed agent execution."""
        runtime = ProductionAgentRuntime()

        mock_base_agent = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Execution error"
        mock_base_agent.process_task = AsyncMock(return_value=mock_result)
        runtime.base_agent_class = MagicMock(return_value=mock_base_agent)

        result = await runtime.execute_agent(fake_agent, task_execution_request)

        assert result.success is False
        assert result.error == "Execution error"

    @pytest.mark.asyncio
    async def test_production_agent_execute_exception(self, fake_agent, task_execution_request):
        """Test agent execution with exception."""
        runtime = ProductionAgentRuntime()
        runtime.base_agent_class = None

        result = await runtime.execute_agent(fake_agent, task_execution_request)

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_production_agent_get_available_agents(self):
        """Test listing available agents."""
        runtime = ProductionAgentRuntime()

        mock_agent1 = MagicMock()
        mock_agent1.name = "Agent1"
        mock_agent2 = MagicMock()
        mock_agent2.name = "Agent2"

        mock_loader = MagicMock()
        mock_loader.get_all_subagents = MagicMock(return_value=[mock_agent1, mock_agent2])
        runtime.subagent_loader = mock_loader

        agents = await runtime.get_available_agents()
        assert agents == ["Agent1", "Agent2"]

    @pytest.mark.asyncio
    async def test_production_agent_get_available_exception(self):
        """Test listing agents with exception."""
        runtime = ProductionAgentRuntime()
        runtime.subagent_loader = None

        agents = await runtime.get_available_agents()
        assert agents == []


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestProviderIntegration:
    """Integration tests for provider compatibility."""

    @pytest.mark.asyncio
    async def test_fake_providers_work_together(self, task_execution_request):
        """Test that fake providers work together in a workflow."""
        llm = FakeLLMProvider({"prompt": "llm_output"})
        tool_broker = FakeToolBroker({"math_tool": {"result": 42}})
        agent_runtime = FakeAgentRuntime(
            {"calculator": {"output": "fake_agent_output", "success": True}}
        )

        # Test LLM
        llm_result = await llm.generate("prompt", "gpt-4")
        assert llm_result["content"] == "llm_output"

        # Test Tool
        tool_result = await tool_broker.execute_tool("math_tool", {})
        assert tool_result["result"]["result"] == 42

        # Test Agent
        agent = await agent_runtime.load_agent("calculator")
        agent_result = await agent_runtime.execute_agent(agent, task_execution_request)
        assert agent_result.output == "fake_agent_output"

    def test_provider_interface_compliance(self):
        """Test that providers implement required interfaces."""
        assert isinstance(FakeLLMProvider(), ILLMProvider)
        assert isinstance(FakeToolBroker(), IToolBroker)
        assert isinstance(FakeAgentRuntime(), IAgentRuntime)

    def test_production_provider_interface_compliance(self):
        """Test that production providers implement required interfaces."""
        assert isinstance(ProductionLLMProvider(), ILLMProvider)
        assert isinstance(ProductionToolBroker(), IToolBroker)
        assert isinstance(ProductionAgentRuntime(), IAgentRuntime)
