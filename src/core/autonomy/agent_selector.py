"""
Agent Selector Service - Capability-based Agent Selection
Implements dynamic agent selection based on capabilities and load balancing
ASCII-only compliance enforced
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.collaboration.agent_mesh import AgentRegistry, RegisteredAgent, get_agent_registry

from .goal_parsers import GoalIntent

logger = logging.getLogger(__name__)


class AgentSelectionStrategy:
    """
    Base class for agent selection strategies
    Allows different algorithms for agent selection
    """

    def select_agent(
        self, candidates: list[RegisteredAgent], goal_intent: GoalIntent
    ) -> RegisteredAgent | None:
        """
        Select best agent from candidates

        Args:
            candidates: List[Any] of capable agents  # TODO(TYPE): replace Any with concrete type
            goal_intent: Goal intent with requirements

        Returns:
            Best agent or None if no suitable agent
        """
        raise NotImplementedError


class LoadBalancedSelectionStrategy(AgentSelectionStrategy):
    """
    Load-balanced agent selection strategy
    Selects agent with lowest current load
    """

    def select_agent(
        self, candidates: list[RegisteredAgent], goal_intent: GoalIntent
    ) -> RegisteredAgent | None:
        """Select agent with lowest load"""
        if not candidates:
            return None

        # Filter healthy and available agents
        available_agents = [
            agent for agent in candidates if agent.is_healthy() and agent.is_available()
        ]

        if not available_agents:
            # Fallback to any capable agent if none are "available"
            available_agents = [agent for agent in candidates if agent.is_healthy()]

        if not available_agents:
            logger.warning("No healthy agents available for selection")
            return None

        # Sort by current load (ascending)
        available_agents.sort(key=lambda a: a.current_load)

        selected = available_agents[0]
        logger.debug(f"Selected agent {selected.agent_id} with load {selected.current_load}%")

        return selected


class PriorityBasedSelectionStrategy(AgentSelectionStrategy):
    """
    Priority-based agent selection strategy
    Considers both load and goal priority
    """

    def select_agent(
        self, candidates: list[RegisteredAgent], goal_intent: GoalIntent
    ) -> RegisteredAgent | None:
        """Select agent based on priority and load combination"""
        if not candidates:
            return None

        # Filter healthy agents
        healthy_agents = [agent for agent in candidates if agent.is_healthy()]

        if not healthy_agents:
            logger.warning("No healthy agents available for priority selection")
            return None

        # Calculate selection score for each agent
        scored_agents: list[tuple[RegisteredAgent, float]] = []
        for agent in healthy_agents:
            score = self._calculate_selection_score(agent, goal_intent)
            scored_agents.append((agent, score))

        # Sort by score (higher is better)
        scored_agents.sort(key=lambda x: x[1], reverse=True)

        selected = scored_agents[0][0]
        score = scored_agents[0][1]

        logger.debug(f"Selected agent {selected.agent_id} with score {score:.2f}")
        return selected

    def _calculate_selection_score(self, agent: RegisteredAgent, goal_intent: GoalIntent) -> float:
        """Calculate selection score for agent"""
        # Base score
        score = 100.0

        # Penalize high load
        load_penalty = agent.current_load * 0.5
        score -= load_penalty

        # Penalize high active tasks
        task_penalty = (agent.active_tasks / max(agent.max_concurrent_tasks, 1)) * 20
        score -= task_penalty

        # Bonus for high priority goals and low load
        if goal_intent.priority >= 8 and agent.current_load < 30:
            score += 20

        # Availability bonus
        if agent.is_available():
            score += 10

        return max(score, 0.0)


class AgentSelector:
    """
    Service for capability-based agent selection
    Implements dynamic agent discovery and load-balanced selection
    """

    def __init__(self, agent_registry: AgentRegistry | None = None) -> None:
        self.agent_registry = agent_registry or get_agent_registry()
        self.selection_strategy: AgentSelectionStrategy = LoadBalancedSelectionStrategy()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Selection statistics
        self._selection_stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "total_selections": 0,
            "successful_selections": 0,
            "failed_selections": 0,
            "last_selection_time": None,
            "agent_selection_counts": {},
        }

        self.logger.info("AgentSelector initialized with load-balanced strategy")

    def set_selection_strategy(self, strategy: AgentSelectionStrategy) -> None:
        """
        Set agent selection strategy

        Args:
            strategy: Selection strategy to use
        """
        self.selection_strategy = strategy
        self.logger.info(f"Agent selection strategy updated: {strategy.__class__.__name__}")

    async def find_best_agent(self, goal_intent: GoalIntent) -> RegisteredAgent | None:
        """
        Find best agent for goal based on capabilities and current load

        Args:
            goal_intent: Goal intent with capability requirements

        Returns:
            Best available agent or None if no suitable agent found
        """
        try:
            self._selection_stats["total_selections"] += 1
            self._selection_stats["last_selection_time"] = datetime.now(timezone.utc)

            self.logger.info(f"Finding agent for goal type: {goal_intent.goal_type}")
            self.logger.debug(f"Required capabilities: {goal_intent.required_capabilities}")

            # Get all available agents
            available_agents_dict = self.agent_registry.get_available_agents()

            if not available_agents_dict:
                self.logger.warning("No agents available in registry")
                self._selection_stats["failed_selections"] += 1
                return None

            # Filter agents by required capabilities
            capable_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for agent in available_agents_dict.values():
                if self._agent_has_capabilities(agent, goal_intent.required_capabilities):
                    capable_agents.append(agent)

            if not capable_agents:
                self.logger.warning(
                    f"No agents found with required capabilities: {goal_intent.required_capabilities}"
                )
                self._selection_stats["failed_selections"] += 1
                return None

            self.logger.debug(f"Found {len(capable_agents)} capable agents")

            # Use sync selection logic (M-MDP compliant)
            selected_agent = self.select_best_agent_from_candidates(capable_agents, goal_intent)

            return selected_agent

        except Exception as e:
            self.logger.error(f"Agent selection failed: {e}")
            self._selection_stats["failed_selections"] += 1
            return None

    def _agent_has_capabilities(
        self, agent: RegisteredAgent, required_capabilities: list[str]
    ) -> bool:
        """
        Check if agent has all required capabilities

        Args:
            agent: Agent to check
            required_capabilities: List[Any] of required capabilities  # TODO(TYPE): replace Any with concrete type

        Returns:
            True if agent has all required capabilities
        """
        if not required_capabilities:
            return True

        return all(agent.has_capability(capability) for capability in required_capabilities)

    def select_best_agent_from_candidates(
        self, candidates: list[RegisteredAgent], goal_intent: GoalIntent
    ) -> RegisteredAgent | None:
        """
        Select best agent from candidates using pure logic (M-MDP compliant sync)

        Args:
            candidates: List[Any] of candidate agents (pre-filtered for capabilities)  # TODO(TYPE): replace Any with concrete type
            goal_intent: Goal intent with requirements

        Returns:
            Best agent or None if no suitable agent found
        """
        try:
            # Use selection strategy for algorithm (pure logic - sync)
            selected_agent = self.selection_strategy.select_agent(candidates, goal_intent)

            if selected_agent:
                self._selection_stats["successful_selections"] += 1
                agent_id = selected_agent.agent_id
                self._selection_stats["agent_selection_counts"][agent_id] = (
                    self._selection_stats["agent_selection_counts"].get(agent_id, 0) + 1
                )
                self.logger.info(f"Selected agent: {agent_id}")
            else:
                self._selection_stats["failed_selections"] += 1
                self.logger.warning("No suitable agent found despite having capable agents")

            return selected_agent

        except Exception as e:
            self.logger.error(f"Agent selection logic failed: {e}")
            self._selection_stats["failed_selections"] += 1
            return None

    async def get_agents_for_capability(self, capability: str) -> list[RegisteredAgent]:
        """
        Get all agents with specific capability

        Args:
            capability: Capability to search for

        Returns: List[Any] of agents with the capability  # TODO(TYPE): replace Any with concrete type
        """
        try:
            all_agents_dict = self.agent_registry.get_all_agents()
            return [agent for agent in all_agents_dict.values() if agent.has_capability(capability)]

        except Exception as e:
            self.logger.error(f"Failed to get agents for capability '{capability}': {e}")
            return []

    async def get_agents_for_task_type(self, task_type: str) -> list[RegisteredAgent]:
        """
        Get all agents that support specific task type

        Args:
            task_type: Task type to search for

        Returns: List[Any] of agents supporting the task type  # TODO(TYPE): replace Any with concrete type
        """
        try:
            all_agents_dict = self.agent_registry.get_all_agents()
            return [
                agent for agent in all_agents_dict.values() if agent.can_handle_task_type(task_type)
            ]

        except Exception as e:
            self.logger.error(f"Failed to get agents for task type '{task_type}': {e}")
            return []

    def validate_agent_for_goal(self, agent: RegisteredAgent, goal_intent: GoalIntent) -> bool:
        """
        Validate if agent is suitable for goal

        Args:
            agent: Agent to validate
            goal_intent: Goal intent to validate against

        Returns:
            True if agent is suitable for goal
        """
        try:
            # Check health
            if not agent.is_healthy():
                self.logger.debug(f"Agent {agent.agent_id} is not healthy")
                return False

            # Check capabilities
            if not self._agent_has_capabilities(agent, goal_intent.required_capabilities):
                self.logger.debug(f"Agent {agent.agent_id} missing required capabilities")
                return False

            # Check task type support (if specified in parameters)
            task_type: str | None = goal_intent.parameters.get("task_type")
            if task_type:
                if not agent.can_handle_task_type(task_type):
                    self.logger.debug(f"Agent {agent.agent_id} cannot handle task type")
                    return False

            # Check availability for high-priority goals
            if goal_intent.priority >= 8 and not agent.is_available():
                self.logger.debug(f"Agent {agent.agent_id} not available for high-priority goal")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Agent validation failed: {e}")
            return False

    def get_selection_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get agent selection statistics

        Returns: Dict[str, Any]ionary with selection statistics  # TODO(TYPE): replace Any with concrete type
        """
        stats = self._selection_stats.copy()

        # Calculate success rate
        total = stats["total_selections"]
        successful = stats["successful_selections"]
        stats["success_rate"] = (successful / total * 100) if total > 0 else 0.0

        # Add strategy information
        stats["current_strategy"] = self.selection_strategy.__class__.__name__

        return stats

    async def get_capability_matrix(self) -> dict[str, list[str]]:
        """
        Get matrix of capabilities and supporting agents

        Returns: Dict[str, Any]ionary mapping capabilities to agent IDs  # TODO(TYPE): replace Any with concrete type
        """
        try:
            all_agents_dict = self.agent_registry.get_all_agents()
            capability_matrix: dict[str, list[str]] = {}

            for agent in all_agents_dict.values():
                agent_capabilities: list[str] = getattr(agent, "capabilities", []) or []
                for capability in agent_capabilities:
                    if capability not in capability_matrix:
                        capability_matrix[capability] = []
                    capability_matrix[capability].append(agent.agent_id)

            return capability_matrix

        except Exception as e:
            self.logger.error(f"Failed to get capability matrix: {e}")
            return {}

    async def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Perform health check on agent selection service

        Returns:
            Health check results
        """
        try:
            # Check agent registry availability
            available_agents_dict = self.agent_registry.get_available_agents()
            total_agents_dict = self.agent_registry.get_all_agents()
            available_count = len(available_agents_dict)
            total_count = len(total_agents_dict)

            health_info: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "service": "agent_selector",
                "status": "healthy",
                "total_agents": total_count,
                "available_agents": available_count,
                "selection_strategy": self.selection_strategy.__class__.__name__,
                "selection_stats": self.get_selection_stats(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Check if we have sufficient agent coverage
            if available_count == 0:
                health_info["status"] = "warning"
                health_info["warning"] = "No agents available"
            elif available_count < total_count * 0.5:
                health_info["status"] = "warning"
                health_info["warning"] = "Low agent availability"

            return health_info

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "service": "agent_selector",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


def create_agent_selector(
    agent_registry: AgentRegistry | None = None,
) -> AgentSelector:
    """
    Factory function for AgentSelector

    Args:
        agent_registry: Optional agent registry instance

    Returns:
        Configured AgentSelector instance
    """
    return AgentSelector(agent_registry)


__all__ = [
    "AgentSelector",
    "AgentSelectionStrategy",
    "LoadBalancedSelectionStrategy",
    "PriorityBasedSelectionStrategy",
    "create_agent_selector",
]
