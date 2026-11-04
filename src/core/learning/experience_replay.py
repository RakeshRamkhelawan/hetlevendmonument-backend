#!/usr/bin/env python3
"""
M-MDP Experience Replay Implementation - Phase 2 Day 8-10
Experience buffer and prioritized sampling for memory-guided learning
"""

from __future__ import annotations

import json
import logging
import random
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, cast

import numpy as np
import numpy.typing as npt
import redis.asyncio as redis

from src.core.database.redis import ensure_async

logger = logging.getLogger(__name__)


class ExperienceType(Enum):
    """Types of experiences stored in replay buffer"""

    TASK_EXECUTION = "task_execution"
    COMMUNICATION = "communication"
    STRATEGIC_DECISION = "strategic_decision"
    LEARNING_EPISODE = "learning_episode"
    COLLABORATION = "collaboration"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class Experience:
    """Individual experience record"""

    experience_id: str
    agent_id: str
    experience_type: ExperienceType
    state: dict[str, object]
    action: dict[str, object]
    reward: float
    next_state: dict[str, object]
    done: bool
    timestamp: datetime
    importance_score: float = 0.0
    memory_context: dict[str, object] | None = None
    metadata: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert experience to dictionary for storage"""
        return {
            **asdict(self),
            "timestamp": self.timestamp.isoformat(),
            "experience_type": self.experience_type.value,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> Experience:
        """Create experience from dictionary"""
        return cls(
            experience_id=cast(str, data["experience_id"]),
            agent_id=cast(str, data["agent_id"]),
            experience_type=ExperienceType(cast(str, data["experience_type"])),
            state=cast(dict[str, object], data["state"]),
            action=cast(dict[str, object], data["action"]),
            reward=float(cast(float, data["reward"])),
            next_state=cast(dict[str, object], data["next_state"]),
            done=bool(cast(bool, data["done"])),
            timestamp=datetime.fromisoformat(cast(str, data["timestamp"])),
            importance_score=float(cast(float, data.get("importance_score", 0.0))),
            memory_context=cast(dict[str, object] | None, data.get("memory_context")),
            metadata=cast(dict[str, object] | None, data.get("metadata")),
        )


class ExperienceBuffer:
    """Basic experience buffer for storing agent experiences"""

    def __init__(
        self,
        capacity: int = 100000,
        agent_id: str = "default",
        redis_client: redis.Redis | None = None,  # type: ignore[type-arg]
    ) -> None:
        self.capacity = capacity
        self.agent_id = agent_id
        self.redis_client = redis_client

        # In-memory buffer
        self.buffer: deque[Experience] = deque(maxlen=capacity)
        self.experience_index: dict[str, int] = {}  # experience_id -> position mapping

        # Statistics
        self.total_experiences: int = 0
        self.experiences_by_type: dict[ExperienceType, int] = {
            exp_type: 0 for exp_type in ExperienceType
        }

        logger.info(f"Experience buffer initialized for agent {agent_id} with capacity {capacity}")

    async def add_experience(self, experience: Experience) -> bool:
        """Add experience to buffer"""
        try:
            # Add to in-memory buffer
            self.buffer.append(experience)
            self.experience_index[experience.experience_id] = len(self.buffer) - 1

            # Update statistics
            self.total_experiences += 1
            self.experiences_by_type[experience.experience_type] += 1

            # Persist to Redis if available
            if self.redis_client:
                await self._persist_experience(experience)

            logger.debug(f"Added experience {experience.experience_id} to buffer")
            return True

        except Exception as e:
            logger.error(f"Failed to add experience: {e}")
            return False

    async def sample_experiences(
        self, batch_size: int, experience_types: list[ExperienceType] | None = None
    ) -> list[Experience]:
        """Sample random experiences from buffer"""
        try:
            if not self.buffer:
                return []

            # Filter by experience types if specified
            available_experiences = list(self.buffer)
            if experience_types:
                available_experiences = [
                    exp for exp in available_experiences if exp.experience_type in experience_types
                ]

            if not available_experiences:
                return []

            # Sample random experiences
            sample_size = min(batch_size, len(available_experiences))
            sampled = random.sample(available_experiences, sample_size)

            logger.debug(f"Sampled {len(sampled)} experiences from buffer")
            return sampled

        except Exception as e:
            logger.error(f"Failed to sample experiences: {e}")
            return []

    async def get_experience_by_id(self, experience_id: str) -> Experience | None:
        """Retrieve specific experience by ID"""
        try:
            # Check in-memory buffer first
            for experience in self.buffer:
                if experience.experience_id == experience_id:
                    return experience

            # Check Redis if available
            if self.redis_client:
                return await self._retrieve_experience_from_redis(experience_id)

            return None

        except Exception as e:
            logger.error(f"Failed to retrieve experience {experience_id}: {e}")
            return None

    async def get_recent_experiences(
        self, count: int = 10, experience_type: ExperienceType | None = None
    ) -> list[Experience]:
        """Get most recent experiences"""
        try:
            experiences = list(self.buffer)

            # Filter by type if specified
            if experience_type:
                experiences = [exp for exp in experiences if exp.experience_type == experience_type]

            # Sort by timestamp (most recent first) and take count
            experiences.sort(key=lambda x: x.timestamp, reverse=True)
            return experiences[:count]

        except Exception as e:
            logger.error(f"Failed to get recent experiences: {e}")
            return []

    async def _persist_experience(self, experience: Experience) -> None:
        """Persist experience to Redis"""
        try:
            if not self.redis_client:
                return

            key = f"experience:{self.agent_id}:{experience.experience_id}"
            value = json.dumps(experience.to_dict())

            # Store with expiration (30 days)
            await ensure_async(self.redis_client.setex(key, 2592000, value))  # type: ignore[arg-type]

            # Add to agent's experience list
            list_key = f"agent_experiences:{self.agent_id}"
            await ensure_async(
                self.redis_client.lpush(list_key, experience.experience_id)  # type: ignore[arg-type]
            )
            # Keep only recent experiences
            await ensure_async(
                self.redis_client.ltrim(list_key, 0, self.capacity - 1)  # type: ignore[arg-type]
            )

        except Exception as e:
            logger.error(f"Failed to persist experience to Redis: {e}")

    async def _retrieve_experience_from_redis(self, experience_id: str) -> Experience | None:
        """Retrieve experience from Redis"""
        try:
            if not self.redis_client:
                return None

            key = f"experience:{self.agent_id}:{experience_id}"
            data = await self.redis_client.get(key)

            if data:
                experience_dict = json.loads(data)
                return Experience.from_dict(experience_dict)

            return None

        except Exception as e:
            logger.error(f"Failed to retrieve experience from Redis: {e}")
            return None

    def get_buffer_stats(self) -> dict[str, object]:
        """Get buffer statistics"""
        return {
            "total_experiences": self.total_experiences,
            "current_buffer_size": len(self.buffer),
            "capacity": self.capacity,
            "utilization": len(self.buffer) / self.capacity,
            "experiences_by_type": dict(self.experiences_by_type),
            "oldest_experience": self.buffer[0].timestamp.isoformat() if self.buffer else None,
            "newest_experience": self.buffer[-1].timestamp.isoformat() if self.buffer else None,
        }


class PrioritizedExperienceReplay:
    """Prioritized experience replay for importance-based sampling"""

    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
        agent_id: str = "default",
    ) -> None:
        self.capacity = capacity
        self.alpha = alpha  # Priority exponent
        self.beta = beta  # Importance sampling exponent
        self.beta_increment = beta_increment
        self.agent_id = agent_id

        # Priority storage
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.experiences: list[Experience | None] = [None] * capacity
        self.position = 0
        self.size = 0

        # Sum tree for efficient sampling
        self._sum_tree = np.zeros(2 * capacity - 1, dtype=np.float32)
        self._min_tree = np.full(2 * capacity - 1, float("inf"), dtype=np.float32)

        logger.info(f"Prioritized experience replay initialized for agent {agent_id}")

    def add_experience(self, experience: Experience, priority: float | None = None) -> None:
        """Add experience with priority"""
        try:
            # Calculate priority if not provided
            if priority is None:
                priority = self._calculate_initial_priority(experience)

            # Store experience
            self.experiences[self.position] = experience
            self.priorities[self.position] = priority

            # Update trees
            self._update_trees(self.position, priority)

            # Update position and size
            self.position = (self.position + 1) % self.capacity
            self.size = min(self.size + 1, self.capacity)

            logger.debug(
                f"Added prioritized experience {experience.experience_id} with priority {priority:.4f}"
            )

        except Exception as e:
            logger.error(f"Failed to add prioritized experience: {e}")

    def sample_batch(self, batch_size: int) -> tuple[
        list[Experience],
        npt.NDArray[np.int64],
        npt.NDArray[np.float32],
    ]:
        """Sample batch of experiences with importance weights"""
        try:
            if self.size == 0:
                return [], np.array([], dtype=np.int64), np.array([], dtype=np.float32)

            # Sample indices based on priorities
            indices = self._sample_proportional(batch_size)

            # Get experiences
            experiences = [self.experiences[idx] for idx in indices]

            # Calculate importance sampling weights
            weights = self._calculate_importance_weights(indices)

            # Increment beta
            self.beta = min(1.0, self.beta + self.beta_increment)

            logger.debug(f"Sampled prioritized batch of size {len(experiences)}")
            return experiences, indices, weights

        except Exception as e:
            logger.error(f"Failed to sample prioritized batch: {e}")
            return [], np.array([], dtype=np.int64), np.array([], dtype=np.float32)

    def update_priorities(
        self,
        indices: npt.NDArray[np.int64],
        priorities: npt.NDArray[np.float32],
    ) -> None:
        """Update priorities for experiences"""
        try:
            for idx, priority in zip(indices, priorities):
                if 0 <= idx < self.size:
                    self.priorities[idx] = priority
                    self._update_trees(idx, priority)

            logger.debug(f"Updated priorities for {len(indices)} experiences")

        except Exception as e:
            logger.error(f"Failed to update priorities: {e}")

    def _calculate_initial_priority(self, experience: Experience) -> float:
        """Calculate initial priority for new experience"""
        base_priority = abs(experience.reward) + 0.01  # Small epsilon to avoid zero priority

        # Boost priority based on experience type
        type_multipliers = {
            ExperienceType.ERROR_RECOVERY: 2.0,
            ExperienceType.STRATEGIC_DECISION: 1.5,
            ExperienceType.COLLABORATION: 1.3,
            ExperienceType.TASK_EXECUTION: 1.0,
            ExperienceType.COMMUNICATION: 0.8,
            ExperienceType.LEARNING_EPISODE: 1.2,
        }

        multiplier = type_multipliers.get(experience.experience_type, 1.0)

        # Apply importance score if available
        if experience.importance_score > 0:
            multiplier *= 1.0 + experience.importance_score

        return base_priority * multiplier

    def _sample_proportional(self, batch_size: int) -> npt.NDArray[np.int64]:
        """Sample indices proportional to priorities"""
        indices: list[int] = []
        segment_size = self._sum_tree[0] / batch_size

        for i in range(batch_size):
            a = segment_size * i
            b = segment_size * (i + 1)
            value = random.uniform(a, b)
            idx = self._retrieve_sample_index(value)
            indices.append(idx)

        return cast("npt.NDArray[np.int64]", np.array(indices, dtype=np.int64))

    def _retrieve_sample_index(self, value: float) -> int:
        """Retrieve sample index from sum tree"""
        idx = 0
        while idx < self.capacity - 1:
            left_child = 2 * idx + 1
            right_child = 2 * idx + 2

            if value <= self._sum_tree[left_child]:
                idx = left_child
            else:
                value -= self._sum_tree[left_child]
                idx = right_child

        return idx - (self.capacity - 1)

    def _calculate_importance_weights(
        self,
        indices: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.float32]:
        """Calculate importance sampling weights"""
        if self.size == 0:
            return np.array([], dtype=np.float32)

        # Calculate probabilities
        priorities = self.priorities[indices]
        probs = priorities / self._sum_tree[0]

        # Calculate weights
        weights = (self.size * probs) ** (-self.beta)
        weights = weights / weights.max()  # Normalize

        return cast("npt.NDArray[np.float32]", weights)

    def _update_trees(self, idx: int, priority: float) -> None:
        """Update sum and min trees"""
        # Update sum tree
        tree_idx = idx + self.capacity - 1
        change = priority - self._sum_tree[tree_idx]
        self._sum_tree[tree_idx] = priority

        while tree_idx != 0:
            tree_idx = (tree_idx - 1) // 2
            self._sum_tree[tree_idx] += change

        # Update min tree
        tree_idx = idx + self.capacity - 1
        self._min_tree[tree_idx] = priority

        while tree_idx != 0:
            tree_idx = (tree_idx - 1) // 2
            left_child = 2 * tree_idx + 1
            right_child = 2 * tree_idx + 2
            self._min_tree[tree_idx] = min(self._min_tree[left_child], self._min_tree[right_child])

    def get_max_priority(self) -> float:
        """Get maximum priority in buffer"""
        if self.size == 0:
            return 1.0
        return float(np.max(self.priorities[: self.size]))

    def get_stats(self) -> dict[str, object]:
        """Get prioritized replay statistics"""
        if self.size == 0:
            return {}

        active_priorities = self.priorities[: self.size]

        return {
            "size": self.size,
            "capacity": self.capacity,
            "alpha": self.alpha,
            "beta": self.beta,
            "mean_priority": np.mean(active_priorities),
            "max_priority": np.max(active_priorities),
            "min_priority": np.min(active_priorities),
            "priority_std": np.std(active_priorities),
        }


class MemoryGuidedSampling:
    """Memory-guided experience sampling using memory context"""

    def __init__(
        self,
        experience_buffer: ExperienceBuffer,
        memory_manager: object,
        similarity_threshold: float = 0.7,
    ) -> None:
        self.experience_buffer = experience_buffer
        self.memory_manager = memory_manager
        self.similarity_threshold = similarity_threshold

        # Context tracking
        self.context_embeddings: dict[str, object] = {}
        self.sampling_history: deque[str] = deque(maxlen=1000)

        logger.info("Memory-guided sampling initialized")

    async def sample_relevant_experiences(
        self,
        current_context: dict[str, object],
        batch_size: int,
        experience_types: list[ExperienceType] | None = None,
    ) -> list[Experience]:
        """Sample experiences relevant to current context"""
        try:
            # Get base sample from buffer
            candidate_experiences = await self.experience_buffer.sample_experiences(
                batch_size * 3,
                experience_types,  # Get larger pool for filtering
            )

            if not candidate_experiences:
                return []

            # Calculate relevance scores
            relevance_scores: list[tuple[Experience, float]] = []
            for experience in candidate_experiences:
                score = await self._calculate_relevance_score(experience, current_context)
                relevance_scores.append((experience, score))

            # Sort by relevance and take top batch_size
            relevance_scores.sort(key=lambda x: x[1], reverse=True)
            selected_experiences = [exp for exp, score in relevance_scores[:batch_size]]

            # Update sampling history
            self.sampling_history.extend([exp.experience_id for exp in selected_experiences])

            logger.debug(f"Selected {len(selected_experiences)} memory-guided experiences")
            return selected_experiences

        except Exception as e:
            logger.error(f"Memory-guided sampling failed: {e}")
            return await self.experience_buffer.sample_experiences(batch_size, experience_types)

    async def _calculate_relevance_score(
        self,
        experience: Experience,
        current_context: dict[str, object],
    ) -> float:
        """Calculate relevance score between experience and current context"""
        try:
            relevance_score = 0.0

            # Context similarity
            context_similarity = self._calculate_context_similarity(
                experience.memory_context or {}, current_context
            )
            relevance_score += context_similarity * 0.4

            # State similarity
            current_state = cast(dict[str, object], current_context.get("current_state", {}))
            state_similarity = self._calculate_state_similarity(experience.state, current_state)
            relevance_score += state_similarity * 0.3

            # Reward magnitude (higher rewards more relevant)
            reward_factor = min(1.0, abs(experience.reward) / 100.0)
            relevance_score += reward_factor * 0.2

            # Recency factor (more recent experiences more relevant)
            time_diff = datetime.now(timezone.utc) - experience.timestamp
            recency_factor = max(
                0.1, 1.0 - (time_diff.total_seconds() / 86400)
            )  # Decay over 24 hours
            relevance_score += recency_factor * 0.1

            return relevance_score

        except Exception as e:
            logger.error(f"Failed to calculate relevance score: {e}")
            return 0.0

    def _calculate_context_similarity(
        self,
        context1: dict[str, object],
        context2: dict[str, object],
    ) -> float:
        """Calculate similarity between two contexts"""
        try:
            if not context1 or not context2:
                return 0.0

            # Find common keys
            common_keys = set(context1.keys()) & set(context2.keys())
            if not common_keys:
                return 0.0

            similarity_scores: list[float] = []
            for key in common_keys:
                val1, val2 = context1[key], context2[key]

                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    # Numerical similarity
                    max_val = max(abs(val1), abs(val2), 1.0)
                    similarity = 1.0 - (abs(val1 - val2) / max_val)
                    similarity_scores.append(similarity)
                elif isinstance(val1, str) and isinstance(val2, str):
                    # String similarity (simple)
                    similarity = 1.0 if val1 == val2 else 0.0
                    similarity_scores.append(similarity)

            return float(np.mean(similarity_scores)) if similarity_scores else 0.0

        except Exception as e:
            logger.error(f"Failed to calculate context similarity: {e}")
            return 0.0

    def _calculate_state_similarity(
        self,
        state1: dict[str, object],
        state2: dict[str, object],
    ) -> float:
        """Calculate similarity between two states"""
        try:
            if not state1 or not state2:
                return 0.0

            # Similar to context similarity but with state-specific logic
            return self._calculate_context_similarity(state1, state2)

        except Exception as e:
            logger.error(f"Failed to calculate state similarity: {e}")
            return 0.0

    async def get_similar_experiences(
        self,
        target_experience: Experience,
        similarity_threshold: float | None = None,
    ) -> list[Experience]:
        """Find experiences similar to target experience"""
        try:
            threshold = similarity_threshold or self.similarity_threshold

            # Get all experiences from buffer
            all_experiences = list(self.experience_buffer.buffer)
            similar_experiences: list[tuple[Experience, float]] = []

            for experience in all_experiences:
                if experience.experience_id == target_experience.experience_id:
                    continue

                # Calculate similarity
                similarity = await self._calculate_experience_similarity(
                    target_experience, experience
                )

                if similarity >= threshold:
                    similar_experiences.append((experience, similarity))

            # Sort by similarity
            similar_experiences.sort(key=lambda x: x[1], reverse=True)

            return [exp for exp, sim in similar_experiences]

        except Exception as e:
            logger.error(f"Failed to find similar experiences: {e}")
            return []

    async def _calculate_experience_similarity(self, exp1: Experience, exp2: Experience) -> float:
        """Calculate similarity between two experiences"""
        try:
            similarity_score = 0.0

            # Type similarity
            type_similarity = 1.0 if exp1.experience_type == exp2.experience_type else 0.0
            similarity_score += type_similarity * 0.3

            # State similarity
            state_similarity = self._calculate_state_similarity(exp1.state, exp2.state)
            similarity_score += state_similarity * 0.3

            # Action similarity
            action_similarity = self._calculate_context_similarity(exp1.action, exp2.action)
            similarity_score += action_similarity * 0.2

            # Reward similarity
            reward_diff = abs(exp1.reward - exp2.reward)
            max_reward = max(abs(exp1.reward), abs(exp2.reward), 1.0)
            reward_similarity = 1.0 - (reward_diff / max_reward)
            similarity_score += reward_similarity * 0.2

            return similarity_score

        except Exception as e:
            logger.error(f"Failed to calculate experience similarity: {e}")
            return 0.0

    def get_sampling_stats(self) -> dict[str, object]:
        """Get memory-guided sampling statistics"""
        return {
            "total_samples": len(self.sampling_history),
            "unique_experiences": len(set(self.sampling_history)),
            "similarity_threshold": self.similarity_threshold,
            "cache_size": len(self.context_embeddings),
            "recent_sampling_diversity": (
                len(set(list(self.sampling_history)[-100:])) / min(100, len(self.sampling_history))
                if self.sampling_history
                else 0.0
            ),
        }
