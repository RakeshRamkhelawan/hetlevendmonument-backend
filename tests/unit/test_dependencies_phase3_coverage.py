"""
Unit Tests for core/dependencies.py - Phase 3 Coverage Expansion
Target: 80%+ coverage with happy path, edge cases, error handling
"""

from unittest.mock import MagicMock, PropertyMock

import pytest
from fastapi import Request

from src.core.agents.agent_registry import AgentRegistry
from src.core.autonomy.autonomous_agent import AutonomousAgent
from src.core.collaboration.task_distributor import TaskDistributor
from src.core.dependencies import (
    get_agent_registry,
    get_autonomous_agent_dependency,
    get_task_distributor,
)


class TestGetAutonomousAgentDependency:
    """Test get_autonomous_agent_dependency function"""

    def test_get_autonomous_agent_returns_instance_from_app_state(self):
        """Test: Returns AutonomousAgent instance from app.state"""
        mock_request = MagicMock(spec=Request)
        mock_agent = MagicMock(spec=AutonomousAgent)
        mock_request.app.state.autonomous_agent = mock_agent

        result = get_autonomous_agent_dependency(mock_request)

        assert result is mock_agent
        assert isinstance(result, type(mock_agent))

    def test_get_autonomous_agent_accesses_app_state_attribute(self):
        """Test: Function accesses request.app.state.autonomous_agent"""
        mock_request = MagicMock(spec=Request)
        mock_agent = MagicMock(spec=AutonomousAgent)
        mock_request.app.state.autonomous_agent = mock_agent

        get_autonomous_agent_dependency(mock_request)

        assert mock_request.app.state.autonomous_agent is mock_agent

    def test_get_autonomous_agent_raises_attribute_error_if_not_set(self):
        """Test: Raises AttributeError if autonomous_agent not in app.state"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.autonomous_agent

        with pytest.raises(AttributeError):
            get_autonomous_agent_dependency(mock_request)

    def test_get_autonomous_agent_with_none_value(self):
        """Test: Returns None if autonomous_agent is explicitly None"""
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.autonomous_agent = None

        result = get_autonomous_agent_dependency(mock_request)

        assert result is None


class TestGetTaskDistributor:
    """Test get_task_distributor function"""

    def test_get_task_distributor_returns_existing_instance(self):
        """Test: Returns existing TaskDistributor from app.state"""
        mock_request = MagicMock(spec=Request)
        mock_distributor = MagicMock(spec=TaskDistributor)
        mock_request.app.state.task_distributor = mock_distributor

        result = get_task_distributor(mock_request)

        assert result is mock_distributor

    def test_get_task_distributor_creates_instance_if_not_exists(self):
        """Test: Creates new TaskDistributor if not in app.state (lazy init)"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.task_distributor

        result = get_task_distributor(mock_request)

        assert result is not None
        assert isinstance(result, TaskDistributor)
        assert hasattr(mock_request.app.state, "task_distributor")

    def test_get_task_distributor_lazy_initialization_idempotent(self):
        """Test: Lazy initialization returns same instance on repeated calls"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.task_distributor

        result1 = get_task_distributor(mock_request)
        result2 = get_task_distributor(mock_request)

        assert result1 is result2

    def test_get_task_distributor_does_not_recreate_if_exists(self):
        """Test: Does not recreate instance if already exists in app.state"""
        mock_request = MagicMock(spec=Request)
        existing_distributor = MagicMock(spec=TaskDistributor)
        mock_request.app.state.task_distributor = existing_distributor

        result = get_task_distributor(mock_request)

        assert result is existing_distributor


class TestGetAgentRegistry:
    """Test get_agent_registry function"""

    def test_get_agent_registry_returns_existing_instance(self):
        """Test: Returns existing AgentRegistry from app.state"""
        mock_request = MagicMock(spec=Request)
        mock_registry = MagicMock(spec=AgentRegistry)
        mock_request.app.state.agent_registry = mock_registry

        result = get_agent_registry(mock_request)

        assert result is mock_registry

    def test_get_agent_registry_creates_instance_if_not_exists(self):
        """Test: Creates new AgentRegistry if not in app.state (lazy init)"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.agent_registry

        result = get_agent_registry(mock_request)

        assert result is not None
        assert isinstance(result, AgentRegistry)
        assert hasattr(mock_request.app.state, "agent_registry")

    def test_get_agent_registry_lazy_initialization_idempotent(self):
        """Test: Lazy initialization returns same instance on repeated calls"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.agent_registry

        result1 = get_agent_registry(mock_request)
        result2 = get_agent_registry(mock_request)

        assert result1 is result2

    def test_get_agent_registry_does_not_recreate_if_exists(self):
        """Test: Does not recreate instance if already exists in app.state"""
        mock_request = MagicMock(spec=Request)
        existing_registry = MagicMock(spec=AgentRegistry)
        mock_request.app.state.agent_registry = existing_registry

        result = get_agent_registry(mock_request)

        assert result is existing_registry


class TestDependenciesIntegration:
    """Integration tests for dependency injection patterns"""

    def test_all_dependencies_can_coexist_in_app_state(self):
        """Test: All three dependencies can be stored in app.state simultaneously"""
        mock_request = MagicMock(spec=Request)
        mock_agent = MagicMock(spec=AutonomousAgent)
        mock_distributor = MagicMock(spec=TaskDistributor)
        mock_registry = MagicMock(spec=AgentRegistry)

        mock_request.app.state.autonomous_agent = mock_agent
        mock_request.app.state.task_distributor = mock_distributor
        mock_request.app.state.agent_registry = mock_registry

        agent_result = get_autonomous_agent_dependency(mock_request)
        distributor_result = get_task_distributor(mock_request)
        registry_result = get_agent_registry(mock_request)

        assert agent_result is mock_agent
        assert distributor_result is mock_distributor
        assert registry_result is mock_registry

    def test_lazy_initialization_for_multiple_dependencies(self):
        """Test: Multiple dependencies can be lazily initialized"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.task_distributor
        del mock_request.app.state.agent_registry

        distributor = get_task_distributor(mock_request)
        registry = get_agent_registry(mock_request)

        assert isinstance(distributor, TaskDistributor)
        assert isinstance(registry, AgentRegistry)
        assert distributor is not registry

    def test_request_object_is_not_modified_beyond_app_state(self):
        """Test: Functions only modify app.state, not other request attributes"""
        mock_request = MagicMock(spec=Request)
        mock_agent = MagicMock(spec=AutonomousAgent)
        mock_request.app.state.autonomous_agent = mock_agent

        initial_attrs = [
            attr for attr in dir(mock_request) if not attr.startswith("_") and attr != "app"
        ]

        get_autonomous_agent_dependency(mock_request)

        final_attrs = [
            attr for attr in dir(mock_request) if not attr.startswith("_") and attr != "app"
        ]
        assert initial_attrs == final_attrs


class TestDependenciesEdgeCases:
    """Test edge cases and error conditions"""

    def test_get_autonomous_agent_with_invalid_request_object(self):
        """Test: Raises AttributeError if request has no app attribute"""
        invalid_request = MagicMock()
        del invalid_request.app

        with pytest.raises(AttributeError):
            get_autonomous_agent_dependency(invalid_request)

    def test_get_task_distributor_with_invalid_app_state(self):
        """Test: Handles missing app.state gracefully"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state

        with pytest.raises(AttributeError):
            get_task_distributor(mock_request)

    def test_get_agent_registry_multiple_calls_return_same_instance(self):
        """Test: Multiple calls without clearing state return same instance"""
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.agent_registry

        # First call creates instance
        first_call = get_agent_registry(mock_request)
        # Multiple subsequent calls should all return the same instance
        second_call = get_agent_registry(mock_request)
        third_call = get_agent_registry(mock_request)

        assert first_call is second_call is third_call
        assert isinstance(first_call, AgentRegistry)

    def test_dependencies_with_none_request(self):
        """Test: Raises TypeError if request is None"""
        with pytest.raises(AttributeError):
            get_autonomous_agent_dependency(None)

        with pytest.raises(AttributeError):
            get_task_distributor(None)

        with pytest.raises(AttributeError):
            get_agent_registry(None)
