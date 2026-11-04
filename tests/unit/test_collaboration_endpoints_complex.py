#!/usr/bin/env python3
"""
Unit tests for collaboration_endpoints_complex.py
Target: 50% coverage of 291 statements (146 lines covered)

Test Strategy:
- Class 1: TestAgentMeshEndpoints (7 tests) - Agent registration, heartbeat, status, network metrics
- Class 2: TestTaskCoordinationEndpoints (5 tests) - Task submission, status, cancellation
- Class 3: TestAdaptiveLearningEndpoints (3 tests) - Learning experience recording, performance tracking

Key Learnings Applied:
1. Mock where function is USED (import location), not where DEFINED
2. Use valid enum values in test data
3. Comprehensive error path testing
"""

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Mock the collaboration modules BEFORE importing the endpoint module
# sys.modules['src.core.collaboration.agent_mesh'] = MagicMock()
# sys.modules['src.core.collaboration.task_coordinator'] = MagicMock()
sys.modules["src.core.knowledge.adaptive_learning"] = MagicMock()
sys.modules["src.core.intelligence.system_optimizer"] = MagicMock()

# Now import endpoint functions
from src.core.api.collaboration_endpoints_complex import (
    AgentCapabilityModel,
    AgentMessageModel,
    AgentRegistrationModel,
    CollaborativeTaskModel,
    LearningExperienceModel,
    TaskRequirementModel,
    cancel_task,
    create_collaboration_group,
    discover_capabilities,
    get_agent_status,
    get_network_metrics,
    get_task_status,
    receive_messages,
    register_agent,
    router,
    send_message,
    submit_collaborative_task,
    unregister_agent,
    update_agent_heartbeat,
)

# ============================================================================
# CLASS 1: Agent Mesh Endpoints Tests (7 tests)
# ============================================================================


class TestAgentMeshEndpoints:
    """Tests for agent mesh network endpoints (registration, status, messaging)"""

    @pytest.mark.asyncio
    async def test_register_agent_success(self):
        """Test successful agent registration"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.register_agent = AsyncMock(return_value=True)

        registration_data = AgentRegistrationModel(
            agent_id="test_agent_001",
            agent_type="data_analysis",
            capabilities=[
                AgentCapabilityModel(
                    name="text_analysis",
                    description="Analyze text data",
                    input_types=["text/plain"],
                    output_types=["application/json"],
                    complexity_score=0.7,
                    processing_time_avg=2.5,
                    success_rate=0.95,
                    resources_required=["cpu", "memory"],
                )
            ],
            status="active",
            load_factor=0.3,
        )

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await register_agent(registration_data)

        # Assert
        assert result["success"] is True
        assert result["agent_id"] == "test_agent_001"
        assert "registered successfully" in result["message"]
        mock_mesh.register_agent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_agent_failure(self):
        """Test agent registration failure"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.register_agent = AsyncMock(return_value=False)

        registration_data = AgentRegistrationModel(
            agent_id="test_agent_002",
            agent_type="system_monitor",
            capabilities=[
                AgentCapabilityModel(
                    name="cpu_monitor",
                    description="Monitor CPU usage",
                    input_types=["system/metrics"],
                    output_types=["application/json"],
                    complexity_score=0.4,
                    processing_time_avg=0.5,
                    success_rate=0.99,
                    resources_required=["system_access"],
                )
            ],
        )

        # Act & Assert
        # When register_agent returns False, the endpoint raises HTTPException(400)
        # But this gets caught by the outer try/except and converted to HTTPException(500)
        # So we expect a 500 with "Failed to register agent" in the detail
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await register_agent(registration_data)

            assert exc_info.value.status_code == 500
            assert str(exc_info.value.detail) == "Er is een interne fout opgetreden."

    @pytest.mark.asyncio
    async def test_unregister_agent_success(self):
        """Test successful agent unregistration"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.unregister_agent = AsyncMock(return_value=True)
        agent_id = "test_agent_001"

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await unregister_agent(agent_id)

        # Assert
        assert result["success"] is True
        assert "unregistered successfully" in result["message"]
        mock_mesh.unregister_agent.assert_awaited_once_with(agent_id)

    @pytest.mark.asyncio
    async def test_unregister_agent_not_found(self):
        """Test agent unregistration when agent doesn't exist"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.unregister_agent = AsyncMock(return_value=False)
        agent_id = "nonexistent_agent"

        # Act & Assert
        # When unregister_agent returns False, gets caught and converted to 500
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await unregister_agent(agent_id)

            assert exc_info.value.status_code == 500
            assert str(exc_info.value.detail) == "Er is een interne fout opgetreden."

    @pytest.mark.asyncio
    async def test_update_agent_heartbeat_success(self):
        """Test successful agent heartbeat update"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.update_agent_heartbeat = AsyncMock(return_value=True)
        agent_id = "test_agent_001"

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await update_agent_heartbeat(agent_id)

        # Assert
        assert result["success"] is True
        assert "timestamp" in result
        # Production passes AgentHeartbeatMessage object, not agent_id string
        mock_mesh.update_agent_heartbeat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_agent_status_success(self):
        """Test retrieving agent status"""
        # Arrange
        mock_mesh = MagicMock()
        agent_id = "test_agent_001"

        # Production calls mesh.get_agent(agent_id) (sync) and reads attributes
        mock_agent = MagicMock()
        mock_agent.agent_id = agent_id
        mock_agent.status = "active"
        mock_agent.current_load = 0.45
        mock_agent.active_tasks = 3
        mock_agent.last_heartbeat = datetime.now(timezone.utc)
        mock_agent.capabilities = ["text_analysis"]
        mock_mesh.get_agent = MagicMock(return_value=mock_agent)

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await get_agent_status(agent_id)

        # Assert
        assert result["agent_id"] == agent_id
        assert result["status"] == "active"
        assert result["current_load"] == 0.45
        mock_mesh.get_agent.assert_called_once_with(agent_id)

    @pytest.mark.asyncio
    async def test_get_network_metrics_success(self):
        """Test retrieving network metrics"""
        # Arrange
        mock_mesh = MagicMock()
        # Production calls mesh.get_agent_statistics() (sync) and restructures keys
        mock_stats = {
            "total_agents": 25,
            "online_agents": 23,
            "available_agents": 20,
            "agents_by_type": {"data_analysis": 10},
            "average_load": 0.67,
        }
        mock_mesh.get_agent_statistics = MagicMock(return_value=mock_stats)

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await get_network_metrics()

        # Assert
        assert result["total_agents"] == 25
        assert result["online_agents"] == 23
        assert result["available_agents"] == 20
        mock_mesh.get_agent_statistics.assert_called_once()


# ============================================================================
# CLASS 2: Task Coordination Endpoints Tests (5 tests)
# ============================================================================


class TestTaskCoordinationEndpoints:
    """Tests for collaborative task coordination endpoints"""

    @pytest.mark.asyncio
    async def test_submit_collaborative_task_success(self):
        """Test successful task submission"""
        # Arrange
        mock_coordinator = AsyncMock()
        task_id = "task_12345"
        mock_coordinator.submit_collaborative_task = AsyncMock(return_value=task_id)

        task_data = CollaborativeTaskModel(
            description="Analyze large dataset collaboratively",
            requirements=[
                TaskRequirementModel(
                    capability="data_processing",
                    priority=8,
                    estimated_time=120.0,
                    resources_needed=["cpu", "memory"],
                    dependencies=[],
                )
            ],
            deadline_hours=4.0,
        )
        requester_agent = "agent_supervisor_001"

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_task_coordinator",
            return_value=mock_coordinator,
        ):
            result = await submit_collaborative_task(task_data, requester_agent)

        # Assert
        assert result["success"] is True
        assert result["task_id"] == task_id
        assert "submitted_at" in result
        mock_coordinator.submit_collaborative_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_collaborative_task_failure(self):
        """Test task submission failure"""
        # Arrange
        mock_coordinator = AsyncMock()
        mock_coordinator.submit_collaborative_task = AsyncMock(return_value=None)

        task_data = CollaborativeTaskModel(
            description="Invalid task",
            requirements=[
                TaskRequirementModel(
                    capability="nonexistent_capability",
                    priority=5,
                    estimated_time=60.0,
                    resources_needed=["gpu"],
                )
            ],
        )

        # Act & Assert
        # When submit returns None, gets caught and converted to 500
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_task_coordinator",
            return_value=mock_coordinator,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await submit_collaborative_task(task_data, "requester_agent")

            assert exc_info.value.status_code == 500
            assert str(exc_info.value.detail) == "Er is een interne fout opgetreden."

    @pytest.mark.asyncio
    async def test_get_task_status_success(self):
        """Test retrieving task status"""
        # Arrange
        mock_coordinator = AsyncMock()
        task_id = "task_12345"
        expected_status = {
            "task_id": task_id,
            "status": "in_progress",
            "progress_percentage": 45.0,
            "assigned_agents": ["agent_001", "agent_002"],
            "estimated_completion": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        }
        mock_coordinator.get_task_status = AsyncMock(return_value=expected_status)

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_task_coordinator",
            return_value=mock_coordinator,
        ):
            result = await get_task_status(task_id)

        # Assert
        assert result == expected_status
        assert result["task_id"] == task_id
        assert result["status"] == "in_progress"
        mock_coordinator.get_task_status.assert_awaited_once_with(task_id)

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self):
        """Test task status retrieval when task doesn't exist"""
        # Arrange
        mock_coordinator = AsyncMock()
        mock_coordinator.get_task_status = AsyncMock(return_value=None)
        task_id = "nonexistent_task"

        # Act & Assert
        # When get_task_status returns None, gets caught and converted to 500
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_task_coordinator",
            return_value=mock_coordinator,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_task_status(task_id)

            assert exc_info.value.status_code == 500
            assert str(exc_info.value.detail) == "Er is een interne fout opgetreden."

    @pytest.mark.asyncio
    async def test_cancel_task_success(self):
        """Test successful task cancellation"""
        # Arrange
        mock_coordinator = AsyncMock()
        mock_coordinator.cancel_task = AsyncMock(return_value=True)
        task_id = "task_12345"

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_task_coordinator",
            return_value=mock_coordinator,
        ):
            result = await cancel_task(task_id)

        # Assert
        assert result["success"] is True
        mock_coordinator.cancel_task.assert_awaited_once_with(task_id)


# ============================================================================
# CLASS 3: Messaging Endpoints Tests (3 tests)
# ============================================================================


class TestMessagingEndpoints:
    """Tests for agent-to-agent messaging endpoints"""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.send_message = AsyncMock(return_value=True)

        from_agent = "agent_001"
        message_data = AgentMessageModel(
            to_agent="agent_002",
            message_type="task_assignment",
            priority="high",
            content={"action": "process_data", "data_id": "dataset_123"},
            requires_response=True,
            expires_in_seconds=300,
        )

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await send_message(from_agent, message_data)

        # Assert
        assert result["success"] is True
        assert "message_id" in result
        assert "sent_at" in result
        mock_mesh.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_receive_messages_success(self):
        """Test receiving messages for an agent"""
        # Arrange
        mock_mesh = AsyncMock()
        agent_id = "agent_002"
        now = datetime.now(timezone.utc)

        # Production uses msg.get("id") — messages are dicts, not objects
        mock_message_1 = {
            "id": "msg_001",
            "from_agent": "agent_001",
            "message_type": "task_request",
            "priority": "HIGH",
            "content": {"task": "analyze"},
            "timestamp": now,
            "requires_response": True,
        }
        mock_message_2 = {
            "id": "msg_002",
            "from_agent": "agent_003",
            "message_type": "status_update",
            "priority": "NORMAL",
            "content": {"status": "completed"},
            "timestamp": now,
            "requires_response": False,
        }

        mock_mesh.receive_messages = AsyncMock(
            return_value=[mock_message_1, mock_message_2]
        )

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await receive_messages(agent_id, limit=10)

        # Assert
        assert result["agent_id"] == agent_id
        assert result["messages_count"] == 2
        assert len(result["messages"]) == 2
        assert result["messages"][0]["id"] == "msg_001"
        assert result["messages"][1]["id"] == "msg_002"
        mock_mesh.receive_messages.assert_awaited_once_with(agent_id, 10)

    @pytest.mark.asyncio
    async def test_create_collaboration_group_success(self):
        """Test creating a collaboration group"""
        # Arrange
        mock_mesh = AsyncMock()
        mock_mesh.create_collaboration_group = AsyncMock(return_value=True)

        group_id = "group_data_analysis"
        agent_ids = ["agent_001", "agent_002", "agent_003"]

        # Act
        with patch(
            "src.core.api.collaboration_endpoints_complex.get_agent_registry",
            return_value=mock_mesh,
        ):
            result = await create_collaboration_group(group_id, agent_ids)

        # Assert
        assert result["success"] is True
        assert result["group_id"] == group_id
        assert result["members"] == agent_ids
        assert "created_at" in result
        mock_mesh.create_collaboration_group.assert_awaited_once_with(group_id, agent_ids)


# ============================================================================
# TEST EXECUTION
# ============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
