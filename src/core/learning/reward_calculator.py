from typing import Any


class RewardCalculator:
    """
    Calculates a numerical reward based on the outcome of a task execution.
    This reward is used to train the PPO Reinforcement Learning model.
    """

    def __init__(
        self,
        success_reward: float = 1.0,
        failure_penalty: float = -1.0,
        max_expected_duration: float = 60.0,
    ) -> None:
        """
        Initializes the RewardCalculator.

        Args:
            success_reward: The reward granted for a successful task.
            failure_penalty: The penalty applied for a failed task.
            max_expected_duration: The maximum expected duration for a task in seconds.
                                   Used for normalizing duration-based penalties.
        """
        self.success_reward = success_reward
        self.failure_penalty = failure_penalty
        self.max_expected_duration = max_expected_duration

    def calculate_reward(self, task_result: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """
        Calculates the reward based on the task result.

        Args:
            task_result: A dictionary containing the task execution result.
                         Expected keys: 'status' (str), 'duration' (float, optional).

        Returns:
            A float representing the calculated reward.
        """
        reward = 0.0

        status = task_result.get("status")
        duration = task_result.get("duration")

        if status == "success":
            reward += self.success_reward
            if duration is not None:
                # Apply a bonus/penalty based on duration for successful tasks
                # Faster is better, so duration penalty reduces reward
                duration_penalty = min(
                    duration / self.max_expected_duration, 1.0
                )  # Normalize to 0-1
                reward -= duration_penalty * (
                    self.success_reward / 2
                )  # Reduce up to half of success reward
        elif status == "error":
            reward += self.failure_penalty
            # For failed tasks, duration might not be as relevant for reward, or could be a fixed penalty
            # For now, just the failure penalty.
        else:
            # Unknown status, neutral or small penalty
            reward -= 0.1

        return reward
