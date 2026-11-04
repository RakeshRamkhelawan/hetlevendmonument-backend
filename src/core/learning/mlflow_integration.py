"""
MLflow Integration Module for Autonomous Workflow Training.

Provides experiment tracking, parameter logging, metrics monitoring,
and model versioning for production training workflows.

SECURITY NOTE: mlflow 3.4.0 has known security vulnerabilities (CVE-2024-37052 through CVE-2024-37060)
that can lead to arbitrary code execution via malicious ML models. Only load models from trusted sources.
See Kanban Board "Known Issues Without Fix" section for details.

Author: Generated via Generale Repetitie Protocol
Date: 2025-10-17
Status: Production-Ready
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional, cast
from collections.abc import Generator

# Optional ML dependency - only import if available
try:
    import mlflow
    from mlflow.tracking import MlflowClient  # pyright: ignore[reportAssignmentType]

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None  # type: ignore[assignment]  # module sentinel; guarded by MLFLOW_AVAILABLE

    class MlflowClient:  # type: ignore[no-redef]
        """Fallback stub -- mlflow unavailable. Never instantiated at runtime."""

        def __init__(self, *args: object, **kwargs: object) -> None: ...


logger = logging.getLogger(__name__)


class MLflowTracker:
    """
    Production-grade MLflow experiment tracker for autonomous workflows.

    Features:
    - Automatic experiment creation and management
    - Parameter and metric logging
    - Model versioning and artifact storage
    - Error handling and logging
    - Context manager support for clean tracking sessions
    """

    def __init__(
        self,
        tracking_uri: str | None = None,
        experiment_name: str = "autonomous_workflow_training",
        artifact_location: str | None = None,
    ) -> None:
        """
        Initialize MLflow tracker.

        Args:
            tracking_uri: MLflow tracking server URI (defaults to env var MLFLOW_TRACKING_URI)
            experiment_name: Name of the MLflow experiment
            artifact_location: Location to store artifacts (optional)
        """
        if not MLFLOW_AVAILABLE or mlflow is None or MlflowClient is None:
            raise ImportError("MLflow is not available. Install it with: pip install mlflow")

        # Set tracking URI from parameter or environment
        self.tracking_uri = str(
            tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        )
        mlflow.set_tracking_uri(self.tracking_uri)

        self.experiment_name = experiment_name
        self.artifact_location = artifact_location

        # Initialize client -- cast to Any so pyright doesn't chase stubs for MlflowClient attributes
        self.client = cast(
            Any,  # TODO(TYPE): replace Any with concrete type
            MlflowClient(tracking_uri=self.tracking_uri),
        )

        # Create or get experiment
        self._setup_experiment()

        logger.info(
            f"MLflowTracker initialized: tracking_uri={self.tracking_uri}, "
            f"experiment={self.experiment_name}"
        )

    def _setup_experiment(self) -> None:
        """Create experiment if it doesn't exist."""
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            experiment = mlflow.get_experiment_by_name(self.experiment_name)

            if experiment is None:
                # Create new experiment
                experiment_id = mlflow.create_experiment(
                    name=self.experiment_name, artifact_location=self.artifact_location
                )
                logger.info(
                    f"Created MLflow experiment: {self.experiment_name} (ID: {experiment_id})"
                )
            else:
                experiment_id = experiment.experiment_id
                logger.debug(
                    f"Using existing experiment: {self.experiment_name} (ID: {experiment_id})"
                )

            # Set as active experiment
            mlflow.set_experiment(self.experiment_name)
            self.experiment_id = experiment_id

        except Exception as e:
            logger.error(f"Failed to setup MLflow experiment: {e}", exc_info=True)
            raise

    @contextmanager
    def start_run(
        self, run_name: str | None = None, tags: dict[str, str] | None = None
    ) -> Generator[Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Context manager for MLflow tracking runs.

        Usage:
            with tracker.start_run(run_name="training_session_1"):
                tracker.log_params({"lr": 0.001})
                tracker.log_metric("loss", 0.5)

        Args:
            run_name: Optional name for the run
            tags: Optional tags for the run

        Yields:
            Active MLflow run
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            # Generate run name if not provided
            if run_name is None:
                run_name = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            # Add default tags
            default_tags = {
                "framework": "pytorch",
                "pipeline": "DynamicTrainingPipeline",
                "environment": os.getenv("ENVIRONMENT", "development"),
            }
            if tags:
                default_tags.update(tags)

            # Start run
            run = mlflow.start_run(run_name=run_name, tags=default_tags)
            logger.info(f"Started MLflow run: {run_name} (ID: {run.info.run_id})")

            yield run

        except Exception as e:
            logger.error(f"Error in MLflow run: {e}", exc_info=True)
            raise

        finally:
            # End run
            mlflow.end_run()
            logger.debug(f"Ended MLflow run: {run_name}")

    def log_params(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Log training parameters.

        Args:
            params: Dict[str, Any]ionary of parameter names and values  # TODO(TYPE): replace Any with concrete type
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            for key, value in params.items():
                # Convert to string if needed
                param_value = (
                    str(value) if not isinstance(value, (int, float, str, bool)) else value
                )
                mlflow.log_param(key, param_value)

            logger.debug(f"Logged {len(params)} parameters to MLflow")

        except Exception as e:
            logger.error(f"Failed to log parameters: {e}", exc_info=True)

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        """
        Log a single metric.

        Args:
            key: Metric name
            value: Metric value
            step: Optional step number for time-series metrics
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            mlflow.log_metric(key, value, step=step)
            logger.debug(f"Logged metric: {key}={value} (step={step})")

        except Exception as e:
            logger.error(f"Failed to log metric {key}: {e}", exc_info=True)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        """
        Log multiple metrics at once.

        Args:
            metrics: Dict[str, Any]ionary of metric names and values  # TODO(TYPE): replace Any with concrete type
            step: Optional step number for time-series metrics
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            mlflow.log_metrics(metrics, step=step)
            logger.debug(f"Logged {len(metrics)} metrics to MLflow (step={step})")

        except Exception as e:
            logger.error(f"Failed to log metrics: {e}", exc_info=True)

    def log_artifact(self, local_path: str, artifact_path: str | None = None) -> None:
        """
        Log a file or directory as an artifact.

        Args:
            local_path: Path to local file or directory
            artifact_path: Optional artifact path within run (subdirectory)
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            mlflow.log_artifact(local_path, artifact_path=artifact_path)
            logger.debug(f"Logged artifact: {local_path} -> {artifact_path}")

        except Exception as e:
            logger.error(f"Failed to log artifact {local_path}: {e}", exc_info=True)

    def log_model(
        self,
        model: Any,  # TODO(TYPE): replace Any with concrete type
        artifact_path: str = "model",
        registered_model_name: str | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Log a PyTorch model.

        Args:
            model: PyTorch model to log
            artifact_path: Path within run to store model
            registered_model_name: Optional name for model registry
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            mlflow.pytorch.log_model(  # pyright: ignore[reportPrivateImportUsage]
                pytorch_model=model,
                artifact_path=artifact_path,
                registered_model_name=registered_model_name,
            )

            logger.info(
                f"Logged model to MLflow: {artifact_path} (registered_name={registered_model_name})"
            )

        except Exception as e:
            logger.error(f"Failed to log model: {e}", exc_info=True)

    def set_tag(self, key: str, value: str) -> None:
        """
        Set a tag for the current run.

        Args:
            key: Tag name
            value: Tag value
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            mlflow.set_tag(key, value)
            logger.debug(f"Set tag: {key}={value}")

        except Exception as e:
            logger.error(f"Failed to set tag {key}: {e}", exc_info=True)

    def set_tags(self, tags: dict[str, str]) -> None:
        """
        Set multiple tags for the current run.

        Args:
            tags: Dict[str, Any]ionary of tag names and values  # TODO(TYPE): replace Any with concrete type
        """
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        try:
            mlflow.set_tags(tags)
            logger.debug(f"Set {len(tags)} tags")

        except Exception as e:
            logger.error(f"Failed to set tags: {e}", exc_info=True)

    def get_run_info(
        self, run_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get information about a specific run.

        Args:
            run_id: MLflow run ID

        Returns: Dict[str, Any]ionary with run information  # TODO(TYPE): replace Any with concrete type
        """
        try:
            run = self.client.get_run(run_id)

            return {
                "run_id": run.info.run_id,
                "experiment_id": run.info.experiment_id,
                "status": run.info.status,
                "start_time": run.info.start_time,
                "end_time": run.info.end_time,
                "artifact_uri": run.info.artifact_uri,
                "params": run.data.params,
                "metrics": run.data.metrics,
                "tags": run.data.tags,
            }

        except Exception as e:
            logger.error(f"Failed to get run info for {run_id}: {e}", exc_info=True)
            return {}

    def search_runs(
        self, filter_string: str | None = None, max_results: int = 100
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Search for runs in the current experiment.

        Args:
            filter_string: Optional filter query (e.g., "metrics.loss < 0.5")
            max_results: Maximum number of results to return

        Returns: List[Any] of run information dictionaries  # TODO(TYPE): replace Any with concrete type
        """
        try:
            runs = self.client.search_runs(
                experiment_ids=[self.experiment_id],
                filter_string=filter_string or "",
                max_results=max_results,
            )

            return [
                {
                    "run_id": run.info.run_id,
                    "status": run.info.status,
                    "start_time": run.info.start_time,
                    "params": run.data.params,
                    "metrics": run.data.metrics,
                }
                for run in runs
            ]

        except Exception as e:
            logger.error(f"Failed to search runs: {e}", exc_info=True)
            return []

    def get_best_run(
        self, metric_name: str, mode: str = "min"
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Get the best run based on a specific metric.

        Args:
            metric_name: Name of the metric to optimize
            mode: "min" or "max" for optimization direction

        Returns:
            Best run information or None
        """
        try:
            # Search all runs
            runs = self.search_runs()

            if not runs:
                logger.warning("No runs found in experiment")
                return None

            # Filter runs with the metric
            runs_with_metric = [run for run in runs if metric_name in run.get("metrics", {})]

            if not runs_with_metric:
                logger.warning(f"No runs found with metric: {metric_name}")
                return None

            # Find best run
            if mode == "min":
                best_run = min(runs_with_metric, key=lambda r: r["metrics"][metric_name])
            else:  # mode == "max"
                best_run = max(runs_with_metric, key=lambda r: r["metrics"][metric_name])

            logger.info(
                f"Best run ({mode} {metric_name}): "
                f"run_id={best_run['run_id']}, "
                f"value={best_run['metrics'][metric_name]}"
            )

            return best_run

        except Exception as e:
            logger.error(f"Failed to get best run: {e}", exc_info=True)
            return None
