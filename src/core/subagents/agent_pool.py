#!/usr/bin/env python3
"""
Agent Pool - M-MDP Dynamic Agent Resource Pool
Dynamic agent pooling, load balancing, and resource optimization
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.types import AgentType
from .agent_manager import AgentManager

logger = logging.getLogger(__name__)


@dataclass
class PoolConfiguration:
    """Configuration for agent pool"""

    min_agents_per_type: dict[AgentType, int]
    max_agents_per_type: dict[AgentType, int]
    scale_up_threshold: float  # Utilization percentage
    scale_down_threshold: float
    scale_check_interval: int  # Seconds
    idle_timeout: int  # Seconds before considering agent for removal


@dataclass
class PoolMetrics:
    """Agent pool performance metrics"""

    total_agents: int = 0
    active_agents: int = 0
    idle_agents: int = 0
    busy_agents: int = 0
    total_capacity: int = 0
    current_utilization: float = 0.0
    scaling_events: int = 0
    last_scale_action: datetime | None = None


class AgentPool:
    """Dynamic agent resource pool with intelligent scaling"""

    def __init__(self, agent_manager: AgentManager) -> None:
        self.agent_manager = agent_manager
        self.agent_factory = agent_manager.agent_factory
        self.pool_config = self._create_default_config()
        self.pool_metrics = PoolMetrics()
        self.agent_usage_history: dict[str, list[float]] = defaultdict(list)
        self.scaling_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.running = False
        self.pool_management_task: asyncio.Task[None] | None = None

    def _create_default_config(self) -> PoolConfiguration:
        """Create default pool configuration"""
        return PoolConfiguration(
            min_agents_per_type={
                AgentType.SYSTEM_MONITOR: 1,
                AgentType.DATA_ANALYSIS: 1,
                AgentType.KNOWLEDGE_RETRIEVAL: 1,
                AgentType.REPORTING: 1,
                AgentType.CODE_EXECUTION: 0,
                AgentType.PERFORMANCE_ANALYSIS: 0,
            },
            max_agents_per_type={
                AgentType.SYSTEM_MONITOR: 3,
                AgentType.DATA_ANALYSIS: 5,
                AgentType.KNOWLEDGE_RETRIEVAL: 3,
                AgentType.REPORTING: 2,
                AgentType.CODE_EXECUTION: 3,
                AgentType.PERFORMANCE_ANALYSIS: 2,
            },
            scale_up_threshold=75.0,  # Scale up when utilization > 75%
            scale_down_threshold=25.0,  # Scale down when utilization < 25%
            scale_check_interval=60,  # Check every minute
            idle_timeout=300,  # 5 minutes idle before considering removal
        )

    async def start_pool(self) -> None:
        """Start the agent pool management"""
        if self.running:
            logger.warning("Agent pool already running")
            return

        self.running = True
        logger.info("Starting M-MDP Agent Pool")

        # Ensure minimum agents are available
        await self._ensure_minimum_agents()

        # Start pool management
        self.pool_management_task = asyncio.create_task(self._pool_management_loop())

        logger.info("Agent pool started successfully")

    async def stop_pool(self) -> None:
        """Stop the agent pool management"""
        self.running = False
        if self.pool_management_task:
            self.pool_management_task.cancel()

        logger.info("Agent pool stopped")

    async def _ensure_minimum_agents(self) -> None:
        """Ensure minimum number of agents are available"""
        for agent_type, min_count in self.pool_config.min_agents_per_type.items():
            current_count = await self._count_agents_of_type(agent_type)

            if current_count < min_count:
                needed = min_count - current_count
                logger.info(f"Creating {needed} minimum agents of type {agent_type.value}")

                for _ in range(needed):
                    agent_id = await self.agent_factory.create_agent(agent_type)
                    if agent_id:
                        logger.info(f"Created minimum agent: {agent_id}")

    async def _count_agents_of_type(self, agent_type: AgentType) -> int:
        """Count agents of specific type"""
        count = 0
        for agent in self.agent_factory.active_agents.values():
            if agent.config.agent_type == agent_type:
                count += 1
        return count

    async def request_agent(
        self, required_capabilities: list[str], priority: int = 5
    ) -> str | None:
        """Request an agent with specific capabilities"""
        try:
            # Find available agents with required capabilities
            suitable_agents = await self.agent_factory.find_capable_agents(required_capabilities)

            if suitable_agents:
                # Select best agent based on current load and performance
                best_agent = await self._select_optimal_agent(suitable_agents)
                return best_agent

            # No suitable agents available, try to create one
            agent_type = await self._determine_agent_type_for_capabilities(required_capabilities)
            if agent_type:
                # Check if we can create more agents of this type
                current_count = await self._count_agents_of_type(agent_type)
                max_count = self.pool_config.max_agents_per_type.get(agent_type, 5)

                if current_count < max_count:
                    agent_id = await self.agent_factory.create_agent(agent_type)
                    if agent_id:
                        logger.info(
                            f"Created on-demand agent {agent_id} for capabilities: {required_capabilities}"
                        )
                        await self._record_scaling_event("scale_up", agent_type, "on_demand")
                        return agent_id

            logger.warning(f"Could not provide agent for capabilities: {required_capabilities}")
            return None

        except Exception as e:
            logger.error(f"Error requesting agent: {e}")
            return None

    async def _select_optimal_agent(self, candidate_agents: list[str]) -> str:
        """Select the optimal agent from candidates"""
        best_agent_id = None
        best_score: float = -1.0

        for agent_id in candidate_agents:
            agent = await self.agent_factory.get_agent(agent_id)
            if not agent:
                continue

            # Calculate selection score based on load and performance
            load_factor = len(agent.current_tasks) / agent.config.max_concurrent_tasks
            performance_factor = self._get_agent_performance_score(agent_id)

            # Lower load and higher performance is better
            score = (1.0 - load_factor) * 0.7 + performance_factor * 0.3

            if score > best_score:
                best_score = score
                best_agent_id = agent_id

        return best_agent_id or candidate_agents[0]

    def _get_agent_performance_score(self, agent_id: str) -> float:
        """Get performance score for agent based on history"""
        if agent_id not in self.agent_usage_history:
            return 0.5  # Default moderate score

        recent_usage = self.agent_usage_history[agent_id][-10:]  # Last 10 data points
        if not recent_usage:
            return 0.5

        # Performance score based on inverse of average usage
        avg_usage = sum(recent_usage) / len(recent_usage)
        return max(0.0, min(1.0, 1.0 - avg_usage))

    async def _determine_agent_type_for_capabilities(
        self, capabilities: list[str]
    ) -> AgentType | None:
        """Determine best agent type for given capabilities"""
        capability_mapping = {
            "data_analysis": AgentType.DATA_ANALYSIS,
            "statistical_analysis": AgentType.DATA_ANALYSIS,
            "pattern_recognition": AgentType.DATA_ANALYSIS,
            "system_monitoring": AgentType.SYSTEM_MONITOR,
            "resource_monitoring": AgentType.SYSTEM_MONITOR,
            "health_checks": AgentType.SYSTEM_MONITOR,
            "code_execution": AgentType.CODE_EXECUTION,
            "python_execution": AgentType.CODE_EXECUTION,
            "javascript_execution": AgentType.CODE_EXECUTION,
            "knowledge_search": AgentType.KNOWLEDGE_RETRIEVAL,
            "document_retrieval": AgentType.KNOWLEDGE_RETRIEVAL,
            "faq_lookup": AgentType.KNOWLEDGE_RETRIEVAL,
            "report_generation": AgentType.REPORTING,
            "data_export": AgentType.REPORTING,
            "performance_analysis": AgentType.PERFORMANCE_ANALYSIS,
            "benchmarking": AgentType.PERFORMANCE_ANALYSIS,
            "bottleneck_analysis": AgentType.PERFORMANCE_ANALYSIS,
        }

        # Find the most specific match
        for capability in capabilities:
            if capability in capability_mapping:
                return capability_mapping[capability]

        # Default fallback
        return AgentType.DATA_ANALYSIS

    async def _pool_management_loop(self) -> None:
        """Main pool management loop"""
        while self.running:
            try:
                # Update pool metrics
                await self._update_pool_metrics()

                # Check for scaling opportunities
                await self._check_scaling_needs()

                # Update agent usage history
                await self._update_agent_usage_history()

                # Clean up idle agents if needed
                await self._cleanup_idle_agents()

                # Record pool state
                await self._record_pool_state()

                await asyncio.sleep(self.pool_config.scale_check_interval)

            except Exception as e:
                logger.error(f"Pool management loop error: {e}")
                await asyncio.sleep(self.pool_config.scale_check_interval)

    async def _update_pool_metrics(self) -> None:
        """Update pool performance metrics"""
        total_agents = len(self.agent_factory.active_agents)
        active_agents = 0
        idle_agents = 0
        busy_agents = 0
        total_capacity = 0

        for agent in self.agent_factory.active_agents.values():
            total_capacity += agent.config.max_concurrent_tasks
            current_tasks = len(agent.current_tasks)

            if current_tasks > 0:
                busy_agents += 1
                if current_tasks < agent.config.max_concurrent_tasks:
                    active_agents += 1
            else:
                idle_agents += 1

        current_utilization = 0.0
        if total_capacity > 0:
            total_allocated_tasks = sum(
                len(agent.current_tasks) for agent in self.agent_factory.active_agents.values()
            )
            current_utilization = (total_allocated_tasks / total_capacity) * 100

        self.pool_metrics = PoolMetrics(
            total_agents=total_agents,
            active_agents=active_agents,
            idle_agents=idle_agents,
            busy_agents=busy_agents,
            total_capacity=total_capacity,
            current_utilization=current_utilization,
            scaling_events=self.pool_metrics.scaling_events,
            last_scale_action=self.pool_metrics.last_scale_action,
        )

    async def _check_scaling_needs(self) -> None:
        """Check if scaling is needed and execute if appropriate"""
        current_utilization = self.pool_metrics.current_utilization

        # Scale up if utilization is high
        if current_utilization > self.pool_config.scale_up_threshold:
            await self._scale_up()

        # Scale down if utilization is low
        elif current_utilization < self.pool_config.scale_down_threshold:
            await self._scale_down()

    async def _scale_up(self) -> None:
        """Scale up the agent pool"""
        # Determine which agent types are most in demand
        demand_analysis = await self._analyze_demand_by_type()

        for agent_type, demand_score in demand_analysis.items():
            if demand_score > 0.7:  # High demand threshold
                current_count = await self._count_agents_of_type(agent_type)
                max_count = self.pool_config.max_agents_per_type.get(agent_type, 5)

                if current_count < max_count:
                    agent_id = await self.agent_factory.create_agent(agent_type)
                    if agent_id:
                        logger.info(f"Scaled up: Created {agent_type.value} agent {agent_id}")
                        await self._record_scaling_event("scale_up", agent_type, "demand_based")
                        break  # Only scale one at a time

    async def _scale_down(self) -> None:
        """Scale down the agent pool"""
        # Find candidates for removal (idle agents above minimum)
        removal_candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, agent in self.agent_factory.active_agents.items():
            agent_type = agent.config.agent_type
            min_count = self.pool_config.min_agents_per_type.get(agent_type, 0)
            current_count = await self._count_agents_of_type(agent_type)

            # Only consider for removal if above minimum
            if current_count > min_count:
                # Check if agent has been idle
                if (
                    not agent.current_tasks
                    and (datetime.now(timezone.utc) - agent.last_activity).total_seconds()
                    > self.pool_config.idle_timeout
                ):
                    removal_candidates.append((agent_id, agent))

        # Remove one idle agent
        if removal_candidates:
            # Select least recently used agent
            removal_candidates.sort(key=lambda x: x[1].last_activity)
            agent_id, agent = removal_candidates[0]

            success = await self.agent_factory.shutdown_agent(agent_id)
            if success:
                logger.info(f"Scaled down: Removed idle agent {agent_id}")
                await self._record_scaling_event(
                    "scale_down", agent.config.agent_type, "idle_cleanup"
                )

    async def _analyze_demand_by_type(self) -> dict[AgentType, float]:
        """Analyze demand for each agent type"""
        demand_scores: dict[AgentType, float] = {}
        for agent_type in AgentType:
            agents_of_type = [
                a
                for a in self.agent_factory.active_agents.values()
                if a.config.agent_type == agent_type
            ]

            if not agents_of_type:
                demand_scores[agent_type] = 0.0
                continue

            # Calculate average utilization for this agent type
            total_utilization = 0.0
            for agent in agents_of_type:
                utilization = len(agent.current_tasks) / agent.config.max_concurrent_tasks
                total_utilization += utilization

            avg_utilization = total_utilization / len(agents_of_type)
            demand_scores[agent_type] = avg_utilization

        return demand_scores

    async def _update_agent_usage_history(self) -> None:
        """Update usage history for all agents"""
        for agent_id, agent in self.agent_factory.active_agents.items():
            utilization = len(agent.current_tasks) / agent.config.max_concurrent_tasks
            self.agent_usage_history[agent_id].append(utilization)

            # Keep only last 100 data points
            if len(self.agent_usage_history[agent_id]) > 100:
                self.agent_usage_history[agent_id] = self.agent_usage_history[agent_id][-100:]

    async def _cleanup_idle_agents(self) -> None:
        """Clean up agents that have been idle for too long."""
        await self._scale_down()

    async def _record_pool_state(self) -> None:
        """Record current pool state for monitoring"""
        # Keep pool state history for analysis
        pool_state = {
            "timestamp": datetime.now(timezone.utc),
            "metrics": self.pool_metrics,
            "agent_counts": {
                agent_type.value: await self._count_agents_of_type(agent_type)
                for agent_type in AgentType
            },
        }
        self.scaling_history.append(pool_state)

        # Keep only last 24 hours of pool states (assuming 1-minute intervals)
        if len(self.scaling_history) > 1440:
            self.scaling_history = self.scaling_history[-1440:]

    async def _record_scaling_event(self, action: str, agent_type: AgentType, reason: str) -> None:
        """Record a scaling event"""
        scaling_event = {
            "timestamp": datetime.now(timezone.utc),
            "action": action,
            "agent_type": agent_type.value,
            "reason": reason,
            "pool_utilization": self.pool_metrics.current_utilization,
            "total_agents_before": self.pool_metrics.total_agents,
        }

        self.scaling_history.append(scaling_event)
        self.pool_metrics.scaling_events += 1
        self.pool_metrics.last_scale_action = datetime.now(timezone.utc)

        logger.info(f"Scaling event: {action} {agent_type.value} ({reason})")

    def configure_pool(self, config: PoolConfiguration) -> None:
        """Update pool configuration"""
        self.pool_config = config
        logger.info("Pool configuration updated")

    def get_pool_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive pool status"""
        agent_type_breakdown: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_type in AgentType:
            agents_of_type = [
                a
                for a in self.agent_factory.active_agents.values()
                if a.config.agent_type == agent_type
            ]

            agent_type_breakdown[agent_type.value] = {
                "count": len(agents_of_type),
                "min_configured": self.pool_config.min_agents_per_type.get(agent_type, 0),
                "max_configured": self.pool_config.max_agents_per_type.get(agent_type, 5),
                "average_utilization": (
                    sum(
                        len(a.current_tasks) / a.config.max_concurrent_tasks for a in agents_of_type
                    )
                    / len(agents_of_type)
                    if agents_of_type
                    else 0
                ),
            }

        recent_scaling_events = [
            {
                "timestamp": event["timestamp"].isoformat(),
                "action": event["action"],
                "agent_type": event["agent_type"],
                "reason": event["reason"],
            }
            for event in self.scaling_history[-10:]  # Last 10 events
        ]

        return {
            "pool_running": self.running,
            "metrics": {
                "total_agents": self.pool_metrics.total_agents,
                "active_agents": self.pool_metrics.active_agents,
                "idle_agents": self.pool_metrics.idle_agents,
                "busy_agents": self.pool_metrics.busy_agents,
                "total_capacity": self.pool_metrics.total_capacity,
                "current_utilization": round(self.pool_metrics.current_utilization, 2),
                "scaling_events": self.pool_metrics.scaling_events,
                "last_scale_action": (
                    self.pool_metrics.last_scale_action.isoformat()
                    if self.pool_metrics.last_scale_action
                    else None
                ),
            },
            "agent_type_breakdown": agent_type_breakdown,
            "configuration": {
                "scale_up_threshold": self.pool_config.scale_up_threshold,
                "scale_down_threshold": self.pool_config.scale_down_threshold,
                "scale_check_interval": self.pool_config.scale_check_interval,
                "idle_timeout": self.pool_config.idle_timeout,
            },
            "recent_scaling_events": recent_scaling_events,
        }

    async def get_pool_analytics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get detailed pool analytics"""
        # Usage pattern analysis
        usage_patterns: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_id, history in self.agent_usage_history.items():
            if history:
                usage_patterns[agent_id] = {
                    "average_utilization": sum(history) / len(history),
                    "peak_utilization": max(history),
                    "min_utilization": min(history),
                    "data_points": len(history),
                }

        # Scaling efficiency analysis
        scaling_efficiency = {
            "total_scale_events": len(self.scaling_history),
            "scale_up_events": len([e for e in self.scaling_history if e["action"] == "scale_up"]),
            "scale_down_events": len(
                [e for e in self.scaling_history if e["action"] == "scale_down"]
            ),
            "avg_time_between_scales": None,
        }

        if len(self.scaling_history) > 1:
            time_deltas: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for i in range(1, len(self.scaling_history)):
                delta = (
                    self.scaling_history[i]["timestamp"] - self.scaling_history[i - 1]["timestamp"]
                ).total_seconds()
                time_deltas.append(delta)
            scaling_efficiency["avg_time_between_scales"] = sum(time_deltas) / len(time_deltas)

        return {
            "usage_patterns": usage_patterns,
            "scaling_efficiency": scaling_efficiency,
            "pool_health": (
                "optimal" if 30 <= self.pool_metrics.current_utilization <= 80 else "suboptimal"
            ),
            "recommendations": await self._generate_pool_recommendations(),
        }

    async def _generate_pool_recommendations(self) -> list[str]:
        """Generate recommendations for pool optimization"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        utilization = self.pool_metrics.current_utilization

        if utilization > 90:
            recommendations.append("Consider increasing maximum agents per type")
        elif utilization < 10:
            recommendations.append("Consider reducing minimum agents per type")

        if self.pool_metrics.idle_agents > self.pool_metrics.busy_agents:
            recommendations.append("Many agents are idle - consider adjusting scale-down threshold")

        if len(self.scaling_history) > 20:  # Frequent scaling
            recommendations.append("Frequent scaling detected - consider adjusting thresholds")

        return recommendations


# Global agent pool instance
_agent_pool: AgentPool | None = None


def create_agent_pool() -> AgentPool:
    """Create or get global agent pool instance"""
    global _agent_pool
    if _agent_pool is None:
        from .agent_manager import create_agent_manager

        manager = create_agent_manager()
        _agent_pool = AgentPool(manager)
    return _agent_pool


def get_agent_pool() -> AgentPool | None:
    """Get global agent pool instance"""
    return _agent_pool
