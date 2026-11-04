#!/usr/bin/env python3
"""
M-MDP Experiment Tracker Implementation - Phase 2 Day 13-14
MLflow and Wandb integration for training experiment management
"""

import json
import logging
import os
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import yaml

if TYPE_CHECKING:
    import mlflow
    import wandb

# Optional MLflow import
try:
    import mlflow

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None  # type: ignore[assignment]

# Optional Weights & Biases import
try:
    import wandb

    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False
    wandb = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


__all__ = [
    "ExperimentConfig",
    "TrainingMetrics",
    "ExperimentResult",
    "MLflowTracker",
    "WandbTracker",
    "ExperimentTracker",
]


@dataclass
class ExperimentConfig:
    """Configuration for a training experiment"""

    experiment_name: str
    run_name: str
    agent_type: str
    training_parameters: dict[str, Any]  # TODO(TYPE): Any -- numpy scalars prevent narrowing
    tags: dict[str, str]
    description: str | None = None


@dataclass
class TrainingMetrics:
    """Training metrics for experiment tracking"""

    episode: int
    episode_reward: float
    episode_length: int
    policy_loss: float
    value_loss: float
    entropy_loss: float
    memory_retrieval_accuracy: float
    communication_efficiency: float
    timestamp: datetime


@dataclass
class ExperimentResult:
    """Results of a completed experiment"""

    experiment_id: str
    run_id: str
    final_metrics: dict[str, float]
    best_metrics: dict[str, float]
    total_episodes: int
    total_training_time: float
    success_rate: float
    artifacts_saved: list[str]


class MLflowTracker:
    """MLflow experiment tracking implementation"""

    def __init__(
        self,
        config: dict[str, Any],  # TODO(TYPE): Any -- replace with concrete type
    ) -> None:
        self.config = config.get("mlflow", {})
        self.enabled = self.config.get("enabled", True) and MLFLOW_AVAILABLE

        if not MLFLOW_AVAILABLE:
            logger.warning("MLflow not available - experiment tracking disabled")
            self.enabled = False

        if self.enabled:
            self._setup_mlflow()

        self.current_run_id: str | None = None
        self.experiment_id: str | None = None

    def _setup_mlflow(self) -> None:
        """Setup MLflow tracking configuration"""
        if mlflow is None:
            self.enabled = False
            return

        try:
            # Set tracking URI
            tracking_uri = self.config.get("tracking_uri", "file:./mlruns")
            mlflow.set_tracking_uri(tracking_uri)

            # Create or get experiment
            experiment_name = self.config.get("experiment_name", "M-MDP_Learning")
            try:
                self.experiment_id = mlflow.create_experiment(
                    experiment_name,
                    artifact_location=self.config.get("artifact_location", "./mlartifacts"),
                )
            except Exception:
                # Experiment already exists
                experiment = mlflow.get_experiment_by_name(experiment_name)
                if experiment is not None:
                    self.experiment_id = experiment.experiment_id

            mlflow.set_experiment(experiment_name)

            # Enable autologging if configured
            if self.config.get("auto_log_models", False):
                mlflow.pytorch.autolog()  # pyright: ignore[reportPrivateImportUsage]

            logger.info(f"MLflow tracking initialized: {tracking_uri}")

        except Exception as e:
            logger.error(f"Failed to setup MLflow: {e}")
            self.enabled = False

    def start_run(self, experiment_config: ExperimentConfig) -> str:
        """Start a new MLflow run"""
        if not self.enabled or mlflow is None:
            return "disabled"

        try:
            # Start MLflow run
            run = mlflow.start_run(
                experiment_id=self.experiment_id,
                run_name=experiment_config.run_name,
                description=experiment_config.description,
            )

            self.current_run_id = run.info.run_id

            # Log parameters
            for key, value in experiment_config.training_parameters.items():
                if isinstance(value, (int, float, str, bool)):
                    mlflow.log_param(key, value)
                else:
                    mlflow.log_param(key, str(value))

            # Log tags
            for key, value in experiment_config.tags.items():
                mlflow.set_tag(key, value)

            # Log system info
            mlflow.set_tag("agent_type", experiment_config.agent_type)
            mlflow.set_tag("start_time", datetime.now(timezone.utc).isoformat())

            logger.info(f"MLflow run started: {self.current_run_id}")
            return self.current_run_id or "unknown"

        except Exception as e:
            logger.error(f"Failed to start MLflow run: {e}")
            return "error"

    def log_metrics(self, metrics: dict[str, float | int], step: int | None = None) -> None:
        """Log training metrics"""
        if not self.enabled or not self.current_run_id or mlflow is None:
            return

        try:
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and not (np.isnan(value) or np.isinf(value)):
                    mlflow.log_metric(key, float(value), step=step)

        except Exception as e:
            logger.error(f"Failed to log metrics to MLflow: {e}")

    def log_artifact(self, artifact_path: str, artifact_name: str | None = None) -> None:
        """Log artifacts to MLflow"""
        if not self.enabled or not self.current_run_id or mlflow is None:
            return

        try:
            if artifact_name:
                mlflow.log_artifact(artifact_path, artifact_name)
            else:
                mlflow.log_artifact(artifact_path)

        except Exception as e:
            logger.error(f"Failed to log artifact to MLflow: {e}")

    def log_model(self, model: object, model_name: str) -> None:
        """Log model to MLflow"""
        if not self.enabled or not self.current_run_id or mlflow is None:
            return

        try:
            mlflow.pytorch.log_model(model, model_name)  # pyright: ignore[reportPrivateImportUsage]

        except Exception as e:
            logger.error(f"Failed to log model to MLflow: {e}")

    def end_run(self) -> None:
        """End current MLflow run"""
        if not self.enabled or not self.current_run_id or mlflow is None:
            return

        try:
            mlflow.end_run()
            logger.info(f"MLflow run ended: {self.current_run_id}")
            self.current_run_id = None

        except Exception as e:
            logger.error(f"Failed to end MLflow run: {e}")


class WandbTracker:
    """Wandb experiment tracking implementation"""

    def __init__(
        self,
        config: dict[str, Any],  # TODO(TYPE): Any -- replace with concrete type
    ) -> None:
        self.config = config.get("wandb", {})
        self.enabled = self.config.get("enabled", False) and WANDB_AVAILABLE
        self.run: Any = None  # wandb.sdk.wandb_run.Run | None -- deferred import

        if self.enabled and wandb is None:
            logger.warning("Wandb not available - install with: pip install wandb")
            self.enabled = False

    def start_run(self, experiment_config: ExperimentConfig) -> str:
        """Start a new Wandb run"""
        if not self.enabled or wandb is None:
            return "disabled"

        try:
            self.run = wandb.init(
                project=self.config.get("project", "mmdp-learning"),
                entity=self.config.get("entity"),
                name=experiment_config.run_name,
                tags=self.config.get("tags", []),
                notes=self.config.get("notes", ""),
                config=experiment_config.training_parameters,
            )

            logger.info(f"Wandb run started: {self.run.id}")
            return str(self.run.id)

        except Exception as e:
            logger.error(f"Failed to start Wandb run: {e}")
            return "error"

    def log_metrics(self, metrics: dict[str, float | int], step: int | None = None) -> None:
        """Log training metrics"""
        if not self.enabled or not self.run or wandb is None:
            return

        try:
            # Filter out invalid values
            clean_metrics: dict[str, float] = {}
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and not (np.isnan(value) or np.isinf(value)):
                    clean_metrics[key] = float(value)

            if clean_metrics:
                self.run.log(clean_metrics, step=step)

        except Exception as e:
            logger.error(f"Failed to log metrics to Wandb: {e}")

    def log_artifact(self, artifact_path: str, artifact_name: str | None = None) -> None:
        """Log artifacts to Wandb"""
        if not self.enabled or not self.run or wandb is None:
            return

        try:
            artifact = wandb.Artifact(
                name=artifact_name or os.path.basename(artifact_path), type="model"
            )
            artifact.add_file(artifact_path)
            self.run.log_artifact(artifact)

        except Exception as e:
            logger.error(f"Failed to log artifact to Wandb: {e}")

    def end_run(self) -> None:
        """End current Wandb run"""
        if not self.enabled or not self.run:
            return

        try:
            self.run.finish()
            logger.info("Wandb run ended")
            self.run = None

        except Exception as e:
            logger.error(f"Failed to end Wandb run: {e}")


class ExperimentTracker:
    """Main experiment tracker coordinating MLflow and Wandb"""

    def __init__(self, config_path: str = "training_config.yaml") -> None:
        # Load configuration
        self.config = self._load_config(config_path)
        self.tracking_config = self.config.get("experiment_tracking", {})

        # Initialize trackers
        self.mlflow_tracker = MLflowTracker(self.tracking_config)
        self.wandb_tracker = WandbTracker(self.tracking_config)

        # Tracking state
        self.current_experiment: (
            dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
        ) = (  # TODO(TYPE): replace Any with concrete type
            None  # keys: config, mlflow_run_id, wandb_run_id, start_time
        )
        self.metrics_history: list[dict[str, Any]] = (  # TODO(TYPE): replace Any with concrete type
            []
        )  # each entry: episode(int), timestamp, metrics(dict[str,float])
        self.start_time: datetime | None = None

        # Metrics configuration
        self.tracked_metrics = set(self.tracking_config.get("metrics", []))
        self.artifacts_to_save = set(self.tracking_config.get("artifacts", []))

        logger.info("Experiment tracker initialized")

    def _load_config(
        self, config_path: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Load training configuration"""
        try:
            with open(config_path, encoding="ascii") as f:
                # yaml.safe_load returns object; cast to dict for mypy
                return cast(
                    dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                    yaml.safe_load(f),  # TODO(TYPE): replace Any with concrete type
                )  # TODO(TYPE): Any -- yaml returns object
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            return {}

    def start_experiment(
        self,
        experiment_name: str,
        agent_type: str,
        training_parameters: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ],  # TODO(TYPE): Any -- numpy scalars prevent narrowing; hyperparams: int | float | str | bool values
        description: str | None = None,
    ) -> str:
        """Start a new training experiment"""
        try:
            # Generate run name
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            run_name = f"{agent_type}_{timestamp}"

            # Create experiment config
            experiment_config = ExperimentConfig(
                experiment_name=experiment_name,
                run_name=run_name,
                agent_type=agent_type,
                training_parameters=training_parameters,
                tags={
                    "agent_type": agent_type,
                    "experiment_type": "mmdp_training",
                    "framework": "ppo",
                    "memory_augmented": "true",
                },
                description=description,
            )

            # Start tracking runs
            mlflow_run_id = self.mlflow_tracker.start_run(experiment_config)
            wandb_run_id = self.wandb_tracker.start_run(experiment_config)

            # Store current experiment info
            self.current_experiment = {
                "config": experiment_config,
                "mlflow_run_id": mlflow_run_id,
                "wandb_run_id": wandb_run_id,
                "start_time": datetime.now(timezone.utc),
            }

            self.start_time = datetime.now(timezone.utc)
            self.metrics_history = []

            logger.info(f"Experiment started: {run_name}")
            return run_name

        except Exception as e:
            logger.error(f"Failed to start experiment: {e}")
            raise

    def log_training_metrics(self, metrics: TrainingMetrics) -> None:
        """Log training metrics from a training step"""
        if not self.current_experiment:
            logger.warning("No active experiment - cannot log metrics")
            return

        try:
            # Convert to dictionary
            metrics_dict = {
                "episode_reward": metrics.episode_reward,
                "episode_length": metrics.episode_length,
                "policy_loss": metrics.policy_loss,
                "value_loss": metrics.value_loss,
                "entropy_loss": metrics.entropy_loss,
                "memory_retrieval_accuracy": metrics.memory_retrieval_accuracy,
                "communication_efficiency": metrics.communication_efficiency,
            }

            # Filter tracked metrics
            if self.tracked_metrics:
                metrics_dict = {k: v for k, v in metrics_dict.items() if k in self.tracked_metrics}

            # Log to both trackers
            self.mlflow_tracker.log_metrics(metrics_dict, step=metrics.episode)
            self.wandb_tracker.log_metrics(metrics_dict, step=metrics.episode)

            # Store in history
            self.metrics_history.append(
                {
                    "episode": metrics.episode,
                    "timestamp": metrics.timestamp,
                    "metrics": metrics_dict,
                }
            )

            logger.debug(f"Logged metrics for episode {metrics.episode}")

        except Exception as e:
            logger.error(f"Failed to log training metrics: {e}")

    def log_evaluation_metrics(self, metrics: dict[str, float], episode: int) -> None:
        """Log evaluation metrics"""
        if not self.current_experiment:
            return

        try:
            # Add evaluation prefix
            eval_metrics = {f"eval_{k}": v for k, v in metrics.items()}

            # Log to trackers
            self.mlflow_tracker.log_metrics(eval_metrics, step=episode)
            self.wandb_tracker.log_metrics(eval_metrics, step=episode)

            logger.debug(f"Logged evaluation metrics for episode {episode}")

        except Exception as e:
            logger.error(f"Failed to log evaluation metrics: {e}")

    def log_system_metrics(self, metrics: dict[str, float], episode: int) -> None:
        """Log system performance metrics"""
        if not self.current_experiment:
            return

        try:
            # Add system prefix
            system_metrics = {f"system_{k}": v for k, v in metrics.items()}

            # Log to trackers
            self.mlflow_tracker.log_metrics(system_metrics, step=episode)
            self.wandb_tracker.log_metrics(system_metrics, step=episode)

        except Exception as e:
            logger.error(f"Failed to log system metrics: {e}")

    def save_checkpoint(
        self,
        model: Any,  # TODO(TYPE): replace Any with concrete type
        checkpoint_path: str,
        episode: int,  # PyTorch nn.Module or compatible
    ) -> None:
        """Save and log model checkpoint"""
        if not self.current_experiment:
            return

        try:
            # Save checkpoint locally
            checkpoint_data = {
                "model_state_dict": model.state_dict() if hasattr(model, "state_dict") else model,
                "episode": episode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "experiment_config": asdict(self.current_experiment["config"]),
            }

            with open(checkpoint_path, "wb") as f:
                pickle.dump(checkpoint_data, f)

            # Log as artifact
            if "model_checkpoints" in self.artifacts_to_save:
                self.mlflow_tracker.log_artifact(checkpoint_path, "checkpoints")
                self.wandb_tracker.log_artifact(checkpoint_path, f"checkpoint_episode_{episode}")

            logger.info(f"Checkpoint saved: {checkpoint_path}")

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def save_training_logs(self, log_path: str) -> None:
        """Save and log training logs"""
        if not self.current_experiment:
            return

        try:
            # Save metrics history
            with open(log_path, "w", encoding="ascii") as f:
                json.dump(self.metrics_history, f, indent=2, default=str)

            # Log as artifact
            if "training_logs" in self.artifacts_to_save:
                self.mlflow_tracker.log_artifact(log_path, "logs")
                self.wandb_tracker.log_artifact(log_path, "training_log")

        except Exception as e:
            logger.error(f"Failed to save training logs: {e}")

    def end_experiment(self) -> ExperimentResult:
        """End current experiment and return results"""
        if not self.current_experiment:
            raise ValueError("No active experiment to end")

        try:
            # Calculate final metrics
            final_metrics: dict[str, float] = {}
            best_metrics: dict[str, float] = {}
            if self.metrics_history:
                final_metrics = self.metrics_history[-1]["metrics"]

                # Calculate best metrics
                for metric_name in final_metrics.keys():
                    values = [m["metrics"].get(metric_name, 0) for m in self.metrics_history]
                    if values:
                        best_metrics[f"best_{metric_name}"] = max(values)

                # Calculate success rate (episodes with positive reward)
                positive_rewards = sum(
                    1 for m in self.metrics_history if m["metrics"].get("episode_reward", 0) > 0
                )
                success_rate = (
                    positive_rewards / len(self.metrics_history) if self.metrics_history else 0.0
                )
            else:
                success_rate = 0.0

            # Calculate training time
            training_time = (
                (datetime.now(timezone.utc) - self.start_time).total_seconds()
                if self.start_time
                else 0.0
            )

            # Log final summary metrics
            summary_metrics = {
                "total_episodes": len(self.metrics_history),
                "total_training_time_seconds": training_time,
                "success_rate": success_rate,
                **best_metrics,
            }

            self.mlflow_tracker.log_metrics(summary_metrics)
            self.wandb_tracker.log_metrics(summary_metrics)

            # Create result
            result = ExperimentResult(
                experiment_id=self.current_experiment.get("mlflow_run_id", "unknown"),
                run_id=self.current_experiment.get("wandb_run_id", "unknown"),
                final_metrics=final_metrics,
                best_metrics=best_metrics,
                total_episodes=len(self.metrics_history),
                total_training_time=training_time,
                success_rate=success_rate,
                artifacts_saved=list(self.artifacts_to_save),
            )

            # End tracking runs
            self.mlflow_tracker.end_run()
            self.wandb_tracker.end_run()

            # Reset state
            self.current_experiment = None
            self.metrics_history = []
            self.start_time = None

            logger.info(f"Experiment ended - Success rate: {success_rate:.2%}")
            return result

        except Exception as e:
            logger.error(f"Failed to end experiment: {e}")
            raise

    def get_experiment_status(self) -> dict[str, Any]:  # TODO(TYPE): Any -- ExperimentStatusDict
        """Get current experiment status"""
        if not self.current_experiment:
            return {"status": "no_active_experiment"}

        return {
            "status": "active",
            "experiment_name": self.current_experiment["config"].experiment_name,
            "run_name": self.current_experiment["config"].run_name,
            "agent_type": self.current_experiment["config"].agent_type,
            "start_time": self.current_experiment["start_time"].isoformat(),
            "episodes_logged": len(self.metrics_history),
            "mlflow_enabled": self.mlflow_tracker.enabled,
            "wandb_enabled": self.wandb_tracker.enabled,
            "tracked_metrics": list(self.tracked_metrics),
            "artifacts_to_save": list(self.artifacts_to_save),
        }
