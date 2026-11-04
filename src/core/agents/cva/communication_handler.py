import logging
from typing import Any, Optional

from src.core.communication.communication_manager import communication_manager
from src.core.communication.message_protocol import MessageFactory, MessagePriority
from src.core.shared.interfaces import AgentType

logger = logging.getLogger(__name__)

__all__ = [
    "CommunicationHandler",
    "communication_manager",
    "MessageFactory",
]


class CommunicationHandler:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.communication_initialized = False

    async def initialize(self) -> None:
        """Initialize M-MDP communication infrastructure"""
        if not self.communication_initialized:
            try:
                await communication_manager.initialize()

                # Register this CVA agent in the communication system
                await communication_manager.register_agent(
                    agent_id=self.agent_id,
                    agent_type=AgentType.CVA,
                    capabilities=["strategic_planning", "delegation", "ceo_mode"],
                )

                self.communication_initialized = True
                logger.info(f"CVA agent {self.agent_id} registered in communication system")
            except Exception as e:
                logger.error(f"Failed to initialize communication system: {e}")
                self.communication_initialized = False

    async def send_strategic_command(
        self,
        command_type: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        recipient_id: str = "ultimate_orchestrator",
        masterprompt: str | None = None,
        priority: MessagePriority = MessagePriority.HIGH,
    ) -> bool:
        """Send strategic command message to orchestrator"""
        try:
            # Ensure communication system is initialized
            if not self.communication_initialized:
                await self.initialize()

            # Create command message
            command_message = MessageFactory.create_command_message(
                sender_id=self.agent_id,
                sender_type=AgentType.CVA,
                recipient_id=recipient_id,
                command_type=command_type,
                parameters=parameters,
                masterprompt=masterprompt,
                priority=priority,
            )

            # Send message through communication manager
            success = await communication_manager.send_message(command_message)

            if success:
                logger.info(f"Strategic command sent: {command_type} to {recipient_id}")

                # Collect telemetry
                await communication_manager.collect_telemetry(
                    agent_id=self.agent_id,
                    metrics={"commands_sent": 1, "command_type": command_type},
                    performance_indicators={"command_success_rate": 1.0},
                    resource_usage={"cpu_usage": 0.1, "memory_usage": 50.0},
                )
            else:
                logger.warning(f"Failed to send strategic command: {command_type}")

            return success

        except Exception as e:
            logger.error(f"Error sending strategic command: {e}")
            return False
