#!/usr/bin/env python3
"""
Agent Factory - M-MDP Specialized Agent Creation
Dynamic agent creation and configuration system
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# Import types from central source
from src.core.types import AgentType

__all__ = ["AgentType", "AgentStatus", "AgentConfiguration", "AgentMetrics"]

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent operational status"""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    BUSY = "busy"
    IDLE = "idle"
    MAINTENANCE = "maintenance"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class AgentConfiguration:
    """Configuration for agent creation"""

    agent_type: AgentType
    name: str
    capabilities: list[str]
    max_concurrent_tasks: int
    memory_limit_mb: int
    cpu_priority: str
    specialized_parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    auto_scale: bool = False
    health_check_interval: int = 60


@dataclass
class AgentMetrics:
    """Agent performance metrics"""

    tasks_completed: int = 0
    tasks_failed: int = 0
    average_execution_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    uptime_seconds: int = 0
    last_health_check: datetime | None = None


class BaseAgent:
    """Base class for all specialized agents"""

    def __init__(self, agent_id: str, config: AgentConfiguration) -> None:
        self.agent_id = agent_id
        self.config = config
        self.status = AgentStatus.INITIALIZING
        self.metrics = AgentMetrics()
        self.created_at = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)
        self.current_tasks: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.capabilities = set(config.capabilities)

    async def initialize(self) -> bool:
        """Initialize the agent"""
        try:
            logger.info(f"Initializing {self.config.agent_type.value} agent: {self.agent_id}")

            # Perform agent-specific initialization
            await self._agent_specific_init()

            self.status = AgentStatus.IDLE
            self.metrics.last_health_check = datetime.now(timezone.utc)

            logger.info(f"Agent {self.agent_id} initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize agent {self.agent_id}: {e}")
            self.status = AgentStatus.ERROR
            return False

    async def _agent_specific_init(self) -> None:
        """Override in subclasses for specific initialization."""
        self.metrics.last_health_check = datetime.now(timezone.utc)

    async def execute_task(self, task_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute a task"""
        task_id = task_data.get("id", str(uuid.uuid4()))

        try:
            if len(self.current_tasks) >= self.config.max_concurrent_tasks:
                return {
                    "success": False,
                    "error": "Agent at maximum capacity",
                    "task_id": task_id,
                }

            self.status = AgentStatus.BUSY
            self.current_tasks[task_id] = {
                "start_time": datetime.now(timezone.utc),
                "task_data": task_data,
            }

            start_time = time.time()

            # Execute the specific task
            result = await self._execute_specific_task(task_data)

            execution_time = time.time() - start_time

            # Update metrics
            self.metrics.tasks_completed += 1
            self._update_average_execution_time(execution_time)

            # Clean up
            del self.current_tasks[task_id]
            self.status = AgentStatus.IDLE if not self.current_tasks else AgentStatus.BUSY
            self.last_activity = datetime.now(timezone.utc)

            return {
                "success": True,
                "result": result,
                "execution_time": execution_time,
                "task_id": task_id,
                "agent_id": self.agent_id,
            }

        except Exception as e:
            logger.error(f"Task execution failed for agent {self.agent_id}: {e}")
            self.metrics.tasks_failed += 1

            if task_id in self.current_tasks:
                del self.current_tasks[task_id]

            self.status = AgentStatus.IDLE if not self.current_tasks else AgentStatus.BUSY

            return {
                "success": False,
                "error": str(e),
                "task_id": task_id,
                "agent_id": self.agent_id,
            }

    async def _execute_specific_task(self, task_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Override in subclasses for specific task execution"""
        raise NotImplementedError("Subclasses must implement _execute_specific_task")

    def _update_average_execution_time(self, execution_time: float) -> None:
        """Update average execution time"""
        total_tasks = self.metrics.tasks_completed
        if total_tasks == 1:
            self.metrics.average_execution_time = execution_time
        else:
            current_avg = self.metrics.average_execution_time
            self.metrics.average_execution_time = (
                (current_avg * (total_tasks - 1)) + execution_time
            ) / total_tasks

    async def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Perform health check"""
        self.metrics.last_health_check = datetime.now(timezone.utc)
        self.metrics.uptime_seconds = int((datetime.now(timezone.utc) - self.created_at).total_seconds())

        # Calculate success rate
        total_tasks = self.metrics.tasks_completed + self.metrics.tasks_failed
        success_rate = self.metrics.tasks_completed / total_tasks * 100 if total_tasks > 0 else 100

        return {
            "agent_id": self.agent_id,
            "agent_type": self.config.agent_type.value,
            "status": self.status.value,
            "health": (
                "healthy"
                if self.status in [AgentStatus.ACTIVE, AgentStatus.IDLE, AgentStatus.BUSY]
                else "unhealthy"
            ),
            "metrics": {
                "tasks_completed": self.metrics.tasks_completed,
                "tasks_failed": self.metrics.tasks_failed,
                "success_rate": success_rate,
                "average_execution_time": self.metrics.average_execution_time,
                "uptime_seconds": self.metrics.uptime_seconds,
                "current_tasks": len(self.current_tasks),
                "max_concurrent_tasks": self.config.max_concurrent_tasks,
            },
            "capabilities": list(self.capabilities),
            "last_activity": self.last_activity.isoformat(),
        }

    async def shutdown(self) -> None:
        """Shutdown the agent"""
        logger.info(f"Shutting down agent {self.agent_id}")
        self.status = AgentStatus.SHUTDOWN

        # Wait for current tasks to complete or timeout
        timeout_time = time.time() + 30  # 30 second timeout
        while self.current_tasks and time.time() < timeout_time:
            await asyncio.sleep(0.1)

        if self.current_tasks:
            logger.warning(
                f"Agent {self.agent_id} shutdown with {len(self.current_tasks)} tasks still running"
            )


class AgentFactory:
    """Factory for creating and managing specialized agents"""

    def __init__(self) -> None:
        self.agent_registry: dict[AgentType, type[BaseAgent]] = {}
        self.active_agents: dict[str, BaseAgent] = {}
        self.agent_configurations: dict[AgentType, AgentConfiguration] = {}
        self.creation_count = 0

    def register_agent_type(self, agent_type: AgentType, agent_class: type[BaseAgent]) -> None:
        """Register an agent type with its implementation class"""
        self.agent_registry[agent_type] = agent_class
        logger.info(f"Registered agent type: {agent_type.value}")

    def register_default_configuration(
        self, agent_type: AgentType, config: AgentConfiguration
    ) -> None:
        """Register default configuration for an agent type"""
        self.agent_configurations[agent_type] = config
        logger.info(f"Registered default configuration for: {agent_type.value}")

    async def create_agent(
        self,
        agent_type: AgentType,
        name: str | None = None,
        custom_config: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """Create a new agent instance"""
        try:
            if agent_type not in self.agent_registry:
                logger.error(f"Unknown agent type: {agent_type.value}")
                return None

            # Generate agent ID
            self.creation_count += 1
            agent_id = f"{agent_type.value}_{self.creation_count}_{int(time.time())}"

            # Get configuration
            base_config = self.agent_configurations.get(agent_type)
            if not base_config:
                logger.error(f"No configuration found for agent type: {agent_type.value}")
                return None

            # Apply custom configuration
            config = base_config
            if custom_config:
                # Create new config with custom parameters
                config = AgentConfiguration(
                    agent_type=agent_type,
                    name=custom_config.get(
                        "name", name or f"{agent_type.value}_{self.creation_count}"
                    ),
                    capabilities=custom_config.get("capabilities", base_config.capabilities),
                    max_concurrent_tasks=custom_config.get(
                        "max_concurrent_tasks", base_config.max_concurrent_tasks
                    ),
                    memory_limit_mb=custom_config.get(
                        "memory_limit_mb", base_config.memory_limit_mb
                    ),
                    cpu_priority=custom_config.get("cpu_priority", base_config.cpu_priority),
                    specialized_parameters=custom_config.get(
                        "specialized_parameters", base_config.specialized_parameters
                    ),
                    auto_scale=custom_config.get("auto_scale", base_config.auto_scale),
                    health_check_interval=custom_config.get(
                        "health_check_interval", base_config.health_check_interval
                    ),
                )

            # Create agent instance
            agent_class = self.agent_registry[agent_type]
            agent = agent_class(agent_id, config)

            # Initialize agent
            if await agent.initialize():
                self.active_agents[agent_id] = agent
                logger.info(f"Created agent {agent_id} of type {agent_type.value}")
                return agent_id
            else:
                logger.error(f"Failed to initialize agent {agent_id}")
                return None

        except Exception as e:
            logger.error(f"Agent creation failed: {e}")
            return None

    async def get_agent(self, agent_id: str) -> BaseAgent | None:
        """Get agent by ID"""
        return self.active_agents.get(agent_id)

    async def list_agents(self, agent_type: AgentType | None = None) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """List all agents or agents of specific type"""
        agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, agent in self.active_agents.items():
            if agent_type is None or agent.config.agent_type == agent_type:
                health_info = await agent.health_check()
                agents.append(health_info)

        return agents

    async def find_capable_agents(self, required_capabilities: list[str]) -> list[str]:
        """Find agents with required capabilities"""
        capable_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, agent in self.active_agents.items():
            if agent.status in [AgentStatus.IDLE, AgentStatus.BUSY]:
                # Check if agent has all required capabilities
                if all(cap in agent.capabilities for cap in required_capabilities):
                    # Check if agent has capacity
                    if len(agent.current_tasks) < agent.config.max_concurrent_tasks:
                        capable_agents.append(agent_id)

        return capable_agents

    async def shutdown_agent(self, agent_id: str) -> bool:
        """Shutdown specific agent"""
        try:
            if agent_id not in self.active_agents:
                logger.warning(f"Agent {agent_id} not found for shutdown")
                return False

            agent = self.active_agents[agent_id]
            await agent.shutdown()
            del self.active_agents[agent_id]

            logger.info(f"Agent {agent_id} shut down successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to shutdown agent {agent_id}: {e}")
            return False

    async def shutdown_all_agents(self) -> None:
        """Shutdown all active agents"""
        logger.info("Shutting down all agents")

        shutdown_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id in list(self.active_agents.keys()):
            task = asyncio.create_task(self.shutdown_agent(agent_id))
            shutdown_tasks.append(task)

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        logger.info("All agents shut down")

    def get_factory_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get factory status and statistics"""
        agent_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent in self.active_agents.values():
            agent_type = agent.config.agent_type.value
            if agent_type not in agent_counts:
                agent_counts[agent_type] = {
                    "total": 0,
                    "active": 0,
                    "busy": 0,
                    "idle": 0,
                }

            agent_counts[agent_type]["total"] += 1
            if agent.status == AgentStatus.ACTIVE:
                agent_counts[agent_type]["active"] += 1
            elif agent.status == AgentStatus.BUSY:
                agent_counts[agent_type]["busy"] += 1
            elif agent.status == AgentStatus.IDLE:
                agent_counts[agent_type]["idle"] += 1

        return {
            "total_agents": len(self.active_agents),
            "registered_types": len(self.agent_registry),
            "creation_count": self.creation_count,
            "agent_counts_by_type": agent_counts,
            "available_types": [agent_type.value for agent_type in self.agent_registry.keys()],
        }

    # Async wrapper methods for endpoint compatibility
    async def get_system_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get system status (async wrapper for get_factory_status)"""
        status = self.get_factory_status()
        return {
            "status": "operational" if status["total_agents"] > 0 else "idle",
            "active_agents": sum(
                counts["active"] for counts in status["agent_counts_by_type"].values()
            ),
            "templates_count": len(status["available_types"]),
            **status,
        }

    async def start(self) -> None:
        """Start the agent factory (stub for compatibility)"""
        logger.info("AgentFactory started")

    async def get_agent_templates(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get available agent templates"""
        templates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_type in self.agent_registry.keys():
            config = self.agent_configurations.get(agent_type)
            templates.append(
                {
                    "archetype": agent_type.value,
                    "name": f"{agent_type.value.title()}Agent",
                    "description": f"Template for {agent_type.value} agents",
                    "core_capabilities": config.capabilities if config else [],
                    "required_tools": (
                        config.specialized_parameters.get("tools", []) if config else []
                    ),
                }
            )
        return templates

    async def register_template(self, template: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """Register an agent template (stub for compatibility)"""
        template_id = f"template_{uuid.uuid4().hex[:8]}"
        logger.info(f"Registered template: {template_id}")
        return template_id

    async def get_factory_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get factory performance metrics"""
        status = self.get_factory_status()
        total = status["creation_count"]
        active = sum(counts["active"] for counts in status["agent_counts_by_type"].values())
        return {
            "total_agents_created": total,
            "active_agents": active,
            "creation_success_rate": 1.0 if total > 0 else 0.0,
            "avg_creation_time": 0.5,  # Stub value
            "templates_count": len(status["available_types"]),
            "archetype_distribution": {
                atype: counts["total"] for atype, counts in status["agent_counts_by_type"].items()
            },
            "performance_summary": {
                "agents_active": active,
                "total_created": total,
            },
        }

    async def request_agent_generation(self, request: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """Request agent generation (stub for compatibility)"""
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        logger.info(f"Agent generation requested: {request_id}")
        return request_id


# Global agent factory instance
_agent_factory: AgentFactory | None = None


def create_agent_factory() -> AgentFactory:
    """Create or get global agent factory instance with registered agents"""
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory()

        # Import and register all specialist agents
        from .specialist_agents import (
            CodeExecutionAgent,
            DataAnalysisAgent,
            KnowledgeAgent,
            PerformanceAgent,
            ReportingAgent,
            SystemMonitorAgent,
        )

        # Register agent types with their implementations
        _agent_factory.register_agent_type(AgentType.DATA_ANALYSIS, DataAnalysisAgent)
        _agent_factory.register_agent_type(AgentType.SYSTEM_MONITOR, SystemMonitorAgent)
        _agent_factory.register_agent_type(AgentType.CODE_EXECUTION, CodeExecutionAgent)
        _agent_factory.register_agent_type(AgentType.KNOWLEDGE_RETRIEVAL, KnowledgeAgent)
        _agent_factory.register_agent_type(AgentType.REPORTING, ReportingAgent)
        _agent_factory.register_agent_type(AgentType.PERFORMANCE_ANALYSIS, PerformanceAgent)

        # Register default configurations
        _agent_factory.register_default_configuration(
            AgentType.DATA_ANALYSIS,
            AgentConfiguration(
                agent_type=AgentType.DATA_ANALYSIS,
                name="DataAnalysisAgent",
                capabilities=[
                    "statistical_analysis",
                    "pattern_recognition",
                    "correlation_analysis",
                    "trend_analysis",
                    "anomaly_detection",
                ],
                max_concurrent_tasks=5,
                memory_limit_mb=512,
                cpu_priority="normal",
                specialized_parameters={"analysis_timeout": 300},
            ),
        )

        _agent_factory.register_default_configuration(
            AgentType.SYSTEM_MONITOR,
            AgentConfiguration(
                agent_type=AgentType.SYSTEM_MONITOR,
                name="SystemMonitorAgent",
                capabilities=[
                    "health_check",
                    "performance_monitoring",
                    "resource_analysis",
                    "alert_generation",
                ],
                max_concurrent_tasks=3,
                memory_limit_mb=256,
                cpu_priority="high",
                specialized_parameters={"monitoring_interval": 60},
            ),
        )

        _agent_factory.register_default_configuration(
            AgentType.CODE_EXECUTION,
            AgentConfiguration(
                agent_type=AgentType.CODE_EXECUTION,
                name="CodeExecutionAgent",
                capabilities=[
                    "python_execution",
                    "javascript_execution",
                    "shell_execution",
                    "code_validation",
                ],
                max_concurrent_tasks=2,
                memory_limit_mb=1024,
                cpu_priority="normal",
                specialized_parameters={
                    "execution_timeout": 30,
                    "security_level": "high",
                },
            ),
        )

        _agent_factory.register_default_configuration(
            AgentType.KNOWLEDGE_RETRIEVAL,
            AgentConfiguration(
                agent_type=AgentType.KNOWLEDGE_RETRIEVAL,
                name="KnowledgeAgent",
                capabilities=[
                    "semantic_search",
                    "document_analysis",
                    "knowledge_extraction",
                    "rag_processing",
                ],
                max_concurrent_tasks=4,
                memory_limit_mb=512,
                cpu_priority="normal",
                specialized_parameters={"search_timeout": 120},
            ),
        )

        _agent_factory.register_default_configuration(
            AgentType.REPORTING,
            AgentConfiguration(
                agent_type=AgentType.REPORTING,
                name="ReportingAgent",
                capabilities=[
                    "report_generation",
                    "data_visualization",
                    "analytics",
                    "export",
                ],
                max_concurrent_tasks=3,
                memory_limit_mb=256,
                cpu_priority="low",
                specialized_parameters={"report_timeout": 180},
            ),
        )

        _agent_factory.register_default_configuration(
            AgentType.PERFORMANCE_ANALYSIS,
            AgentConfiguration(
                agent_type=AgentType.PERFORMANCE_ANALYSIS,
                name="PerformanceAgent",
                capabilities=[
                    "benchmarking",
                    "optimization_analysis",
                    "bottleneck_detection",
                    "performance_tuning",
                ],
                max_concurrent_tasks=2,
                memory_limit_mb=512,
                cpu_priority="normal",
                specialized_parameters={"benchmark_timeout": 600},
            ),
        )

        logger.info("Agent factory initialized with all specialist agents registered")

    return _agent_factory


def get_agent_factory() -> AgentFactory | None:
    """Get global agent factory instance"""
    return _agent_factory
