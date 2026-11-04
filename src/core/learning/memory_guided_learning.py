#!/usr/bin/env python3
"""
M-MDP Memory-Guided Learning Implementation - Phase 2 Day 11-12
Integration between memory system and reinforcement learning
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from src.core.learning.experience_replay import Experience, ExperienceBuffer, ExperienceType
from src.core.learning.reward_systems import MultiLevelRewardSystem
from src.core.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


@dataclass
class LearningContext:
    """Context for memory-guided learning"""

    agent_id: str
    current_state: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    action_space: list[str]
    memory_retrieval_results: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    learning_objectives: list[str]
    context_embeddings: np.ndarray[Any, Any] | None = None  # TODO(TYPE): replace Any with concrete type


@dataclass
class LearningOutcome:
    """Result of memory-guided learning episode"""

    agent_id: str
    learning_episode_id: str
    reward_gained: float
    memory_updates: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    strategy_improvements: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    confidence_score: float
    execution_time: float
    timestamp: datetime


class MemoryGuidedLearningManager:
    """Manages memory-guided learning processes for M-MDP agents"""

    def __init__(
        self,
        memory_manager: MemoryManager,
        reward_system: MultiLevelRewardSystem,
        experience_buffer: ExperienceBuffer,
    ) -> None:
        self.memory_manager = memory_manager
        self.reward_system = reward_system
        self.experience_buffer = experience_buffer

        # Learning state tracking
        self.active_learning_episodes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.learning_history: deque[LearningOutcome] = deque(maxlen=1000)
        self.agent_learning_profiles: defaultdict[str, dict[str, float]] = defaultdict(
            lambda: {
                "learning_rate": 0.001,
                "memory_retention": 0.95,
                "exploration_factor": 0.1,
                "adaptation_speed": 0.8,
            }
        )

        # Performance metrics
        self.learning_metrics = {
            "total_learning_episodes": 0,
            "successful_adaptations": 0,
            "memory_integration_score": 0.0,
            "strategy_improvement_rate": 0.0,
        }

        logger.info("Memory-guided learning manager initialized")

    async def initiate_learning_episode(
        self, agent_id: str, learning_context: LearningContext
    ) -> str:
        """Initiate a new memory-guided learning episode"""
        try:
            episode_id = f"learning_{agent_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            # Retrieve relevant memories
            relevant_memories = await self._retrieve_learning_memories(learning_context)

            # Generate learning strategy based on memories
            learning_strategy = await self._generate_learning_strategy(
                learning_context, relevant_memories
            )

            # Create learning episode
            episode_data = {
                "episode_id": episode_id,
                "agent_id": agent_id,
                "context": learning_context,
                "relevant_memories": relevant_memories,
                "strategy": learning_strategy,
                "start_time": datetime.now(timezone.utc),
                "status": "active",
            }

            self.active_learning_episodes[episode_id] = episode_data
            self.learning_metrics["total_learning_episodes"] += 1

            logger.info(f"Learning episode {episode_id} initiated for agent {agent_id}")
            return episode_id

        except Exception as e:
            logger.error(f"Failed to initiate learning episode for {agent_id}: {e}")
            raise

    async def _retrieve_learning_memories(self, context: LearningContext) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Retrieve memories relevant to current learning context"""
        try:
            # Query memories based on current state and objectives
            memories = await self.memory_manager.query_memories(
                agent_id=context.agent_id,
                memory_types=["strategy", "experience", "learning"],
                query_vector=context.context_embeddings,
                top_k=10,
            )

            # Filter memories by relevance to learning objectives
            relevant_memories: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for memory in memories:
                relevance_score = self._calculate_memory_relevance(memory, context)
                if relevance_score > 0.6:  # Relevance threshold
                    memory["relevance_score"] = relevance_score
                    relevant_memories.append(memory)

            # Sort by relevance
            relevant_memories.sort(key=lambda x: x["relevance_score"], reverse=True)

            logger.debug(f"Retrieved {len(relevant_memories)} relevant memories for learning")
            return relevant_memories

        except Exception as e:
            logger.error(f"Failed to retrieve learning memories: {e}")
            return []

    def _calculate_memory_relevance(
        self, memory: dict[str, Any], context: LearningContext  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate relevance of memory to current learning context"""
        try:
            relevance_score = 0.0

            # Objective alignment
            memory_content = memory.get("content", {})
            for objective in context.learning_objectives:
                if objective.lower() in str(memory_content).lower():
                    relevance_score += 0.3

            # State similarity
            memory_state = memory_content.get("state", {})
            state_similarity = self._calculate_state_similarity(memory_state, context.current_state)
            relevance_score += state_similarity * 0.4

            # Importance score from memory
            importance = float(memory.get("importance_score", 0.0))
            relevance_score += (importance / 10.0) * 0.3  # Normalize importance

            return float(min(relevance_score, 1.0))

        except Exception as e:
            logger.error(f"Failed to calculate memory relevance: {e}")
            return 0.0

    def _calculate_state_similarity(self, state1: dict[str, Any], state2: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate similarity between two states"""
        try:
            if not state1 or not state2:
                return 0.0

            common_keys = set(state1.keys()) & set(state2.keys())
            if not common_keys:
                return 0.0

            similarities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for key in common_keys:
                val1, val2 = state1[key], state2[key]

                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    max_val = max(abs(val1), abs(val2), 1.0)
                    similarity = 1.0 - (abs(val1 - val2) / max_val)
                    similarities.append(similarity)
                elif isinstance(val1, str) and isinstance(val2, str):
                    similarity = 1.0 if val1 == val2 else 0.0
                    similarities.append(similarity)

            return float(float(np.mean(similarities)) if similarities else 0.0)

        except Exception as e:
            logger.error(f"Failed to calculate state similarity: {e}")
            return 0.0

    async def _generate_learning_strategy(
        self, context: LearningContext, memories: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate learning strategy based on context and retrieved memories"""
        try:
            strategy = {
                "exploration_rate": 0.1,
                "memory_weight": 0.3,
                "adaptation_speed": 0.5,
                "focus_areas": [],
                "learned_patterns": [],
            }

            # Analyze successful patterns from memories
            successful_memories = [m for m in memories if m.get("importance_score", 0) > 0.7]

            if successful_memories:
                # Extract common patterns
                patterns = self._extract_success_patterns(successful_memories)
                strategy["learned_patterns"] = patterns

                # Adjust exploration based on memory confidence
                memory_confidence = np.mean(
                    [m.get("importance_score", 0) for m in successful_memories]
                )
                strategy["exploration_rate"] = max(0.05, 0.2 - memory_confidence * 0.15)

            # Focus areas based on learning objectives
            strategy["focus_areas"] = context.learning_objectives[:3]  # Top 3 objectives

            # Adaptive parameters based on agent profile
            agent_profile = self.agent_learning_profiles[context.agent_id]
            strategy["adaptation_speed"] = agent_profile["adaptation_speed"]

            return strategy

        except Exception as e:
            logger.error(f"Failed to generate learning strategy: {e}")
            return {"exploration_rate": 0.1, "focus_areas": []}

    def _extract_success_patterns(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Extract successful patterns from memory data"""
        try:
            patterns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Group memories by similarity
            memory_groups = self._group_similar_memories(memories)

            for group in memory_groups:
                if len(group) >= 2:  # Need multiple instances for pattern
                    pattern = self._identify_common_pattern(group)
                    if pattern:
                        patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error(f"Failed to extract success patterns: {e}")
            return []

    def _group_similar_memories(self, memories: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Group memories by similarity"""
        try:
            groups: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            used_indices = set()

            for i, memory1 in enumerate(memories):
                if i in used_indices:
                    continue

                group = [memory1]
                used_indices.add(i)

                for j, memory2 in enumerate(memories[i + 1 :], i + 1):
                    if j in used_indices:
                        continue

                    similarity = self._calculate_memory_similarity(memory1, memory2)
                    if similarity > 0.7:
                        group.append(memory2)
                        used_indices.add(j)

                if len(group) > 1:
                    groups.append(group)

            return groups

        except Exception as e:
            logger.error(f"Failed to group similar memories: {e}")
            return []

    def _calculate_memory_similarity(
        self, memory1: dict[str, Any], memory2: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate similarity between two memories"""
        try:
            content1 = memory1.get("content", {})
            content2 = memory2.get("content", {})

            # State similarity
            state_sim = self._calculate_state_similarity(
                content1.get("state", {}), content2.get("state", {})
            )

            # Action similarity
            action_sim = 1.0 if content1.get("action") == content2.get("action") else 0.0

            # Context similarity
            context_sim = self._calculate_state_similarity(
                content1.get("context", {}), content2.get("context", {})
            )

            return state_sim * 0.4 + action_sim * 0.3 + context_sim * 0.3

        except Exception as e:
            logger.error(f"Failed to calculate memory similarity: {e}")
            return 0.0

    def _identify_common_pattern(
        self, memory_group: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Identify common pattern across a group of memories"""
        try:
            if not memory_group:
                return None

            # Find common elements across memories
            common_states: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            common_actions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for memory in memory_group:
                content = memory.get("content", {})

                # Aggregate common state elements
                state = content.get("state", {})
                for key, value in state.items():
                    if key not in common_states:
                        common_states[key] = []
                    common_states[key].append(value)

                # Aggregate common actions
                action = content.get("action")
                if action:
                    if action not in common_actions:
                        common_actions[action] = 0
                    common_actions[action] += 1

            # Build pattern from most common elements
            pattern = {
                "pattern_type": "success_sequence",
                "frequency": len(memory_group),
                "confidence": np.mean([m.get("importance_score", 0) for m in memory_group]),
                "common_state_elements": {},
                "most_common_action": (
                    max(common_actions.items(), key=lambda x: x[1])[0] if common_actions else None
                ),
            }

            # Include state elements that appear in most memories
            for key, values in common_states.items():
                if len(set(values)) <= 2:  # Low variance indicates pattern
                    pattern["common_state_elements"][key] = max(set(values), key=values.count)

            return pattern if pattern["most_common_action"] else None

        except Exception as e:
            logger.error(f"Failed to identify common pattern: {e}")
            return None

    async def execute_learning_step(
        self, episode_id: str, action_taken: dict[str, Any], outcome: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Execute a learning step within an episode"""
        try:
            if episode_id not in self.active_learning_episodes:
                logger.warning(f"Learning episode {episode_id} not found")
                return False

            episode = self.active_learning_episodes[episode_id]
            context = episode["context"]

            # Calculate reward for this step
            reward_calculation = self.reward_system.calculate_comprehensive_reward(
                agent_id=context.agent_id,
                performance_data=outcome,
                context={"learning_episode": True, "episode_id": episode_id},
            )

            # Create experience for replay buffer
            experience = Experience(
                experience_id=f"{episode_id}_step_{datetime.now(timezone.utc).strftime('%H%M%S')}",
                agent_id=context.agent_id,
                experience_type=ExperienceType.LEARNING_EPISODE,
                state=context.current_state,
                action=action_taken,
                reward=reward_calculation.total_reward,
                next_state=outcome.get("resulting_state", {}),
                done=outcome.get("episode_complete", False),
                timestamp=datetime.now(timezone.utc),
                importance_score=reward_calculation.confidence_score,
                memory_context={
                    "episode_id": episode_id,
                    "learning_strategy": episode["strategy"],
                    "memory_guided": True,
                },
            )

            # Store experience
            await self.experience_buffer.add_experience(experience)

            # Update episode with step results
            if "steps" not in episode:
                episode["steps"] = []

            episode["steps"].append(
                {
                    "action": action_taken,
                    "outcome": outcome,
                    "reward": reward_calculation.total_reward,
                    "timestamp": datetime.now(timezone.utc),
                }
            )

            logger.debug(f"Learning step executed for episode {episode_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to execute learning step: {e}")
            return False

    async def complete_learning_episode(self, episode_id: str) -> LearningOutcome:
        """Complete a learning episode and extract outcomes"""
        try:
            if episode_id not in self.active_learning_episodes:
                raise ValueError(f"Learning episode {episode_id} not found")

            episode = self.active_learning_episodes[episode_id]
            context = episode["context"]

            # Calculate total reward and performance
            total_reward = sum(step["reward"] for step in episode.get("steps", []))
            execution_time = (datetime.now(timezone.utc) - episode["start_time"]).total_seconds()

            # Generate memory updates based on learning
            memory_updates = await self._generate_memory_updates(episode)

            # Identify strategy improvements
            strategy_improvements = await self._identify_strategy_improvements(episode)

            # Calculate confidence score
            confidence_score = self._calculate_learning_confidence(episode)

            # Create learning outcome
            outcome = LearningOutcome(
                agent_id=context.agent_id,
                learning_episode_id=episode_id,
                reward_gained=total_reward,
                memory_updates=memory_updates,
                strategy_improvements=strategy_improvements,
                confidence_score=confidence_score,
                execution_time=execution_time,
                timestamp=datetime.now(timezone.utc),
            )

            # Store learning outcome in memory
            await self._store_learning_outcome(outcome)

            # Update agent learning profile
            await self._update_agent_learning_profile(context.agent_id, outcome)

            # Clean up active episode
            del self.active_learning_episodes[episode_id]
            self.learning_history.append(outcome)

            # Update metrics
            if total_reward > 0:
                self.learning_metrics["successful_adaptations"] += 1

            logger.info(f"Learning episode {episode_id} completed with reward {total_reward:.2f}")
            return outcome

        except Exception as e:
            logger.error(f"Failed to complete learning episode {episode_id}: {e}")
            raise

    async def _generate_memory_updates(self, episode: dict[str, Any]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Generate memory updates based on learning episode"""
        try:
            updates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Extract successful patterns
            successful_steps = [step for step in episode.get("steps", []) if step["reward"] > 0]

            for step in successful_steps:
                update = {
                    "memory_type": "learning_pattern",
                    "content": {
                        "action": step["action"],
                        "outcome": step["outcome"],
                        "reward": step["reward"],
                        "context": episode["context"].current_state,
                    },
                    "importance_score": min(step["reward"] / 100.0, 1.0),
                    "metadata": {
                        "episode_id": episode["episode_id"],
                        "learning_type": "reinforcement",
                        "verified": True,
                    },
                }
                updates.append(update)

            return updates

        except Exception as e:
            logger.error(f"Failed to generate memory updates: {e}")
            return []

    async def _identify_strategy_improvements(self, episode: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Identify strategy improvements from episode results"""
        try:
            improvements: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "exploration_adjustments": {},
                "focus_area_updates": [],
                "learned_optimizations": [],
            }

            steps = episode.get("steps", [])
            if not steps:
                return improvements

            # Analyze reward patterns
            rewards = [step["reward"] for step in steps]
            avg_reward = np.mean(rewards)

            if avg_reward > 50:  # Successful episode
                # Reduce exploration for successful strategies
                current_strategy = episode.get("strategy", {})
                current_exploration = current_strategy.get("exploration_rate", 0.1)
                improvements["exploration_adjustments"]["exploration_rate"] = max(
                    0.05, current_exploration * 0.9
                )

                # Identify successful action patterns
                successful_actions = [
                    step["action"] for step in steps if step["reward"] > avg_reward
                ]
                if successful_actions:
                    improvements["learned_optimizations"] = list(
                        {str(action) for action in successful_actions}
                    )

            else:  # Less successful episode
                # Increase exploration
                current_strategy = episode.get("strategy", {})
                current_exploration = current_strategy.get("exploration_rate", 0.1)
                improvements["exploration_adjustments"]["exploration_rate"] = min(
                    0.3, current_exploration * 1.1
                )

            return improvements

        except Exception as e:
            logger.error(f"Failed to identify strategy improvements: {e}")
            return {}

    def _calculate_learning_confidence(self, episode: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate confidence score for learning episode"""
        try:
            steps = episode.get("steps", [])
            if not steps:
                return 0.0

            # Factor 1: Reward consistency
            rewards = [step["reward"] for step in steps]
            reward_std = np.std(rewards)
            consistency_score = max(0, 1.0 - (reward_std / 50.0))

            # Factor 2: Number of steps (more data = higher confidence)
            sample_score = min(1.0, len(steps) / 10.0)

            # Factor 3: Strategy alignment
            strategy_score = 1.0 if episode.get("strategy") else 0.5

            confidence = (
                float(consistency_score) * 0.4
                + float(sample_score) * 0.3
                + float(strategy_score) * 0.3
            )
            return float(confidence)

        except Exception as e:
            logger.error(f"Failed to calculate learning confidence: {e}")
            return 0.0

    async def _store_learning_outcome(self, outcome: LearningOutcome) -> None:
        """Store learning outcome in memory system"""
        try:
            memory_content = {
                "learning_episode_id": outcome.learning_episode_id,
                "reward_gained": outcome.reward_gained,
                "strategy_improvements": outcome.strategy_improvements,
                "confidence_score": outcome.confidence_score,
                "execution_time": outcome.execution_time,
            }

            await self.memory_manager.store_memory(
                agent_id=outcome.agent_id,
                memory_type="learning_outcome",
                content=memory_content,
                importance_score=outcome.confidence_score,
            )

        except Exception as e:
            logger.error(f"Failed to store learning outcome: {e}")

    async def _update_agent_learning_profile(self, agent_id: str, outcome: LearningOutcome) -> None:
        """Update agent learning profile based on outcome"""
        try:
            profile = self.agent_learning_profiles[agent_id]

            # Update learning rate based on success
            if outcome.reward_gained > 0:
                profile["learning_rate"] = min(0.01, profile["learning_rate"] * 1.05)
            else:
                profile["learning_rate"] = max(0.0001, profile["learning_rate"] * 0.95)

            # Update adaptation speed based on confidence
            profile["adaptation_speed"] = (
                profile["adaptation_speed"] * 0.9 + outcome.confidence_score * 0.1
            )

            # Update memory retention based on strategy improvements
            if outcome.strategy_improvements:
                profile["memory_retention"] = min(0.99, profile["memory_retention"] + 0.01)

            logger.debug(f"Updated learning profile for agent {agent_id}")

        except Exception as e:
            logger.error(f"Failed to update agent learning profile: {e}")

    def get_learning_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get learning system statistics"""
        try:
            recent_outcomes = list(self.learning_history)[-50:] if self.learning_history else []

            stats = {
                "total_episodes": self.learning_metrics["total_learning_episodes"],
                "active_episodes": len(self.active_learning_episodes),
                "successful_adaptations": self.learning_metrics["successful_adaptations"],
                "success_rate": (
                    self.learning_metrics["successful_adaptations"]
                    / max(self.learning_metrics["total_learning_episodes"], 1)
                ),
                "average_confidence": (
                    np.mean([o.confidence_score for o in recent_outcomes])
                    if recent_outcomes
                    else 0.0
                ),
                "average_reward": (
                    np.mean([o.reward_gained for o in recent_outcomes]) if recent_outcomes else 0.0
                ),
                "registered_agents": len(self.agent_learning_profiles),
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get learning statistics: {e}")
            return {}
