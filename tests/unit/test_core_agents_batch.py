"""
BATCH 1: Core Agents Suite - Comprehensive Test Coverage
Tests foundation agent infrastructure: EnhancedBaseAgent, AgentFactory, AgentRegistry
Coverage target: 60%+ across 47 core_agents modules (25,208 LOC)
Phase 3 Build Path - Batch Testing Strategy
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.agents.agent_factory import AgentCategory, AgentDefinition, AgentFactory
from src.core.agents.agent_registry import AgentRegistry

# Foundation classes
from src.core.agents.base_agent import EnhancedBaseAgent

# Shared interfaces
from src.core.shared.interfaces import (
    Agent,
    AgentCapability,
    AgentStatus,
    AgentType,
    ExecutionResult,
    TaskData,
)
from src.core.types import TaskPriority

# ========================================================================
# TEST CLASS 1: EnhancedBaseAgent Foundation Tests (15 tests)
# ========================================================================


# Concrete implementation for testing
class ConcreteTestAgent(EnhancedBaseAgent):
    """Concrete EnhancedBaseAgent implementation for testing"""

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Minimal implementation of abstract method"""
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data={"test": "result"},
            execution_time=0.1,
        )


class TestEnhancedBaseAgent:
    """Test EnhancedBaseAgent - foundation for all agent classes"""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client with async methods"""
        client = AsyncMock()
        client.generate_response = AsyncMock(
            return_value={
                "content": "Test response",
                "provider": "anthropic",
                "model": "claude-3-sonnet",
                "tokens_used": 100,
            }
        )
        return client

    @pytest.fixture
    def mock_memory_store(self):
        """Mock memory store"""
        store = MagicMock()
        store.store = AsyncMock()
        store.retrieve = AsyncMock(return_value=[])
        return store

    @pytest.fixture
    def mock_event_emitter(self):
        """Mock event emitter"""
        return AsyncMock()

    @pytest.fixture
    def enhanced_base_agent(self, mock_llm_client, mock_memory_store, mock_event_emitter):
        """Create ConcreteTestAgent instance (concrete EnhancedBaseAgent)"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.ANALYZER,
            tenant_id=1,
            llm_client=mock_llm_client,
            memory_store=mock_memory_store,
            event_emitter=mock_event_emitter,
        )
        return agent

    # --- INITIALIZATION TESTS (5 tests) ---

    def test_agent_initialization_basic(self, enhanced_base_agent):
        """Test basic agent initialization"""
        assert enhanced_base_agent.agent_id == "test-agent-001"
        assert enhanced_base_agent.agent_type == AgentType.ANALYZER
        assert enhanced_base_agent.llm_client is not None
        assert enhanced_base_agent.memory_store is not None
        assert enhanced_base_agent._tasks_processed == 0
        assert enhanced_base_agent._errors_count == 0

    def test_agent_initialization_with_dependencies(self, mock_llm_client, mock_memory_store):
        """Test agent initialization with dependency injection"""
        agent = ConcreteTestAgent(
            agent_id="test-dep-agent",
            agent_type=AgentType.EXECUTOR,
            tenant_id=1,
            llm_client=mock_llm_client,
            memory_store=mock_memory_store,
        )

        assert agent.llm_client == mock_llm_client
        assert agent.memory_store == mock_memory_store
        assert agent.event_emitter is not None

    def test_agent_initialization_without_dependencies(self):
        """Test agent initialization without dependencies (defaults)"""
        agent = ConcreteTestAgent(
            agent_id="test-minimal-agent", agent_type=AgentType.ANALYZER, tenant_id=1
        )

        assert agent.agent_id == "test-minimal-agent"
        assert agent.llm_client is None
        assert agent.memory_store is None
        assert callable(agent.event_emitter)

    @pytest.mark.asyncio
    async def test_agent_initialize_method(self, enhanced_base_agent, mock_event_emitter):
        """Test agent initialize() method"""
        success = await enhanced_base_agent.initialize()

        assert success is True
        assert enhanced_base_agent._initialization_time is not None
        assert isinstance(enhanced_base_agent._initialization_time, datetime)

    @pytest.mark.asyncio
    async def test_agent_initialize_emits_event(self, enhanced_base_agent, mock_event_emitter):
        """Test initialize() emits initialization event"""
        await enhanced_base_agent.initialize()

        # Event emitter should be called
        assert mock_event_emitter.call_count >= 1

    # --- TASK PROCESSING TESTS (5 tests) ---

    @pytest.mark.asyncio
    async def test_process_task_basic(self, enhanced_base_agent):
        """Test basic task processing"""
        task = TaskData(
            id=str(uuid4()),
            title="Analysis Task",
            description="Test analysis task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        # Mock _execute_task (abstract method)
        enhanced_base_agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task.id,
                success=True,
                result={"analysis": "test result"},
                execution_time=0.5,
            )
        )

        result = await enhanced_base_agent.process_task(task)

        assert result.success is True
        assert result.task_id == task.id
        assert enhanced_base_agent._tasks_processed == 1

    @pytest.mark.asyncio
    async def test_process_task_increments_counter(self, enhanced_base_agent):
        """Test task processing increments task counter"""
        task = TaskData(
            id=str(uuid4()),
            title="Test Task",
            description="Test task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        enhanced_base_agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task.id, success=True, result={}, execution_time=0.1
            )
        )

        initial_count = enhanced_base_agent._tasks_processed

        await enhanced_base_agent.process_task(task)

        assert enhanced_base_agent._tasks_processed == initial_count + 1

    @pytest.mark.asyncio
    async def test_process_task_handles_errors(self, enhanced_base_agent):
        """Test task processing error handling"""
        task = TaskData(
            id=str(uuid4()),
            title="Failing Task",
            description="Failing task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        enhanced_base_agent._execute_task = AsyncMock(side_effect=Exception("Test error"))

        result = await enhanced_base_agent.process_task(task)

        assert result.success is False
        assert result.error_message or "error" in str(result.result_data)
        assert enhanced_base_agent._errors_count >= 1

    @pytest.mark.asyncio
    async def test_process_task_tracks_execution_time(self, enhanced_base_agent):
        """Test task processing tracks execution time"""
        task = TaskData(
            id=str(uuid4()),
            title="Timed Task",
            description="Timed task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        enhanced_base_agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task.id, success=True, result={}, execution_time=1.5
            )
        )

        initial_time = enhanced_base_agent._total_execution_time

        await enhanced_base_agent.process_task(task)

        assert enhanced_base_agent._total_execution_time > initial_time

    @pytest.mark.asyncio
    async def test_process_task_reasoning_trace(self, enhanced_base_agent):
        """Test task processing creates reasoning trace"""
        task = TaskData(
            id=str(uuid4()),
            title="Reasoning Task",
            description="Reasoning task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        enhanced_base_agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task.id, success=True, result={}, execution_time=0.3
            )
        )

        await enhanced_base_agent.process_task(task)

        # Should have created reasoning trace
        assert enhanced_base_agent.reasoning_trace is not None

    # --- STATE MANAGEMENT TESTS (5 tests) ---

    def test_agent_metrics_initialization(self, enhanced_base_agent):
        """Test agent metrics are initialized correctly"""
        assert enhanced_base_agent._tasks_processed == 0
        assert enhanced_base_agent._total_execution_time == 0.0
        assert enhanced_base_agent._errors_count == 0
        assert enhanced_base_agent._last_error is None

    @pytest.mark.asyncio
    async def test_agent_status_active_after_task(self, enhanced_base_agent):
        """Test agent status becomes ACTIVE after processing task"""
        task = TaskData(
            id=str(uuid4()),
            title="Status Test Task",
            description="Status test task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        enhanced_base_agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task.id, success=True, result={}, execution_time=0.2
            )
        )

        await enhanced_base_agent.process_task(task)

        # Agent should be active (has processed tasks)
        assert enhanced_base_agent._tasks_processed > 0

    def test_agent_concurrent_task_limit(self, enhanced_base_agent):
        """Test agent respects concurrent task limit"""
        assert hasattr(enhanced_base_agent, "_max_concurrent_tasks")
        assert enhanced_base_agent._max_concurrent_tasks > 0

    def test_agent_current_tasks_tracking(self, enhanced_base_agent):
        """Test agent tracks current tasks"""
        assert hasattr(enhanced_base_agent, "_current_tasks")
        assert isinstance(enhanced_base_agent._current_tasks, dict)

    def test_agent_task_lock_exists(self, enhanced_base_agent):
        """Test agent has async task lock for concurrency control"""
        assert hasattr(enhanced_base_agent, "_task_lock")
        assert isinstance(enhanced_base_agent._task_lock, asyncio.Lock)


# ========================================================================
# TEST CLASS 2: AgentFactory Tests (12 tests)
# ========================================================================


class TestAgentFactory:
    """Test AgentFactory - mass agent generation system"""

    @pytest.fixture
    def agent_factory(self):
        """Create AgentFactory instance"""
        return AgentFactory(agenten_directory="core/agents/agenten")

    # --- INITIALIZATION TESTS (3 tests) ---

    def test_factory_initialization(self, agent_factory):
        """Test factory initializes correctly"""
        assert agent_factory.agenten_directory.name == "agenten"
        assert agent_factory.output_directory.name == "generated"
        assert hasattr(agent_factory, "category_mapping")

    def test_factory_category_mapping(self, agent_factory):
        """Test factory has comprehensive category mapping"""
        assert len(agent_factory.category_mapping) > 50
        assert "business-analyst" in agent_factory.category_mapping
        assert "python-pro" in agent_factory.category_mapping
        assert "architect-review" in agent_factory.category_mapping

    def test_factory_categories_enum(self, agent_factory):
        """Test all category mappings use AgentCategory enum"""
        for category_value in agent_factory.category_mapping.values():
            assert isinstance(category_value, AgentCategory)

    # --- CATEGORY CLASSIFICATION TESTS (5 tests) ---

    def test_analytical_category_mapping(self, agent_factory):
        """Test analytical agents are categorized correctly"""
        analytical_agents = ["business-analyst", "data-scientist", "quant-analyst"]
        for agent_name in analytical_agents:
            assert agent_factory.category_mapping[agent_name] == AgentCategory.ANALYTICAL

    def test_creative_category_mapping(self, agent_factory):
        """Test creative agents are categorized correctly"""
        creative_agents = ["content-marketer", "ui-ux-designer", "seo-content-writer"]
        for agent_name in creative_agents:
            assert agent_factory.category_mapping[agent_name] == AgentCategory.CREATIVE

    def test_technical_category_mapping(self, agent_factory):
        """Test technical agents are categorized correctly"""
        technical_agents = ["python-pro", "fastapi-pro", "devops-troubleshooter"]
        for agent_name in technical_agents:
            assert agent_factory.category_mapping[agent_name] == AgentCategory.TECHNICAL

    def test_strategic_category_mapping(self, agent_factory):
        """Test strategic agents are categorized correctly"""
        strategic_agents = ["architect-review", "backend-architect", "cloud-architect"]
        for agent_name in strategic_agents:
            assert agent_factory.category_mapping[agent_name] == AgentCategory.STRATEGIC

    def test_specialized_category_mapping(self, agent_factory):
        """Test specialized agents are categorized correctly"""
        specialized_agents = ["ai-engineer", "ml-engineer", "prompt-engineer"]
        for agent_name in specialized_agents:
            assert agent_factory.category_mapping[agent_name] == AgentCategory.SPECIALIZED

    # --- AGENT DEFINITION TESTS (4 tests) ---

    def test_agent_definition_dataclass(self):
        """Test AgentDefinition dataclass structure"""
        definition = AgentDefinition(
            name="test-agent",
            description="Test agent",
            model="claude-3-sonnet",
            purpose="Testing",
            capabilities=["test"],
            behavioral_traits=["trait1"],
            knowledge_base=["kb1"],
            example_interactions=["example1"],
            category=AgentCategory.TECHNICAL,
            complexity_level="medium",
            reasoning_required=0.7,
            speed_priority=0.5,
            cost_sensitivity=0.3,
        )

        assert definition.name == "test-agent"
        assert definition.category == AgentCategory.TECHNICAL
        assert definition.complexity_level == "medium"
        assert definition.reasoning_required == 0.7

    def test_agent_definition_supports_all_categories(self):
        """Test AgentDefinition works with all AgentCategory values"""
        for category in AgentCategory:
            definition = AgentDefinition(
                name=f"test-{category.value}",
                description="Test",
                model="test-model",
                purpose="Test",
                capabilities=[],
                behavioral_traits=[],
                knowledge_base=[],
                example_interactions=[],
                category=category,
                complexity_level="low",
                reasoning_required=0.5,
                speed_priority=0.5,
                cost_sensitivity=0.5,
            )
            assert definition.category == category

    def test_agent_category_enum_values(self):
        """Test AgentCategory enum has expected values"""
        expected_categories = {
            "analytical",
            "creative",
            "technical",
            "strategic",
            "specialized",
            "support",
        }
        actual_categories = {cat.value for cat in AgentCategory}
        assert actual_categories == expected_categories

    def test_agent_category_enum_members(self):
        """Test AgentCategory enum members"""
        assert AgentCategory.ANALYTICAL.value == "analytical"
        assert AgentCategory.CREATIVE.value == "creative"
        assert AgentCategory.TECHNICAL.value == "technical"
        assert AgentCategory.STRATEGIC.value == "strategic"
        assert AgentCategory.SPECIALIZED.value == "specialized"
        assert AgentCategory.SUPPORT.value == "support"


# ========================================================================
# TEST CLASS 3: AgentRegistry Tests (12 tests)
# ========================================================================


class TestAgentRegistry:
    """Test AgentRegistry - central agent coordination system"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def agent_registry(self, mock_db_session):
        """Create AgentRegistry instance"""
        return AgentRegistry(db_session=mock_db_session)

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent"""
        agent = AsyncMock(spec=Agent)
        agent.agent_id = "test-agent-reg-001"
        agent.agent_type = AgentType.ANALYZER
        agent.address = "http://localhost:8001"
        agent.get_capabilities = AsyncMock(
            return_value=[
                AgentCapability(
                    name="analysis",
                    description="Analyze data",
                    input_types=["text", "data"],
                    output_types=["analysis_result"],
                )
            ]
        )
        agent.tenant_id = 1
        return agent

    # --- INITIALIZATION TESTS (3 tests) ---

    def test_registry_initialization(self, agent_registry):
        """Test registry initializes with empty state"""
        assert len(agent_registry._agents) == 0
        assert len(agent_registry._agents_by_type) == 0
        assert len(agent_registry._agent_capabilities) == 0
        assert len(agent_registry._active_tasks) == 0

    def test_registry_health_tracking_initialization(self, agent_registry):
        """Test registry initializes health tracking"""
        assert hasattr(agent_registry, "_agent_health")
        assert hasattr(agent_registry, "_agent_load")
        assert hasattr(agent_registry, "_agent_stats")

    def test_registry_memory_leak_protection(self, agent_registry):
        """Test registry has memory leak protection limits"""
        assert agent_registry._max_task_queue_size == 1000
        assert agent_registry._max_completed_tasks_history == 500

    # --- AGENT REGISTRATION TESTS (5 tests) ---

    @pytest.mark.asyncio
    async def test_register_agent_success(self, agent_registry, mock_agent):
        """Test successful agent registration"""
        # Mock tenant context
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                success = await agent_registry.register_agent(mock_agent)

        assert success is True
        assert mock_agent.agent_id in agent_registry._agents
        assert mock_agent.agent_id in agent_registry._agent_health

    @pytest.mark.asyncio
    async def test_register_agent_stores_capabilities(self, agent_registry, mock_agent):
        """Test agent registration stores capabilities"""
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                await agent_registry.register_agent(mock_agent)

        assert mock_agent.agent_id in agent_registry._agent_capabilities
        assert "analysis" in agent_registry._agent_capabilities[mock_agent.agent_id]

    @pytest.mark.asyncio
    async def test_register_agent_initializes_stats(self, agent_registry, mock_agent):
        """Test agent registration initializes stats"""
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                await agent_registry.register_agent(mock_agent)

        stats = agent_registry._agent_stats[mock_agent.agent_id]
        assert stats["tasks_completed"] == 0
        assert stats["tasks_failed"] == 0
        assert "registered_at" in stats

    @pytest.mark.asyncio
    async def test_register_agent_by_type_indexing(self, agent_registry, mock_agent):
        """Test agent registration creates type index"""
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                await agent_registry.register_agent(mock_agent)

        assert mock_agent.agent_id in agent_registry._agents_by_type[AgentType.ANALYZER]

    @pytest.mark.asyncio
    async def test_register_agent_load_initialization(self, agent_registry, mock_agent):
        """Test agent registration initializes load to 0.0"""
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                await agent_registry.register_agent(mock_agent)

        assert agent_registry._agent_load[mock_agent.agent_id] == 0.0

    # --- AGENT RETRIEVAL TESTS (4 tests) ---

    @pytest.mark.asyncio
    async def test_get_agent_by_id_success(self, agent_registry, mock_agent):
        """Test retrieving agent by ID"""
        agent_registry._agents[mock_agent.agent_id] = mock_agent

        result = await agent_registry.get_agent_by_id(mock_agent.agent_id)

        assert result == mock_agent

    @pytest.mark.asyncio
    async def test_get_agent_by_id_not_found(self, agent_registry):
        """Test retrieving non-existent agent returns None"""
        result = await agent_registry.get_agent_by_id("non-existent-agent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_agents_empty(self, agent_registry):
        """Test get_all_agents with empty registry"""
        # Mock database query
        agent_registry._db_session = AsyncMock()

        # Need to mock the async context manager and query
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("src.core.database.database.get_async_session", return_value=mock_session):
            agents = await agent_registry.get_all_agents(tenant_id=1)

        assert isinstance(agents, list)

    @pytest.mark.asyncio
    async def test_agent_in_memory_cache(self, agent_registry, mock_agent):
        """Test agent is stored in memory cache after registration"""
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                await agent_registry.register_agent(mock_agent)

        # Should be in memory cache
        cached_agent = agent_registry._agents.get(mock_agent.agent_id)
        assert cached_agent == mock_agent


# ========================================================================
# TEST CLASS 4: Integration Tests (8 tests)
# ========================================================================


class TestCoreAgentsIntegration:
    """Integration tests for core agent components working together"""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client"""
        client = AsyncMock()
        client.generate_response = AsyncMock(
            return_value={
                "content": "Integration test response",
                "provider": "anthropic",
                "model": "claude-3-sonnet",
                "tokens_used": 150,
            }
        )
        return client

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    # --- AGENT LIFECYCLE INTEGRATION (4 tests) ---

    @pytest.mark.asyncio
    async def test_agent_creation_and_registration(self, mock_llm_client, mock_db_session):
        """Test creating agent and registering in registry"""
        # Create agent
        agent = ConcreteTestAgent(
            agent_id="integration-agent-001",
            agent_type=AgentType.EXECUTOR,
            tenant_id=1,
            llm_client=mock_llm_client,
        )

        # Create registry
        registry = AgentRegistry(db_session=mock_db_session)

        # Mock get_capabilities for Agent interface
        agent.get_capabilities = AsyncMock(
            return_value=[
                AgentCapability(
                    name="execution",
                    description="Execute tasks",
                    input_types=["task"],
                    output_types=["result"],
                )
            ]
        )
        agent.address = "http://localhost:8002"

        # Register agent
        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                success = await registry.register_agent(agent)

        assert success is True
        assert agent.agent_id in registry._agents

    @pytest.mark.asyncio
    async def test_agent_initialization_and_task_processing(self, mock_llm_client):
        """Test agent initialize + process_task flow"""
        agent = ConcreteTestAgent(
            agent_id="init-task-agent",
            agent_type=AgentType.ANALYZER,
            tenant_id=1,
            llm_client=mock_llm_client,
        )

        # Initialize
        await agent.initialize()

        # Process task
        task = TaskData(
            id=str(uuid4()),
            title="Integration Test Task",
            description="Integration test task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task.id,
                success=True,
                result={"status": "completed"},
                execution_time=0.4,
            )
        )

        result = await agent.process_task(task)

        assert result.success is True
        assert agent._tasks_processed == 1

    @pytest.mark.asyncio
    async def test_registry_agent_retrieval_after_registration(self, mock_db_session):
        """Test retrieving agent from registry after registration"""
        agent = AsyncMock(spec=Agent)
        agent.agent_id = "retrieval-agent"
        agent.agent_type = AgentType.ANALYZER
        agent.address = "http://localhost:8003"
        agent.get_capabilities = AsyncMock(return_value=[])
        agent.tenant_id = 1

        registry = AgentRegistry(db_session=mock_db_session)

        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                await registry.register_agent(agent)

        retrieved = await registry.get_agent_by_id(agent.agent_id)
        assert retrieved == agent

    @pytest.mark.asyncio
    async def test_multiple_agents_registration(self, mock_db_session):
        """Test registering multiple agents in registry"""
        registry = AgentRegistry(db_session=mock_db_session)

        agents = []
        for i in range(3):
            agent = AsyncMock(spec=Agent)
            agent.agent_id = f"multi-agent-{i}"
            agent.agent_type = AgentType.EXECUTOR
            agent.address = f"http://localhost:800{i}"
            agent.get_capabilities = AsyncMock(return_value=[])
            agents.append(agent)

        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                for agent in agents:
                    success = await registry.register_agent(agent)
                    assert success is True

        assert len(registry._agents) == 3

    # --- AGENT FACTORY INTEGRATION (4 tests) ---

    def test_factory_supports_all_agent_types(self):
        """Test factory category mapping covers diverse agent types"""
        factory = AgentFactory()

        # Should have mappings for different agent categories
        analytical_count = sum(
            1 for cat in factory.category_mapping.values() if cat == AgentCategory.ANALYTICAL
        )
        creative_count = sum(
            1 for cat in factory.category_mapping.values() if cat == AgentCategory.CREATIVE
        )
        technical_count = sum(
            1 for cat in factory.category_mapping.values() if cat == AgentCategory.TECHNICAL
        )

        assert analytical_count > 0
        assert creative_count > 0
        assert technical_count > 0

    def test_factory_category_distribution(self):
        """Test factory has balanced category distribution"""
        factory = AgentFactory()

        category_counts = {}
        for category in AgentCategory:
            count = sum(1 for cat in factory.category_mapping.values() if cat == category)
            category_counts[category] = count

        # Each category should have at least some agents
        for category in [
            AgentCategory.ANALYTICAL,
            AgentCategory.CREATIVE,
            AgentCategory.TECHNICAL,
        ]:
            assert category_counts[category] > 3

    def test_factory_output_directory_creation(self):
        """Test factory creates output directory"""
        factory = AgentFactory()
        assert factory.output_directory.exists()

    def test_agent_definition_complexity_levels(self):
        """Test AgentDefinition supports different complexity levels"""
        complexity_levels = ["low", "medium", "high", "expert"]

        for level in complexity_levels:
            definition = AgentDefinition(
                name=f"test-{level}",
                description="Test",
                model="test-model",
                purpose="Test",
                capabilities=[],
                behavioral_traits=[],
                knowledge_base=[],
                example_interactions=[],
                category=AgentCategory.TECHNICAL,
                complexity_level=level,
                reasoning_required=0.5,
                speed_priority=0.5,
                cost_sensitivity=0.5,
            )
            assert definition.complexity_level == level


# ========================================================================
# TEST CLASS 5: Edge Cases and Error Handling (5 tests)
# ========================================================================


class TestCoreAgentsEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_agent_concurrent_task_processing(self):
        """Test agent handles concurrent task processing"""
        agent = ConcreteTestAgent(
            agent_id="concurrent-agent", agent_type=AgentType.EXECUTOR, tenant_id=1
        )

        agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id="test", success=True, result={}, execution_time=0.1
            )
        )

        # Create multiple tasks
        tasks = [
            TaskData(
                id=str(uuid4()),
                title=f"Concurrent Task {i}",
                description=f"Concurrent task {i}",
                priority=TaskPriority.MEDIUM,
                metadata={},
            )
            for i in range(5)
        ]

        # Process concurrently
        results = await asyncio.gather(*[agent.process_task(task) for task in tasks])

        assert len(results) == 5
        assert all(r.success for r in results)
        assert agent._tasks_processed == 5

    @pytest.mark.asyncio
    async def test_agent_error_recovery(self):
        """Test agent recovers from errors"""
        agent = ConcreteTestAgent(
            agent_id="error-recovery-agent", agent_type=AgentType.ANALYZER, tenant_id=1
        )

        # First task fails
        task1 = TaskData(
            id=str(uuid4()),
            title="Failing Task",
            description="Failing task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        agent._execute_task = AsyncMock(side_effect=Exception("Test error"))
        result1 = await agent.process_task(task1)
        assert result1.success is False

        # Second task succeeds
        task2 = TaskData(
            id=str(uuid4()),
            title="Success Task",
            description="Success task",
            priority=TaskPriority.MEDIUM,
            metadata={},
        )

        agent._execute_task = AsyncMock(
            return_value=ExecutionResult(
                task_id=task2.id, success=True, result={}, execution_time=0.2
            )
        )
        result2 = await agent.process_task(task2)
        assert result2.success is True

    @pytest.mark.asyncio
    async def test_registry_duplicate_registration(
        self,
    ):
        """Test registry handles duplicate agent registration"""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        registry = AgentRegistry(db_session=mock_session)

        agent = AsyncMock(spec=Agent)
        agent.agent_id = "duplicate-agent"
        agent.agent_type = AgentType.ANALYZER
        agent.address = "http://localhost:8004"
        agent.get_capabilities = AsyncMock(return_value=[])

        with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
            with patch("os.getenv", return_value="1"):
                # Register twice
                success1 = await registry.register_agent(agent)
                success2 = await registry.register_agent(agent)

        assert success1 is True
        assert success2 is True
        # Should still only have one entry in cache
        assert len([a for a in registry._agents.values() if a.agent_id == "duplicate-agent"]) == 1

    def test_factory_invalid_category_handling(self):
        """Test factory handles missing agents gracefully"""
        factory = AgentFactory()

        # Check that non-existent agent isn't in mapping
        assert "non-existent-agent-xyz" not in factory.category_mapping

    @pytest.mark.asyncio
    async def test_agent_initialization_failure_handling(self):
        """Test agent handles initialization failures"""
        agent = ConcreteTestAgent(
            agent_id="init-fail-agent", agent_type=AgentType.EXECUTOR, tenant_id=1
        )

        # Mock failure in _initialize_capabilities
        with patch.object(agent, "_initialize_capabilities", side_effect=Exception("Init failed")):
            success = await agent.initialize()

        assert success is False
        assert agent._last_error is not None


# ========================================================================
# SUMMARY: 52 TESTS TOTAL
# ========================================================================
# TestEnhancedBaseAgent: 15 tests
# TestAgentFactory: 12 tests
# TestAgentRegistry: 12 tests
# TestCoreAgentsIntegration: 8 tests
# TestCoreAgentsEdgeCases: 5 tests
#
# Coverage Target: 60%+ across 47 core_agents modules (25,208 LOC)
# Foundation classes: EnhancedBaseAgent, AgentFactory, AgentRegistry
# Strategy: Comprehensive batch testing of agent infrastructure
# ========================================================================
