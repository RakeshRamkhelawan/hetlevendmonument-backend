"""Tests for memory service wiring into agent base class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_setup_memory_store_returns_dict_of_services():
    """_setup_memory_store should return a dict with session_factory and tenant_id."""
    with patch("src.core.container.get_container") as mock_container:
        mock_session_factory = MagicMock()
        mock_container.return_value.session_factory.return_value = mock_session_factory

        from src.core.agents.base_agent import _setup_memory_store

        result = await _setup_memory_store(tenant_id=1)

        assert result is not None
        assert "session_factory" in result
        assert "tenant_id" in result
        assert result["tenant_id"] == 1


@pytest.mark.asyncio
async def test_process_task_loads_boot_context_when_memory_available():
    """process_task should call context_packer.build() if memory_store is set."""
    from src.core.agents.base_agent import EnhancedBaseAgent
    from src.core.shared.interfaces import AgentType, TaskData

    mock_session = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)
    # session_factory is the raw async_sessionmaker: a SYNC callable whose call
    # returns the async context manager (OP-172, base_agent.py does
    # `async with session_factory() as db:`, not `async with session_factory as db:`).
    mock_session_factory = MagicMock(return_value=mock_session_cm)

    agent = EnhancedBaseAgent(
        agent_id="test-agent",
        agent_type=AgentType.GENERIC,
        tenant_id=1,
        memory_store={
            "session_factory": mock_session_factory,
            "tenant_id": 1,
        },
    )
    agent._execute_task = AsyncMock(return_value=MagicMock(success=True, output="done"))

    with patch("src.core.agents.base_agent.ContextPackerService") as mock_packer_cls:
        mock_packer = AsyncMock()
        mock_packer.build = AsyncMock(return_value={"identity": "test", "goals": []})
        mock_packer_cls.return_value = mock_packer

        task = TaskData(id="task-1", title="Test task", description="test")
        await agent.process_task(task)

        mock_packer.build.assert_called_once_with(
            agent_id="test-agent",
            session_id=None,
            token_budget=2000,
        )


@pytest.mark.asyncio
async def test_process_task_writes_memory_on_success():
    """process_task should call write_service.write() after successful execution."""
    from src.core.agents.base_agent import EnhancedBaseAgent
    from src.core.shared.interfaces import AgentType, TaskData

    mock_session = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)
    # session_factory is the raw async_sessionmaker: a SYNC callable whose call
    # returns the async context manager (OP-172, base_agent.py does
    # `async with session_factory() as db:`, not `async with session_factory as db:`).
    mock_session_factory = MagicMock(return_value=mock_session_cm)

    agent = EnhancedBaseAgent(
        agent_id="test-agent",
        agent_type=AgentType.GENERIC,
        tenant_id=1,
        memory_store={
            "session_factory": mock_session_factory,
            "tenant_id": 1,
        },
    )
    agent._execute_task = AsyncMock(
        return_value=MagicMock(success=True, output="task completed successfully")
    )

    with (
        patch("src.core.agents.base_agent.MemoryWriteService") as mock_writer_cls,
        patch("src.core.agents.base_agent.ContextPackerService") as mock_packer_cls,
    ):
        mock_writer = AsyncMock()
        mock_writer.write = AsyncMock()
        mock_writer_cls.return_value = mock_writer
        mock_packer_cls.return_value = AsyncMock(build=AsyncMock(return_value=None))

        task = TaskData(id="task-1", title="Test task", description="test")
        result = await agent.process_task(task)

        assert result.success
        mock_writer.write.assert_called_once()
        # Verify a MemoryItemWrite schema was passed, not kwargs
        payload = mock_writer.write.call_args[0][0]
        assert payload.agent_id == "test-agent"
        assert payload.source_type == "workflow"


@pytest.mark.asyncio
async def test_process_task_does_not_write_memory_on_failure():
    """process_task should NOT call write_service.write() after failed execution."""
    from src.core.agents.base_agent import EnhancedBaseAgent
    from src.core.shared.interfaces import AgentType, TaskData

    mock_session_factory = AsyncMock()

    agent = EnhancedBaseAgent(
        agent_id="test-agent",
        agent_type=AgentType.GENERIC,
        tenant_id=1,
        memory_store={
            "session_factory": mock_session_factory,
            "tenant_id": 1,
        },
    )
    agent._execute_task = AsyncMock(
        return_value=MagicMock(success=False, error_message="task failed")
    )

    with (
        patch("src.core.agents.base_agent.MemoryWriteService") as mock_writer_cls,
        patch("src.core.agents.base_agent.ContextPackerService") as mock_packer_cls,
    ):
        mock_writer = AsyncMock()
        mock_writer_cls.return_value = mock_writer
        mock_packer_cls.return_value = AsyncMock(build=AsyncMock(return_value=None))

        task = TaskData(id="task-1", title="Test task", description="test")
        result = await agent.process_task(task)

        assert not result.success
        mock_writer.write.assert_not_called()


@pytest.mark.asyncio
async def test_process_task_without_memory_store_works():
    """process_task should work fine when memory_store is None (backward compat)."""
    from src.core.agents.base_agent import EnhancedBaseAgent
    from src.core.shared.interfaces import AgentType, TaskData

    agent = EnhancedBaseAgent(
        agent_id="test-agent",
        agent_type=AgentType.GENERIC,
        tenant_id=1,
        memory_store=None,
    )
    agent._execute_task = AsyncMock(return_value=MagicMock(success=True, output="done"))

    task = TaskData(id="task-1", title="Test task", description="test")
    result = await agent.process_task(task)

    assert result.success
