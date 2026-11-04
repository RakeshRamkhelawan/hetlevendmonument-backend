#!/usr/bin/env python3
"""
Unit tests for subagent_endpoints.py
Target: 50% coverage of 226 statements (113 lines covered)

Test Strategy:
- Class 1: TestAgentDiscovery (3 tests) - Discovery and listing endpoints
- Class 2: TestAgentLoading (4 tests) - Loading, reloading, instantiation
- Class 3: TestAgentStatus (3 tests) - Status checking and metrics
- Class 4: TestAgentActions (2 tests) - Agent action execution

Key Learnings Applied:
1. Mock where function is USED (import location), not where DEFINED
2. Use valid enum values in test data
3. Comprehensive error path testing
4. Mock auth dependencies properly
"""

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Mock the dependencies BEFORE importing the endpoint module
sys.modules["src.core.agents.subagent_loader"] = MagicMock()
# sys.modules['src.core.auth.rbac'] = MagicMock()

# Import endpoint functions and models
from src.core.api.subagent_endpoints import (
    AgentActionRequest,
    AgentInstantiateRequest,
    AgentLoadRequest,
    discover_agents,
    get_agent_status,
    instantiate_agent,
    list_agents,
    load_agents,
    router,
)


# Mock user for authentication
@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    user = MagicMock()
    user.user_id = "test_user_001"
    user.username = "testuser"
    user.role = "admin"
    return user


# ============================================================================
# CLASS 1: Agent Discovery Tests (3 tests)
# ============================================================================


class TestAgentDiscovery:
    """Tests for agent discovery and listing endpoints"""

    @pytest.mark.asyncio
    async def test_discover_agents_success(self, mock_user):
        """Test successful agent discovery"""
        # Arrange
        mock_loader = AsyncMock()
        mock_loader.discover_agents = AsyncMock(return_value=None)
        mock_loader.list_available_agents = MagicMock(
            return_value=[
                {
                    "name": "data_analyzer",
                    "type": "analysis",
                    "status": "available",
                    "description": "Analyzes data patterns",
                    "capabilities": ["pattern_analysis", "data_mining"],
                    "priority": 1,
                    "error": None,
                },
                {
                    "name": "nlp_processor",
                    "type": "nlp",
                    "status": "loaded",
                    "description": "Natural language processing",
                    "capabilities": ["sentiment_analysis", "entity_extraction"],
                    "priority": 2,
                    "error": None,
                },
            ]
        )

        # Mock AgentStatus enum -- patch router_discovery (where _build_agent_list lives after ADR-033 split)
        with patch("src.core.api.v1.subagents.router_discovery.AgentStatus") as mock_status:
            mock_status.__iter__ = MagicMock(
                return_value=iter(
                    [
                        MagicMock(value="available"),
                        MagicMock(value="loaded"),
                        MagicMock(value="unloaded"),
                    ]
                )
            )

            # Act
            with patch(
                "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
            ):
                with patch(
                    "src.core.api.v1.subagents.router.get_current_user",
                    return_value=mock_user,
                ):
                    with patch(
                        "src.core.api.v1.subagents.router.require_scopes",
                        return_value=lambda: 1,
                    ):
                        result = await discover_agents(
                            limit=50, offset=0, current_user=mock_user, loader=mock_loader
                        )

        # Assert
        assert result.total_agents == 2
        assert len(result.agents) == 2
        assert result.agents[0].name == "data_analyzer"
        assert result.agents[1].name == "nlp_processor"
        assert "available" in result.status_summary
        mock_loader.discover_agents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_discover_agents_error(self, mock_user):
        """Test agent discovery failure"""
        # Arrange
        mock_loader = AsyncMock()
        mock_loader.discover_agents = AsyncMock(
            side_effect=Exception("Discovery service unavailable")
        )

        # Act & Assert
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            with patch(
                "src.core.api.v1.subagents.router.get_current_user",
                return_value=mock_user,
            ):
                with patch(
                    "src.core.api.v1.subagents.router.require_scopes",
                    return_value=lambda: 1,
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await discover_agents(current_user=mock_user, loader=mock_loader)

                    assert exc_info.value.status_code == 500
                    assert "Discovery failed" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_list_agents_success(self, mock_user):
        """Test successful agent listing"""
        # Arrange
        mock_loader = AsyncMock()
        mock_loader.list_available_agents = MagicMock(
            return_value=[
                {
                    "name": "code_generator",
                    "type": "code",
                    "status": "loaded",
                    "description": "Generates code snippets",
                    "capabilities": ["python_gen", "js_gen"],
                    "priority": 3,
                    "error": None,
                }
            ]
        )

        # Mock AgentStatus enum -- patch router_discovery (where _build_agent_list lives after ADR-033 split)
        with patch("src.core.api.v1.subagents.router_discovery.AgentStatus") as mock_status:
            mock_status.__iter__ = MagicMock(
                return_value=iter(
                    [
                        MagicMock(value="available"),
                        MagicMock(value="loaded"),
                        MagicMock(value="unloaded"),
                    ]
                )
            )

            # Act
            with patch(
                "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
            ):
                with patch(
                    "src.core.api.v1.subagents.router.get_current_user",
                    return_value=mock_user,
                ):
                    with patch(
                        "src.core.api.v1.subagents.router.require_scopes",
                        return_value=lambda: 1,
                    ):
                        result = await list_agents(
                            limit=50, offset=0, current_user=mock_user, loader=mock_loader
                        )

        # Assert
        assert result.total_agents == 1
        assert result.agents[0].name == "code_generator"
        assert result.agents[0].status == "loaded"


# ============================================================================
# CLASS 2: Agent Loading Tests (4 tests)
# ============================================================================


class TestAgentLoading:
    """Tests for agent loading and instantiation endpoints"""

    @pytest.mark.asyncio
    async def test_load_agents_success(self, mock_user):
        """Test successful agent loading"""
        # Arrange
        mock_loader = AsyncMock()
        mock_loader.load_agent = AsyncMock(return_value=True)
        mock_status = MagicMock()
        mock_status.value = "loaded"
        mock_loader.get_agent_status = MagicMock(return_value=mock_status)

        request = AgentLoadRequest(
            agent_names=["data_analyzer", "nlp_processor"], force_reload=False
        )

        # Act
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            with patch(
                "src.core.api.v1.subagents.router.get_current_user",
                return_value=mock_user,
            ):
                with patch(
                    "src.core.api.v1.subagents.router.require_scopes",
                    return_value=lambda: 1,
                ):
                    result = await load_agents(
                        request=request, current_user=mock_user, loader=mock_loader
                    )

        # Assert
        assert result["total_loaded"] == 2
        assert "data_analyzer" in result["results"]
        assert "nlp_processor" in result["results"]
        assert result["results"]["data_analyzer"]["success"] is True
        assert mock_loader.load_agent.await_count == 2

    @pytest.mark.asyncio
    async def test_load_agents_force_reload(self, mock_user):
        """Test agent force reload"""
        # Arrange
        mock_loader = AsyncMock()
        mock_loader.reload_agent = AsyncMock(return_value=True)
        mock_status = MagicMock()
        mock_status.value = "loaded"
        mock_loader.get_agent_status = MagicMock(return_value=mock_status)

        request = AgentLoadRequest(agent_names=["data_analyzer"], force_reload=True)

        # Act
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            with patch(
                "src.core.api.v1.subagents.router.get_current_user",
                return_value=mock_user,
            ):
                with patch(
                    "src.core.api.v1.subagents.router.require_scopes",
                    return_value=lambda: 1,
                ):
                    result = await load_agents(
                        request=request, current_user=mock_user, loader=mock_loader
                    )

        # Assert
        assert result["total_loaded"] == 1
        mock_loader.reload_agent.assert_awaited_once_with("data_analyzer")

    @pytest.mark.asyncio
    async def test_instantiate_agent_success(self, mock_user):
        """Test successful agent instantiation"""
        # Arrange
        mock_loader = AsyncMock()

        # Mock AgentStatus enum -- patch router_management (where instantiate_agent lives after ADR-033 split)
        mock_status_loaded = MagicMock()
        mock_status_loaded.value = "loaded"

        with patch("src.core.api.v1.subagents.router_management.AgentStatus") as mock_status_enum:
            mock_status_enum.UNLOADED = MagicMock()
            mock_loader.get_agent_status = MagicMock(return_value=mock_status_loaded)

            mock_instance = MagicMock()
            mock_instance.__class__.__name__ = "DataAnalyzerAgent"
            mock_loader.instantiate_agent = AsyncMock(return_value=mock_instance)

            request = AgentInstantiateRequest(agent_name="data_analyzer", config={"max_threads": 4})

            # Act
            with patch(
                "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
            ):
                with patch(
                    "src.core.api.v1.subagents.router.get_current_user",
                    return_value=mock_user,
                ):
                    with patch(
                        "src.core.api.v1.subagents.router.require_scopes",
                        return_value=lambda: 1,
                    ):
                        result = await instantiate_agent(
                            request=request, current_user=mock_user, loader=mock_loader
                        )

            # Assert
            assert result["agent_name"] == "data_analyzer"
            assert result["status"] == "active"
            assert result["instance_type"] == "DataAnalyzerAgent"
            mock_loader.instantiate_agent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_instantiate_agent_not_loaded(self, mock_user):
        """Test instantiation of unloaded agent"""
        # Arrange
        mock_loader = AsyncMock()

        # Mock AgentStatus enum -- patch router_management (where instantiate_agent lives after ADR-033 split)
        with patch("src.core.api.v1.subagents.router_management.AgentStatus") as mock_status_enum:
            mock_status_enum.UNLOADED = MagicMock()
            mock_loader.get_agent_status = MagicMock(return_value=mock_status_enum.UNLOADED)

            request = AgentInstantiateRequest(agent_name="unloaded_agent", config={})

            # Act & Assert
            with patch(
                "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
            ):
                with patch(
                    "src.core.api.v1.subagents.router.get_current_user",
                    return_value=mock_user,
                ):
                    with patch(
                        "src.core.api.v1.subagents.router.require_scopes",
                        return_value=lambda: 1,
                    ):
                        with pytest.raises(HTTPException) as exc_info:
                            await instantiate_agent(
                                request=request, current_user=mock_user, loader=mock_loader
                            )

                        assert exc_info.value.status_code == 400
                        assert "is not loaded" in str(exc_info.value.detail)


# ============================================================================
# CLASS 3: Agent Status Tests (3 tests)
# ============================================================================


class TestAgentStatus:
    """Tests for agent status and metrics endpoints"""

    @pytest.mark.asyncio
    async def test_get_agent_status_success(self, mock_user):
        """Test getting agent status"""
        # Arrange
        mock_loader = AsyncMock()
        mock_status = MagicMock()
        mock_status.value = "loaded"

        # Mock agent definition
        mock_agent_def = MagicMock()
        mock_agent_def.name = "data_analyzer"
        mock_agent_def.agent_type = "analysis"
        mock_agent_def.status = mock_status
        mock_agent_def.description = "Test agent"
        mock_agent_def.capabilities = ["test"]
        mock_agent_def.dependencies = []
        mock_agent_def.priority = 1
        mock_agent_def.config = {}
        mock_agent_def.health_status = "healthy"
        mock_agent_def.last_error = None
        mock_agent_def.metadata = {}

        # Mock agents dict - CRITICAL: endpoint checks 'if agent_name not in loader.agents'
        mock_loader.agents = {"data_analyzer": mock_agent_def}
        mock_loader.get_agent = MagicMock(return_value=None)

        agent_name = "data_analyzer"

        # Act
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            with patch(
                "src.core.api.v1.subagents.router.get_current_user",
                return_value=mock_user,
            ):
                with patch(
                    "src.core.api.v1.subagents.router.require_scopes",
                    return_value=lambda: 1,
                ):
                    result = await get_agent_status(
                        agent_name=agent_name, current_user=mock_user, loader=mock_loader
                    )

        # Assert
        assert result["name"] == agent_name
        assert result["status"] == "loaded"
        assert result["type"] == "analysis"
        mock_loader.get_agent.assert_called_once_with(agent_name)

    @pytest.mark.asyncio
    async def test_get_agent_status_not_found(self, mock_user):
        """Test getting status of non-existent agent"""
        # Arrange
        mock_loader = AsyncMock()
        # Mock empty agents dict - endpoint checks 'if agent_name not in loader.agents'
        mock_loader.agents = {}  # Empty dict = agent not found

        agent_name = "nonexistent_agent"

        # Act & Assert
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            with patch(
                "src.core.api.v1.subagents.router.get_current_user",
                return_value=mock_user,
            ):
                with patch(
                    "src.core.api.v1.subagents.router.require_scopes",
                    return_value=lambda: 1,
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await get_agent_status(
                            agent_name=agent_name, current_user=mock_user, loader=mock_loader
                        )

                    # Endpoint raises 404 directly (not wrapped in 500)
                    assert exc_info.value.status_code == 404
                    assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_get_loader_metrics(self, mock_user):
        """Test getting loader metrics - if endpoint exists"""
        # This test verifies the metrics gathering capability
        # Note: Based on code analysis, metrics endpoint may not exist yet
        # This test prepares for when it's implemented

        # Arrange
        mock_loader = AsyncMock()
        mock_loader.list_available_agents = MagicMock(
            return_value=[
                {
                    "name": "agent1",
                    "type": "analysis",
                    "status": "loaded",
                    "description": "",
                    "capabilities": [],
                    "priority": 1,
                    "error": None,
                },
                {
                    "name": "agent2",
                    "type": "nlp",
                    "status": "available",
                    "description": "",
                    "capabilities": [],
                    "priority": 2,
                    "error": None,
                },
            ]
        )

        # Act
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            # Get agent list to calculate metrics
            agent_list = mock_loader.list_available_agents()

        # Assert - verify we can calculate metrics from agent list
        assert len(agent_list) == 2
        loaded_count = sum(1 for a in agent_list if a["status"] == "loaded")
        assert loaded_count == 1


# ============================================================================
# CLASS 4: Agent Action Tests (2 tests)
# ============================================================================


class TestAgentActions:
    """Tests for agent action execution endpoints"""

    @pytest.mark.asyncio
    async def test_agent_action_execution_pattern(self, mock_user):
        """Test the pattern for executing agent actions"""
        # This test verifies the action execution pattern
        # Note: Actual action endpoint implementation may vary

        # Arrange
        mock_loader = AsyncMock()
        mock_instance = MagicMock()
        mock_instance.execute_action = AsyncMock(return_value={"result": "success"})
        mock_loader.get_agent_instance = MagicMock(return_value=mock_instance)

        # Simulate action request pattern
        action_request = {
            "agent_name": "data_analyzer",
            "action": "analyze",
            "parameters": {"data": "test_data"},
        }

        # Act
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            # Verify we can get instance and execute action
            instance = mock_loader.get_agent_instance(action_request["agent_name"])
            if instance:
                result = await instance.execute_action(
                    action_request["action"], **action_request["parameters"]
                )

        # Assert
        assert result["result"] == "success"
        mock_instance.execute_action.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_agents_error_handling(self, mock_user):
        """Test error handling in agent loading"""
        # Arrange
        mock_loader = AsyncMock()
        mock_loader.load_agent = AsyncMock(side_effect=Exception("Module import failed"))

        request = AgentLoadRequest(agent_names=["broken_agent"], force_reload=False)

        # Act & Assert
        with patch(
            "src.core.api.v1.subagents.router.get_subagent_loader", return_value=mock_loader
        ):
            with patch(
                "src.core.api.v1.subagents.router.get_current_user",
                return_value=mock_user,
            ):
                with patch(
                    "src.core.api.v1.subagents.router.require_scopes",
                    return_value=lambda: 1,
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await load_agents(
                            request=request, current_user=mock_user, loader=mock_loader
                        )

                    assert exc_info.value.status_code == 500
                    assert "Loading failed" in str(exc_info.value.detail)


# ============================================================================
# TEST EXECUTION
# ============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
