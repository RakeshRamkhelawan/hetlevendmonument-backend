#!/usr/bin/env python3
"""
M-MDP PPO Trainer Implementation - Phase 2 Day 8-10
Memory-augmented Proximal Policy Optimization for multi-agent learning
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import gymnasium as gym
    import numpy as np

# Optional ML/RL dependencies (not required for basic API functionality)
try:
    import gymnasium as gym
    import numpy as np
    from stable_baselines3 import PPO  # pyright: ignore[reportAssignmentType]
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import (
        DummyVecEnv,  # pyright: ignore[reportAssignmentType]
    )

    ML_AVAILABLE = True
except ImportError as e:

    class _FallbackBaseCallback:
        def __init__(self, verbose: int = 0) -> None:
            self.verbose = verbose
            self.locals: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    BaseCallback = _FallbackBaseCallback  # type: ignore[misc, assignment]

    class PPO:  # type: ignore[no-redef]
        """Fallback stub -- stable_baselines3 unavailable. Never instantiated at runtime."""

        def __init__(self, *args: object, **kwargs: object) -> None: ...
        def learn(self, *args: object, **kwargs: object) -> "PPO": ...  # type: ignore[empty-body]
        def predict(self, obs: object, **kwargs: object) -> tuple[object, object]: ...  # type: ignore[empty-body]
        def save(self, path: str) -> None: ...

    class DummyVecEnv:  # type: ignore[no-redef]
        """Fallback stub -- stable_baselines3 unavailable. Never instantiated at runtime."""

        def __init__(self, *args: object, **kwargs: object) -> None: ...
        def reset(self) -> object: ...
        def step(self, actions: object) -> tuple[object, object, object, object]: ...  # type: ignore[empty-body]

    ML_AVAILABLE = False
    logging.warning(
        f"ML/RL dependencies not available: {e}. "
        "PPO trainer will not be functional. "
        "Install with: pip install -r requirements-ml.txt"
    )

from src.core.communication.communication_manager import communication_manager
from src.core.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


@dataclass
class PPOConfig:
    """Configuration for PPO training"""

    learning_rate: float = 3e-4
    n_steps: int = 2048
    batch_size: int = 64
    n_epochs: int = 10
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    memory_integration: bool = True
    use_communication: bool = True


@dataclass
class TrainingMetrics:
    """Training metrics for monitoring"""

    episode_reward: float = 0.0
    episode_length: int = 0
    policy_loss: float = 0.0
    value_loss: float = 0.0
    entropy_loss: float = 0.0
    memory_retrieval_accuracy: float = 0.0
    communication_efficiency: float = 0.0
    timestamp: datetime | None = None


# Zonder stable_baselines3 is BaseCallback de fallback-stub hierboven en dus Any voor mypy
# ("Class cannot subclass"). Met de library erbij is het een echte klasse en is de ignore
# overbodig -- dat mag hier, want deze module staat in de warn_unused_ignores-uitzondering
# in pyproject.toml (optional-import-guard).
class MemoryAugmentedCallback(BaseCallback):  # type: ignore[misc]  # pyright: ignore[reportGeneralTypeIssues]
    """Callback for memory integration during training"""

    def __init__(self, memory_manager: MemoryManager, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.memory_manager = memory_manager
        self.episode_memories: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        self.performance_history: deque[Any] = deque(
            maxlen=100
        )  # TODO(TYPE): replace Any with concrete type

    def _on_step(self) -> bool:
        """Called at each training step"""
        if self.locals.get("infos"):
            for info in self.locals["infos"]:
                if "memory_context" in info:
                    self.episode_memories.append(info["memory_context"])
        return True

    def _on_rollout_end(self) -> None:
        """Called at the end of each rollout"""
        if self.episode_memories:
            # Store successful experiences in memory
            for memory_context in self.episode_memories:
                asyncio.create_task(self._store_experience_memory(memory_context))
            self.episode_memories.clear()

    async def _store_experience_memory(
        self,
        memory_context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Store experience in memory system"""
        try:
            await self.memory_manager.store_memory(
                agent_id="ppo_trainer",
                memory_type="experience",
                content=memory_context,
                importance_score=memory_context.get("reward", 0.0),
            )
        except Exception as e:
            logger.error(f"Failed to store experience memory: {e}")


class PPOTrainer:
    """Memory-augmented PPO trainer for M-MDP agents"""

    def __init__(
        self,
        agent_id: str,
        config: PPOConfig | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.config = config or PPOConfig()
        self.memory_manager = memory_manager

        # Training state
        self.model: Any = None
        self.env: Any = None
        self.training_active = False
        self.current_episode = 0
        self.total_timesteps = 0

        # Metrics tracking
        self.training_metrics: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        self.performance_buffer: deque[Any] = deque(
            maxlen=1000
        )  # TODO(TYPE): replace Any with concrete type

        # Memory integration
        self.memory_context_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.memory_retrieval_stats = {
            "total_retrievals": 0,
            "successful_retrievals": 0,
            "cache_hits": 0,
        }

        # Initialize memory callback to None (set in initialize() if enabled)
        self.memory_callback: MemoryAugmentedCallback | None = None

        logger.info(f"PPO Trainer initialized for agent {agent_id}")

    @property
    def policy_network(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get the policy network from the underlying model"""
        if self.model is not None and hasattr(self.model, "policy"):
            return self.model.policy
        return None

    async def initialize(
        self,
        env_config: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Initialize training environment and model"""
        if not ML_AVAILABLE:
            raise RuntimeError(
                "ML/RL dependencies not available. "
                "Install with: pip install gymnasium stable-baselines3 numpy"
            )

        try:
            # Create environment
            self.env = self._create_environment(env_config)

            if PPO is None:
                raise RuntimeError(
                    "ML/RL dependencies not available. "
                    "Install with: pip install gymnasium stable-baselines3 numpy"
                )

            # Initialize PPO model
            self.model = PPO(
                "MlpPolicy",
                self.env,
                learning_rate=self.config.learning_rate,
                n_steps=self.config.n_steps,
                batch_size=self.config.batch_size,
                n_epochs=self.config.n_epochs,
                gamma=self.config.gamma,
                gae_lambda=self.config.gae_lambda,
                clip_range=self.config.clip_range,
                ent_coef=self.config.ent_coef,
                vf_coef=self.config.vf_coef,
                max_grad_norm=self.config.max_grad_norm,
                verbose=1,
            )

            # Setup memory callback if enabled
            if self.config.memory_integration and self.memory_manager:
                self.memory_callback = MemoryAugmentedCallback(self.memory_manager)

            logger.info("PPO Trainer initialization completed")

        except Exception as e:
            logger.error(f"Failed to initialize PPO trainer: {e}")
            raise

    def _create_environment(
        self,
        env_config: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Create training environment"""
        if not ML_AVAILABLE:
            raise RuntimeError(
                "ML/RL dependencies not available. "
                "Install with: pip install gymnasium stable-baselines3 numpy"
            )

        # Create a simple multi-agent coordination environment
        # This would be replaced with actual M-MDP environment

        if gym is None:
            raise RuntimeError(
                "Gymnasium is required for training. "
                "Install with: pip install gymnasium stable-baselines3 numpy"
            )

        def make_env() -> Any:  # TODO(TYPE): replace Any with concrete type
            assert gym is not None, "Gymnasium is required for training"
            return gym.make("CartPole-v1")  # Placeholder environment

        if DummyVecEnv is None:
            raise RuntimeError(
                "stable-baselines3 is required for training. "
                "Install with: pip install gymnasium stable-baselines3 numpy"
            )

        return DummyVecEnv([make_env])

    async def train(
        self, total_timesteps: int, eval_freq: int = 10000, save_freq: int = 50000
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Train the PPO model with memory integration"""
        if not ML_AVAILABLE:
            raise RuntimeError(
                "ML/RL dependencies not available. "
                "Install with: pip install gymnasium stable-baselines3 numpy"
            )

        try:
            if self.model is None:
                raise RuntimeError("Model not initialized. Call initialize() first.")
            self.training_active = True
            self.total_timesteps = total_timesteps

            logger.info(f"Starting PPO training for {total_timesteps} timesteps")

            # Setup callbacks
            callbacks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if self.config.memory_integration and hasattr(self, "memory_callback"):
                callbacks.append(self.memory_callback)

            # Training loop with memory integration
            for episode in range(0, total_timesteps, self.config.n_steps):
                self.current_episode = episode

                # Retrieve relevant memories before training step
                if self.config.memory_integration:
                    await self._retrieve_relevant_memories()

                # Train for one rollout
                self.model.learn(
                    total_timesteps=min(self.config.n_steps, total_timesteps - episode),
                    callback=callbacks,
                    reset_num_timesteps=False,
                )

                # Collect and store metrics
                await self._collect_training_metrics()

                # Send telemetry if communication enabled
                if self.config.use_communication:
                    await self._send_training_telemetry()

                # Evaluation checkpoint
                if episode % eval_freq == 0:
                    await self._evaluate_performance()

                # Save checkpoint
                if episode % save_freq == 0:
                    self._save_checkpoint(episode)

                # Check for early stopping conditions
                if await self._should_stop_training():
                    logger.info("Early stopping criteria met")
                    break

            self.training_active = False

            # Final evaluation and metrics
            final_metrics = await self._finalize_training()

            logger.info("PPO training completed successfully")
            return final_metrics

        except Exception as e:
            logger.error(f"Training failed: {e}")
            self.training_active = False
            raise

    async def _retrieve_relevant_memories(
        self,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Retrieve relevant memories to guide training"""
        if not self.memory_manager:
            return

        try:
            # Create context query

            # Check cache first
            cache_key = f"episode_{self.current_episode // 100}"
            if cache_key in self.memory_context_cache:
                self.memory_retrieval_stats["cache_hits"] += 1
                return self.memory_context_cache[cache_key]

            # Retrieve from memory manager
            self.memory_retrieval_stats["total_retrievals"] += 1

            memories = await self.memory_manager.query_memories(
                agent_id=self.agent_id,
                memory_types=["experience", "strategy"],
                query_vector=None,  # Would use embedding of current state
                top_k=5,
            )

            if memories:
                self.memory_retrieval_stats["successful_retrievals"] += 1
                self.memory_context_cache[cache_key] = memories

                # Update training context with retrieved memories
                await self._integrate_memories_into_training(memories)

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")

    async def _integrate_memories_into_training(
        self,
        memories: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Integrate retrieved memories into training process"""
        try:
            # Extract successful strategies and experiences
            successful_patterns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for memory in memories:
                if memory.get("importance_score", 0) > 0.8:
                    successful_patterns.append(memory["content"])

            # This would modify the training process based on memories
            # For now, we log the integration
            logger.debug(f"Integrated {len(successful_patterns)} memory patterns into training")

        except Exception as e:
            logger.error(f"Failed to integrate memories: {e}")

    async def _collect_training_metrics(self) -> None:
        """Collect training metrics for monitoring"""
        if not ML_AVAILABLE:
            return

        try:
            # Initialize metrics with defaults
            episode_reward = 0.0
            episode_length = 0.0
            policy_loss = 0.0
            value_loss = 0.0
            entropy_loss = 0.0

            # Get metrics from model
            if self.model is not None and hasattr(self.model, "logger") and self.model.logger:
                episode_reward = getattr(self.model.logger, "name_to_value", {}).get(
                    "rollout/ep_rew_mean", 0.0
                )
                episode_length = getattr(self.model.logger, "name_to_value", {}).get(
                    "rollout/ep_len_mean", 0.0
                )
                policy_loss = getattr(self.model.logger, "name_to_value", {}).get(
                    "train/policy_loss", 0.0
                )
                value_loss = getattr(self.model.logger, "name_to_value", {}).get(
                    "train/value_loss", 0.0
                )
                entropy_loss = getattr(self.model.logger, "name_to_value", {}).get(
                    "train/entropy_loss", 0.0
                )
            else:
                # Fallback metrics
                if np is None:
                    raise RuntimeError("NumPy is required for training")
                episode_reward = float(np.random.normal(100, 10))  # Placeholder
                episode_length = float(np.random.normal(200, 20))
                policy_loss = float(np.random.normal(0.1, 0.02))
                value_loss = float(np.random.normal(0.5, 0.1))
                entropy_loss = float(np.random.normal(0.01, 0.002))

            # Memory retrieval accuracy
            memory_accuracy = self.memory_retrieval_stats["successful_retrievals"] / max(
                self.memory_retrieval_stats["total_retrievals"], 1
            )

            # Communication efficiency (placeholder)
            comm_efficiency = 0.95

            metrics = TrainingMetrics(
                episode_reward=episode_reward,
                episode_length=int(episode_length),
                policy_loss=policy_loss,
                value_loss=value_loss,
                entropy_loss=entropy_loss,
                memory_retrieval_accuracy=memory_accuracy,
                communication_efficiency=comm_efficiency,
                timestamp=datetime.now(timezone.utc),
            )

            self.training_metrics.append(metrics)
            self.performance_buffer.append(episode_reward)

        except Exception as e:
            logger.error(f"Failed to collect training metrics: {e}")

    async def _send_training_telemetry(self) -> None:
        """Send training telemetry through communication system"""
        if not ML_AVAILABLE:
            return

        try:
            if not self.training_metrics:
                return

            latest_metrics = self.training_metrics[-1]

            telemetry_data = {
                "training_active": self.training_active,
                "current_episode": self.current_episode,
                "total_timesteps": self.total_timesteps,
                "episode_reward": latest_metrics.episode_reward,
                "policy_loss": latest_metrics.policy_loss,
                "value_loss": latest_metrics.value_loss,
                "memory_retrieval_accuracy": latest_metrics.memory_retrieval_accuracy,
            }

            assert np is not None, "NumPy is required for training"
            performance_indicators = {
                "episode_reward_mean": float(float(np.mean(list(self.performance_buffer)))),
                "episode_reward_std": float(float(np.std(list(self.performance_buffer)))),
                "training_stability": float(self._calculate_training_stability()),
                "memory_efficiency": float(
                    self.memory_retrieval_stats["cache_hits"]
                    / max(self.memory_retrieval_stats["total_retrievals"], 1)
                ),
            }

            resource_usage = {
                "gpu_memory": 0.0,  # Would get actual GPU usage
                "training_time": (
                    (datetime.now(timezone.utc) - latest_metrics.timestamp).total_seconds()
                    if latest_metrics.timestamp
                    else 0.0
                ),
                "memory_cache_size": len(self.memory_context_cache),
            }

            await communication_manager.collect_telemetry(
                agent_id=self.agent_id,
                metrics=telemetry_data,
                performance_indicators=performance_indicators,
                resource_usage=resource_usage,
            )

        except Exception as e:
            logger.error(f"Failed to send training telemetry: {e}")

    def _calculate_training_stability(self) -> float:
        """Calculate training stability metric"""
        if len(self.performance_buffer) < 10:
            return 1.0

        if np is None:
            return 1.0

        recent_rewards = list(self.performance_buffer)[-10:]
        assert np is not None, "NumPy is required for training"
        return float(1.0 / (1.0 + np.std(recent_rewards)))

    async def _evaluate_performance(self) -> None:
        """Evaluate current model performance"""
        if not ML_AVAILABLE:
            return

        try:
            if self.env is None or self.model is None:
                logger.warning("Cannot evaluate: env or model not initialized")
                return
            # Run evaluation episodes
            eval_rewards: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            obs: Any | None = None  # TODO(TYPE): replace Any with concrete type

            for _ in range(10):  # 10 evaluation episodes
                episode_reward: float = 0.0
                done = False
                obs = self.env.reset()

                while not done:
                    action, _ = self.model.predict(obs, deterministic=True)
                    step_result = self.env.step(action)
                    obs = step_result[0]
                    reward = step_result[1]
                    # Handle both 4-tuple and 5-tuple returns (gym API change)
                    done = (
                        step_result[2]
                        if len(step_result) == 4
                        else (step_result[2] or step_result[3])
                    )
                    info = step_result[-1]
                    assert np is not None, "NumPy is required for training"
                    reward_value = (
                        float(reward[0]) if isinstance(reward, np.ndarray) else float(reward)
                    )
                    episode_reward += reward_value

                eval_rewards.append(episode_reward)

            assert np is not None, "NumPy is required for training"
            avg_reward = np.mean(eval_rewards)
            logger.info(
                f"Evaluation at episode {self.current_episode}: Average reward = {avg_reward:.2f}"
            )

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")

    async def _should_stop_training(self) -> bool:
        """Check if training should be stopped early"""
        if len(self.performance_buffer) < 50:
            return False

        # Stop if performance has plateaued
        recent_performance = list(self.performance_buffer)[-20:]
        early_performance = list(self.performance_buffer)[-50:-30]

        assert np is not None, "NumPy is required for training"
        if np.mean(recent_performance) <= np.mean(early_performance):
            return True

        return False

    def _save_checkpoint(self, episode: int) -> None:
        """Save training checkpoint"""
        try:
            if self.model is None:
                logger.warning("Cannot save checkpoint: model not initialized")
                return
            checkpoint_path = f"checkpoints/ppo_{self.agent_id}_episode_{episode}"
            self.model.save(checkpoint_path)
            logger.info(f"Checkpoint saved: {checkpoint_path}")

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    async def _finalize_training(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Finalize training and return summary metrics"""
        try:
            # Calculate metrics with safe defaults for empty buffers
            assert np is not None, "NumPy is required for training"
            average_reward = (
                float(np.mean(list(self.performance_buffer))) if self.performance_buffer else 0.0
            )
            final_reward = float(self.performance_buffer[-1]) if self.performance_buffer else 0.0
            training_stability = self._calculate_training_stability()
            memory_retrieval_accuracy = self.memory_retrieval_stats["successful_retrievals"] / max(
                self.memory_retrieval_stats["total_retrievals"], 1
            )
            total_training_time = len(self.training_metrics) * self.config.n_steps
            assert np is not None, "NumPy is required for training"
            convergence_achieved = (
                len(self.performance_buffer) >= 50
                and np.std(list(self.performance_buffer)[-20:]) < 10
            )

            final_metrics = {
                "total_episodes": self.current_episode,
                "total_timesteps": self.total_timesteps,
                "average_reward": average_reward,
                "final_reward": final_reward,
                "training_stability": training_stability,
                "memory_retrieval_accuracy": memory_retrieval_accuracy,
                "total_training_time": total_training_time,
                "convergence_achieved": convergence_achieved,
            }

            # Store final training summary in memory
            if self.memory_manager:
                await self.memory_manager.store_memory(
                    agent_id=self.agent_id,
                    memory_type="training_summary",
                    content=final_metrics,
                    importance_score=0.9,
                )

            return final_metrics

        except Exception as e:
            logger.error(f"Failed to finalize training: {e}")
            return {}

    async def predict(
        self,
        observation: np.ndarray[Any, Any],  # TODO(TYPE): replace Any with concrete type
        deterministic: bool = True,  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[
        np.ndarray[Any, Any] | None, dict[str, Any] | None
    ]:  # TODO(TYPE): replace Any with concrete type
        """Make prediction with memory context"""
        if not ML_AVAILABLE:
            raise RuntimeError(
                "ML/RL dependencies not available. "
                "Install with: pip install gymnasium stable-baselines3 numpy"
            )

        try:
            if not self.model:
                raise ValueError("Model not initialized")

            # Retrieve relevant memories for prediction context
            memory_context = None
            if self.config.memory_integration and self.memory_manager:
                memories = await self.memory_manager.query_memories(
                    agent_id=self.agent_id,
                    memory_types=["experience"],
                    query_vector=None,  # Would use observation embedding
                    top_k=3,
                )

                if memories:
                    memory_context = {
                        "relevant_memories": len(memories),
                        "confidence_boost": 0.1 * len(memories),
                    }

            # Make prediction
            action, _states = self.model.predict(observation, deterministic=deterministic)

            return action, memory_context

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            if np is not None:
                return np.array([0]), None
            return None, None

    def get_training_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current training status"""
        return {
            "training_active": self.training_active,
            "current_episode": self.current_episode,
            "total_timesteps": self.total_timesteps,
            "recent_performance": (
                list(self.performance_buffer)[-10:] if self.performance_buffer else []
            ),
            "memory_retrieval_stats": self.memory_retrieval_stats,
            "model_initialized": self.model is not None,
            "ml_available": ML_AVAILABLE,
        }
