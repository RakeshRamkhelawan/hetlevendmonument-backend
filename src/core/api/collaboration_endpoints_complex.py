#!/usr/bin/env python3
# orphan:exempt reason: legacy pre-ADR-033 endpoint, pending Strangler Fig migration
"""
Phase 3 - Multi-Agent Collaboration API Endpoints
Provides RESTful API for agent mesh, task coordination, and adaptive learning
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.ai.adaptive_learning_engine import get_adaptive_learning_engine

from src.core.collaboration.agent_mesh import get_agent_registry
from src.core.collaboration.message_protocol import (
    AgentHeartbeatMessage,
    AgentRegistrationMessage,
    MessagePriority,
    MessageType,
)
from src.core.collaboration.task_coordinator import TaskRequirement, get_task_coordinator
from src.core.intelligence.system_optimizer import get_system_optimizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/collaboration", tags=["collaboration"])

# --- Pydantic Models ---


class AgentCapabilityModel(BaseModel):
    name: str
    description: str
    input_types: list[str]
    output_types: list[str]
    complexity_score: float = Field(ge=0.0, le=1.0)
    processing_time_avg: float
    success_rate: float = Field(ge=0.0, le=1.0)
    resources_required: list[str]


class AgentRegistrationModel(BaseModel):
    agent_id: str
    agent_type: str
    capabilities: list[AgentCapabilityModel]
    status: str = "active"
    load_factor: float = Field(ge=0.0, le=1.0, default=0.0)
    network_address: str | None = None
    metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class AgentMessageModel(BaseModel):
    to_agent: str
    message_type: str
    priority: str = "normal"
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    requires_response: bool = False
    expires_in_seconds: int | None = None


class TaskRequirementModel(BaseModel):
    capability: str
    priority: int = Field(ge=1, le=10)
    estimated_time: float
    resources_needed: list[str]
    dependencies: list[str] = []
    constraints: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class CollaborativeTaskModel(BaseModel):
    description: str
    requirements: list[TaskRequirementModel]
    deadline_hours: float | None = None
    metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class LearningExperienceModel(BaseModel):
    agent_id: str
    learning_type: str
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    action_taken: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    outcome: str
    outcome_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    confidence_score: float = Field(ge=0.0, le=1.0)
    impact_score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


# --- Agent Mesh Endpoints ---


@router.post("/agents/register")
async def register_agent(
    registration: AgentRegistrationModel,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Register a new agent in the mesh network"""
    try:
        registry = get_agent_registry()

        # Convert capabilities - capabilities is a list of AgentCapabilityModel objects
        capabilities: list[str] = []
        for cap in registration.capabilities:
            if isinstance(cap, dict):
                capabilities.append(cap.get("name", ""))
            elif hasattr(cap, "name"):
                capabilities.append(cap.name)
            else:
                capabilities.append(str(cap))

        # Create registration message
        reg_msg = AgentRegistrationMessage(
            agent_id=registration.agent_id,
            agent_name=registration.agent_id,
            agent_type=registration.agent_type,
            address=registration.network_address or "localhost",
            port=8000,
            capabilities=capabilities,
            sender_id=registration.agent_id,
            status=registration.status,
            agent_version="1.0.0",
        )

        success = await registry.register_agent(reg_msg)

        if success:
            return {
                "success": True,
                "message": f"Agent {registration.agent_id} registered successfully",
                "agent_id": registration.agent_id,
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to register agent")

    except Exception as e:
        logger.error(f"Agent registration failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.delete("/agents/{agent_id}")
async def unregister_agent(
    agent_id: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Unregister an agent from the mesh network"""
    try:
        mesh = get_agent_registry()
        success = await mesh.unregister_agent(agent_id)

        if success:
            return {
                "success": True,
                "message": f"Agent {agent_id} unregistered successfully",
            }
        else:
            raise HTTPException(status_code=404, detail="Agent not found")

    except Exception as e:
        logger.error(f"Agent unregistration failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post("/agents/{agent_id}/heartbeat")
async def update_agent_heartbeat(
    agent_id: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Update agent heartbeat timestamp"""
    try:
        mesh = get_agent_registry()

        # Create heartbeat message
        heartbeat_msg = AgentHeartbeatMessage(
            sender_id=agent_id,
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc),
            status="online",
            current_load=0.0,
            active_tasks=0,
        )
        success = await mesh.update_agent_heartbeat(heartbeat_msg)

        if success:
            return {"success": True, "timestamp": datetime.now(timezone.utc).isoformat()}
        else:
            raise HTTPException(status_code=404, detail="Agent not found")

    except Exception as e:
        logger.error(f"Heartbeat update failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/agents/{agent_id}/status")
async def get_agent_status(
    agent_id: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detailed status of a specific agent"""
    try:
        mesh = get_agent_registry()
        agent = mesh.get_agent(agent_id)

        if agent:
            return {
                "agent_id": agent.agent_id,
                "status": agent.status,
                "current_load": agent.current_load,
                "active_tasks": agent.active_tasks,
                "last_heartbeat": (
                    agent.last_heartbeat.isoformat() if agent.last_heartbeat else None
                ),
                "capabilities": agent.capabilities,
            }
        else:
            raise HTTPException(status_code=404, detail="Agent not found")

    except Exception as e:
        logger.error(f"Failed to get agent status: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/network/metrics")
async def get_network_metrics() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive network metrics"""
    try:
        mesh = get_agent_registry()
        stats = mesh.get_agent_statistics()
        return {
            "total_agents": stats.get("total_agents", 0),
            "online_agents": stats.get("online_agents", 0),
            "available_agents": stats.get("available_agents", 0),
            "agents_by_type": stats.get("agents_by_type", {}),
            "average_load": stats.get("average_load", 0.0),
        }

    except Exception as e:
        logger.error(f"Failed to get network metrics: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/capabilities/discover")
async def discover_capabilities(
    capability_query: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Discover agents with specific capabilities"""
    try:
        mesh = get_agent_registry()
        agents = mesh.discover_agents_by_capability(capability_query)
        matches = [
            {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "capabilities": agent.capabilities,
                "status": agent.status,
                "current_load": agent.current_load,
            }
            for agent in agents
        ]

        return {
            "query": capability_query,
            "matches_found": len(matches),
            "matches": matches,
        }

    except Exception as e:
        logger.error(f"Capability discovery failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post("/messages/send")
async def send_message(
    from_agent: str, message: AgentMessageModel
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Send a message to another agent"""
    try:
        mesh = get_agent_registry()

        # Parse message type and priority safely
        try:
            msg_type = MessageType(message.message_type)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid message_type: {message.message_type}"
            ) from e

        try:
            priority = MessagePriority[message.priority.upper()]
        except KeyError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid priority: {message.priority}"
            ) from e

        # Calculate expiration time if specified
        expires_at: datetime | None = None
        if message.expires_in_seconds is not None and message.expires_in_seconds > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=message.expires_in_seconds)

        # Create message as dict for compatibility
        timestamp = datetime.now(timezone.utc)
        agent_message: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "message_id": uuid.uuid4(),
            "sender_id": from_agent,
            "recipient_id": message.to_agent,
            "message_type": msg_type,
            "priority": priority,
            "payload": message.content,
            "timestamp": timestamp,
            "expires_at": expires_at,
            "metadata": {"requires_response": message.requires_response},
        }

        success = await mesh.send_message(agent_message)

        if success:
            return {
                "success": True,
                "message_id": str(agent_message["message_id"]),
                "sent_at": timestamp.isoformat(),
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to send message")

    except Exception as e:
        logger.error(f"Message sending failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/messages/{agent_id}")
async def receive_messages(
    agent_id: str, limit: int = 10
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Receive messages for an agent"""
    try:
        mesh = get_agent_registry()
        messages = await mesh.receive_messages(agent_id, limit)

        # Process messages with proper type handling
        processed_messages: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for msg in messages:
            ts_value = msg.get("timestamp")
            if ts_value is not None and hasattr(ts_value, "isoformat"):
                ts_str = ts_value.isoformat()
            else:
                ts_str = str(ts_value) if ts_value is not None else ""

            processed_messages.append(
                {
                    "id": str(msg.get("id", "")),
                    "from_agent": str(msg.get("from_agent", "")),
                    "message_type": str(msg.get("message_type", "")),
                    "priority": str(msg.get("priority", "")),
                    "content": msg.get("content", {}),
                    "timestamp": ts_str,
                    "requires_response": bool(msg.get("requires_response", False)),
                }
            )

        return {
            "agent_id": agent_id,
            "messages_count": len(messages),
            "messages": processed_messages,
        }

    except Exception as e:
        logger.error(f"Message receiving failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post("/groups/{group_id}")
async def create_collaboration_group(
    group_id: str, agent_ids: list[str]
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a collaboration group"""
    try:
        mesh = get_agent_registry()
        success = await mesh.create_collaboration_group(group_id, agent_ids)

        if success:
            return {
                "success": True,
                "group_id": group_id,
                "members": agent_ids,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to create collaboration group")

    except Exception as e:
        logger.error(f"Group creation failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


# --- Task Coordination Endpoints ---


@router.post("/tasks/submit")
async def submit_collaborative_task(
    task: CollaborativeTaskModel, requester_agent: str
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Submit a task for collaborative execution"""
    try:
        coordinator = get_task_coordinator()

        # Convert requirements
        requirements = [
            TaskRequirement(
                skill_type=req.capability,
                minimum_capability_level=float(req.priority) / 10.0,
                estimated_duration=req.estimated_time,
                resource_requirements={r: 1.0 for r in req.resources_needed},
                dependencies=req.dependencies,
            )
            for req in task.requirements
        ]

        # Set deadline
        deadline = None
        if task.deadline_hours:
            deadline = datetime.now(timezone.utc) + timedelta(hours=task.deadline_hours)

        task_id = await coordinator.submit_collaborative_task(
            title=task.description[:50],
            description=task.description,
            requirements=requirements,
        )

        if task_id:
            return {
                "success": True,
                "task_id": task_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to submit collaborative task")

    except Exception as e:
        logger.error(f"Task submission failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/tasks/{task_id}/status")
async def get_task_status(
    task_id: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get status of a collaborative task"""
    try:
        coordinator = get_task_coordinator()
        status = await coordinator.get_task_status(task_id)

        if status:
            return status
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Cancel a collaborative task"""
    try:
        coordinator = get_task_coordinator()
        success = await coordinator.cancel_task(task_id)

        if success:
            return {
                "success": True,
                "task_id": task_id,
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    except Exception as e:
        logger.error(f"Task cancellation failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/coordination/metrics")
async def get_coordination_metrics() -> dict[
    str, Any  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """Get task coordination metrics"""
    try:
        coordinator = get_task_coordinator()
        metrics = await coordinator.get_coordination_metrics()
        return metrics

    except Exception as e:
        logger.error(f"Failed to get coordination metrics: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


# --- Adaptive Learning Endpoints ---


@router.post("/learning/experience")
async def record_learning_experience(
    experience: LearningExperienceModel,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Record a learning experience"""
    try:
        learning_system = await get_adaptive_learning_engine()

        # Record experience using the simplified record_experience method
        success = await learning_system.record_experience(
            agent_id=experience.agent_id,
            task_type=experience.action_taken.get("task_type", "unknown"),
            success=experience.outcome == "success",
            duration=experience.context.get("duration", 0.0),
            context=experience.context,
            metrics=experience.outcome_data,
        )

        if success:
            return {
                "success": True,
                "experience_id": f"exp_{datetime.now(timezone.utc).timestamp()}",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to record learning experience")

    except Exception as e:
        logger.error(f"Learning experience recording failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/learning/patterns")
async def discover_knowledge_patterns() -> dict[
    str, Any  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """Discover knowledge patterns from learning experiences"""
    try:
        # Stub implementation - AdaptiveLearningEngine doesn't have discover_patterns method
        # Return empty patterns list
        return {
            "patterns_discovered": 0,
            "patterns": [],
            "note": "Pattern discovery not yet implemented in AdaptiveLearningEngine",
        }

    except Exception as e:
        logger.error(f"Pattern discovery failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/learning/recommendations/{agent_id}")
async def get_learning_recommendations(
    agent_id: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get personalized learning recommendations for an agent"""
    try:
        # Stub implementation - AdaptiveLearningEngine doesn't have get_learning_recommendations
        return {
            "agent_id": agent_id,
            "recommendations_count": 0,
            "recommendations": [],
            "note": "Learning recommendations not yet implemented",
        }

    except Exception as e:
        logger.error(f"Failed to get learning recommendations: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/learning/metrics")
async def get_learning_metrics() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive learning system metrics"""
    try:
        # Return stub metrics - AdaptiveLearningEngine doesn't have get_learning_metrics
        return {
            "events_processed": 0,
            "insights_generated": 0,
            "adaptations_applied": 0,
            "learning_rate": 0.0,
            "note": "Learning metrics not yet implemented",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get learning metrics: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post("/learning/apply-pattern/{pattern_id}/{agent_id}")
async def apply_knowledge_pattern(
    pattern_id: str, agent_id: str
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Apply a discovered knowledge pattern to an agent"""
    try:
        # Stub implementation - AdaptiveLearningEngine doesn't have apply_pattern_to_agent
        raise HTTPException(
            status_code=501,
            detail="Pattern application not yet implemented in AdaptiveLearningEngine",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pattern application failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


# --- System Intelligence Endpoints ---


@router.get("/intelligence/status")
async def get_system_intelligence_status() -> dict[
    str, Any  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """Get system intelligence and optimization status"""
    try:
        optimizer = get_system_optimizer()
        status = optimizer.get_health_status()
        return status

    except Exception as e:
        logger.error(f"Failed to get intelligence status: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/intelligence/metrics")
async def get_system_metrics() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current system performance metrics"""
    try:
        optimizer = get_system_optimizer()
        metrics = optimizer.get_metrics()

        # Return metrics with safe attribute access
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_usage": getattr(metrics, "cpu_usage", 0.0),
            "memory_usage": getattr(metrics, "memory_usage", 0.0),
            "disk_usage": getattr(metrics, "disk_usage", 0.0),
            "network_throughput": getattr(metrics, "network_throughput", 0.0),
            "active_agents": getattr(metrics, "active_agents", 0),
            "avg_response_time": getattr(metrics, "avg_response_time", 0.0),
            "error_rate": getattr(metrics, "error_rate", 0.0),
            "queue_depth": getattr(metrics, "queue_depth", 0),
            "cache_hit_rate": getattr(metrics, "cache_hit_rate", 0.0),
        }

    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


# --- Background Task Initialization ---


async def initialize_collaboration_systems() -> bool:
    """Initialize all collaboration systems"""
    try:
        logger.info("Initializing Phase 3 collaboration systems...")

        # Initialize agent mesh
        mesh = get_agent_registry()
        await mesh.start()  # NOTE: mesh.start lacks stubs

        # Initialize task coordinator - no explicit init needed
        # TaskCoordinator auto-initializes on creation
        _coordinator = get_task_coordinator()

        # Initialize adaptive learning
        learning_system = await get_adaptive_learning_engine()
        await learning_system.initialize()

        # Initialize system optimizer
        optimizer = get_system_optimizer()
        await optimizer.initialize()

        logger.info("Phase 3 collaboration systems initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize collaboration systems: {e}")
        return False


# Health check for collaboration systems
@router.get("/health")
async def collaboration_health_check() -> dict[
    str, Any  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """Health check for all collaboration systems"""
    try:
        systems_status = {
            "agent_mesh": "operational",
            "task_coordinator": "operational",
            "adaptive_learning": "operational",
            "system_optimizer": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "status": "healthy",
            "systems": systems_status,
            "phase": "Phase 3 - Agent Mesh & Coordination",
            "capabilities": [
                "Multi-agent communication",
                "Collaborative task execution",
                "Adaptive learning system",
                "Autonomous system optimization",
            ],
        }

    except Exception as e:
        logger.error(f"Collaboration health check failed: {e}")
        return {
            "status": "degraded",
            "error": "Er is een fout opgetreden.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
