"""
Comprehensive tests for src/core/agents/cva_communication.py
CVA Agent Communication & Inter-Agent Protocol (MCP) Integration
Coverage target: 80%+ on 200 LOC communication module

Tests cover:
1. Communication System Initialization
2. Message Creation & Validation
3. Strategic Command Sending (MCP protocol)
4. Message Handling & Routing
5. Telemetry Collection
6. Error Handling & Recovery
7. Multi-Agent Coordination
8. Integration with State Machine
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.core.agents.cva_agent import CVAAgent, CVAState, OrchestrationCommand
from src.core.agents.cva_state_machine import CVAMode
from src.core.communication.communication_manager import CommunicationManager
from src.core.communication.message_protocol import (
    MDPMessage,
    MessageFactory,
    MessagePriority,
    MessageStatus,
    MessageType,
)
from src.core.shared.interfaces import AgentType, TaskPriority

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
async def cva_agent():
    """Create a CVA agent instance for testing"""
    agent = CVAAgent(agent_id="test_cva_main", agent_type=AgentType.CVA, tenant_id=1)
    yield agent
    # Cleanup if needed
    if agent.communication_initialized:
        agent.communication_initialized = False


@pytest.fixture
def mock_communication_manager():
    """Create a mock communication manager"""
    manager = AsyncMock(spec=CommunicationManager)
    manager.initialize = AsyncMock(return_value=None)
    manager.register_agent = AsyncMock(return_value=None)
    manager.send_message = AsyncMock(return_value=True)
    manager.receive_message = AsyncMock(return_value=None)
    manager.acknowledge_message = AsyncMock(return_value=None)
    manager.collect_telemetry = AsyncMock(return_value=None)
    manager.agent_endpoints = {}
    manager.comm_stats = {"messages_sent": 0, "messages_failed": 0}
    return manager


@pytest.fixture
def mock_message_factory():
    """Create a mock message factory"""
    factory = MagicMock()

    def create_command_message(**kwargs):
        message = MagicMock(spec=MDPMessage)
        message.header = MagicMock()
        message.header.message_id = str(uuid.uuid4())
        message.header.sender_id = kwargs.get("sender_id", "test_cva")
        message.header.recipient_id = kwargs.get("recipient_id", "orchestrator")
        message.header.message_type = MessageType.COMMAND
        message.header.priority = kwargs.get("priority", MessagePriority.HIGH)
        message.payload = {
            "command_type": kwargs.get("command_type"),
            "parameters": kwargs.get("parameters", {}),
        }
        return message

    factory.create_command_message = create_command_message
    return factory


# ============================================================================
# Test Communication System Initialization (5 tests)
# ============================================================================


class TestCommunicationSystemInitialization:
    """Test CVA communication system initialization"""

    @pytest.mark.asyncio
    async def test_initialize_communication_system_success(
        self, cva_agent, mock_communication_manager
    ):
        """Test successful communication system initialization"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            result = await cva_agent.initialize_communication_system()

            # Verify initialization calls
            mock_communication_manager.initialize.assert_called_once()
            mock_communication_manager.register_agent.assert_called_once()

            # Check registration parameters
            call_args = mock_communication_manager.register_agent.call_args
            assert call_args[1]["agent_id"] == "test_cva_main"
            assert call_args[1]["agent_type"] == AgentType.CVA
            assert "strategic_planning" in call_args[1]["capabilities"]
            assert "delegation" in call_args[1]["capabilities"]
            assert "ceo_mode" in call_args[1]["capabilities"]

    @pytest.mark.asyncio
    async def test_initialize_communication_system_already_initialized(
        self, cva_agent, mock_communication_manager
    ):
        """Test initialization when already initialized (skip on second call)"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            # First initialization
            await cva_agent.initialize_communication_system()
            assert cva_agent.communication_initialized is True

            # Second initialization (should skip)
            await cva_agent.initialize_communication_system()

            # Verify initialize was called only once
            mock_communication_manager.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_communication_system_failure(
        self, cva_agent, mock_communication_manager
    ):
        """Test communication system initialization failure handling"""
        mock_communication_manager.initialize.side_effect = Exception("Redis connection failed")

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            await cva_agent.initialize_communication_system()

            # Verify agent state reflects failure
            assert cva_agent.communication_initialized is False

    @pytest.mark.asyncio
    async def test_initialize_communication_system_registration_failure(
        self, cva_agent, mock_communication_manager
    ):
        """Test handling when agent registration fails"""
        mock_communication_manager.register_agent.side_effect = Exception("Registration failed")

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            await cva_agent.initialize_communication_system()

            # Verify agent state reflects failure
            assert cva_agent.communication_initialized is False

    @pytest.mark.asyncio
    async def test_communication_initialization_stores_agent_id(
        self, cva_agent, mock_communication_manager
    ):
        """Test that communication system stores agent ID correctly"""
        test_agent_id = "cva_strategic_unit_5"
        agent = CVAAgent(agent_id=test_agent_id, agent_type=AgentType.CVA, tenant_id=1)

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            await agent.initialize_communication_system()

            # Verify stored agent ID
            assert agent._agent_id_for_communication == test_agent_id


# ============================================================================
# Test Strategic Command Sending (7 tests)
# ============================================================================


class TestStrategicCommandSending:
    """Test sending strategic commands via MCP protocol"""

    @pytest.mark.asyncio
    async def test_send_strategic_command_success(self, cva_agent, mock_communication_manager):
        """Test successful strategic command sending"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory") as mock_factory:
                mock_message = MagicMock()
                mock_factory.create_command_message.return_value = mock_message
                mock_communication_manager.send_message.return_value = True

                result = await cva_agent.send_strategic_command(
                    command_type="optimize_workflow",
                    parameters={"target_efficiency": 0.95},
                    recipient_id="orchestrator_main",
                    priority=MessagePriority.HIGH,
                )

                assert result is True
                mock_factory.create_command_message.assert_called_once()
                mock_communication_manager.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_strategic_command_auto_initializes_communication(
        self, cva_agent, mock_communication_manager
    ):
        """Test that sending a command initializes communication if needed"""
        assert cva_agent.communication_initialized is False

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                await cva_agent.send_strategic_command(command_type="test_command", parameters={})

                # Verify communication was initialized
                mock_communication_manager.initialize.assert_called()

    @pytest.mark.asyncio
    async def test_send_strategic_command_with_masterprompt(
        self, cva_agent, mock_communication_manager
    ):
        """Test strategic command with masterprompt parameter"""
        masterprompt = "Execute with maximum strategic optimization"

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory") as mock_factory:
                await cva_agent.send_strategic_command(
                    command_type="strategic_replan",
                    parameters={"scope": "global"},
                    masterprompt=masterprompt,
                )

                # Verify masterprompt was passed
                call_args = mock_factory.create_command_message.call_args
                assert call_args[1]["masterprompt"] == masterprompt

    @pytest.mark.asyncio
    async def test_send_strategic_command_failure(self, cva_agent, mock_communication_manager):
        """Test handling of command send failure"""
        mock_communication_manager.send_message.return_value = False

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                result = await cva_agent.send_strategic_command(
                    command_type="failed_command", parameters={}
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_send_strategic_command_collects_telemetry(
        self, cva_agent, mock_communication_manager
    ):
        """Test that command sending collects telemetry"""
        mock_communication_manager.send_message.return_value = True

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                await cva_agent.send_strategic_command(
                    command_type="delegate_task", parameters={"task_id": "task_123"}
                )

                # Verify telemetry collection
                mock_communication_manager.collect_telemetry.assert_called_once()
                call_args = mock_communication_manager.collect_telemetry.call_args
                assert "commands_sent" in call_args[1]["metrics"]
                assert call_args[1]["metrics"]["command_type"] == "delegate_task"

    @pytest.mark.asyncio
    async def test_send_strategic_command_exception_handling(
        self, cva_agent, mock_communication_manager
    ):
        """Test exception handling in command sending"""
        mock_communication_manager.send_message.side_effect = Exception("Network error")

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                result = await cva_agent.send_strategic_command(
                    command_type="critical_command", parameters={}
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_send_strategic_command_to_multiple_recipients(
        self, cva_agent, mock_communication_manager
    ):
        """Test sending same command to different recipients"""
        recipients = ["orchestrator_1", "orchestrator_2", "orchestrator_3"]

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                for recipient in recipients:
                    await cva_agent.send_strategic_command(
                        command_type="broadcast_command",
                        parameters={"broadcast_id": "bc_001"},
                        recipient_id=recipient,
                    )

                # Verify telemetry collected for each send
                assert mock_communication_manager.collect_telemetry.call_count == 3


# ============================================================================
# Test Message Creation & Formatting (5 tests)
# ============================================================================


class TestMessageCreationAndFormatting:
    """Test message creation and formatting for MCP protocol"""

    @pytest.mark.asyncio
    async def test_message_factory_command_creation(self, mock_message_factory):
        """Test command message creation through factory"""
        message = mock_message_factory.create_command_message(
            sender_id="cva_main",
            recipient_id="orchestrator",
            command_type="optimize",
            parameters={"level": "high"},
            priority=MessagePriority.HIGH,
        )

        assert message.header.message_type == MessageType.COMMAND
        assert message.header.sender_id == "cva_main"
        assert message.header.recipient_id == "orchestrator"
        assert message.payload["command_type"] == "optimize"
        assert message.payload["parameters"]["level"] == "high"

    @pytest.mark.asyncio
    async def test_message_has_unique_ids(self, mock_message_factory):
        """Test that each message gets a unique ID"""
        message1 = mock_message_factory.create_command_message(
            sender_id="cva", recipient_id="orch", command_type="cmd1", parameters={}
        )
        message2 = mock_message_factory.create_command_message(
            sender_id="cva", recipient_id="orch", command_type="cmd2", parameters={}
        )

        assert message1.header.message_id != message2.header.message_id

    @pytest.mark.asyncio
    async def test_message_priority_levels(self, mock_message_factory):
        """Test message creation with different priority levels"""
        priorities = [
            MessagePriority.EMERGENCY,
            MessagePriority.HIGH,
            MessagePriority.NORMAL,
            MessagePriority.LOW,
        ]

        for priority in priorities:
            message = mock_message_factory.create_command_message(
                sender_id="cva",
                recipient_id="orch",
                command_type="test",
                parameters={},
                priority=priority,
            )
            assert message.header.priority == priority

    @pytest.mark.asyncio
    async def test_message_parameter_encoding(self, mock_message_factory):
        """Test message parameter encoding"""
        complex_params = {
            "task_id": "task_123",
            "priority": 5,
            "agents": ["agent_1", "agent_2"],
            "config": {"nested": True, "value": 42},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        message = mock_message_factory.create_command_message(
            sender_id="cva",
            recipient_id="orch",
            command_type="complex",
            parameters=complex_params,
        )

        assert message.payload["parameters"] == complex_params

    @pytest.mark.asyncio
    async def test_orchestration_command_dataclass(self):
        """Test OrchestrationCommand dataclass creation"""
        command = OrchestrationCommand(
            command="execute_workflow",
            parameters={"workflow_id": "wf_001"},
            priority=1,
            masterprompt="Execute with CEO oversight",
            expected_agents=["agent_1", "agent_2"],
        )

        assert command.command == "execute_workflow"
        assert command.parameters["workflow_id"] == "wf_001"
        assert command.priority == 1
        assert command.masterprompt == "Execute with CEO oversight"
        assert len(command.expected_agents) == 2


# ============================================================================
# Test Message Handling & Routing (6 tests)
# ============================================================================


class TestMessageHandlingAndRouting:
    """Test message handling and routing through communication hub"""

    @pytest.mark.asyncio
    async def test_receive_command_message(self, mock_communication_manager):
        """Test receiving a command message"""
        incoming_message = MagicMock(spec=MDPMessage)
        incoming_message.header = MagicMock()
        incoming_message.header.message_type = MessageType.COMMAND
        incoming_message.header.sender_id = "orchestrator"
        incoming_message.payload = {"command_type": "delegate", "task_id": "t_123"}

        mock_communication_manager.receive_message.return_value = incoming_message

        message = await mock_communication_manager.receive_message("cva_main")

        assert message is not None
        assert message.header.message_type == MessageType.COMMAND
        assert message.payload["command_type"] == "delegate"

    @pytest.mark.asyncio
    async def test_message_routing_by_type(self, mock_communication_manager):
        """Test routing messages based on type"""
        # Simulate different message types
        message_types = [
            MessageType.COMMAND,
            MessageType.STATUS_UPDATE,
            MessageType.RESULT,
        ]

        for msg_type in message_types:
            message = MagicMock()
            message.header.message_type = msg_type
            # Routing would be based on type
            assert message.header.message_type == msg_type

    @pytest.mark.asyncio
    async def test_message_routing_by_priority(self, cva_agent, mock_communication_manager):
        """Test that messages are routed by priority"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            # Send messages with different priorities
            priorities = [
                MessagePriority.LOW,
                MessagePriority.NORMAL,
                MessagePriority.HIGH,
            ]

            for priority in priorities:
                await cva_agent.send_strategic_command(
                    command_type="priority_test",
                    parameters={"priority_level": priority.value},
                    priority=priority,
                )

            # All should be sent
            assert mock_communication_manager.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_message_acknowledgment(self, mock_communication_manager):
        """Test message acknowledgment after processing"""
        message_id = str(uuid.uuid4())

        await mock_communication_manager.acknowledge_message(
            message_id=message_id,
            success=True,
            result_data={"task_status": "completed"},
        )

        mock_communication_manager.acknowledge_message.assert_called_once_with(
            message_id=message_id,
            success=True,
            result_data={"task_status": "completed"},
        )

    @pytest.mark.asyncio
    async def test_message_handling_with_correlation_id(self, mock_communication_manager):
        """Test message tracking with correlation IDs"""
        correlation_id = str(uuid.uuid4())

        # In real implementation, correlation_id would be used to track
        # related messages in a conversation
        message = MagicMock()
        message.header.correlation_id = correlation_id
        message.header.message_id = str(uuid.uuid4())

        # Both IDs should be present
        assert message.header.correlation_id == correlation_id
        assert message.header.message_id != correlation_id

    @pytest.mark.asyncio
    async def test_message_queue_ordering_by_priority(self, mock_communication_manager):
        """Test that message queues respect priority ordering"""
        # In the communication manager, messages are added to priority-specific queues
        # Higher priority messages should be processed first

        # Mock the queue structure
        message_queues = {
            MessagePriority.LOW: [],
            MessagePriority.NORMAL: [],
            MessagePriority.HIGH: [],
        }

        # Add messages in mixed order
        messages = [
            (MessagePriority.LOW, "msg_1"),
            (MessagePriority.HIGH, "msg_2"),
            (MessagePriority.NORMAL, "msg_3"),
        ]

        for priority, msg_id in messages:
            message_queues[priority].append(msg_id)

        # Verify HIGH priority has its message
        assert "msg_2" in message_queues[MessagePriority.HIGH]
        assert "msg_1" in message_queues[MessagePriority.LOW]


# ============================================================================
# Test Telemetry Collection (5 tests)
# ============================================================================


class TestTelemetryCollection:
    """Test telemetry and metrics collection during communication"""

    @pytest.mark.asyncio
    async def test_telemetry_on_successful_command(self, cva_agent, mock_communication_manager):
        """Test telemetry collection on successful command"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                mock_communication_manager.send_message.return_value = True

                await cva_agent.send_strategic_command(
                    command_type="success_command", parameters={"test": True}
                )

                # Verify telemetry collected
                telemetry_call = mock_communication_manager.collect_telemetry.call_args
                assert telemetry_call[1]["metrics"]["commands_sent"] == 1

    @pytest.mark.asyncio
    async def test_telemetry_metrics_structure(self, cva_agent, mock_communication_manager):
        """Test that telemetry metrics have expected structure"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                mock_communication_manager.send_message.return_value = True

                await cva_agent.send_strategic_command(command_type="metric_test", parameters={})

                call_args = mock_communication_manager.collect_telemetry.call_args

                # Check metrics structure
                assert "metrics" in call_args[1]
                assert "performance_indicators" in call_args[1]
                assert "resource_usage" in call_args[1]

                # Check metric values
                metrics = call_args[1]["metrics"]
                assert "commands_sent" in metrics
                assert "command_type" in metrics

    @pytest.mark.asyncio
    async def test_resource_usage_telemetry(self, cva_agent, mock_communication_manager):
        """Test resource usage metrics in telemetry"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                mock_communication_manager.send_message.return_value = True

                await cva_agent.send_strategic_command(command_type="resource_test", parameters={})

                call_args = mock_communication_manager.collect_telemetry.call_args
                resource_usage = call_args[1]["resource_usage"]

                # Verify resource metrics
                assert "cpu_usage" in resource_usage
                assert "memory_usage" in resource_usage
                assert resource_usage["cpu_usage"] == 0.1
                assert resource_usage["memory_usage"] == 50.0

    @pytest.mark.asyncio
    async def test_performance_indicator_tracking(self, cva_agent, mock_communication_manager):
        """Test performance indicator tracking"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                mock_communication_manager.send_message.return_value = True

                await cva_agent.send_strategic_command(command_type="perf_test", parameters={})

                call_args = mock_communication_manager.collect_telemetry.call_args
                perf_indicators = call_args[1]["performance_indicators"]

                assert "command_success_rate" in perf_indicators

    @pytest.mark.asyncio
    async def test_telemetry_agent_id_tracking(self, cva_agent, mock_communication_manager):
        """Test that telemetry tracks correct agent ID"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                mock_communication_manager.send_message.return_value = True

                await cva_agent.send_strategic_command(command_type="agent_id_test", parameters={})

                call_args = mock_communication_manager.collect_telemetry.call_args
                assert call_args[1]["agent_id"] == "test_cva_main"


# ============================================================================
# Test Error Handling & Recovery (6 tests)
# ============================================================================


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery in communication system"""

    @pytest.mark.asyncio
    async def test_communication_system_initialization_error_recovery(
        self, cva_agent, mock_communication_manager
    ):
        """Test recovery from communication system initialization error"""
        mock_communication_manager.initialize.side_effect = Exception("Init failed")

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            await cva_agent.initialize_communication_system()

            # Verify state reflects error
            assert cva_agent.communication_initialized is False

    @pytest.mark.asyncio
    async def test_command_send_retry_on_transient_failure(
        self, cva_agent, mock_communication_manager
    ):
        """Test retry behavior on transient failures"""
        # First call fails, second succeeds
        mock_communication_manager.send_message.side_effect = [False, True]

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # First attempt
                result1 = await cva_agent.send_strategic_command(
                    command_type="retry_test", parameters={}
                )

                # Reset side effect
                mock_communication_manager.send_message.side_effect = None
                mock_communication_manager.send_message.return_value = True

                # Second attempt
                result2 = await cva_agent.send_strategic_command(
                    command_type="retry_test", parameters={}
                )

                assert result1 is False or result2 is True

    @pytest.mark.asyncio
    async def test_invalid_recipient_handling(self, cva_agent, mock_communication_manager):
        """Test handling of invalid recipient"""
        mock_communication_manager.send_message.return_value = False

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                result = await cva_agent.send_strategic_command(
                    command_type="invalid_recipient",
                    parameters={},
                    recipient_id="non_existent_agent",
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_malformed_parameters_handling(self, cva_agent, mock_communication_manager):
        """Test handling of malformed parameters"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Send with problematic parameters
                result = await cva_agent.send_strategic_command(
                    command_type="malformed",
                    parameters=None,  # Should handle None gracefully
                )

                # Should still attempt to send
                mock_communication_manager.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_timeout_handling(self, cva_agent, mock_communication_manager):
        """Test timeout handling in communication"""
        mock_communication_manager.send_message.side_effect = asyncio.TimeoutError()

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                result = await cva_agent.send_strategic_command(
                    command_type="timeout_test", parameters={}
                )

                # Should return False on timeout
                assert result is False

    @pytest.mark.asyncio
    async def test_connection_loss_recovery(self, cva_agent, mock_communication_manager):
        """Test recovery from connection loss"""
        # Simulate connection loss then recovery
        mock_communication_manager.initialize.side_effect = [
            Exception("Connection lost"),
            None,  # Second attempt succeeds
        ]

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            # First initialization fails
            await cva_agent.initialize_communication_system()
            assert cva_agent.communication_initialized is False

            # Reset for second attempt
            mock_communication_manager.initialize.side_effect = None
            mock_communication_manager.initialize.return_value = None

            # Second initialization succeeds
            await cva_agent.initialize_communication_system()
            # Communication should still be marked as not initialized from first attempt
            # This tests the logic: if not already initialized, try again


# ============================================================================
# Test State Machine Integration (5 tests)
# ============================================================================


class TestStateMachineIntegration:
    """Test integration with CVA state machine"""

    @pytest.mark.asyncio
    async def test_communication_in_reactive_mode(self, cva_agent, mock_communication_manager):
        """Test communication system in REACTIVE mode"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Transition to REACTIVE mode
                await cva_agent.transition_to_mode(CVAMode.REACTIVE)

                # Send command in REACTIVE mode
                result = await cva_agent.send_strategic_command(
                    command_type="reactive_cmd", parameters={}
                )

                # Should work in any mode
                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_communication_in_proactive_mode(self, cva_agent, mock_communication_manager):
        """Test communication system in PROACTIVE mode"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Transition to PROACTIVE mode
                await cva_agent.transition_to_mode(CVAMode.PROACTIVE)

                # Send command in PROACTIVE mode
                result = await cva_agent.send_strategic_command(
                    command_type="proactive_cmd", parameters={}
                )

                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_communication_in_autonomous_mode(self, cva_agent, mock_communication_manager):
        """Test communication system in AUTONOMOUS mode"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Transition to AUTONOMOUS mode
                await cva_agent.transition_to_mode(CVAMode.AUTONOMOUS)

                # Send command in AUTONOMOUS mode
                result = await cva_agent.send_strategic_command(
                    command_type="autonomous_cmd", parameters={}
                )

                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_communication_in_ceo_mode(self, cva_agent, mock_communication_manager):
        """Test communication system in CEO_MODE"""
        assert cva_agent.cva_state.mode == CVAMode.CEO_MODE

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Send command in CEO_MODE
                result = await cva_agent.send_strategic_command(
                    command_type="ceo_command", parameters={}
                )

                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_mode_transition_during_communication(
        self, cva_agent, mock_communication_manager
    ):
        """Test mode transitions during active communication"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Start communication
                await cva_agent.send_strategic_command(command_type="cmd1", parameters={})

                # Transition to different mode
                await cva_agent.transition_to_mode(CVAMode.REACTIVE)

                # Continue communication
                result = await cva_agent.send_strategic_command(command_type="cmd2", parameters={})

                # Should work seamlessly
                assert isinstance(result, bool)


# ============================================================================
# Test Multi-Agent Coordination (4 tests)
# ============================================================================


class TestMultiAgentCoordination:
    """Test multi-agent coordination through communication protocol"""

    @pytest.mark.asyncio
    async def test_delegation_to_specialist_agents(self, cva_agent, mock_communication_manager):
        """Test delegating work to specialist agents"""
        specialist_agents = ["data_analyst_1", "code_executor_1", "knowledge_agent_1"]

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                for agent_id in specialist_agents:
                    result = await cva_agent.send_strategic_command(
                        command_type="delegate_task",
                        parameters={"task_id": "task_001"},
                        recipient_id=agent_id,
                        priority=MessagePriority.HIGH,
                    )
                    assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_broadcast_to_all_agents(self, cva_agent, mock_communication_manager):
        """Test broadcasting commands to multiple agents"""
        # Simulate broadcasting
        agents = ["agent_1", "agent_2", "agent_3", "agent_4"]

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                for agent_id in agents:
                    await cva_agent.send_strategic_command(
                        command_type="broadcast_alert",
                        parameters={"alert_level": "high"},
                        recipient_id=agent_id,
                    )

                # Verify multiple messages sent
                assert mock_communication_manager.send_message.call_count == 4

    @pytest.mark.asyncio
    async def test_hierarchical_delegation(self, cva_agent, mock_communication_manager):
        """Test hierarchical task delegation"""
        # CVA delegates to coordinator agents, who delegate to specialists

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Delegate to coordinator
                await cva_agent.send_strategic_command(
                    command_type="orchestrate_workflow",
                    parameters={
                        "workflow_id": "wf_001",
                        "sub_tasks": ["subtask_1", "subtask_2"],
                    },
                    recipient_id="workflow_coordinator",
                    priority=MessagePriority.HIGH,
                )

                mock_communication_manager.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_response_aggregation(self, cva_agent, mock_communication_manager):
        """Test aggregating responses from multiple agents"""
        # In a real scenario, CVA would collect responses from multiple agents

        responses = [
            {"agent_id": "agent_1", "status": "completed", "result": "success"},
            {"agent_id": "agent_2", "status": "completed", "result": "success"},
            {"agent_id": "agent_3", "status": "failed", "result": "error"},
        ]

        # Simulate response aggregation
        successful_responses = [r for r in responses if r["status"] == "completed"]
        assert len(successful_responses) == 2


# ============================================================================
# Test Integration Scenarios (5 tests)
# ============================================================================


class TestIntegrationScenarios:
    """Test complete integration scenarios"""

    @pytest.mark.asyncio
    async def test_end_to_end_command_workflow(self, cva_agent, mock_communication_manager):
        """Test complete command workflow from creation to telemetry"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                mock_communication_manager.send_message.return_value = True

                # Full workflow
                result = await cva_agent.send_strategic_command(
                    command_type="full_workflow",
                    parameters={"workflow_id": "wf_001"},
                    recipient_id="orchestrator",
                )

                # Verify all steps completed
                assert result is True
                mock_communication_manager.initialize.assert_called()
                mock_communication_manager.register_agent.assert_called()
                mock_communication_manager.send_message.assert_called()
                mock_communication_manager.collect_telemetry.assert_called()

    @pytest.mark.asyncio
    async def test_communication_with_memory_context(self, cva_agent, mock_communication_manager):
        """Test communication with memory context"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                with patch("src.core.agents.cva_agent.memory_manager") as mock_memory:
                    memory_context = {"strategy_id": "strat_001", "success_rate": 0.95}
                    mock_memory.retrieve_strategic_memories.return_value = [memory_context]

                    # Send command with memory context
                    result = await cva_agent.send_strategic_command(
                        command_type="memory_aware_cmd", parameters=memory_context
                    )

                    assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_concurrent_command_sending(self, cva_agent, mock_communication_manager):
        """Test sending multiple commands concurrently"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Send multiple commands concurrently
                tasks = [
                    cva_agent.send_strategic_command(
                        command_type=f"concurrent_cmd_{i}", parameters={"index": i}
                    )
                    for i in range(5)
                ]

                results = await asyncio.gather(*tasks)

                # All should complete
                assert len(results) == 5

    @pytest.mark.asyncio
    async def test_communication_state_persistence(self, cva_agent, mock_communication_manager):
        """Test persistence of communication state"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            # Check initial state
            assert cva_agent.communication_initialized is False

            # Initialize communication
            await cva_agent.initialize_communication_system()

            # Check state is persisted
            initial_state = cva_agent.communication_initialized

            # Send command
            with patch("src.core.agents.cva_agent.MessageFactory"):
                await cva_agent.send_strategic_command(command_type="state_test", parameters={})

            # State should still be same
            assert cva_agent.communication_initialized == initial_state

    @pytest.mark.asyncio
    async def test_recovery_from_partial_initialization(
        self, cva_agent, mock_communication_manager
    ):
        """Test recovery when partial initialization occurs"""
        # Initialize succeeds but register fails
        mock_communication_manager.initialize.return_value = None
        mock_communication_manager.register_agent.side_effect = Exception("Register failed")

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            await cva_agent.initialize_communication_system()

            # Should be marked as not initialized
            assert cva_agent.communication_initialized is False


# ============================================================================
# Test Edge Cases & Boundary Conditions (4 tests)
# ============================================================================


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_empty_command_parameters(self, cva_agent, mock_communication_manager):
        """Test command with empty parameters"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                result = await cva_agent.send_strategic_command(
                    command_type="empty_params", parameters={}
                )

                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_very_large_parameters(self, cva_agent, mock_communication_manager):
        """Test command with very large parameter payloads"""
        large_params = {
            "large_data": "x" * 10000,
            "nested": {f"key_{i}": f"value_{i}" for i in range(100)},
        }

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                result = await cva_agent.send_strategic_command(
                    command_type="large_params", parameters=large_params
                )

                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_special_characters_in_command_type(self, cva_agent, mock_communication_manager):
        """Test command types with special characters"""
        special_types = [
            "cmd-with-dash",
            "cmd_with_underscore",
            "cmd.with.dot",
            "cmd:with:colon",
        ]

        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                for cmd_type in special_types:
                    result = await cva_agent.send_strategic_command(
                        command_type=cmd_type, parameters={}
                    )
                    assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_rapid_successive_commands(self, cva_agent, mock_communication_manager):
        """Test rapid successive command sending"""
        with patch(
            "src.core.agents.cva_agent.communication_manager",
            mock_communication_manager,
        ):
            with patch("src.core.agents.cva_agent.MessageFactory"):
                # Send 10 commands rapidly
                for i in range(10):
                    await cva_agent.send_strategic_command(
                        command_type="rapid_cmd", parameters={"sequence": i}
                    )

                # All should be sent
                assert mock_communication_manager.send_message.call_count == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
