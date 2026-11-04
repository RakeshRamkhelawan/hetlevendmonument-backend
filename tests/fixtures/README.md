# Test Fixtures Library

**Shared, reusable test utilities for SanskritiSetu.org**

This directory provides modular, production-ready test fixtures that eliminate boilerplate and ensure consistency across all tests.

## Philosophy

1. **Deterministic**: All mocks return predictable results (no randomness)
2. **Isolated**: No external dependencies (no network, no real databases)
3. **Composable**: Mix and match fixtures as needed
4. **Type-Safe**: Full type hints for IDE autocomplete
5. **Thread-Safe**: Safe for concurrent test execution

## Quick Start

### Import Fixtures

```python
# In your test file
import pytest
from tests.fixtures.llm_mocks import FakeLLMProvider, MockGeminiClient
from tests.fixtures.agent_mocks import FakeAgentRuntime, MockAgentRegistry
from tests.fixtures.external_mocks import FakeRedisClient, FakeRabbitMQ
from tests.fixtures.database_mocks import InMemoryRepository, MockTenantContext
```

### Or use pytest fixtures:

```python
def test_with_fixtures(
    fake_llm_provider,
    mock_agent_registry,
    fake_redis_client,
):
    # Fixtures are automatically injected
    pass
```

## Module Guide

### 1. `llm_mocks.py` - LLM Provider Mocks

Mock LLM providers (Gemini, Ollama) with configurable responses.

#### FakeLLMProvider

Generic LLM mock with prompt -> response mapping:

```python
async def test_llm_generation(fake_llm_provider):
    # Configure responses
    fake_llm_provider.set_response(
        "What is AI?",
        "AI is artificial intelligence."
    )

    # Generate response
    result = await fake_llm_provider.generate("What is AI?")

    # Verify
    assert result.text == "AI is artificial intelligence."
    assert result.model == "mock-model"
    assert fake_llm_provider.call_count == 1
```

**Configuration options:**

```python
llm = FakeLLMProvider(
    responses={
        "prompt1": "response1",
        "prompt2": "response2",
    },
    default_response="I don't know",  # Fallback
    should_fail=False,  # Set True to raise errors
    model_name="custom-model",
)
```

#### MockGeminiClient

Gemini API mock with response cycling:

```python
async def test_gemini(mock_gemini_client):
    # Set multiple responses (cycles through them)
    mock_gemini_client.set_responses([
        "First response",
        "Second response",
        "Third response",
    ])

    # First call
    result1 = await mock_gemini_client.generate_content("Test prompt")
    assert result1.text == "First response"

    # Second call
    result2 = await mock_gemini_client.generate_content("Another prompt")
    assert result2.text == "Second response"

    # Verify call log
    assert len(mock_gemini_client.call_log) == 2
```

**Response structure (matches Gemini API):**

```python
response.text  # Direct text access
response.candidates[0].content.parts[0].text  # Nested access
response.candidates[0].finish_reason  # "STOP"
```

#### MockOllamaClient

Ollama API mock with chat/generate support:

```python
async def test_ollama(mock_ollama_client):
    # Chat API
    response = await mock_ollama_client.chat(
        model="llama2",
        messages=[
            {"role": "user", "content": "Hello!"},
        ],
    )
    assert response["message"]["content"] == "Mock Ollama response"

    # Generate API
    result = await mock_ollama_client.generate(
        model="llama2",
        prompt="Tell me a joke",
    )
    assert result["response"]
```

### 2. `agent_mocks.py` - Agent System Mocks

Mock agent runtime, registry, and worker pool.

#### FakeAgentRuntime

Mock agent execution with configurable results:

```python
async def test_agent_execution(fake_agent_runtime):
    # Configure agent response
    fake_agent_runtime.set_response("agent1", {
        "status": "completed",
        "output": {"result": "Success!"},
    })

    # Execute agent
    result = await fake_agent_runtime.execute(
        "agent1",
        {"input": "test data"},
    )

    # Verify
    assert result.status == AgentStatus.COMPLETED
    assert result.output["result"] == "Success!"
    assert result.agent_id == "agent1"
```

**Simulating failures:**

```python
fake_agent_runtime.set_response("failing_agent", {
    "status": "failed",
    "error": "Agent encountered an error",
})

result = await fake_agent_runtime.execute("failing_agent", {})
assert result.status == AgentStatus.FAILED
assert result.error == "Agent encountered an error"
```

**Testing timeouts:**

```python
runtime = FakeAgentRuntime(execution_delay_ms=5000)

with pytest.raises(asyncio.TimeoutError):
    await runtime.execute("slow_agent", {}, timeout_ms=1000)
```

#### MockAgentRegistry

In-memory agent registry:

```python
async def test_agent_registry(mock_agent_registry):
    # Register agent
    agent = await mock_agent_registry.register(
        agent_id="agent1",
        name="Test Agent",
        agent_type="core",
        capabilities=["analyze", "summarize"],
    )

    # Retrieve agent
    found = await mock_agent_registry.get("agent1")
    assert found.name == "Test Agent"

    # List agents by type
    core_agents = await mock_agent_registry.list_agents(agent_type="core")
    assert len(core_agents) == 1
```

#### MockAgentPool

Worker pool without real workers:

```python
async def test_agent_pool(mock_agent_pool):
    # Submit task
    task_id = await mock_agent_pool.submit(
        agent_id="worker1",
        input_data={"job": "process"},
    )

    # Get result (instant in mock)
    result = await mock_agent_pool.get_result(task_id)
    assert result["status"] == "completed"

    # Check pool stats
    stats = mock_agent_pool.get_pool_stats()
    assert stats["completed_tasks"] == 1
```

### 3. `external_mocks.py` - External Service Mocks

Mock Redis, RabbitMQ, MLflow without external services.

#### FakeRedisClient

In-memory Redis with full API:

```python
async def test_redis_caching(fake_redis_client):
    # Set with TTL
    await fake_redis_client.set("key1", "value1", ex=60)

    # Get value
    value = await fake_redis_client.get("key1")
    assert value == "value1"

    # Hash operations
    await fake_redis_client.hset("user:1", "name", "Alice")
    name = await fake_redis_client.hget("user:1", "name")
    assert name == "Alice"

    # Set operations
    await fake_redis_client.sadd("tags", "python", "testing")
    members = await fake_redis_client.smembers("tags")
    assert "python" in members
```

**Supported operations:**

- Strings: `get`, `set`, `delete`, `exists`, `expire`, `incr`, `decr`
- Hashes: `hset`, `hget`, `hgetall`
- Sets: `sadd`, `smembers`, `sismember`
- Utility: `flushdb`, `close`

#### FakeRabbitMQ

Message queue without RabbitMQ server:

```python
async def test_message_queue(fake_rabbitmq):
    # Declare queue
    await fake_rabbitmq.declare_queue("tasks")

    # Publish messages
    await fake_rabbitmq.publish("tasks", {"job": "process_data"})
    await fake_rabbitmq.publish("tasks", {"job": "send_email"})

    # Consume messages (FIFO)
    msg1 = await fake_rabbitmq.consume("tasks")
    assert msg1["job"] == "process_data"

    msg2 = await fake_rabbitmq.consume("tasks")
    assert msg2["job"] == "send_email"

    # Check queue size
    assert fake_rabbitmq.get_queue_size("tasks") == 0
```

#### MockMLflowClient

MLflow tracking without server:

```python
def test_mlflow_tracking(mock_mlflow_client):
    # Create experiment
    exp_id = mock_mlflow_client.create_experiment("test_exp")

    # Create run
    run = mock_mlflow_client.create_run(exp_id)
    run_id = run.info.run_id

    # Log parameters and metrics
    mock_mlflow_client.log_param(run_id, "learning_rate", 0.01)
    mock_mlflow_client.log_metric(run_id, "accuracy", 0.95)

    # End run
    mock_mlflow_client.end_run(run_id)

    # Retrieve run
    stored_run = mock_mlflow_client.get_run(run_id)
    assert stored_run.params["learning_rate"] == 0.01
    assert stored_run.metrics["accuracy"] == 0.95
```

### 4. `database_mocks.py` - Database Mocking

In-memory repositories and transaction mocks.

#### InMemoryRepository

Generic repository for any model:

```python
async def test_user_repository(in_memory_repository):
    from src.core.models.rbac_models import User

    # Create repository
    user_repo = in_memory_repository(User)

    # Add user
    user = User(email="test@example.com", tenant_id=1)
    await user_repo.add(user)

    # Retrieve by ID
    found = await user_repo.get_by_id(user.id)
    assert found.email == "test@example.com"

    # Filter
    users = await user_repo.get_all(filters={"tenant_id": 1})
    assert len(users) == 1

    # Update
    user.email = "updated@example.com"
    await user_repo.update(user)

    # Delete
    deleted = await user_repo.delete(user.id)
    assert deleted
```

**Tenant isolation:**

```python
# Create tenant-aware repository
repo = in_memory_repository(User, tenant_aware=True)
repo.set_tenant_context(tenant_id=1)

# Add users to different tenants
user1 = User(email="user1@tenant1.com", tenant_id=1)
user2 = User(email="user2@tenant2.com", tenant_id=2)

await repo.add(user1)
await repo.add(user2)

# Only sees tenant 1 users
users = await repo.get_all()
assert len(users) == 1
assert users[0].tenant_id == 1
```

#### MockTenantContext

Simulate tenant context:

```python
async def test_tenant_isolation(mock_tenant_context):
    # Use context manager
    async with MockTenantContext(tenant_id=5) as ctx:
        assert ctx.tenant_id == 5
        # Code here runs with tenant_id=5
```

#### MockTransaction

Test transaction behavior:

```python
async def test_transaction_rollback(mock_transaction):
    async with mock_transaction as tx:
        # Do work
        # ...
        # Simulate error
        raise ValueError("Test error")

    # Transaction auto-rolled back
    assert mock_transaction.rolled_back
    assert not mock_transaction.committed
```

## Integration with conftest.py

The fixtures are automatically available when pytest is configured:

```python
# tests/conftest.py
pytest_plugins = [
    "tests.fixtures.llm_mocks",
    "tests.fixtures.agent_mocks",
    "tests.fixtures.external_mocks",
    "tests.fixtures.database_mocks",
]
```

Or import explicitly:

```python
# tests/conftest.py
from tests.fixtures.llm_mocks import *
from tests.fixtures.agent_mocks import *
from tests.fixtures.external_mocks import *
from tests.fixtures.database_mocks import *
```

## Advanced Patterns

### Combining Fixtures

```python
async def test_full_workflow(
    fake_llm_provider,
    mock_agent_registry,
    fake_redis_client,
    in_memory_repository,
):
    from src.core.models.rbac_models import User

    # Setup LLM
    fake_llm_provider.set_response("Analyze", "Analysis complete")

    # Setup agent
    await mock_agent_registry.register("analyzer", "Analyzer", "core")

    # Setup cache
    await fake_redis_client.set("config", "enabled")

    # Setup repository
    user_repo = in_memory_repository(User)
    user = User(email="test@example.com", tenant_id=1)
    await user_repo.add(user)

    # Run test with all mocks active
    # ...
```

### Custom Configuration

```python
from tests.fixtures.llm_mocks import create_fake_llm

def test_custom_llm():
    # Create custom-configured LLM
    llm = create_fake_llm(
        responses={
            "Hello": "Hi there!",
            "Goodbye": "See you later!",
        },
        model_name="gpt-4-turbo",
        should_fail=False,
    )

    # Use in test
    # ...
```

### Parametrized Testing

```python
@pytest.mark.parametrize("agent_type,expected_count", [
    ("core", 3),
    ("specialist", 5),
    ("custom", 2),
])
async def test_agent_types(mock_agent_registry, agent_type, expected_count):
    # Register agents of different types
    for i in range(expected_count):
        await mock_agent_registry.register(
            f"{agent_type}_{i}",
            f"{agent_type.title()} Agent {i}",
            agent_type,
        )

    # Verify filtering
    agents = await mock_agent_registry.list_agents(agent_type=agent_type)
    assert len(agents) == expected_count
```

## Testing Edge Cases

### LLM Failures

```python
async def test_llm_failure_handling(fake_llm_provider):
    # Configure LLM to fail
    fake_llm_provider.should_fail = True
    fake_llm_provider.failure_message = "API rate limit exceeded"

    # Test error handling
    with pytest.raises(Exception, match="API rate limit exceeded"):
        await fake_llm_provider.generate("Test prompt")
```

### Agent Timeouts

```python
async def test_agent_timeout():
    runtime = FakeAgentRuntime(execution_delay_ms=10000)

    with pytest.raises(asyncio.TimeoutError):
        await runtime.execute("slow_agent", {}, timeout_ms=100)
```

### Cache Expiration

```python
async def test_redis_expiration(fake_redis_client):
    # Set with 1 second TTL
    await fake_redis_client.set("temp_key", "value", ex=1)

    # Immediately available
    assert await fake_redis_client.get("temp_key") == "value"

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Now expired
    assert await fake_redis_client.get("temp_key") is None
```

## Best Practices

1. **Reset between tests**: Call `.reset()` on mocks if reusing fixtures
2. **Use call logs**: Verify interactions with `.call_log`
3. **Deterministic data**: Avoid randomness in test data
4. **Clear naming**: Use descriptive fixture names
5. **Isolate concerns**: One mock per responsibility

## 5. `workflow_mocks.py` - Workflow & Process Execution Mocks

Mock workflow engine, task scheduler, and execution monitoring.

### MockWorkflowEngine

Deterministic workflow execution with task orchestration:

```python
async def test_workflow_execution(mock_workflow_engine):
    # Define tasks
    task1 = TaskDefinition(
        name="fetch_data",
        timeout_seconds=30,
    )
    task2 = TaskDefinition(
        name="process_data",
        dependencies=["fetch_data"],
    )

    # Configure handlers
    async def fetch_handler(params):
        return {"data": [1, 2, 3]}

    mock_workflow_engine.set_task_handler("fetch_data", fetch_handler)
    mock_workflow_engine.set_task_outcome("process_data", {"status": "processed"})

    # Execute workflow
    result = await mock_workflow_engine.execute_workflow(
        workflow_id="wf1",
        tasks=[task1, task2],
    )

    # Verify execution
    assert result.state == WorkflowState.SUCCEEDED
    assert result.get_completed_count() == 2
    assert result.success_rate() == 100.0
```

### MockTaskScheduler

Task queuing with priority support:

```python
async def test_task_scheduling(mock_task_scheduler):
    # Create tasks with different priorities
    critical_task = TaskDefinition(
        name="urgent",
        priority=TaskPriority.CRITICAL,
    )
    low_task = TaskDefinition(
        name="background",
        priority=TaskPriority.LOW,
    )

    # Schedule in reverse order
    await mock_task_scheduler.schedule(low_task)
    await mock_task_scheduler.schedule(critical_task)

    # Verify queue order (critical should be first)
    first = await mock_task_scheduler.get_next()
    assert first.name == "urgent"
```

## Troubleshooting

### Fixture not found

```
Error: fixture 'fake_llm_provider' not found
```

**Solution**: Add to conftest.py:

```python
from tests.fixtures.llm_mocks import fake_llm_provider
```

### Event loop issues

```
Error: Task got Future attached to a different loop
```

**Solution**: Use `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_async_operation():
    # async test
```

### Type errors

```
Error: 'NoneType' object has no attribute 'id'
```

**Solution**: Ensure models are properly initialized with required fields:

```python
# Bad
user = User()  # Missing required fields

# Good
user = User(email="test@example.com", tenant_id=1, hashed_password="hash")
```

## Contributing

When adding new fixtures:

1. Follow existing patterns (async-compatible, type-hinted)
2. Add docstrings with usage examples
3. Include pytest fixture decorator
4. Add to this README
5. Write unit tests for the fixture itself

## Support

For questions or issues, see:

- Test Infrastructure Documentation: `docs/testing/`
- Example Tests: `tests/unit/` and `tests/integration/`
- Team Chat: #testing channel
