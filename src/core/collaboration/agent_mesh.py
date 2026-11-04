"""
Agent Registry - Production Implementation
Agent registration, status tracking en discovery zoals gespecificeerd in FASE 2 STAP 2.2
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .message_protocol import AgentHeartbeatMessage, AgentRegistrationMessage

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent status states"""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class RegisteredAgent(BaseModel):
    """Registered agent information"""

    model_config = ConfigDict(use_enum_values=True, arbitrary_types_allowed=True)

    # Basic identification
    agent_id: str = Field(description="Unique agent identifier")
    agent_name: str = Field(description="Human-readable agent name")
    agent_type: str = Field(description="Type/category of the agent")
    agent_version: str = Field(default="1.0.0", description="Agent version")

    # Connection details
    address: str = Field(description="Agent network address")
    port: int = Field(description="Agent listening port")
    endpoints: dict[str, str] = Field(default_factory=dict, description="Available endpoints")

    # Capabilities
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    max_concurrent_tasks: int = Field(default=1, description="Maximum concurrent tasks")
    supported_task_types: list[str] = Field(
        default_factory=list, description="Supported task types"
    )

    # Status tracking
    status: AgentStatus = Field(default=AgentStatus.ONLINE, description="Current agent status")
    current_load: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Current load percentage"
    )
    active_tasks: int = Field(default=0, description="Number of active tasks")

    # Timestamps
    registered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Registration timestamp"
    )
    last_heartbeat: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Last heartbeat timestamp"
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Last activity timestamp"
    )

    # Health metrics
    uptime: float = Field(default=0.0, description="Agent uptime in seconds")
    cpu_usage: float = Field(default=0.0, description="CPU usage percentage")
    memory_usage: float = Field(default=0.0, description="Memory usage percentage")

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional agent metadata")  # TODO(TYPE): replace Any with concrete type

    def is_available(self) -> bool:
        """Check if agent is available for new tasks"""
        return (
            self.status == AgentStatus.ONLINE
            and self.current_load < 80.0
            and self.active_tasks < self.max_concurrent_tasks
        )

    def is_healthy(self, heartbeat_timeout: int = 120) -> bool:
        """Check if agent is healthy based on heartbeat"""
        time_since_heartbeat = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return time_since_heartbeat < heartbeat_timeout

    def can_handle_task_type(self, task_type: str) -> bool:
        """Check if agent can handle specific task type"""
        return task_type in self.supported_task_types

    def has_capability(self, capability: str) -> bool:
        """Check if agent has specific capability"""
        return capability in self.capabilities


class AgentRegistry:
    """
    Agent Registry - zoals gespecificeerd in FASE 2 STAP 2.2
    Voor agent registratie, status tracking en discovery
    """

    def __init__(self) -> None:
        self.agents: dict[str, RegisteredAgent] = {}
        self.agent_groups: dict[str, set[str]] = {}
        self.discovery_filters: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._heartbeat_timeout = 120  # seconds
        self._cleanup_interval = 300  # seconds
        self._running = False
        self._cleanup_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        # Message queue for agent communication
        self._message_queues: dict[str, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type

        logger.info("AgentRegistry initialized")

    async def start(self) -> None:
        """Start the agent registry service"""
        if self._running:
            logger.warning("AgentRegistry already running")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("AgentRegistry service started")

    async def stop(self) -> None:
        """Stop the agent registry service"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("AgentRegistry service stopped")

    async def register_agent(self, registration_message: AgentRegistrationMessage) -> bool:
        """
        Register agent zoals gespecificeerd in plan
        """
        try:
            agent_id = registration_message.agent_id

            # Create RegisteredAgent from registration message
            registered_agent = RegisteredAgent(
                agent_id=agent_id,
                agent_name=registration_message.agent_name,
                agent_type=registration_message.agent_type,
                agent_version=registration_message.agent_version,
                address=registration_message.address,
                port=registration_message.port,
                endpoints=registration_message.endpoints,
                capabilities=registration_message.capabilities,
                max_concurrent_tasks=registration_message.max_concurrent_tasks,
                supported_task_types=registration_message.supported_task_types,
                status=AgentStatus(registration_message.status),
            )

            # Store in registry
            was_update = agent_id in self.agents
            self.agents[agent_id] = registered_agent

            # Add to type-based groups
            agent_type = registration_message.agent_type
            if agent_type not in self.agent_groups:
                self.agent_groups[agent_type] = set()
            self.agent_groups[agent_type].add(agent_id)

            action = "updated" if was_update else "registered"
            logger.info(f"Agent {agent_id} {action} successfully")

            return True

        except Exception as e:
            logger.error(f"Failed to register agent {registration_message.agent_id}: {e}")
            return False

    async def update_agent_heartbeat(self, heartbeat_message: AgentHeartbeatMessage) -> bool:
        """
        Update agent status via heartbeat zoals gespecificeerd in plan
        """
        try:
            agent_id = heartbeat_message.agent_id

            if agent_id not in self.agents:
                logger.warning(f"Received heartbeat from unknown agent: {agent_id}")
                return False

            agent = self.agents[agent_id]

            # Update heartbeat information
            agent.last_heartbeat = datetime.now(timezone.utc)
            agent.last_seen = datetime.now(timezone.utc)
            agent.status = AgentStatus(heartbeat_message.status)
            agent.current_load = heartbeat_message.current_load
            agent.active_tasks = heartbeat_message.active_tasks
            agent.cpu_usage = heartbeat_message.cpu_usage
            agent.memory_usage = heartbeat_message.memory_usage
            agent.uptime = heartbeat_message.uptime

            logger.debug(f"Updated heartbeat for agent {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update heartbeat for agent {heartbeat_message.agent_id}: {e}")
            return False

    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister agent from registry
        """
        try:
            if agent_id not in self.agents:
                logger.warning(f"Cannot unregister unknown agent: {agent_id}")
                return False

            agent = self.agents[agent_id]

            # Remove from type groups
            agent_type = agent.agent_type
            if agent_type in self.agent_groups:
                self.agent_groups[agent_type].discard(agent_id)
                if not self.agent_groups[agent_type]:
                    del self.agent_groups[agent_type]

            # Remove from registry
            del self.agents[agent_id]

            logger.info(f"Agent {agent_id} unregistered successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister agent {agent_id}: {e}")
            return False

    def get_agent(self, agent_id: str) -> RegisteredAgent | None:
        """Get registered agent by ID"""
        return self.agents.get(agent_id)

    def get_all_agents(self) -> dict[str, RegisteredAgent]:
        """Get all registered agents"""
        return self.agents.copy()

    def get_online_agents(self) -> dict[str, RegisteredAgent]:
        """Get all online agents zoals gespecificeerd in plan"""
        return {
            agent_id: agent
            for agent_id, agent in self.agents.items()
            if agent.status == AgentStatus.ONLINE and agent.is_healthy(self._heartbeat_timeout)
        }

    def get_available_agents(self) -> dict[str, RegisteredAgent]:
        """Get all available agents (online and not overloaded)"""
        return {
            agent_id: agent
            for agent_id, agent in self.agents.items()
            if agent.is_available() and agent.is_healthy(self._heartbeat_timeout)
        }

    def discover_agents_by_type(self, agent_type: str) -> list[RegisteredAgent]:
        """
        Discover agents by type zoals gespecificeerd in plan
        """
        agent_ids = self.agent_groups.get(agent_type, set())
        return [
            self.agents[agent_id]
            for agent_id in agent_ids
            if agent_id in self.agents and self.agents[agent_id].is_healthy(self._heartbeat_timeout)
        ]

    def discover_agents_by_capability(self, capability: str) -> list[RegisteredAgent]:
        """
        Discover agents by capability zoals gespecificeerd in plan
        """
        return [
            agent
            for agent in self.agents.values()
            if agent.has_capability(capability) and agent.is_healthy(self._heartbeat_timeout)
        ]

    def discover_agents_by_task_type(self, task_type: str) -> list[RegisteredAgent]:
        """
        Discover agents by supported task type zoals gespecificeerd in plan
        """
        return [
            agent
            for agent in self.agents.values()
            if agent.can_handle_task_type(task_type) and agent.is_healthy(self._heartbeat_timeout)
        ]

    def find_best_agent_for_task(
        self, task_type: str, required_capabilities: list[str] | None = None
    ) -> RegisteredAgent | None:
        """
        Find best available agent for specific task
        """
        # Get agents that can handle the task type
        candidate_agents = self.discover_agents_by_task_type(task_type)

        # Filter by required capabilities if specified
        if required_capabilities:
            candidate_agents = [
                agent
                for agent in candidate_agents
                if all(agent.has_capability(cap) for cap in required_capabilities)
            ]

        # Filter only available agents
        available_agents = [agent for agent in candidate_agents if agent.is_available()]

        if not available_agents:
            return None

        # Sort by load (prefer less loaded agents)
        available_agents.sort(key=lambda a: a.current_load)

        return available_agents[0]

    def get_agent_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get registry statistics zoals gespecificeerd in plan
        """
        total_agents = len(self.agents)
        online_agents = len(self.get_online_agents())
        available_agents = len(self.get_available_agents())

        # Count by type
        type_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_type, agent_ids in self.agent_groups.items():
            healthy_count = len(
                [
                    agent_id
                    for agent_id in agent_ids
                    if agent_id in self.agents
                    and self.agents[agent_id].is_healthy(self._heartbeat_timeout)
                ]
            )
            type_counts[agent_type] = healthy_count

        # Calculate average load
        online_agent_list = list(self.get_online_agents().values())
        avg_load = (
            sum(agent.current_load for agent in online_agent_list) / len(online_agent_list)
            if online_agent_list
            else 0.0
        )

        return {
            "total_agents": total_agents,
            "online_agents": online_agents,
            "available_agents": available_agents,
            "agents_by_type": type_counts,
            "average_load": round(avg_load, 2),
            "registry_uptime": self._running,
            "heartbeat_timeout": self._heartbeat_timeout,
        }

    async def send_message(self, message: dict[str, Any] | Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """
        Send a message to an agent's message queue.

        Args:
            message: Message object or dict with recipient_id attribute

        Returns:
            True if message was queued successfully
        """
        try:
            recipient_id: str | None = None
            message_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

            # Handle both dict-like and object-like messages
            if isinstance(message, dict):
                recipient_id = message.get("recipient_id")
                message_data = message
            else:
                # Object-like message: extract recipient_id
                recipient_id = getattr(message, "recipient_id", None)

                # Convert message object to dict for storage
                timestamp_value = getattr(message, "timestamp", datetime.now(timezone.utc))
                metadata_dict: dict[str, Any] = getattr(message, "metadata", {})  # TODO(TYPE): replace Any with concrete type
                requires_response: bool = (
                    metadata_dict.get("requires_response", False)
                    if isinstance(metadata_dict, dict)
                    else False
                )

                message_data = {
                    "id": str(getattr(message, "message_id", "")),
                    "from_agent": str(getattr(message, "sender_id", "")),
                    "message_type": str(getattr(message, "message_type", "")),
                    "priority": str(getattr(message, "priority", "")),
                    "content": getattr(message, "payload", {}),
                    "timestamp": timestamp_value,
                    "requires_response": requires_response,
                }

            if recipient_id is None:
                # Broadcast to all agents
                for agent_id in self.agents:
                    if agent_id not in self._message_queues:
                        self._message_queues[agent_id] = []
                    self._message_queues[agent_id].append(message_data)
            else:
                # Send to specific agent
                if recipient_id not in self._message_queues:
                    self._message_queues[recipient_id] = []
                self._message_queues[recipient_id].append(message_data)

            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return False

    async def receive_messages(self, agent_id: str, limit: int = 10) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Retrieve messages for an agent.

        Args:
            agent_id: The agent's ID
            limit: Maximum number of messages to retrieve

        Returns: List[Any] of messages for the agent  # TODO(TYPE): replace Any with concrete type
        """
        if agent_id not in self._message_queues:
            return []

        messages = self._message_queues[agent_id][:limit]
        # Remove retrieved messages from queue
        self._message_queues[agent_id] = self._message_queues[agent_id][limit:]
        return messages

    async def create_collaboration_group(self, group_id: str, agent_ids: list[str]) -> bool:
        """
        Create a collaboration group with specified agents.

        Args:
            group_id: Unique identifier for the group
            agent_ids: List[Any] of agent IDs to include in the group  # TODO(TYPE): replace Any with concrete type

        Returns:
            True if group was created successfully
        """
        try:
            # Validate all agents exist
            for agent_id in agent_ids:
                if agent_id not in self.agents:
                    logger.warning(f"Cannot create group: agent {agent_id} not found")
                    return False

            # Create group as a special agent group
            self.agent_groups[group_id] = set(agent_ids)
            logger.info(f"Created collaboration group {group_id} with {len(agent_ids)} agents")
            return True
        except Exception as e:
            logger.error(f"Failed to create collaboration group: {e}")
            return False

    async def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Get detailed status of a specific agent.

        Args:
            agent_id: The agent's ID

        Returns:
            Agent status dict or None if not found
        """
        agent = self.agents.get(agent_id)
        if agent is None:
            return None

        return {
            "agent_id": agent.agent_id,
            "agent_name": agent.agent_name,
            "agent_type": agent.agent_type,
            "status": agent.status.value if hasattr(agent.status, "value") else str(agent.status),
            "current_load": agent.current_load,
            "active_tasks": agent.active_tasks,
            "capabilities": agent.capabilities,
            "last_heartbeat": (
                agent.last_heartbeat.isoformat()
                if hasattr(agent.last_heartbeat, "isoformat")
                else str(agent.last_heartbeat)
            ),
            "is_healthy": agent.is_healthy(self._heartbeat_timeout),
            "is_available": agent.is_available(),
        }

    async def get_network_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get comprehensive network metrics.

        Returns: Dict[str, Any]ionary with network-wide metrics  # TODO(TYPE): replace Any with concrete type
        """
        total_agents = len(self.agents)
        online_agents = len(self.get_online_agents())
        available_agents = len(self.get_available_agents())

        # Calculate average load
        online_agent_list = list(self.get_online_agents().values())
        avg_load = (
            sum(agent.current_load for agent in online_agent_list) / len(online_agent_list)
            if online_agent_list
            else 0.0
        )

        return {
            "total_agents": total_agents,
            "online_agents": online_agents,
            "offline_agents": total_agents - online_agents,
            "available_agents": available_agents,
            "average_load": round(avg_load, 2),
            "agent_groups": len(self.agent_groups),
            "agents_by_type": {
                agent_type: len(agent_ids) for agent_type, agent_ids in self.agent_groups.items()
            },
            "heartbeat_timeout": self._heartbeat_timeout,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def discover_capabilities(self, capability_query: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Discover agents with specific capabilities.

        Args:
            capability_query: The capability to search for

        Returns: List[Any] of matching agent information  # TODO(TYPE): replace Any with concrete type
        """
        matching_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, agent in self.agents.items():
            if capability_query.lower() in [c.lower() for c in agent.capabilities]:
                matching_agents.append(
                    {
                        "agent_id": agent.agent_id,
                        "agent_name": agent.agent_name,
                        "agent_type": agent.agent_type,
                        "capabilities": agent.capabilities,
                        "status": (
                            agent.status.value
                            if hasattr(agent.status, "value")
                            else str(agent.status)
                        ),
                        "current_load": agent.current_load,
                        "is_available": agent.is_available(),
                    }
                )
        return matching_agents

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of stale agents"""
        while self._running:
            try:
                await self._cleanup_stale_agents()
                await asyncio.sleep(self._cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def _cleanup_stale_agents(self) -> None:
        """Remove agents that haven't sent heartbeats"""
        current_time = datetime.now(timezone.utc)
        stale_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, agent in self.agents.items():
            time_since_heartbeat = (current_time - agent.last_heartbeat).total_seconds()
            if time_since_heartbeat > self._heartbeat_timeout * 2:  # Double timeout for removal
                stale_agents.append(agent_id)

        for agent_id in stale_agents:
            logger.info(f"Removing stale agent: {agent_id}")
            await self.unregister_agent(agent_id)

    def __len__(self) -> int:
        """Get number of registered agents"""
        return len(self.agents)

    def __contains__(self, agent_id: str) -> bool:
        """Check if agent is registered"""
        return agent_id in self.agents


# Global registry instance
_agent_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Get or create global agent registry instance"""
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry


def create_agent_registry() -> AgentRegistry:
    """Create new agent registry instance"""
    return AgentRegistry()


__all__ = [
    "AgentRegistry",
    "RegisteredAgent",
    "AgentStatus",
    "get_agent_registry",
    "create_agent_registry",
]
