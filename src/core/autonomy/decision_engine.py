"""
DecisionEngine Implementation - FASE 5 UPGRADE
Implements performance-based agent selection using learning data
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from stable_baselines3 import PPO

try:
    from stable_baselines3 import PPO

    PPO_AVAILABLE = True
except Exception:
    PPO_AVAILABLE = False

import numpy as np

from src.core.ai.adaptive_learning_engine import AdaptiveLearningEngine
from src.core.collaboration.agent_mesh import AgentRegistry, RegisteredAgent, get_agent_registry
from src.core.learning.model_registry import ModelRegistryManager
from src.core.learning.state_builder import StateBuilder

logger = logging.getLogger(__name__)


class AgentNotFoundException(Exception):
    """
    Exception raised when no suitable agent is found for a task type
    zoals gespecificeerd in FASE 4 plan
    """

    def __init__(self, task_type: str, available_agents: list[str] | None = None) -> None:
        self.task_type = task_type
        self.available_agents = available_agents or []

        if self.available_agents:
            message = f"No agent found with capability '{task_type}'. Available agents: {', '.join(self.available_agents)}"
        else:
            message = (
                f"No agent found with capability '{task_type}'. No agents are currently registered."
            )

        super().__init__(message)


class DecisionEngine:
    """
    DecisionEngine klasse - FASE 5 UPGRADE

    FASE 5 SPECIFICATIE:
    Upgraded voor performance-based agent selection. Na het vinden van agents
    met de juiste capabilities, bevraagt de engine de AdaptiveLearningEngine
    om de agent met de hoogste succesratio te selecteren.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        learning_engine: AdaptiveLearningEngine | None = None,
        model_registry_manager: ModelRegistryManager | None = None,
    ) -> None:
        """
        Initialize DecisionEngine met dependencies

        Args:
            agent_registry: AgentRegistry voor agent discovery (optioneel, gebruikt factory)
            learning_engine: AdaptiveLearningEngine voor performance data (optioneel, gebruikt factory)
            model_registry_manager: ModelRegistryManager voor het laden van PPO modellen (optioneel, gebruikt factory)
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.agent_registry = agent_registry or get_agent_registry()
        self.learning_engine = learning_engine  # Will be lazily loaded
        self.model_registry_manager = model_registry_manager  # Dependency for model loading
        self.state_builder = StateBuilder()  # Instantiate StateBuilder
        self.ppo_model: Any | None = (  # TODO(TYPE): replace Any with concrete type
            None  # Placeholder for loaded PPO model  # TODO(TYPE): replace Any with concrete type
        )

        self.logger.info("DecisionEngine initialized for FASE 5 performance-based agent selection")

    async def _load_production_model(self) -> None:
        """
        Loads the latest production-ready PPO model from the ModelRegistryManager.
        """
        # Guard if PPO library is unavailable
        if not PPO_AVAILABLE:
            self.logger.warning("stable_baselines3 not installed; skipping PPO model load.")
            return
        if self.ppo_model is None and self.model_registry_manager:
            try:
                model_version = await self.model_registry_manager.get_production_model(
                    "ppo_decision_model"
                )
                if model_version is not None:
                    # Extract model path from MLflow model version source
                    model_path = model_version.source
                    self.ppo_model = PPO.load(
                        model_path  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                    )
                    self.logger.info(f"Successfully loaded production PPO model from {model_path}")
                else:
                    self.logger.warning("No production PPO model found in registry.")
            except Exception as e:
                self.logger.error(f"Failed to load production PPO model: {e}", exc_info=True)
        elif self.ppo_model:
            self.logger.debug("PPO model already loaded.")
        else:
            self.logger.warning("ModelRegistryManager not available, cannot load PPO model.")

    async def select_agent_for_task(
        self,
        task_type: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> RegisteredAgent:
        """
        FASE 5: Select agent for task based on PPO model prediction.

        Args:
            task_type: Type of task requiring agent capability.
            context: Additional context for state building.

        Returns:
            RegisteredAgent: Best performing agent with matching capability as predicted by PPO.

        Raises:
            AgentNotFoundException: If no suitable agent found or PPO model fails.
        """
        self.logger.info(f"Selecting agent for task type: {task_type} (PPO model-based)")

        # Step 1: Haal alle actieve agents op uit de AgentRegistry
        all_agents = self.agent_registry.get_all_agents()
        self.logger.debug(f"Found {len(all_agents)} total agents in registry")

        # Filter agents based on capabilities and availability
        suitable_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        available_agent_ids: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent in all_agents.values():
            available_agent_ids.append(agent.agent_id)

            if not agent.is_available():
                self.logger.debug(
                    f"Agent {agent.agent_id} is not available (status: {agent.status})"
                )
                continue

            if task_type in agent.capabilities:
                suitable_agents.append(agent)
                self.logger.debug(f"Agent {agent.agent_id} has capability '{task_type}'")

        if not suitable_agents:
            self.logger.warning(f"No suitable agent found for task type '{task_type}'")
            raise AgentNotFoundException(task_type, available_agent_ids)

        # Step 2: Load PPO model if not already loaded
        await self._load_production_model()

        if self.ppo_model is None:
            self.logger.warning("PPO model not loaded. Falling back to capability-based selection.")
            # Fallback: No PPO model, use first suitable agent
            selected_agent = suitable_agents[0]
            self.logger.info(
                f"Selected agent {selected_agent.agent_id} for task type '{task_type}' (fallback: no PPO model)"
            )
            return cast(RegisteredAgent, selected_agent)

        # Step 3: Build state vector for the current task
        current_time = datetime.now(timezone.utc)
        state_vector = self.state_builder.build_state_vector(
            tool_name=task_type, payload=context or {}, current_time=current_time
        )
        obs = np.array([state_vector], dtype=np.float32)  # PPO expects batch dimension

        # Step 4: Use PPO model to predict action (agent choice)
        try:
            # PPO model predicts an action (integer representing agent index)
            action, _states = self.ppo_model.predict(obs, deterministic=True)
            predicted_agent_index = action[0]  # Get the single action from the batch

            # Map predicted_agent_index to an actual agent from suitable_agents
            # This mapping needs to be consistent with how actions were defined during training.
            # For now, a simple mapping based on index.
            if predicted_agent_index < len(suitable_agents):
                selected_agent = suitable_agents[predicted_agent_index]
                self.logger.info(
                    f"PPO model selected agent {selected_agent.agent_id} for task type '{task_type}'"
                )
                return cast(RegisteredAgent, selected_agent)
            else:
                self.logger.warning(
                    f"PPO model predicted invalid agent index {predicted_agent_index}. Falling back."
                )
                selected_agent = suitable_agents[0]
                self.logger.info(
                    f"Selected agent {selected_agent.agent_id} for task type '{task_type}' (fallback: invalid PPO prediction)"
                )
                return cast(RegisteredAgent, selected_agent)

        except Exception as e:
            self.logger.error(
                f"Error during PPO model prediction: {e}. Falling back to capability-based selection.",
                exc_info=True,
            )
            selected_agent = suitable_agents[0]
            self.logger.info(
                f"Selected agent {selected_agent.agent_id} for task type '{task_type}' (fallback: PPO prediction error)"
            )
            return cast(RegisteredAgent, selected_agent)

    def get_agents_with_capability(self, capability: str) -> list[RegisteredAgent]:
        """
        Get all agents with specific capability

        Args:
            capability: Required capability

        Returns:
            list[RegisteredAgent]: All agents with the capability
        """
        all_agents = self.agent_registry.get_all_agents()
        return [
            agent
            for agent in all_agents.values()
            if capability in agent.capabilities and agent.is_available()
        ]

    def get_available_capabilities(self) -> list[str]:
        """
        Get all available capabilities in the system

        Returns:
            list[str]: Unique list of all capabilities from available agents
        """
        all_agents = self.agent_registry.get_all_agents()
        capabilities = set()

        for agent in all_agents.values():
            if agent.is_available():
                capabilities.update(agent.capabilities)

        return sorted(list(capabilities))

    def get_agent_selection_stats(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get statistics about agent selection capabilities

        Returns:
            dict: Statistics about agents and capabilities
        """
        all_agents = self.agent_registry.get_all_agents()
        available_agents = [agent for agent in all_agents.values() if agent.is_available()]

        capability_count: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent in available_agents:
            for capability in agent.capabilities:
                capability_count[capability] = capability_count.get(capability, 0) + 1

        return {
            "total_agents": len(all_agents),
            "available_agents": len(available_agents),
            "total_capabilities": len(capability_count),
            "capability_distribution": capability_count,
            "agents_by_id": [agent.agent_id for agent in available_agents],
        }


def create_decision_engine(
    agent_registry: AgentRegistry | None = None,
    learning_engine: AdaptiveLearningEngine | None = None,
) -> DecisionEngine:
    """
    Factory function voor DecisionEngine instantie

    Args:
        agent_registry: Optional AgentRegistry dependency
        learning_engine: Optional AdaptiveLearningEngine dependency

    Returns:
        DecisionEngine: Geconfigureerde DecisionEngine instantie
    """
    return DecisionEngine(agent_registry=agent_registry, learning_engine=learning_engine)
