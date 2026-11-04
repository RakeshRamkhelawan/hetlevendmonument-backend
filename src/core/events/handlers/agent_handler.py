"""
Agent Event Handler - Processes agent-related events within the monolith.

Handles agent lifecycle, status changes, and inter-agent communication.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager

logger = logging.getLogger(__name__)


class AgentEventHandler:
    """
    Handles agent-related events.

    Responsibilities:
    - Handle agent registration/activation
    - Process agent messages and routing
    - Monitor agent health and status
    - Coordinate multi-agent workflows
    """

    def __init__(self, pubsub_manager: RedisPubSubManager) -> None:
        self.pubsub = pubsub_manager
        self.logger = logger
        # Track active agents
        self._active_agents: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    async def register_handlers(self) -> None:
        """Register all agent event handlers."""
        await self.pubsub.subscribe(EventType.AGENT_REGISTERED.value, self.on_agent_registered)
        await self.pubsub.subscribe(EventType.AGENT_ACTIVATED.value, self.on_agent_activated)
        await self.pubsub.subscribe(EventType.AGENT_DEACTIVATED.value, self.on_agent_deactivated)
        await self.pubsub.subscribe(EventType.AGENT_MESSAGE.value, self.on_agent_message)
        await self.pubsub.subscribe(
            EventType.AGENT_STATUS_CHANGED.value, self.on_agent_status_changed
        )

        self.logger.info("AgentEventHandler registered")

    async def on_agent_registered(self, message: PubSubMessage) -> None:
        """Handle agent registration."""
        agent_id = message.data.get("agent_id")
        agent_type = message.data.get("agent_type")
        tenant_id = message.tenant_id

        if agent_id is None:
            self.logger.warning("Agent registration failed: missing agent_id")
            return

        agent_id_str = str(agent_id)

        self.logger.info(f"Agent registered: {agent_id_str} (type: {agent_type})")

        self._active_agents[agent_id_str] = {
            "agent_id": agent_id_str,
            "agent_type": agent_type,
            "tenant_id": tenant_id,
            "status": "registered",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        # Auto-activate agent
        await self.pubsub.publish(
            event_type=EventType.AGENT_ACTIVATED,
            data={
                "agent_id": agent_id_str,
                "agent_type": agent_type,
                "auto_activated": True,
            },
            tenant_id=tenant_id,
            source="agent_handler",
        )

    async def on_agent_activated(self, message: PubSubMessage) -> None:
        """Handle agent activation."""
        agent_id = message.data.get("agent_id")

        if agent_id is None:
            self.logger.warning("Agent activation failed: missing agent_id")
            return

        agent_id_str = str(agent_id)

        if agent_id_str in self._active_agents:
            self._active_agents[agent_id_str]["status"] = "active"
            self._active_agents[agent_id_str]["activated_at"] = datetime.now(timezone.utc).isoformat()

        self.logger.info(f"Agent activated: {agent_id_str}")

    async def on_agent_deactivated(self, message: PubSubMessage) -> None:
        """Handle agent deactivation."""
        agent_id = message.data.get("agent_id")
        reason = message.data.get("reason", "unknown")

        if agent_id is None:
            self.logger.warning("Agent deactivation failed: missing agent_id")
            return

        agent_id_str = str(agent_id)

        if agent_id_str in self._active_agents:
            self._active_agents[agent_id_str]["status"] = "inactive"
            self._active_agents[agent_id_str]["deactivated_at"] = datetime.now(timezone.utc).isoformat()
            self._active_agents[agent_id_str]["deactivation_reason"] = reason

        self.logger.info(f"Agent deactivated: {agent_id_str} (reason: {reason})")

    async def on_agent_message(self, message: PubSubMessage) -> None:
        """
        Handle agent messages and routing requests.

        This is the core handler for task routing between agents.
        """
        try:
            action = message.data.get("action")
            tenant_id = message.tenant_id

            if action == "route_task":
                await self._handle_task_routing(message)
            elif action == "delegate":
                await self._handle_delegation(message)
            elif action == "collaborate":
                await self._handle_collaboration(message)
            else:
                self.logger.warning(f"Unknown agent action: {action}")

        except Exception as e:
            self.logger.error(f"Failed to handle agent message: {e}")

    async def _handle_task_routing(self, message: PubSubMessage) -> None:
        """Route task to appropriate agent/department."""
        task_id = message.data.get("task_id")
        department = message.data.get("department")
        priority = message.data.get("priority", "medium")
        tenant_id = message.tenant_id

        if department is None:
            self.logger.warning(f"Task routing failed: missing department for task {task_id}")
            return

        if tenant_id is None:
            self.logger.warning(f"Task routing failed: missing tenant_id for task {task_id}")
            return

        department_str = str(department)
        self.logger.info(f"Routing task {task_id} to {department_str} (priority: {priority})")

        # Find available agent for department
        available_agents = self._find_agents_by_department(department_str, tenant_id)

        if available_agents:
            selected_agent = available_agents[0]  # Simple round-robin

            # Notify selected agent
            await self.pubsub.publish(
                event_type=EventType.AGENT_MESSAGE,
                data={
                    "action": "execute_task",
                    "task_id": task_id,
                    "assigned_to": selected_agent["agent_id"],
                    "priority": priority,
                },
                tenant_id=tenant_id,
                source="agent_handler",
            )

            self.logger.info(f"Task {task_id} assigned to agent {selected_agent['agent_id']}")
        else:
            # No available agent - queue for later
            self.logger.warning(f"No available agents for {department_str}, task queued")

            await self.pubsub.publish(
                event_type=EventType.SYSTEM_ALERT,
                data={
                    "level": "warning",
                    "message": f"No agents available in {department_str} for task {task_id}",
                    "task_id": task_id,
                    "department": department_str,
                },
                tenant_id=tenant_id,
                source="agent_handler",
            )

    async def _handle_delegation(self, message: PubSubMessage) -> None:
        """Handle task delegation between agents."""
        from_agent = message.data.get("from_agent")
        to_agent = message.data.get("to_agent")
        task_id = message.data.get("task_id")

        self.logger.info(f"Delegation: {from_agent} -> {to_agent} (task: {task_id})")

        # Forward message to target agent
        await self.pubsub.publish(
            event_type=EventType.AGENT_MESSAGE,
            data={
                "action": "execute_task",
                "task_id": task_id,
                "delegated_by": from_agent,
                "priority": "high",  # Delegated tasks are urgent
            },
            tenant_id=message.tenant_id,
            source="agent_handler",
        )

    async def _handle_collaboration(self, message: PubSubMessage) -> None:
        """Handle multi-agent collaboration request."""
        task_id = message.data.get("task_id")
        departments = message.data.get("departments", [])
        tenant_id = message.tenant_id

        self.logger.info(f"Collaboration request for task {task_id}: {departments}")

        # Create sub-tasks for each department
        for dept in departments:
            await self.pubsub.publish(
                event_type=EventType.AGENT_MESSAGE,
                data={
                    "action": "route_task",
                    "parent_task_id": task_id,
                    "department": dept,
                    "priority": "high",
                },
                tenant_id=tenant_id,
                source="agent_handler",
            )

    async def on_agent_status_changed(self, message: PubSubMessage) -> None:
        """Handle agent status changes (health monitoring)."""
        agent_id = message.data.get("agent_id")
        new_status = message.data.get("status")
        health_score = message.data.get("health_score", 1.0)

        if agent_id is None:
            self.logger.warning("Agent status change failed: missing agent_id")
            return

        agent_id_str = str(agent_id)

        if agent_id_str in self._active_agents:
            self._active_agents[agent_id_str]["status"] = new_status
            self._active_agents[agent_id_str]["health_score"] = health_score
            self._active_agents[agent_id_str]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()

        # Alert if health is critical
        if health_score < 0.3:
            self.logger.error(f"Agent {agent_id_str} health critical: {health_score}")
            await self.pubsub.publish(
                event_type=EventType.SYSTEM_ALERT,
                data={
                    "level": "error",
                    "message": f"Agent {agent_id_str} health critical: {health_score}",
                    "agent_id": agent_id_str,
                    "health_score": health_score,
                },
                tenant_id=message.tenant_id,
                source="agent_handler",
            )

    def _find_agents_by_department(self, department: str, tenant_id: int) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Find active agents for a department."""
        return [
            agent
            for agent in self._active_agents.values()
            if agent.get("status") == "active"
            and agent.get("tenant_id") == tenant_id
            and agent.get("department") == department
        ]

    def get_active_agents(self, tenant_id: int | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get list of active agents."""
        if tenant_id:
            return {k: v for k, v in self._active_agents.items() if v.get("tenant_id") == tenant_id}
        return self._active_agents.copy()
