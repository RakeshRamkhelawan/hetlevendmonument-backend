"""
tests/fixtures/test_fixtures_demo.py - Demonstration Tests for New Fixtures

This file demonstrates how to use the new P4.0.4 shared fixtures.
Run with: pytest tests/fixtures/test_fixtures_demo.py -v

Created: 2025-12-11
"""

import asyncio

import pytest

from tests.fixtures.agent_mocks import (
    AgentStatus,
    FakeAgentRuntime,
    MockAgentPool,
    MockAgentRegistry,
)
from tests.fixtures.database_mocks import InMemoryRepository, MockTenantContext, MockTransaction
from tests.fixtures.external_mocks import FakeRabbitMQ, FakeRedisClient, MockMLflowClient
from tests.fixtures.llm_mocks import FakeLLMProvider, MockGeminiClient, MockOllamaClient

# ============================================================================
# LLM MOCKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_fake_llm_provider():
    """Test FakeLLMProvider with custom responses."""
    llm = FakeLLMProvider(
        responses={
            "What is AI?": "AI is artificial intelligence.",
            "Hello": "Hi there!",
        }
    )

    # Test matching prompt
    result = await llm.generate("What is AI?")
    assert result.text == "AI is artificial intelligence."
    assert result.model == "mock-model"

    # Test default response
    result2 = await llm.generate("Unknown question")
    assert result2.text == "Mock LLM response"

    # Verify call tracking
    assert llm.call_count == 2
    assert len(llm.call_log) == 2


@pytest.mark.asyncio
async def test_mock_gemini_client():
    """Test MockGeminiClient response cycling."""
    client = MockGeminiClient(responses=["First", "Second", "Third"])

    result1 = await client.generate_content("Test 1")
    assert result1.text == "First"

    result2 = await client.generate_content("Test 2")
    assert result2.text == "Second"

    result3 = await client.generate_content("Test 3")
    assert result3.text == "Third"

    # Cycles back to first
    result4 = await client.generate_content("Test 4")
    assert result4.text == "First"


@pytest.mark.asyncio
async def test_mock_ollama_client():
    """Test MockOllamaClient chat and generate."""
    client = MockOllamaClient(responses=["Test response"])

    # Chat API
    chat_result = await client.chat(
        model="llama2",
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert chat_result["message"]["content"] == "Test response"

    # Generate API
    gen_result = await client.generate(model="llama2", prompt="Test")
    assert gen_result["response"] == "Test response"


# ============================================================================
# AGENT MOCKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_fake_agent_runtime():
    """Test FakeAgentRuntime execution."""
    runtime = FakeAgentRuntime(
        responses={
            "agent1": {"status": "completed", "output": "Success!"},
            "agent2": {"status": "failed", "error": "Agent failed"},
        }
    )

    # Successful execution
    result1 = await runtime.execute("agent1", {"input": "test"})
    assert result1.status == AgentStatus.COMPLETED
    assert result1.output == "Success!"

    # Failed execution
    result2 = await runtime.execute("agent2", {})
    assert result2.status == AgentStatus.FAILED
    assert result2.error == "Agent failed"


@pytest.mark.asyncio
async def test_mock_agent_registry():
    """Test MockAgentRegistry registration and retrieval."""
    registry = MockAgentRegistry()

    # Register agents
    await registry.register("agent1", "Test Agent", "core", capabilities=["analyze"])
    await registry.register("agent2", "Another Agent", "specialist")

    # Retrieve by ID
    agent = await registry.get("agent1")
    assert agent.name == "Test Agent"
    assert "analyze" in agent.capabilities

    # List by type
    core_agents = await registry.list_agents(agent_type="core")
    assert len(core_agents) == 1


@pytest.mark.asyncio
async def test_mock_agent_pool():
    """Test MockAgentPool task submission."""
    pool = MockAgentPool(max_workers=3)

    # Submit task
    task_id = await pool.submit("agent1", {"input": "test"})
    assert task_id

    # Get result
    result = await pool.get_result(task_id)
    assert result["status"] == "completed"

    # Check stats
    stats = pool.get_pool_stats()
    assert stats["completed_tasks"] == 1


# ============================================================================
# EXTERNAL MOCKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_fake_redis_client():
    """Test FakeRedisClient operations."""
    redis = FakeRedisClient()

    # String operations
    await redis.set("key1", "value1")
    value = await redis.get("key1")
    assert value == "value1"

    # Hash operations
    await redis.hset("user:1", "name", "Alice")
    name = await redis.hget("user:1", "name")
    assert name == "Alice"

    # Set operations
    await redis.sadd("tags", "python", "testing")
    members = await redis.smembers("tags")
    assert "python" in members


@pytest.mark.asyncio
async def test_fake_rabbitmq():
    """Test FakeRabbitMQ message queue."""
    mq = FakeRabbitMQ()

    # Declare queue
    await mq.declare_queue("tasks")

    # Publish messages
    await mq.publish("tasks", {"job": "task1"})
    await mq.publish("tasks", {"job": "task2"})

    # Consume messages (FIFO)
    msg1 = await mq.consume("tasks")
    assert msg1["job"] == "task1"

    msg2 = await mq.consume("tasks")
    assert msg2["job"] == "task2"

    # Empty queue
    msg3 = await mq.consume("tasks")
    assert msg3 is None


def test_mock_mlflow_client():
    """Test MockMLflowClient tracking."""
    mlflow = MockMLflowClient()

    # Create experiment
    exp_id = mlflow.create_experiment("test_exp")

    # Create run
    run = mlflow.create_run(exp_id)
    run_id = run.info.run_id

    # Log parameters and metrics
    mlflow.log_param(run_id, "lr", 0.01)
    mlflow.log_metric(run_id, "accuracy", 0.95)

    # End run
    mlflow.end_run(run_id)

    # Retrieve run
    stored_run = mlflow.get_run(run_id)
    assert stored_run.params["lr"] == 0.01
    assert stored_run.metrics["accuracy"] == 0.95


# ============================================================================
# DATABASE MOCKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_in_memory_repository():
    """Test InMemoryRepository CRUD operations."""
    from dataclasses import dataclass

    @dataclass
    class User:
        id: int = None
        email: str = ""
        tenant_id: int = 1

    repo = InMemoryRepository(User)

    # Add
    user = User(email="test@example.com", tenant_id=1)
    await repo.add(user)
    assert user.id  # Auto-assigned

    # Get by ID
    found = await repo.get_by_id(user.id)
    assert found.email == "test@example.com"

    # Filter
    users = await repo.get_all(filters={"tenant_id": 1})
    assert len(users) == 1

    # Update
    user.email = "updated@example.com"
    await repo.update(user)
    updated = await repo.get_by_id(user.id)
    assert updated.email == "updated@example.com"

    # Delete
    deleted = await repo.delete(user.id)
    assert deleted


@pytest.mark.asyncio
async def test_mock_tenant_context():
    """Test MockTenantContext."""
    async with MockTenantContext(tenant_id=5) as ctx:
        assert ctx.tenant_id == 5
        assert not ctx.bypass_filter


@pytest.mark.asyncio
async def test_mock_transaction():
    """Test MockTransaction commit and rollback."""
    # Test commit
    tx1 = MockTransaction()
    async with tx1:
        await tx1.commit()
    assert tx1.committed
    assert not tx1.rolled_back

    # Test rollback on error
    tx2 = MockTransaction()
    try:
        async with tx2:
            raise ValueError("Test error")
    except ValueError:
        pass
    assert tx2.rolled_back
    assert not tx2.committed


# ============================================================================
# INTEGRATION TEST (Multiple Fixtures)
# ============================================================================


@pytest.mark.asyncio
async def test_full_workflow_integration():
    """Test combining multiple fixtures in one workflow."""
    # Setup LLM
    llm = FakeLLMProvider(responses={"Analyze": "Analysis complete"})

    # Setup agent registry
    registry = MockAgentRegistry()
    await registry.register("analyzer", "Analyzer Agent", "core")

    # Setup cache
    redis = FakeRedisClient()
    await redis.set("config", "enabled")

    # Setup repository
    from dataclasses import dataclass

    @dataclass
    class Task:
        id: int = None
        name: str = ""
        status: str = "pending"

    task_repo = InMemoryRepository(Task)
    task = Task(name="Test Task")
    await task_repo.add(task)

    # Execute workflow
    llm_result = await llm.generate("Analyze")
    agent = await registry.get("analyzer")
    config = await redis.get("config")
    stored_task = await task_repo.get_by_id(task.id)

    # Verify all components
    assert llm_result.text == "Analysis complete"
    assert agent.name == "Analyzer Agent"
    assert config == "enabled"
    assert stored_task.name == "Test Task"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
