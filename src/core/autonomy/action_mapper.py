"""
Action Mapper Service - Goal Intent to Agent Action Transformation
Maps parsed goal intents to specific agent actions and parameters
ASCII-only compliance enforced
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from .goal_parsers import GoalIntent

logger = logging.getLogger(__name__)


class ActionMapping:
    """
    Represents a mapped action for agent execution
    Contains agent routing and execution parameters
    """

    def __init__(
        self,
        agent_id: str,
        action: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        priority: int = 5,
        timeout_seconds: int = 30,
    ) -> None:
        self.agent_id = agent_id
        self.action = action
        self.parameters = parameters
        self.priority = priority
        self.timeout_seconds = timeout_seconds
        self.mapped_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization"""
        return {
            "agent_id": self.agent_id,
            "action": self.action,
            "parameters": self.parameters,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "mapped_at": self.mapped_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"ActionMapping(agent={self.agent_id}, action={self.action}, priority={self.priority})"
        )


class ActionMappingStrategy(ABC):
    """
    Abstract base class for action mapping strategies
    Allows different approaches to mapping goal intents to actions
    """

    @abstractmethod
    def map_goal_to_action(self, goal_intent: GoalIntent) -> ActionMapping | None:
        """
        Map goal intent to specific agent action

        Args:
            goal_intent: Parsed goal intent to map

        Returns:
            ActionMapping instance or None if unmappable
        """


class DirectMappingStrategy(ActionMappingStrategy):
    """
    Direct mapping strategy for straightforward goal-to-action mappings
    Uses predefined mapping rules for known goal types
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Predefined mappings: goal_type -> (agent_id, action, default_params)
        self.goal_mappings: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "archive_goal": ("knowledge_agent", "archive_knowledge", {}),
            "sentiment_analysis": ("knowledge_agent", "analyze_sentiment", {}),
            "translation_goal": ("translation_agent", "translate_text", {}),
            "diagnostics_goal": ("knowledge_agent", "diagnose_system", {}),
            "knowledge_query": ("knowledge_agent", "execute_knowledge_task", {}),
            "general_task": ("knowledge_agent", "execute_knowledge_task", {}),
        }

        self.logger.info("DirectMappingStrategy initialized with predefined mappings")

    def map_goal_to_action(self, goal_intent: GoalIntent) -> ActionMapping | None:
        """Map goal intent using direct mapping rules"""
        try:
            goal_type = goal_intent.goal_type

            if goal_type not in self.goal_mappings:
                self.logger.warning(f"No direct mapping found for goal type: {goal_type}")
                return None

            agent_id, action, default_params = self.goal_mappings[goal_type]

            # Merge default parameters with goal parameters
            merged_params = default_params.copy()
            merged_params.update(goal_intent.parameters)

            # Add goal content if not explicitly set
            if "content" not in merged_params and goal_intent.content:
                merged_params["content"] = goal_intent.content

            # Set timeout based on goal complexity
            timeout = self._calculate_timeout(goal_intent)

            mapping = ActionMapping(
                agent_id=agent_id,
                action=action,
                parameters=merged_params,
                priority=goal_intent.priority,
                timeout_seconds=timeout,
            )

            self.logger.info(f"Mapped {goal_type} -> {agent_id}.{action}")
            return mapping

        except Exception as e:
            self.logger.error(f"Direct mapping failed: {e}")
            return None

    def _calculate_timeout(self, goal_intent: GoalIntent) -> int:
        """Calculate appropriate timeout based on goal characteristics"""
        base_timeout = 30

        # Increase timeout for complex operations
        if goal_intent.goal_type in ["sentiment_analysis", "diagnostics_goal"]:
            base_timeout = 60
        elif goal_intent.goal_type == "translation_goal":
            # Base timeout for translation
            text_length = len(goal_intent.content)
            if text_length > 1000:
                base_timeout = 45

        # High priority gets more time
        if goal_intent.priority >= 8:
            base_timeout += 15

        return base_timeout


class CapabilityBasedMappingStrategy(ActionMappingStrategy):
    """
    Capability-based mapping strategy
    Maps based on required capabilities and agent specialization
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Capability-to-agent mappings
        self.capability_mappings: dict[str, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
            "text_translation": {
                "agent_id": "translation_agent",
                "actions": ["translate_text", "detect_language"],
            },
            "language_processing": {
                "agent_id": "translation_agent",
                "actions": ["translate_text", "detect_language"],
            },
            "knowledge_management": {
                "agent_id": "knowledge_agent",
                "actions": ["archive_knowledge", "execute_knowledge_task"],
            },
            "sentiment_analysis": {
                "agent_id": "knowledge_agent",
                "actions": ["analyze_sentiment"],
            },
            "system_diagnostics": {
                "agent_id": "knowledge_agent",
                "actions": ["diagnose_system"],
            },
        }

        self.logger.info("CapabilityBasedMappingStrategy initialized")

    def map_goal_to_action(self, goal_intent: GoalIntent) -> ActionMapping | None:
        """Map goal intent based on required capabilities"""
        try:
            if not goal_intent.required_capabilities:
                self.logger.warning("No required capabilities specified for mapping")
                return None

            # Find best capability match
            best_mapping = None
            best_score: float = 0

            for capability in goal_intent.required_capabilities:
                if capability in self.capability_mappings:
                    mapping_info = self.capability_mappings[capability]
                    score = self._calculate_capability_score(goal_intent, capability)

                    if score > best_score:
                        best_score = score
                        best_mapping = mapping_info

            if not best_mapping:
                self.logger.warning(
                    f"No capability mapping found for: {goal_intent.required_capabilities}"
                )
                return None

            # Select appropriate action
            action = self._select_action(goal_intent, best_mapping["actions"])

            # Prepare parameters
            parameters = goal_intent.parameters.copy()
            parameters["content"] = goal_intent.content

            mapping = ActionMapping(
                agent_id=best_mapping["agent_id"],
                action=action,
                parameters=parameters,
                priority=goal_intent.priority,
                timeout_seconds=self._calculate_timeout(goal_intent),
            )

            self.logger.info(
                f"Capability mapping: {goal_intent.required_capabilities} -> {mapping.agent_id}.{action}"
            )
            return mapping

        except Exception as e:
            self.logger.error(f"Capability-based mapping failed: {e}")
            return None

    def _calculate_capability_score(self, goal_intent: GoalIntent, capability: str) -> float:
        """Calculate match score for capability"""
        score = 1.0

        # Boost score for exact goal type matches
        if goal_intent.goal_type == "translation_goal" and capability == "text_translation":
            score += 2.0
        elif goal_intent.goal_type == "sentiment_analysis" and capability == "sentiment_analysis":
            score += 2.0
        elif goal_intent.goal_type == "diagnostics_goal" and capability == "system_diagnostics":
            score += 2.0

        # Priority boost
        if goal_intent.priority >= 7:
            score += 0.5

        return score

    def _select_action(self, goal_intent: GoalIntent, available_actions: list[str]) -> str:
        """Select most appropriate action from available actions"""
        # Goal type specific action selection
        if goal_intent.goal_type == "translation_goal":
            return "translate_text"
        elif goal_intent.goal_type == "sentiment_analysis":
            return "analyze_sentiment"
        elif goal_intent.goal_type == "diagnostics_goal":
            return "diagnose_system"
        elif goal_intent.goal_type == "archive_goal":
            return "archive_knowledge"

        # Default to first available action
        return available_actions[0] if available_actions else "execute_knowledge_task"

    def _calculate_timeout(self, goal_intent: GoalIntent) -> int:
        """Calculate timeout based on goal complexity"""
        base_timeout = 45  # More generous for capability-based mapping

        # Adjust based on content length
        content_length = len(goal_intent.content) if goal_intent.content else 0
        if content_length > 2000:
            base_timeout += 30
        elif content_length > 500:
            base_timeout += 15

        return base_timeout


class ActionMapper:
    """
    Service for mapping goal intents to agent actions
    Supports multiple mapping strategies and fallback mechanisms
    """

    def __init__(self, strategy: ActionMappingStrategy | None = None) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.primary_strategy = strategy or DirectMappingStrategy()
        self.fallback_strategy = CapabilityBasedMappingStrategy()

        # Mapping statistics
        self._mapping_stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "total_mappings": 0,
            "successful_mappings": 0,
            "failed_mappings": 0,
            "strategy_usage": {"primary": 0, "fallback": 0},
            "agent_distribution": {},
            "last_mapping_time": None,
        }

        self.logger.info(
            f"ActionMapper initialized with {self.primary_strategy.__class__.__name__}"
        )

    def map_goal_to_action(self, goal_intent: GoalIntent) -> ActionMapping | None:
        """
        Map goal intent to agent action using available strategies

        Args:
            goal_intent: Parsed goal intent to map

        Returns:
            ActionMapping or None if mapping fails
        """
        try:
            self._mapping_stats["total_mappings"] += 1
            self._mapping_stats["last_mapping_time"] = datetime.now(timezone.utc)

            self.logger.info(f"Mapping goal: {goal_intent.goal_type}")
            self.logger.debug(f"Goal content: {goal_intent.content[:100]}...")

            # Try primary strategy first
            mapping = self.primary_strategy.map_goal_to_action(goal_intent)

            if mapping:
                self._mapping_stats["successful_mappings"] += 1
                self._mapping_stats["strategy_usage"]["primary"] += 1
                self._update_agent_distribution(mapping.agent_id)

                self.logger.info(f"Primary mapping successful: {mapping}")
                return mapping

            # Try fallback strategy
            self.logger.info("Primary mapping failed, trying fallback strategy")
            mapping = self.fallback_strategy.map_goal_to_action(goal_intent)

            if mapping:
                self._mapping_stats["successful_mappings"] += 1
                self._mapping_stats["strategy_usage"]["fallback"] += 1
                self._update_agent_distribution(mapping.agent_id)

                self.logger.info(f"Fallback mapping successful: {mapping}")
                return mapping

            # Both strategies failed
            self._mapping_stats["failed_mappings"] += 1
            self.logger.warning(f"All mapping strategies failed for goal: {goal_intent.goal_type}")
            return None

        except Exception as e:
            self._mapping_stats["failed_mappings"] += 1
            self.logger.error(f"Action mapping failed: {e}")
            return None

    def _update_agent_distribution(self, agent_id: str) -> None:
        """Update agent usage statistics"""
        if agent_id not in self._mapping_stats["agent_distribution"]:
            self._mapping_stats["agent_distribution"][agent_id] = 0
        self._mapping_stats["agent_distribution"][agent_id] += 1

    def set_primary_strategy(self, strategy: ActionMappingStrategy) -> None:
        """
        Set primary mapping strategy

        Args:
            strategy: New primary strategy
        """
        self.primary_strategy = strategy
        self.logger.info(f"Primary strategy updated: {strategy.__class__.__name__}")

    def get_mapping_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get action mapping statistics

        Returns: Dict[str, Any]ionary with mapping statistics  # TODO(TYPE): replace Any with concrete type
        """
        stats = self._mapping_stats.copy()

        # Calculate success rate
        total = stats["total_mappings"]
        successful = stats["successful_mappings"]
        stats["success_rate"] = (successful / total * 100) if total > 0 else 0.0

        # Add strategy information
        stats["primary_strategy"] = self.primary_strategy.__class__.__name__
        stats["fallback_strategy"] = self.fallback_strategy.__class__.__name__

        return stats

    def validate_mapping(self, mapping: ActionMapping) -> bool:
        """
        Validate action mapping before execution

        Args:
            mapping: Action mapping to validate

        Returns:
            True if mapping is valid
        """
        try:
            # Basic validation
            if not mapping.agent_id or not mapping.action:
                return False

            # Check required parameters
            if not isinstance(mapping.parameters, dict):
                return False

            # Validate timeout
            if mapping.timeout_seconds <= 0 or mapping.timeout_seconds > 300:
                return False

            # Validate priority
            if not (1 <= mapping.priority <= 10):
                return False

            return True

        except Exception as e:
            self.logger.error(f"Mapping validation failed: {e}")
            return False

    async def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Perform health check on action mapper

        Returns:
            Health check results
        """
        try:
            health_info = {
                "service": "action_mapper",
                "status": "healthy",
                "primary_strategy": self.primary_strategy.__class__.__name__,
                "fallback_strategy": self.fallback_strategy.__class__.__name__,
                "mapping_stats": self.get_mapping_stats(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Check if strategies are functioning
            total_mappings = self._mapping_stats["total_mappings"]
            failed_mappings = self._mapping_stats["failed_mappings"]

            if total_mappings > 0:
                failure_rate = (failed_mappings / total_mappings) * 100
                if failure_rate > 50:
                    health_info["status"] = "warning"
                    health_info["warning"] = f"High failure rate: {failure_rate:.1f}%"

            return health_info

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "service": "action_mapper",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


def create_action_mapper(
    strategy: ActionMappingStrategy | None = None,
) -> ActionMapper:
    """
    Factory function for ActionMapper

    Args:
        strategy: Optional primary mapping strategy

    Returns:
        Configured ActionMapper instance
    """
    return ActionMapper(strategy)


__all__ = [
    "ActionMapping",
    "ActionMappingStrategy",
    "DirectMappingStrategy",
    "CapabilityBasedMappingStrategy",
    "ActionMapper",
    "create_action_mapper",
]
