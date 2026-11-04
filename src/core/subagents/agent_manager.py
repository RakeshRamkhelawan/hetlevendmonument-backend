#!/usr/bin/env python3
"""
Agent Manager - M-MDP Agent Lifecycle Management
Comprehensive agent management, monitoring, and orchestration
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.core.types import AgentType

from .agent_factory import AgentConfiguration, AgentFactory, BaseAgent
from .specialists.code_execution_agent import CodeExecutionAgent
from .specialists.data_analysis_agent import DataAnalysisAgent
from .specialists.knowledge_agent import KnowledgeAgent
from .specialists.performance_agent import PerformanceAgent
from .specialists.reporting_agent import ReportingAgent
from .specialists.system_monitor_agent import SystemMonitorAgent

logger = logging.getLogger(__name__)


@dataclass
class AgentAllocation:
    """Agent allocation information"""

    agent_id: str
    task_id: str
    allocated_at: datetime
    estimated_completion: datetime
    priority: int


class AgentManager:
    """Comprehensive agent lifecycle and resource management"""

    def __init__(self, agent_factory: AgentFactory) -> None:
        self.agent_factory = agent_factory
        self.agent_allocations: dict[str, AgentAllocation] = {}
        self.task_queue: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.completed_tasks: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.agent_health_checks: dict[str, datetime] = {}
        self.performance_metrics: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.running = False
        self.management_task: asyncio.Task[None] | None = None

        # Register agent types with factory
        self._register_agent_types()

    def _register_agent_types(self) -> None:
        """Register all specialist agent types"""
        registrations = [
            (AgentType.DATA_ANALYSIS, DataAnalysisAgent),
            (AgentType.SYSTEM_MONITOR, SystemMonitorAgent),
            (AgentType.CODE_EXECUTION, CodeExecutionAgent),
            (AgentType.KNOWLEDGE_RETRIEVAL, KnowledgeAgent),
            (AgentType.REPORTING, ReportingAgent),
            (AgentType.PERFORMANCE_ANALYSIS, PerformanceAgent),
        ]

        for agent_type, agent_class in registrations:
            self.agent_factory.register_agent_type(agent_type, agent_class)

        # Register default configurations
        self._register_default_configurations()

    def _register_default_configurations(self) -> None:
        """Register default configurations for each agent type"""
        default_configs = {
            AgentType.DATA_ANALYSIS: AgentConfiguration(
                agent_type=AgentType.DATA_ANALYSIS,
                name="DataAnalysisAgent",
                capabilities=[
                    "statistical_analysis",
                    "pattern_recognition",
                    "data_visualization",
                ],
                max_concurrent_tasks=3,
                memory_limit_mb=512,
                cpu_priority="normal",
                specialized_parameters={
                    "analysis_timeout": 300,
                    "max_data_points": 10000,
                },
                auto_scale=True,
                health_check_interval=120,
            ),
            AgentType.SYSTEM_MONITOR: AgentConfiguration(
                agent_type=AgentType.SYSTEM_MONITOR,
                name="SystemMonitorAgent",
                capabilities=["resource_monitoring", "health_checks", "alerting"],
                max_concurrent_tasks=5,
                memory_limit_mb=256,
                cpu_priority="high",
                specialized_parameters={
                    "monitoring_interval": 30,
                    "alert_thresholds": {"cpu": 80, "memory": 85},
                },
                auto_scale=False,
                health_check_interval=60,
            ),
            AgentType.CODE_EXECUTION: AgentConfiguration(
                agent_type=AgentType.CODE_EXECUTION,
                name="CodeExecutionAgent",
                capabilities=[
                    "python_execution",
                    "javascript_execution",
                    "shell_execution",
                ],
                max_concurrent_tasks=2,
                memory_limit_mb=1024,
                cpu_priority="normal",
                specialized_parameters={"execution_timeout": 30, "memory_limit": 100},
                auto_scale=True,
                health_check_interval=180,
            ),
            AgentType.KNOWLEDGE_RETRIEVAL: AgentConfiguration(
                agent_type=AgentType.KNOWLEDGE_RETRIEVAL,
                name="KnowledgeAgent",
                capabilities=["knowledge_search", "document_retrieval", "faq_lookup"],
                max_concurrent_tasks=4,
                memory_limit_mb=384,
                cpu_priority="normal",
                specialized_parameters={"search_timeout": 10, "max_results": 50},
                auto_scale=True,
                health_check_interval=300,
            ),
            AgentType.REPORTING: AgentConfiguration(
                agent_type=AgentType.REPORTING,
                name="ReportingAgent",
                capabilities=["report_generation", "data_export", "visualization"],
                max_concurrent_tasks=2,
                memory_limit_mb=768,
                cpu_priority="low",
                specialized_parameters={"report_timeout": 600, "max_report_size": 100},
                auto_scale=False,
                health_check_interval=240,
            ),
            AgentType.PERFORMANCE_ANALYSIS: AgentConfiguration(
                agent_type=AgentType.PERFORMANCE_ANALYSIS,
                name="PerformanceAgent",
                capabilities=["benchmarking", "bottleneck_analysis", "optimization"],
                max_concurrent_tasks=1,
                memory_limit_mb=512,
                cpu_priority="normal",
                specialized_parameters={
                    "analysis_depth": "standard",
                    "benchmark_duration": 60,
                },
                auto_scale=False,
                health_check_interval=180,
            ),
        }

        for agent_type, config in default_configs.items():
            self.agent_factory.register_default_configuration(agent_type, config)

    async def start_manager(self) -> None:
        """Start the agent manager"""
        if self.running:
            logger.warning("Agent manager already running")
            return

        self.running = True
        logger.info("Starting M-MDP Agent Manager")

        # Create initial agent pool
        await self._create_initial_agent_pool()

        # Start management tasks
        self.management_task = asyncio.create_task(self._management_loop())

        logger.info("Agent manager started successfully")

    async def stop_manager(self) -> None:
        """Stop the agent manager"""
        self.running = False
        if self.management_task:
            self.management_task.cancel()

        # Shutdown all agents
        await self.agent_factory.shutdown_all_agents()

        logger.info("Agent manager stopped")

    async def _create_initial_agent_pool(self) -> None:
        """Create initial pool of agents"""
        initial_agents = [
            (AgentType.SYSTEM_MONITOR, 1),
            (AgentType.DATA_ANALYSIS, 2),
            (AgentType.KNOWLEDGE_RETRIEVAL, 1),
            (AgentType.REPORTING, 1),
        ]

        for agent_type, count in initial_agents:
            for i in range(count):
                agent_id = await self.agent_factory.create_agent(agent_type)
                if agent_id:
                    logger.info(f"Created initial agent: {agent_id}")

    async def submit_task(self, task_data: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Submit a task for execution"""
        task_id = task_data.get("id") or f"task_{int(time.time())}_{len(self.task_queue)}"
        task_data["id"] = task_id
        task_data["submitted_at"] = datetime.now(timezone.utc)
        task_data["status"] = "queued"

        self.task_queue.append(task_data)
        logger.info(f"Task {task_id} submitted to queue")

        # Try to assign immediately
        await self._try_assign_tasks()

        return task_id

    async def _try_assign_tasks(self) -> None:
        """Try to assign queued tasks to available agents"""
        if not self.task_queue:
            return

        for task_data in self.task_queue[:]:  # Copy to avoid modification during iteration
            required_capabilities = task_data.get("required_capabilities", [])
            task_data.get("priority", 5)

            # Find suitable agents
            capable_agents = await self.agent_factory.find_capable_agents(required_capabilities)

            if capable_agents:
                # Select best agent based on load and performance
                best_agent_id = await self._select_best_agent(capable_agents, task_data)

                if best_agent_id:
                    # Assign task to agent
                    await self._assign_task_to_agent(task_data, best_agent_id)
                    self.task_queue.remove(task_data)

    async def _select_best_agent(
        self, candidate_agents: list[str], task_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """Select the best agent for a task based on various criteria"""
        best_agent_id = None
        best_score = -1.0

        for agent_id in candidate_agents:
            agent = await self.agent_factory.get_agent(agent_id)
            if not agent:
                continue

            # Calculate selection score
            score = await self._calculate_agent_score(agent, task_data)

            if score > best_score:
                best_score = score
                best_agent_id = agent_id

        return best_agent_id

    async def _calculate_agent_score(self, agent: BaseAgent, task_data: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate agent selection score"""
        score = 0.0

        # Load factor (lower is better)
        current_load = len(agent.current_tasks) / agent.config.max_concurrent_tasks
        score += (1.0 - current_load) * 40  # Up to 40 points for low load

        # Performance history (higher is better)
        total_tasks = agent.metrics.tasks_completed + agent.metrics.tasks_failed
        if total_tasks > 0:
            success_rate = agent.metrics.tasks_completed / total_tasks
            score += success_rate * 30  # Up to 30 points for high success rate

        # Speed factor (lower execution time is better)
        if agent.metrics.average_execution_time > 0:
            speed_score = min(20, 20 / agent.metrics.average_execution_time)
            score += speed_score  # Up to 20 points for speed

        # Capability match bonus
        required_caps = set(task_data.get("required_capabilities", []))
        agent_caps = agent.capabilities
        match_ratio = (
            len(required_caps.intersection(agent_caps)) / len(required_caps)
            if required_caps
            else 1.0
        )
        score += match_ratio * 10  # Up to 10 points for capability match

        return score

    async def _assign_task_to_agent(self, task_data: dict[str, Any], agent_id: str) -> None:  # TODO(TYPE): replace Any with concrete type
        """Assign a task to a specific agent"""
        try:
            agent = await self.agent_factory.get_agent(agent_id)
            if not agent:
                logger.error(f"Agent {agent_id} not found for task assignment")
                return

            # Create allocation record
            allocation = AgentAllocation(
                agent_id=agent_id,
                task_id=task_data["id"],
                allocated_at=datetime.now(timezone.utc),
                estimated_completion=datetime.now(timezone.utc)
                + timedelta(seconds=task_data.get("estimated_duration", 60)),
                priority=task_data.get("priority", 5),
            )

            self.agent_allocations[task_data["id"]] = allocation

            # Update task status
            task_data["status"] = "assigned"
            task_data["assigned_to"] = agent_id
            task_data["assigned_at"] = datetime.now(timezone.utc)

            # Execute task asynchronously
            asyncio.create_task(self._execute_task_on_agent(task_data, agent))

            logger.info(f"Task {task_data['id']} assigned to agent {agent_id}")

        except Exception as e:
            logger.error(f"Failed to assign task {task_data['id']} to agent {agent_id}: {e}")

    async def _execute_task_on_agent(self, task_data: dict[str, Any], agent: BaseAgent) -> None:  # TODO(TYPE): replace Any with concrete type
        """Execute task on agent and handle completion"""
        try:
            task_id = task_data["id"]

            # Execute the task
            result = await agent.execute_task(task_data)

            # Update task with result
            task_data["status"] = "completed" if result.get("success") else "failed"
            task_data["completed_at"] = datetime.now(timezone.utc)
            task_data["result"] = result
            task_data["execution_time"] = result.get("execution_time", 0)

            # Clean up allocation
            if task_id in self.agent_allocations:
                del self.agent_allocations[task_id]

            # Archive completed task
            self.completed_tasks.append(task_data)

            # Keep only last 1000 completed tasks
            if len(self.completed_tasks) > 1000:
                self.completed_tasks = self.completed_tasks[-1000:]

            logger.info(f"Task {task_id} completed on agent {agent.agent_id}")

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            task_data["status"] = "failed"
            task_data["error"] = str(e)

    async def _management_loop(self) -> None:
        """Main management loop"""
        while self.running:
            try:
                # Try to assign pending tasks
                await self._try_assign_tasks()

                # Perform health checks
                await self._perform_health_checks()

                # Update performance metrics
                await self._update_performance_metrics()

                # Handle auto-scaling
                await self._handle_auto_scaling()

                # Clean up expired allocations
                await self._cleanup_expired_allocations()

                await asyncio.sleep(30)  # Management cycle every 30 seconds

            except Exception as e:
                logger.error(f"Management loop error: {e}")
                await asyncio.sleep(60)

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all agents"""
        current_time = datetime.now(timezone.utc)

        for agent_id, agent in self.agent_factory.active_agents.items():
            last_check = self.agent_health_checks.get(
                agent_id, datetime.min.replace(tzinfo=timezone.utc)
            )
            check_interval = timedelta(seconds=agent.config.health_check_interval)

            if current_time - last_check >= check_interval:
                try:
                    health_info = await agent.health_check()
                    self.agent_health_checks[agent_id] = current_time

                    # Log health issues
                    if health_info.get("health") != "healthy":
                        logger.warning(f"Agent {agent_id} health issue: {health_info}")

                except Exception as e:
                    logger.error(f"Health check failed for agent {agent_id}: {e}")

    async def _update_performance_metrics(self) -> None:
        """Update overall performance metrics"""
        total_agents = len(self.agent_factory.active_agents)
        active_allocations = len(self.agent_allocations)
        queued_tasks = len(self.task_queue)
        completed_tasks_count = len(self.completed_tasks)

        # Calculate success rate for recent tasks
        recent_tasks = [t for t in self.completed_tasks[-100:] if t.get("completed_at")]
        successful_recent = len([t for t in recent_tasks if t.get("status") == "completed"])
        recent_success_rate = (successful_recent / len(recent_tasks) * 100) if recent_tasks else 100

        # Calculate average execution time
        execution_times = [
            t.get("execution_time", 0) for t in recent_tasks if t.get("execution_time")
        ]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0

        self.performance_metrics = {
            "timestamp": datetime.now(timezone.utc),
            "total_agents": total_agents,
            "active_allocations": active_allocations,
            "queued_tasks": queued_tasks,
            "completed_tasks": completed_tasks_count,
            "recent_success_rate": recent_success_rate,
            "average_execution_time": avg_execution_time,
            "system_utilization": (active_allocations / max(total_agents, 1)) * 100,
        }

    async def _handle_auto_scaling(self) -> None:
        """Handle automatic scaling of agent pool"""
        queue_size: int = len(self.task_queue)
        utilization_val = self.performance_metrics.get("system_utilization", 0)
        utilization: int = int(utilization_val) if isinstance(utilization_val, (int, float)) else 0

        # Scale up conditions
        if queue_size > 10 or utilization > 80:
            # Check which agent types are most in demand
            required_capabilities = set()
            for task in self.task_queue:
                required_capabilities.update(task.get("required_capabilities", []))

            # Create additional agents for high-demand capabilities
            for capability in required_capabilities:
                agent_type = self._capability_to_agent_type(capability)
                if agent_type:
                    current_count = len(
                        [
                            a
                            for a in self.agent_factory.active_agents.values()
                            if a.config.agent_type == agent_type
                        ]
                    )
                    if current_count < 3:  # Max 3 agents per type
                        agent_id = await self.agent_factory.create_agent(agent_type)
                        if agent_id:
                            logger.info(f"Auto-scaled: Created {agent_type.value} agent {agent_id}")

        # Scale down conditions (simplified)
        elif queue_size == 0 and utilization < 20:
            # Don't auto-scale down for now to maintain availability
            pass

    def _capability_to_agent_type(self, capability: str) -> AgentType | None:
        """Map capability to agent type"""
        capability_mapping = {
            "data_analysis": AgentType.DATA_ANALYSIS,
            "statistical_analysis": AgentType.DATA_ANALYSIS,
            "system_monitoring": AgentType.SYSTEM_MONITOR,
            "resource_monitoring": AgentType.SYSTEM_MONITOR,
            "code_execution": AgentType.CODE_EXECUTION,
            "knowledge_search": AgentType.KNOWLEDGE_RETRIEVAL,
            "report_generation": AgentType.REPORTING,
            "performance_analysis": AgentType.PERFORMANCE_ANALYSIS,
        }
        return capability_mapping.get(capability)

    async def _cleanup_expired_allocations(self) -> None:
        """Clean up expired task allocations"""
        current_time = datetime.now(timezone.utc)
        expired_allocations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for task_id, allocation in self.agent_allocations.items():
            est = allocation.estimated_completion
            if est.tzinfo is None:
                est = est.replace(tzinfo=timezone.utc)
            if current_time > est + timedelta(minutes=10):
                expired_allocations.append(task_id)

        for task_id in expired_allocations:
            logger.warning(f"Cleaning up expired allocation for task {task_id}")
            del self.agent_allocations[task_id]

    def get_manager_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive manager status"""
        agent_status: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_id, agent in self.agent_factory.active_agents.items():
            agent_status[agent_id] = {
                "type": agent.config.agent_type.value,
                "status": agent.status.value,
                "current_tasks": len(agent.current_tasks),
                "max_tasks": agent.config.max_concurrent_tasks,
                "tasks_completed": agent.metrics.tasks_completed,
                "average_execution_time": agent.metrics.average_execution_time,
            }

        return {
            "manager_running": self.running,
            "performance_metrics": self.performance_metrics,
            "agent_factory_status": self.agent_factory.get_factory_status(),
            "task_queue_size": len(self.task_queue),
            "active_allocations": len(self.agent_allocations),
            "completed_tasks": len(self.completed_tasks),
            "agents": agent_status,
        }

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get status of a specific task"""
        # Check in queue
        for task in self.task_queue:
            if task["id"] == task_id:
                return task

        # Check in allocations
        if task_id in self.agent_allocations:
            allocation = self.agent_allocations[task_id]
            return {
                "id": task_id,
                "status": "executing",
                "assigned_to": allocation.agent_id,
                "allocated_at": allocation.allocated_at.isoformat(),
                "estimated_completion": allocation.estimated_completion.isoformat(),
            }

        # Check in completed tasks
        for task in self.completed_tasks:
            if task["id"] == task_id:
                return task

        return None


# Global agent manager instance
_agent_manager: AgentManager | None = None


def create_agent_manager() -> AgentManager:
    """Create or get global agent manager instance"""
    global _agent_manager
    if _agent_manager is None:
        from .agent_factory import create_agent_factory

        factory = create_agent_factory()
        _agent_manager = AgentManager(factory)
    return _agent_manager


def get_agent_manager() -> AgentManager | None:
    """Get global agent manager instance"""
    return _agent_manager
