#!/usr/bin/env python3
"""
M-MDP Reward Systems Implementation - Phase 2 Day 8-10
Multi-level reward calculation for agent performance optimization
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast

import numpy as np

logger = logging.getLogger(__name__)


class RewardType(Enum):
    """Types of rewards in the M-MDP system"""

    TASK_COMPLETION = "task_completion"
    COMMUNICATION_EFFICIENCY = "communication_efficiency"
    MEMORY_UTILIZATION = "memory_utilization"
    STRATEGIC_ALIGNMENT = "strategic_alignment"
    LEARNING_PROGRESS = "learning_progress"
    COLLABORATION_QUALITY = "collaboration_quality"
    RESOURCE_EFFICIENCY = "resource_efficiency"


@dataclass
class RewardComponent:
    """Individual reward component"""

    reward_type: RewardType
    base_value: float
    weight: float
    time_decay: float = 1.0
    performance_multiplier: float = 1.0
    context_bonus: float = 0.0


@dataclass
class RewardCalculation:
    """Result of reward calculation"""

    total_reward: float
    component_rewards: dict[RewardType, float]
    bonus_rewards: dict[str, float]
    penalty_deductions: dict[str, float]
    calculation_timestamp: datetime
    confidence_score: float


class RewardCalculator:
    """Base reward calculator for individual reward components"""

    def __init__(
        self, reward_type: RewardType, base_config: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.reward_type = reward_type
        self.config = base_config or {}
        self.performance_history: deque[float] = deque(maxlen=100)
        self.calibration_data: dict[RewardType, list[dict[str, Any]]] = defaultdict(list)  # TODO(TYPE): replace Any with concrete type

    def calculate_reward(
        self,
        agent_performance: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for specific performance metrics"""
        try:
            context = context or {}

            # Base reward calculation based on type
            base_reward = self._calculate_base_reward(agent_performance, context)

            # Apply performance multipliers
            performance_multiplier = self._calculate_performance_multiplier(agent_performance)

            # Apply context bonuses
            context_bonus = self._calculate_context_bonus(context)

            # Apply time decay if applicable
            time_decay = self._calculate_time_decay(context.get("timestamp"))

            # Calculate final reward
            final_reward = base_reward * performance_multiplier * time_decay + context_bonus

            # Store for calibration
            self.performance_history.append(final_reward)
            self._update_calibration_data(agent_performance, final_reward)

            return final_reward

        except Exception as e:
            logger.error(f"Reward calculation failed for {self.reward_type.value}: {e}")
            return 0.0

    def _calculate_base_reward(self, performance: dict[str, Any], context: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate base reward based on reward type"""
        if self.reward_type == RewardType.TASK_COMPLETION:
            return self._task_completion_reward(performance, context)
        elif self.reward_type == RewardType.COMMUNICATION_EFFICIENCY:
            return self._communication_efficiency_reward(performance, context)
        elif self.reward_type == RewardType.MEMORY_UTILIZATION:
            return self._memory_utilization_reward(performance, context)
        elif self.reward_type == RewardType.STRATEGIC_ALIGNMENT:
            return self._strategic_alignment_reward(performance, context)
        elif self.reward_type == RewardType.LEARNING_PROGRESS:
            return self._learning_progress_reward(performance, context)
        elif self.reward_type == RewardType.COLLABORATION_QUALITY:
            return self._collaboration_quality_reward(performance, context)
        elif self.reward_type == RewardType.RESOURCE_EFFICIENCY:
            return self._resource_efficiency_reward(performance, context)
        else:
            return 0.0

    def _task_completion_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for task completion"""
        success_rate = performance.get("success_rate", 0.0)
        quality_score = performance.get("quality_score", 0.0)
        completion_time = performance.get("completion_time", float("inf"))
        expected_time = context.get("expected_completion_time", completion_time)

        # Base reward from success and quality
        base_reward = (success_rate * 0.6 + quality_score * 0.4) * 100

        # Time bonus for early completion
        if completion_time < expected_time:
            time_bonus = min(20, (expected_time - completion_time) / expected_time * 20)
            base_reward += time_bonus

        return float(base_reward)

    def _communication_efficiency_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for communication efficiency"""
        message_success_rate = performance.get("message_success_rate", 0.0)
        response_latency = performance.get("average_response_latency", 1.0)
        coordination_score = performance.get("coordination_effectiveness", 0.0)

        # Reward for successful communication
        comm_reward = message_success_rate * 50

        # Bonus for low latency (inverse relationship)
        latency_bonus = max(0, 25 - response_latency * 10)

        # Coordination effectiveness bonus
        coordination_bonus = coordination_score * 25

        return float(comm_reward + latency_bonus + coordination_bonus)

    def _memory_utilization_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for memory utilization"""
        memory_retrieval_accuracy = performance.get("memory_retrieval_accuracy", 0.0)
        memory_usage_efficiency = performance.get("memory_usage_efficiency", 0.0)
        context_relevance = performance.get("context_relevance_score", 0.0)

        # Reward accurate memory retrieval
        retrieval_reward = memory_retrieval_accuracy * 40

        # Reward efficient memory usage
        efficiency_reward = memory_usage_efficiency * 30

        # Bonus for contextually relevant memory usage
        relevance_bonus = context_relevance * 30

        return float(retrieval_reward + efficiency_reward + relevance_bonus)

    def _strategic_alignment_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for strategic alignment"""
        alignment_score = performance.get("strategic_alignment_score", 0.0)
        goal_achievement = performance.get("goal_achievement_rate", 0.0)
        priority_adherence = performance.get("priority_adherence_score", 0.0)

        # Primary reward from alignment
        alignment_reward = alignment_score * 60

        # Goal achievement bonus
        goal_bonus = goal_achievement * 25

        # Priority adherence bonus
        priority_bonus = priority_adherence * 15

        return float(alignment_reward + goal_bonus + priority_bonus)

    def _learning_progress_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for learning progress"""
        improvement_rate = performance.get("performance_improvement_rate", 0.0)
        adaptation_speed = performance.get("adaptation_speed", 0.0)
        knowledge_retention = performance.get("knowledge_retention_score", 0.0)

        # Reward continuous improvement
        improvement_reward = improvement_rate * 50

        # Bonus for fast adaptation
        adaptation_bonus = adaptation_speed * 30

        # Knowledge retention bonus
        retention_bonus = knowledge_retention * 20

        return float(improvement_reward + adaptation_bonus + retention_bonus)

    def _collaboration_quality_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for collaboration quality"""
        teamwork_score = performance.get("teamwork_effectiveness", 0.0)
        knowledge_sharing = performance.get("knowledge_sharing_rate", 0.0)
        conflict_resolution = performance.get("conflict_resolution_success", 0.0)

        # Primary collaboration reward
        collab_reward = teamwork_score * 40

        # Knowledge sharing bonus
        sharing_bonus = knowledge_sharing * 35

        # Conflict resolution bonus
        resolution_bonus = conflict_resolution * 25

        return float(collab_reward + sharing_bonus + resolution_bonus)

    def _resource_efficiency_reward(
        self, performance: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate reward for resource efficiency"""
        cpu_efficiency = performance.get("cpu_usage_efficiency", 0.0)
        memory_efficiency = performance.get("memory_usage_efficiency", 0.0)
        energy_efficiency = performance.get("energy_efficiency_score", 0.0)

        # Resource usage efficiency
        cpu_reward = (1.0 - cpu_efficiency) * 30  # Lower usage is better
        memory_reward = (1.0 - memory_efficiency) * 30
        energy_reward = energy_efficiency * 40

        return float(cpu_reward + memory_reward + energy_reward)

    def _calculate_performance_multiplier(self, performance: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate performance-based multiplier"""
        overall_performance: Any = performance.get("overall_performance_score", 0.5)  # TODO(TYPE): replace Any with concrete type

        # Scale multiplier between 0.5 and 2.0 based on performance
        multiplier = 0.5 + (cast(float, overall_performance) * 1.5)
        clipped: Any = np.clip(multiplier, 0.5, 2.0)  # TODO(TYPE): replace Any with concrete type
        return float(clipped)

    def _calculate_context_bonus(self, context: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate context-based bonus rewards"""
        bonus = 0.0

        # Urgency bonus
        if context.get("urgency_level") == "high":
            bonus += 10
        elif context.get("urgency_level") == "critical":
            bonus += 20

        # Complexity bonus
        complexity = context.get("task_complexity", 0.0)
        bonus += complexity * 15

        # Innovation bonus
        if context.get("innovation_required", False):
            bonus += 25

        return float(bonus)

    def _calculate_time_decay(self, timestamp: datetime | None) -> float:
        """Calculate time-based decay factor"""
        if not timestamp:
            return 1.0

        time_diff = datetime.now(timezone.utc) - timestamp
        hours_elapsed = time_diff.total_seconds() / 3600

        # Decay factor: rewards become less valuable over time
        decay_rate: Any = self.config.get("time_decay_rate", 0.1)  # TODO(TYPE): replace Any with concrete type
        decay_factor = np.exp(-cast(float, decay_rate) * hours_elapsed)
        clipped: Any = np.clip(decay_factor, 0.1, 1.0)  # TODO(TYPE): replace Any with concrete type

        return float(clipped)

    def _update_calibration_data(self, performance: dict[str, Any], reward: float) -> None:  # TODO(TYPE): replace Any with concrete type
        """Update calibration data for reward tuning"""
        performance_level = performance.get("overall_performance_score", 0.0)
        self.calibration_data[self.reward_type].append(
            {
                "performance": performance_level,
                "reward": reward,
                "timestamp": datetime.now(timezone.utc),
            }
        )

    def get_calibration_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get calibration statistics for reward tuning"""
        if not self.calibration_data[self.reward_type]:
            return {}

        data = self.calibration_data[self.reward_type]
        rewards: Any = [d["reward"] for d in data]  # TODO(TYPE): replace Any with concrete type
        performances: Any = [d["performance"] for d in data]  # TODO(TYPE): replace Any with concrete type

        mean_reward: Any = np.mean(rewards)  # TODO(TYPE): replace Any with concrete type
        std_reward: Any = np.std(rewards)  # TODO(TYPE): replace Any with concrete type
        mean_performance: Any = np.mean(performances)  # TODO(TYPE): replace Any with concrete type

        correlation: float = 0.0
        if len(rewards) > 1:
            corr_matrix: Any = np.corrcoef(performances, rewards)  # TODO(TYPE): replace Any with concrete type
            correlation = float(corr_matrix[0, 1])

        return {
            "mean_reward": float(mean_reward),
            "std_reward": float(std_reward),
            "mean_performance": float(mean_performance),
            "correlation": correlation,
            "sample_count": len(data),
        }


class MultiLevelRewardSystem:
    """Multi-level reward system combining different reward components"""

    def __init__(self, reward_weights: dict[RewardType, float] | None = None) -> None:
        self.reward_weights = reward_weights or self._default_reward_weights()
        self.reward_calculators: dict[RewardType, RewardCalculator] = {}
        self.system_performance_history: deque[float] = deque(maxlen=1000)
        self.agent_performance_profiles: defaultdict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Initialize individual reward calculators
        for reward_type in RewardType:
            self.reward_calculators[reward_type] = RewardCalculator(reward_type)

        logger.info("Multi-level reward system initialized")

    def _default_reward_weights(self) -> dict[RewardType, float]:
        """Default weights for different reward types"""
        return {
            RewardType.TASK_COMPLETION: 0.25,
            RewardType.COMMUNICATION_EFFICIENCY: 0.15,
            RewardType.MEMORY_UTILIZATION: 0.15,
            RewardType.STRATEGIC_ALIGNMENT: 0.20,
            RewardType.LEARNING_PROGRESS: 0.10,
            RewardType.COLLABORATION_QUALITY: 0.10,
            RewardType.RESOURCE_EFFICIENCY: 0.05,
        }

    def calculate_comprehensive_reward(
        self,
        agent_id: str,
        performance_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> RewardCalculation:
        """Calculate comprehensive reward using all components"""
        try:
            context = context or {}
            component_rewards: dict[RewardType, float] = {}
            bonus_rewards: dict[str, float] = {}
            penalty_deductions: dict[str, float] = {}

            # Calculate individual reward components
            for reward_type, weight in self.reward_weights.items():
                calculator = self.reward_calculators[reward_type]
                component_reward = calculator.calculate_reward(performance_data, context)
                weighted_reward = component_reward * weight

                component_rewards[reward_type] = weighted_reward

            # Calculate bonus rewards
            bonus_rewards = self._calculate_bonus_rewards(agent_id, performance_data, context)

            # Calculate penalty deductions
            penalty_deductions = self._calculate_penalty_deductions(performance_data, context)

            # Compute total reward
            base_total = sum(component_rewards.values())
            bonus_total = sum(bonus_rewards.values())
            penalty_total = sum(penalty_deductions.values())

            total_reward = base_total + bonus_total - penalty_total

            # Apply system-level modifiers
            total_reward = self._apply_system_modifiers(agent_id, total_reward, context)

            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(performance_data, context)

            # Store performance data
            self.system_performance_history.append(total_reward)
            self.agent_performance_profiles[agent_id].append(total_reward)

            result = RewardCalculation(
                total_reward=total_reward,
                component_rewards=component_rewards,
                bonus_rewards=bonus_rewards,
                penalty_deductions=penalty_deductions,
                calculation_timestamp=datetime.now(timezone.utc),
                confidence_score=confidence_score,
            )

            logger.debug(f"Comprehensive reward calculated for {agent_id}: {total_reward:.2f}")
            return result

        except Exception as e:
            logger.error(f"Comprehensive reward calculation failed for {agent_id}: {e}")
            return RewardCalculation(
                total_reward=0.0,
                component_rewards={},
                bonus_rewards={},
                penalty_deductions={},
                calculation_timestamp=datetime.now(timezone.utc),
                confidence_score=0.0,
            )

    def _calculate_bonus_rewards(
        self, agent_id: str, performance_data: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """Calculate bonus rewards for exceptional performance"""
        bonuses: dict[str, float] = {}

        # Consistency bonus
        agent_history: Any = list(self.agent_performance_profiles[agent_id])  # TODO(TYPE): replace Any with concrete type
        if len(agent_history) >= 10:
            recent_std: Any = np.std(agent_history[-10:])  # TODO(TYPE): replace Any with concrete type
            if cast(float, recent_std) < 5.0:  # Low variance indicates consistency
                bonuses["consistency_bonus"] = 15.0

        # Improvement bonus
        if len(agent_history) >= 5:
            recent_avg: Any = np.mean(agent_history[-3:])  # TODO(TYPE): replace Any with concrete type
            older_avg: Any = np.mean(agent_history[-6:-3])  # TODO(TYPE): replace Any with concrete type
            if cast(float, recent_avg) > cast(float, older_avg) * 1.1:  # 10% improvement
                bonuses["improvement_bonus"] = 20.0

        # Exceptional performance bonus
        if performance_data.get("overall_performance_score", 0.0) > 0.9:
            bonuses["exceptional_performance"] = 25.0

        # First-time achievement bonus
        if context.get("first_time_achievement", False):
            bonuses["first_time_bonus"] = 30.0

        return bonuses

    def _calculate_penalty_deductions(
        self, performance_data: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """Calculate penalty deductions for poor performance"""
        penalties: dict[str, float] = {}

        # Failure penalty
        failure_rate = 1.0 - performance_data.get("success_rate", 1.0)
        if failure_rate > 0.1:
            penalties["failure_penalty"] = failure_rate * 20

        # Timeout penalty
        if context.get("timeout_occurred", False):
            penalties["timeout_penalty"] = 15.0

        # Resource waste penalty
        resource_waste = performance_data.get("resource_waste_score", 0.0)
        if resource_waste > 0.3:
            penalties["resource_waste"] = resource_waste * 25

        # Communication failure penalty
        comm_failures = performance_data.get("communication_failures", 0)
        if comm_failures > 0:
            penalties["communication_failure"] = min(comm_failures * 5, 20)

        return penalties

    def _apply_system_modifiers(
        self, agent_id: str, base_reward: float, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Apply system-level modifiers to reward"""

        # System load modifier
        system_load = context.get("system_load", 0.5)
        load_modifier = 1.0 - (system_load - 0.5) * 0.2  # Reduce rewards during high load

        # Agent experience modifier
        agent_experience = context.get("agent_experience_level", 1.0)
        experience_modifier = 0.8 + (agent_experience * 0.4)  # Scale between 0.8 and 1.2

        # Time of day modifier (optional)
        current_hour = datetime.now(timezone.utc).hour
        if 9 <= current_hour <= 17:  # Business hours
            time_modifier = 1.1
        else:
            time_modifier = 0.9

        final_reward = base_reward * load_modifier * experience_modifier * time_modifier

        return float(final_reward)

    def _calculate_confidence_score(
        self, performance_data: dict[str, Any], context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate confidence score for reward calculation"""

        # Data completeness factor
        expected_fields = ["success_rate", "quality_score", "overall_performance_score"]
        present_fields = sum(1 for field in expected_fields if field in performance_data)
        completeness_factor = present_fields / len(expected_fields)

        # Sample size factor
        sample_size: Any = context.get("performance_sample_size", 1)  # TODO(TYPE): replace Any with concrete type
        sample_factor = min(1.0, cast(float, sample_size) / 10)  # Full confidence at 10+ samples

        # Recency factor
        timestamp = context.get("timestamp")
        if timestamp:
            time_diff = datetime.now(timezone.utc) - timestamp
            recency_factor = max(0.5, 1.0 - (time_diff.total_seconds() / 3600))  # Decay over 1 hour
        else:
            recency_factor = 0.8

        confidence = completeness_factor * sample_factor * recency_factor
        clipped: Any = np.clip(confidence, 0.0, 1.0)  # TODO(TYPE): replace Any with concrete type
        return float(clipped)

    def update_reward_weights(self, new_weights: dict[RewardType, float]) -> None:
        """Update reward weights for system tuning"""
        # Normalize weights to sum to 1.0
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            self.reward_weights = {k: v / total_weight for k, v in new_weights.items()}
            logger.info("Reward weights updated")

    def get_system_performance_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get system-wide performance statistics"""
        if not self.system_performance_history:
            return {}

        rewards: Any = list(self.system_performance_history)  # TODO(TYPE): replace Any with concrete type
        mean_reward: Any = np.mean(rewards)  # TODO(TYPE): replace Any with concrete type
        std_reward: Any = np.std(rewards)  # TODO(TYPE): replace Any with concrete type
        min_reward: Any = np.min(rewards)  # TODO(TYPE): replace Any with concrete type
        max_reward: Any = np.max(rewards)  # TODO(TYPE): replace Any with concrete type

        return {
            "mean_reward": float(mean_reward),
            "std_reward": float(std_reward),
            "min_reward": float(min_reward),
            "max_reward": float(max_reward),
            "total_evaluations": len(rewards),
            "recent_trend": self._calculate_trend(rewards[-20:]) if len(rewards) >= 20 else 0.0,
        }

    def _calculate_trend(self, values: list[float]) -> float:
        """Calculate trend in recent values"""
        if len(values) < 2:
            return 0.0

        x: Any = np.arange(len(values))  # TODO(TYPE): replace Any with concrete type
        coeffs: Any = np.polyfit(x, values, 1)  # TODO(TYPE): replace Any with concrete type
        return float(coeffs[0])


class AdaptiveRewardScaling:
    """Adaptive reward scaling based on agent performance distribution"""

    def __init__(self, target_mean: float = 50.0, target_std: float = 15.0) -> None:
        self.target_mean = target_mean
        self.target_std = target_std
        self.reward_history: deque[float] = deque(maxlen=1000)
        self.scaling_factor = 1.0
        self.bias_factor = 0.0

    def add_reward(self, reward: float) -> None:
        """Add reward to history for scaling calculation"""
        self.reward_history.append(reward)
        if len(self.reward_history) >= 50:  # Update scaling after sufficient data
            self._update_scaling_factors()

    def scale_reward(self, reward: float) -> float:
        """Scale reward using adaptive factors"""
        scaled_reward = (reward * self.scaling_factor) + self.bias_factor
        return float(scaled_reward)

    def _update_scaling_factors(self) -> None:
        """Update scaling factors based on reward distribution"""
        if len(self.reward_history) < 10:
            return

        rewards: Any = list(self.reward_history)  # TODO(TYPE): replace Any with concrete type
        current_mean: Any = np.mean(rewards)  # TODO(TYPE): replace Any with concrete type
        current_std: Any = np.std(rewards)  # TODO(TYPE): replace Any with concrete type

        # Update scaling factor to match target standard deviation
        if current_std > 0:
            self.scaling_factor = self.target_std / current_std
        else:
            self.scaling_factor = 1.0

        # Update bias factor to match target mean
        scaled_mean = current_mean * self.scaling_factor
        self.bias_factor = self.target_mean - scaled_mean

        logger.debug(
            f"Updated scaling factors: scale={self.scaling_factor:.3f}, bias={self.bias_factor:.3f}"
        )

    def get_scaling_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current scaling statistics"""
        if not self.reward_history:
            return {}

        rewards: Any = list(self.reward_history)  # TODO(TYPE): replace Any with concrete type
        current_mean: Any = np.mean(rewards)  # TODO(TYPE): replace Any with concrete type
        current_std: Any = np.std(rewards)  # TODO(TYPE): replace Any with concrete type

        return {
            "current_mean": float(current_mean),
            "current_std": float(current_std),
            "target_mean": self.target_mean,
            "target_std": self.target_std,
            "scaling_factor": self.scaling_factor,
            "bias_factor": self.bias_factor,
            "sample_count": len(rewards),
        }
