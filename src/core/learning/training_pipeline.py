#!/usr/bin/env python3
"""
M-MDP Training Pipeline Implementation - Phase 2 Day 13-14
Complete training orchestration for memory-augmented multi-agent learning
"""

import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, cast

import numpy as np
import yaml

from src.core.communication.communication_manager import communication_manager
from src.core.learning.experience_replay import ExperienceBuffer
from src.core.learning.experiment_tracker import ExperimentTracker, TrainingMetrics
from src.core.learning.memory_guided_learning import LearningContext, MemoryGuidedLearningManager
from src.core.learning.meta_learning import MetaLearningManager, MetaTask
from src.core.learning.ppo_trainer import PPOConfig, PPOTrainer
from src.core.learning.reward_systems import MultiLevelRewardSystem
from src.core.learning.safety_validation import (
    human_approval_system,
    rollback_system,
    safety_constraint_system,
)
from src.core.memory.memory_manager import resolve_memory_manager
from src.core.types import AgentType

logger = logging.getLogger(__name__)


@dataclass
class TrainingSession:
    """Configuration for a training session"""

    session_id: str
    agent_type: AgentType
    training_config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    start_time: datetime
    end_time: datetime | None = None
    status: str = "initializing"
    total_episodes: int = 0
    best_reward: float = float("-inf")
    success_rate: float = 0.0


@dataclass
class TrainingResults:
    """Results from a completed training session"""

    session_id: str
    agent_type: AgentType
    success: bool
    total_episodes: int
    final_reward: float
    best_reward: float
    success_rate: float
    training_time: float
    convergence_achieved: bool
    artifacts_saved: list[str]


class TrainingPipeline:
    """Complete training pipeline for M-MDP agents"""

    def __init__(self, config_path: str = "training_config.yaml") -> None:
        # Load configuration
        self.config = self._load_config(config_path)
        self.training_config = self.config.get("training", {})
        self.agent_configs = self.config.get("agents", {})

        # Initialize components
        self.reward_system = MultiLevelRewardSystem()
        self.experiment_tracker = ExperimentTracker(config_path)

        # Initialize meta-learning system
        self.meta_learning_manager: MetaLearningManager | None = (
            None  # Initialized in initialize_training_environment
        )

        # Initialize safety systems
        self.safety_constraint_system = safety_constraint_system
        self.human_approval_system = human_approval_system
        self.rollback_system = rollback_system

        # Training state
        self.active_sessions: dict[str, TrainingSession] = {}
        self.completed_sessions: list[TrainingResults] = []
        self.training_statistics = {
            "total_sessions": 0,
            "successful_sessions": 0,
            "total_training_time": 0.0,
            "average_success_rate": 0.0,
        }

        # Resource management
        self.max_concurrent_sessions = self.training_config.get("max_concurrent_experiments", 3)
        self.session_timeout = timedelta(
            hours=self.training_config.get("training_timeout_hours", 24)
        )

        logger.info("Training pipeline initialized")

    def _load_config(self, config_path: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Load training configuration"""
        try:
            with open(config_path, encoding="ascii") as f:
                return cast(dict[str, Any], yaml.safe_load(f))  # TODO(TYPE): replace Any with concrete type
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            return {}

    async def initialize_training_environment(self) -> None:
        """Initialize the training environment"""
        try:
            # Initialize memory manager
            await resolve_memory_manager().initialize()

            # Initialize communication manager
            await communication_manager.initialize()

            # Create necessary directories
            Path("checkpoints").mkdir(exist_ok=True)
            Path("logs").mkdir(exist_ok=True)
            Path("artifacts").mkdir(exist_ok=True)

            # Initialize meta-learning manager
            base_models: dict[str, Any] = {}  # Will be populated with agent models during training  # TODO(TYPE): replace Any with concrete type
            self.meta_learning_manager = MetaLearningManager(
                memory_manager=resolve_memory_manager(), base_models=base_models
            )

            logger.info("Training environment initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize training environment: {e}")
            raise

    async def start_agent_training(
        self, agent_type: AgentType, custom_config: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Start training for a specific agent type"""
        try:
            # Check concurrent session limit
            if len(self.active_sessions) >= self.max_concurrent_sessions:
                raise ValueError(
                    f"Maximum concurrent sessions ({self.max_concurrent_sessions}) reached"
                )

            # Generate session ID
            session_id = f"training_{agent_type.value}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            # Get agent configuration
            agent_config = self.agent_configs.get(agent_type.value, {})
            if not agent_config.get("enable_training", False):
                raise ValueError(f"Training not enabled for agent type: {agent_type.value}")

            # Merge configurations
            training_config = {**self.training_config}
            if custom_config:
                training_config.update(custom_config)

            # Create training session
            session = TrainingSession(
                session_id=session_id,
                agent_type=agent_type,
                training_config=training_config,
                start_time=datetime.now(timezone.utc),
            )

            # Store active session
            self.active_sessions[session_id] = session

            # Start training asynchronously
            asyncio.create_task(self._run_training_session(session))

            logger.info(f"Training session started: {session_id}")
            return session_id

        except Exception as e:
            logger.error(f"Failed to start agent training: {e}")
            raise

    async def _run_training_session(self, session: TrainingSession) -> None:
        """Run a complete training session"""
        try:
            session.status = "running"

            # Start experiment tracking
            experiment_name = f"mmdp_{session.agent_type.value}_training"
            self.experiment_tracker.start_experiment(
                experiment_name=experiment_name,
                agent_type=session.agent_type.value,
                training_parameters=session.training_config,
                description=f"M-MDP training for {session.agent_type.value} agent",
            )

            # Initialize training components
            (
                trainer,
                experience_buffer,
                learning_manager,
            ) = await self._setup_training_components(session)

            # Run training episodes
            results = await self._execute_training_episodes(
                session, trainer, experience_buffer, learning_manager
            )

            # Complete session
            session.status = "completed"
            session.end_time = datetime.now(timezone.utc)
            session.success_rate = results.success_rate
            session.best_reward = results.best_reward
            session.total_episodes = results.total_episodes

            # End experiment tracking
            experiment_result = self.experiment_tracker.end_experiment()

            # Create training results
            training_results = TrainingResults(
                session_id=session.session_id,
                agent_type=session.agent_type,
                success=results.success_rate
                >= self.agent_configs.get(session.agent_type.value, {}).get(
                    "success_threshold", 0.7
                ),
                total_episodes=results.total_episodes,
                final_reward=results.final_reward,
                best_reward=results.best_reward,
                success_rate=results.success_rate,
                training_time=(session.end_time - session.start_time).total_seconds(),
                convergence_achieved=results.convergence_achieved,
                artifacts_saved=experiment_result.artifacts_saved,
            )

            # Store completed session
            self.completed_sessions.append(training_results)
            del self.active_sessions[session.session_id]

            # Update statistics
            self._update_training_statistics(training_results)

            logger.info(
                f"Training session completed: {session.session_id} (Success: {training_results.success})"
            )

        except Exception as e:
            logger.error(f"Training session failed: {session.session_id} - {e}")
            session.status = "failed"
            session.end_time = datetime.now(timezone.utc)

            # Clean up failed session
            if session.session_id in self.active_sessions:
                del self.active_sessions[session.session_id]

            # End experiment tracking
            try:
                self.experiment_tracker.end_experiment()
            except Exception as e:
                logger.warning(f"Failed to end experiment tracking: {str(e)}", exc_info=False)

    async def _setup_training_components(
        self, session: TrainingSession
    ) -> tuple[PPOTrainer, ExperienceBuffer, MemoryGuidedLearningManager]:
        """Setup training components for a session"""
        try:
            # Create PPO configuration
            ppo_config = PPOConfig(
                learning_rate=session.training_config.get("ppo", {}).get("learning_rate", 3e-4),
                n_steps=session.training_config.get("ppo", {}).get("n_steps", 2048),
                batch_size=session.training_config.get("ppo", {}).get("batch_size", 64),
                n_epochs=session.training_config.get("ppo", {}).get("n_epochs", 10),
                gamma=session.training_config.get("ppo", {}).get("gamma", 0.99),
                memory_integration=session.training_config.get("memory", {}).get(
                    "enable_memory_guidance", True
                ),
                use_communication=True,
            )

            # Initialize PPO trainer
            trainer = PPOTrainer(
                agent_id=f"{session.agent_type.value}_{session.session_id}",
                config=ppo_config,
                memory_manager=resolve_memory_manager(),
            )

            # Create training environment configuration
            env_config = {
                "agent_type": session.agent_type.value,
                "max_episode_steps": session.training_config.get("environment", {}).get(
                    "max_episode_steps", 1000
                ),
                "observation_space_size": session.training_config.get("environment", {}).get(
                    "observation_space_size", 256
                ),
                "action_space_size": session.training_config.get("environment", {}).get(
                    "action_space_size", 64
                ),
            }

            await trainer.initialize(env_config)

            # Initialize experience buffer
            experience_buffer = ExperienceBuffer(
                capacity=session.training_config.get("experience_replay", {}).get(
                    "buffer_capacity", 50000
                ),
                agent_id=f"{session.agent_type.value}_{session.session_id}",
            )

            # Initialize memory-guided learning manager
            learning_manager = MemoryGuidedLearningManager(
                memory_manager=resolve_memory_manager(),
                reward_system=self.reward_system,
                experience_buffer=experience_buffer,
            )

            # Register trainer model with meta-learning system
            if self.meta_learning_manager and hasattr(trainer, "policy_network"):
                self.meta_learning_manager.base_models[
                    f"{session.agent_type.value}_{session.session_id}"
                ] = trainer.policy_network

            return trainer, experience_buffer, learning_manager

        except Exception as e:
            logger.error(f"Failed to setup training components: {e}")
            raise

    async def _execute_training_episodes(
        self,
        session: TrainingSession,
        trainer: PPOTrainer,
        experience_buffer: ExperienceBuffer,
        learning_manager: MemoryGuidedLearningManager,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Execute training episodes"""
        try:
            agent_config = self.agent_configs.get(session.agent_type.value, {})
            max_episodes = agent_config.get("training_episodes", 1000)
            evaluation_frequency = agent_config.get("evaluation_frequency", 100)

            episode_rewards: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            evaluation_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            best_reward = float("-inf")

            for episode in range(max_episodes):
                # Check for timeout
                if datetime.now(timezone.utc) - session.start_time > self.session_timeout:
                    logger.warning(f"Training session {session.session_id} timed out")
                    break

                # Check if session was cancelled
                if session.session_id not in self.active_sessions:
                    logger.info(f"Training session {session.session_id} was cancelled")
                    break

                # Run training episode
                episode_result = await self._run_training_episode(
                    episode, trainer, learning_manager, session
                )

                episode_rewards.append(episode_result["reward"])
                if episode_result["reward"] > best_reward:
                    best_reward = episode_result["reward"]

                # Log training metrics
                training_metrics = TrainingMetrics(
                    episode=episode,
                    episode_reward=episode_result["reward"],
                    episode_length=episode_result["length"],
                    policy_loss=episode_result.get("policy_loss", 0.0),
                    value_loss=episode_result.get("value_loss", 0.0),
                    entropy_loss=episode_result.get("entropy_loss", 0.0),
                    memory_retrieval_accuracy=episode_result.get("memory_accuracy", 0.0),
                    communication_efficiency=episode_result.get("communication_efficiency", 0.0),
                    timestamp=datetime.now(timezone.utc),
                )

                self.experiment_tracker.log_training_metrics(training_metrics)

                # Periodic evaluation
                if episode % evaluation_frequency == 0 and episode > 0:
                    eval_result = await self._evaluate_agent(trainer, session)
                    evaluation_results.append(eval_result)

                    self.experiment_tracker.log_evaluation_metrics(eval_result, episode)

                    # Meta-learning adaptation check
                    if self.meta_learning_manager and episode % (evaluation_frequency * 2) == 0:
                        await self._apply_meta_learning_adaptation(
                            trainer, session, evaluation_results
                        )

                    # Save checkpoint
                    checkpoint_path = f"checkpoints/{session.session_id}_episode_{episode}.pkl"
                    model_to_save = cast(Any, trainer.model) if trainer.model is not None else None  # TODO(TYPE): replace Any with concrete type
                    if model_to_save is not None:
                        self.experiment_tracker.save_checkpoint(
                            model_to_save, checkpoint_path, episode
                        )

                # Update session progress
                session.total_episodes = episode + 1

                # Check for early convergence
                if len(episode_rewards) >= 100:
                    recent_rewards = episode_rewards[-50:]
                    if np.std(recent_rewards) < 5.0 and np.mean(recent_rewards) > best_reward * 0.9:
                        logger.info(f"Early convergence detected at episode {episode}")
                        break

            # Calculate final statistics
            success_rate = (
                sum(1 for r in episode_rewards if r > 0) / len(episode_rewards)
                if episode_rewards
                else 0.0
            )
            convergence_achieved = (
                len(episode_rewards) >= 50 and np.std(episode_rewards[-20:]) < 10.0
            )

            return type(
                "Results",
                (),
                {
                    "total_episodes": len(episode_rewards),
                    "final_reward": episode_rewards[-1] if episode_rewards else 0.0,
                    "best_reward": best_reward,
                    "success_rate": success_rate,
                    "convergence_achieved": convergence_achieved,
                },
            )

        except Exception as e:
            logger.error(f"Failed to execute training episodes: {e}")
            raise

    async def _run_training_episode(
        self,
        episode: int,
        trainer: PPOTrainer,
        learning_manager: MemoryGuidedLearningManager,
        session: TrainingSession,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Run a single training episode"""
        try:
            # Create learning context
            learning_context = LearningContext(
                agent_id=f"{session.agent_type.value}_{session.session_id}",
                current_state={
                    "episode": episode,
                    "agent_type": session.agent_type.value,
                },
                action_space=[
                    "strategic_planning",
                    "task_delegation",
                    "resource_allocation",
                ],
                memory_retrieval_results=[],
                learning_objectives=[
                    "improve_efficiency",
                    "enhance_communication",
                    "optimize_performance",
                ],
            )

            # Initiate learning episode
            learning_episode_id = await learning_manager.initiate_learning_episode(
                learning_context.agent_id, learning_context
            )

            # Simulate episode execution (this would be replaced with actual environment interaction)
            episode_reward = np.random.normal(50, 20)  # Placeholder for actual training
            episode_length = np.random.randint(100, 500)

            # Simulate learning step
            action_taken = {"type": "strategic_decision", "confidence": 0.8}
            outcome = {
                "success": episode_reward > 0,
                "efficiency_score": min(episode_reward / 100.0, 1.0),
                "resulting_state": {"episode": episode + 1},
                "episode_complete": True,
            }

            # Execute learning step
            await learning_manager.execute_learning_step(learning_episode_id, action_taken, outcome)

            # Complete learning episode
            learning_outcome = await learning_manager.complete_learning_episode(learning_episode_id)

            # Calculate additional metrics
            memory_accuracy = learning_outcome.confidence_score
            communication_efficiency = 0.85 + np.random.normal(0, 0.1)

            return {
                "reward": episode_reward,
                "length": episode_length,
                "memory_accuracy": memory_accuracy,
                "communication_efficiency": max(0, min(1, communication_efficiency)),
                "policy_loss": np.random.uniform(0.01, 0.1),
                "value_loss": np.random.uniform(0.1, 0.5),
                "entropy_loss": np.random.uniform(0.005, 0.02),
            }

        except Exception as e:
            logger.error(f"Failed to run training episode {episode}: {e}")
            return {
                "reward": 0.0,
                "length": 0,
                "memory_accuracy": 0.0,
                "communication_efficiency": 0.0,
                "policy_loss": 0.0,
                "value_loss": 0.0,
                "entropy_loss": 0.0,
            }

    async def _evaluate_agent(
        self, trainer: PPOTrainer, session: TrainingSession
    ) -> dict[str, float]:
        """Evaluate agent performance"""
        try:
            eval_config = self.config.get("evaluation", {})
            num_eval_episodes = eval_config.get("evaluation_episodes", 10)

            eval_rewards: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            eval_lengths: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for _ in range(num_eval_episodes):
                # Simulate evaluation episode
                eval_reward = np.random.normal(60, 15)  # Placeholder
                eval_length = np.random.randint(80, 400)

                eval_rewards.append(eval_reward)
                eval_lengths.append(eval_length)

            # Calculate evaluation metrics
            return {
                "success_rate": float(sum(1 for r in eval_rewards if r > 0) / len(eval_rewards)),
                "average_reward": float(float(np.mean(eval_rewards))),
                "reward_std": float(float(np.std(eval_rewards))),
                "average_length": float(float(np.mean(eval_lengths))),
                "efficiency_score": float(
                    float(np.mean(eval_rewards)) / float(np.mean(eval_lengths)) * 100
                ),
                "consistency_score": float(1.0 / (1.0 + float(np.std(eval_rewards)))),
            }

        except Exception as e:
            logger.error(f"Failed to evaluate agent: {e}")
            return {}

    def _update_training_statistics(self, results: TrainingResults) -> None:
        """Update overall training statistics"""
        try:
            self.training_statistics["total_sessions"] += 1
            if results.success:
                self.training_statistics["successful_sessions"] += 1

            self.training_statistics["total_training_time"] += results.training_time

            # Update average success rate
            if self.completed_sessions:
                total_success_rate = sum(r.success_rate for r in self.completed_sessions)
                self.training_statistics["average_success_rate"] = total_success_rate / len(
                    self.completed_sessions
                )

        except Exception as e:
            logger.error(f"Failed to update training statistics: {e}")

    async def _apply_meta_learning_adaptation(
        self,
        trainer: PPOTrainer,
        session: TrainingSession,
        evaluation_results: list[dict[str, float]],
    ) -> None:
        """Apply meta-learning adaptation based on training progress"""
        try:
            if not self.meta_learning_manager or not evaluation_results:
                return

            # Get recent performance metrics
            recent_performance = (
                evaluation_results[-3:] if len(evaluation_results) >= 3 else evaluation_results
            )
            avg_success_rate = np.mean([r.get("success_rate", 0.0) for r in recent_performance])
            avg_reward = np.mean([r.get("average_reward", 0.0) for r in recent_performance])

            # Create meta-task for current training context
            meta_task = MetaTask(
                task_id=f"adaptation_{session.session_id}_{len(evaluation_results)}",
                task_type="performance_optimization",
                context={
                    "description": f"Agent {session.agent_type.value} optimization",
                    "success_rate": avg_success_rate,
                    "avg_reward": avg_reward,
                },
                support_data=[
                    {
                        "evaluation_results": recent_performance,
                        "agent_type": session.agent_type.value,
                    }
                ],
                query_data=[{"session_id": session.session_id, "performance": avg_success_rate}],
                agent_type=session.agent_type.value,
                performance_target=0.8,  # Target success rate
            )

            # Apply meta-learning if performance is below threshold
            if avg_success_rate < 0.7:  # Performance threshold
                logger.info(f"Applying meta-learning adaptation for session {session.session_id}")

                # Use MAML for few-shot adaptation
                optimizer = next(iter(self.meta_learning_manager.maml_optimizers.values()), None)
                if optimizer is not None:
                    await cast(Any, optimizer).adapt_to_task(meta_task, num_adaptation_steps=5)  # TODO(TYPE): replace Any with concrete type

                # Apply strategy transfer if available
                if len(self.meta_learning_manager.base_models) > 1:
                    await cast(
                        Any, self.meta_learning_manager.strategy_transfer  # TODO(TYPE): replace Any with concrete type
                    ).transfer_knowledge(
                        source_agent=f"{session.agent_type.value}_{session.session_id}",
                        target_agent=f"{session.agent_type.value}_{session.session_id}",
                        task_context=meta_task.context,
                    )

                logger.info(f"Meta-learning adaptation completed for session {session.session_id}")

        except Exception as e:
            logger.error(f"Failed to apply meta-learning adaptation: {e}")
            logger.error(traceback.format_exc())

    async def stop_training_session(self, session_id: str) -> bool:
        """Stop an active training session"""
        try:
            if session_id not in self.active_sessions:
                logger.warning(f"Training session {session_id} not found or already completed")
                return False

            session = self.active_sessions[session_id]
            session.status = "stopping"

            logger.info(f"Stopping training session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop training session {session_id}: {e}")
            return False

    def get_training_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall training pipeline status"""
        return {
            "active_sessions": len(self.active_sessions),
            "completed_sessions": len(self.completed_sessions),
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "training_statistics": self.training_statistics,
            "active_session_details": [
                {
                    "session_id": session.session_id,
                    "agent_type": session.agent_type.value,
                    "status": session.status,
                    "start_time": session.start_time.isoformat(),
                    "total_episodes": session.total_episodes,
                    "best_reward": session.best_reward,
                }
                for session in self.active_sessions.values()
            ],
        }

    def get_session_details(self, session_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get details for a specific session"""
        # Check active sessions
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            return {
                "session_id": session.session_id,
                "agent_type": session.agent_type.value,
                "status": session.status,
                "start_time": session.start_time.isoformat(),
                "total_episodes": session.total_episodes,
                "best_reward": session.best_reward,
                "success_rate": session.success_rate,
                "active": True,
            }

        # Check completed sessions
        for result in self.completed_sessions:
            if result.session_id == session_id:
                return {
                    "session_id": result.session_id,
                    "agent_type": result.agent_type.value,
                    "status": "completed",
                    "success": result.success,
                    "total_episodes": result.total_episodes,
                    "final_reward": result.final_reward,
                    "best_reward": result.best_reward,
                    "success_rate": result.success_rate,
                    "training_time": result.training_time,
                    "convergence_achieved": result.convergence_achieved,
                    "active": False,
                }

        return None

    async def cleanup(self) -> None:
        """Cleanup training pipeline resources"""
        try:
            # Stop all active sessions
            for session_id in list(self.active_sessions.keys()):
                await self.stop_training_session(session_id)

            # Cleanup memory manager
            await resolve_memory_manager().cleanup()

            # Cleanup communication manager
            await communication_manager.cleanup()

            logger.info("Training pipeline cleanup completed")

        except Exception as e:
            logger.error(f"Failed to cleanup training pipeline: {e}")


# Global training pipeline instance
training_pipeline = TrainingPipeline()
