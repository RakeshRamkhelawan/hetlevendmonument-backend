"""
MLflow Model Registry Workflow Automation
Manages model lifecycle with automated promotion rules

This module provides automated model registry management including:
- Automated promotion from None -> Staging -> Production -> Archived
- Version comparison and rollback capabilities
- Promotion rules engine with configurable thresholds
- Model lifecycle history tracking

Author: ML Production Engineer
Date: 2025-10-17
Status: Production-Ready
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, cast

from anyio import to_thread

# Conditional MLflow import for testing environments
if TYPE_CHECKING:
    # Always use real types during type checking
    from mlflow.entities.model_registry import ModelVersion
    from mlflow.exceptions import MlflowException

    MLFLOW_AVAILABLE = True
else:
    if os.environ.get("TESTING") == "1":
        from unittest.mock import MagicMock

        ModelVersion = MagicMock
        MlflowException = Exception
    else:
        try:
            from mlflow.entities.model_registry import ModelVersion
            from mlflow.exceptions import MlflowException

            MLFLOW_AVAILABLE = True
        except ImportError:
            from unittest.mock import MagicMock

            MLFLOW_AVAILABLE = False
            ModelVersion = MagicMock
            MlflowException = Exception

from src.core.learning.mlflow_integration import MLflowTracker

logger = logging.getLogger(__name__)


class ModelStage(Enum):
    """Model lifecycle stages."""

    NONE = "None"
    STAGING = "Staging"
    PRODUCTION = "Production"
    ARCHIVED = "Archived"


@dataclass
class PromotionRules:
    """
    Rules for automated model promotion.

    Staging requirements:
    - Minimum accuracy and F1 score thresholds

    Production requirements:
    - Higher accuracy threshold
    - Validation period (days in staging)
    - Minimum number of validation runs
    """

    staging_min_accuracy: float = 0.85
    staging_min_f1: float = 0.80
    production_min_accuracy: float = 0.90
    production_validation_days: int = 7
    production_min_runs: int = 10

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return asdict(self)


class ModelRegistryManager:
    """
    Automated MLflow Model Registry management.

    Features:
    - Automatic model registration and promotion
    - Rule-based promotion logic
    - Version comparison and rollback
    - Lifecycle history tracking
    - Thread-safe operations
    """

    def __init__(
        self,
        mlflow_tracker: MLflowTracker,
        promotion_rules: PromotionRules | None = None,
    ) -> None:
        """
        Initialize Model Registry Manager.

        Args:
            mlflow_tracker: MLflow tracker instance
            promotion_rules: Optional custom promotion rules
        """
        self.tracker = mlflow_tracker
        self.client: Any = (  # TODO(TYPE): replace Any with concrete type
            mlflow_tracker.client
        )  # mlflow has no stubs; Any silences cascade attr errors  # TODO(TYPE): replace Any with concrete type
        self.rules = promotion_rules or PromotionRules()
        self.logger = logging.getLogger(__name__)

        # Thread pool for async operations
        self._executor = ThreadPoolExecutor(max_workers=2)

        self.logger.info(
            f"ModelRegistryManager initialized with rules: "
            f"staging_accuracy={self.rules.staging_min_accuracy}, "
            f"production_accuracy={self.rules.production_min_accuracy}"
        )

    async def register_model(self, model_name: str, run_id: str, metrics: dict[str, float]) -> str:
        """
        Register model and auto-promote if rules met.

        Args:
            model_name: Name for registered model
            run_id: MLflow run ID containing the model
            metrics: Model metrics (accuracy, f1_score, etc.)

        Returns:
            Model version string
        """
        try:
            self.logger.info(f"Registering model {model_name} from run {run_id}")

            # Run blocking MLflow operations in executor
            # Get or create registered model
            model_version = await to_thread.run_sync(self._register_model_sync, model_name, run_id)

            version = int(model_version.version)
            self.logger.info(f"Model registered as version {version}")

            # Set metrics as tags
            await self._set_version_metrics(model_name, version, metrics)

            # Check for auto-promotion to staging
            if self._meets_staging_criteria(metrics):
                self.logger.info(f"Version {version} meets staging criteria - promoting")
                success = await self.promote_to_staging(model_name, version, metrics)
                if success:
                    self.logger.info(f"Version {version} auto-promoted to Staging")
            else:
                self.logger.info(f"Version {version} does not meet staging criteria yet")

            return str(version)

        except Exception as e:
            self.logger.error(f"Failed to register model: {e}", exc_info=True)
            raise

    def _register_model_sync(self, model_name: str, run_id: str) -> "ModelVersion":
        """Synchronous model registration (runs in executor)."""
        try:
            # Try to get existing registered model
            try:
                self.client.get_registered_model(model_name)
            except MlflowException:
                # Create registered model if doesn't exist
                self.client.create_registered_model(model_name)

            # Create model version from run
            model_uri = f"runs:/{run_id}/model"
            model_version = self.client.create_model_version(
                name=model_name, source=model_uri, run_id=run_id
            )

            return cast("ModelVersion", model_version)

        except Exception as e:
            self.logger.error(f"Sync model registration failed: {e}")
            raise

    async def _set_version_metrics(
        self, model_name: str, version: int, metrics: dict[str, float]
    ) -> None:
        """Set metrics as tags on model version."""
        try:
            for metric_name, metric_value in metrics.items():
                await to_thread.run_sync(
                    self.client.set_model_version_tag,
                    model_name,
                    str(version),
                    f"metric_{metric_name}",
                    str(metric_value),
                )

            self.logger.debug(f"Set {len(metrics)} metrics on version {version}")

        except Exception as e:
            self.logger.warning(f"Failed to set version metrics: {e}")

    def _meets_staging_criteria(self, metrics: dict[str, float]) -> bool:
        """Check if metrics meet staging criteria."""
        accuracy = metrics.get("accuracy", 0.0)
        f1_score = metrics.get("f1_score", 0.0)

        return accuracy >= self.rules.staging_min_accuracy and f1_score >= self.rules.staging_min_f1

    async def promote_to_staging(
        self, model_name: str, version: int, metrics: dict[str, float]
    ) -> bool:
        """
        Promote model to staging if meets criteria.

        Args:
            model_name: Name of registered model
            version: Model version number
            metrics: Model metrics

        Returns:
            True if promoted successfully
        """
        try:
            # Verify criteria
            if not self._meets_staging_criteria(metrics):
                self.logger.warning(
                    f"Version {version} does not meet staging criteria: "
                    f"accuracy={metrics.get('accuracy', 0):.3f} "
                    f"(required {self.rules.staging_min_accuracy})"
                )
                return False

            # Transition to staging
            await to_thread.run_sync(
                self._transition_version_sync,
                model_name,
                version,
                ModelStage.STAGING.value,
            )

            # Add promotion metadata
            await to_thread.run_sync(
                self.client.set_model_version_tag,
                model_name,
                str(version),
                "promoted_to_staging_at",
                datetime.now(timezone.utc).isoformat(),
            )

            self.logger.info(f"Successfully promoted version {version} to Staging")
            return True

        except Exception as e:
            self.logger.error(f"Failed to promote to staging: {e}", exc_info=True)
            return False

    async def promote_to_production(
        self,
        model_name: str,
        version: int,
        validation_results: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Promote to production after validation period.

        Args:
            model_name: Name of registered model
            version: Model version number
            validation_results: Validation results including:
                - days_in_staging: Days spent in staging
                - validation_runs: Number of validation runs
                - metrics: Current metrics

        Returns:
            True if promoted successfully
        """
        try:
            # Extract validation data
            days_in_staging = validation_results.get("days_in_staging", 0)
            validation_runs = validation_results.get("validation_runs", 0)
            metrics = validation_results.get("metrics", {})
            accuracy = metrics.get("accuracy", 0.0)

            # Check production criteria
            if days_in_staging < self.rules.production_validation_days:
                self.logger.warning(
                    f"Version {version} has only been in staging for {days_in_staging} days "
                    f"(required {self.rules.production_validation_days})"
                )
                return False

            if validation_runs < self.rules.production_min_runs:
                self.logger.warning(
                    f"Version {version} has only {validation_runs} validation runs "
                    f"(required {self.rules.production_min_runs})"
                )
                return False

            if accuracy < self.rules.production_min_accuracy:
                self.logger.warning(
                    f"Version {version} accuracy {accuracy:.3f} below production threshold "
                    f"{self.rules.production_min_accuracy}"
                )
                return False

            # Archive current production model
            current_prod = await self.get_production_model(model_name)
            if current_prod:
                self.logger.info(f"Archiving current production version {current_prod.version}")
                await self._transition_version(
                    model_name, int(current_prod.version), ModelStage.ARCHIVED.value
                )

            # Promote to production
            await to_thread.run_sync(
                self._transition_version_sync,
                model_name,
                version,
                ModelStage.PRODUCTION.value,
            )

            # Add promotion metadata
            await to_thread.run_sync(
                self.client.set_model_version_tag,
                model_name,
                str(version),
                "promoted_to_production_at",
                datetime.now(timezone.utc).isoformat(),
            )

            self.logger.info(f"Successfully promoted version {version} to Production")
            return True

        except Exception as e:
            self.logger.error(f"Failed to promote to production: {e}", exc_info=True)
            return False

    def _transition_version_sync(self, model_name: str, version: int, stage: str) -> None:
        """Synchronous version transition (runs in executor)."""
        self.client.transition_model_version_stage(
            name=model_name, version=str(version), stage=stage
        )

    async def _transition_version(self, model_name: str, version: int, stage: str) -> None:
        """Async wrapper for version transition."""
        await to_thread.run_sync(self._transition_version_sync, model_name, version, stage)

    async def rollback(self, model_name: str, target_version: int) -> bool:
        """
        Rollback production to specific version.

        Args:
            model_name: Name of registered model
            target_version: Version to rollback to

        Returns:
            True if rollback successful
        """
        try:
            self.logger.info(f"Rolling back {model_name} to version {target_version}")

            # Get current production version
            current_prod = await self.get_production_model(model_name)
            if current_prod:
                current_version = int(current_prod.version)

                # Archive current production
                await self._transition_version(
                    model_name, current_version, ModelStage.ARCHIVED.value
                )

                self.logger.info(f"Archived version {current_version}")

            # Promote target version to production
            await self._transition_version(model_name, target_version, ModelStage.PRODUCTION.value)

            # Add rollback metadata
            await to_thread.run_sync(
                self.client.set_model_version_tag,
                model_name,
                str(target_version),
                "rolled_back_at",
                datetime.now(timezone.utc).isoformat(),
            )

            self.logger.info(f"Successfully rolled back to version {target_version}")
            return True

        except Exception as e:
            self.logger.error(f"Rollback failed: {e}", exc_info=True)
            return False

    async def compare_versions(
        self, model_name: str, v1: int, v2: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Compare metrics between versions.

        Args:
            model_name: Name of registered model
            v1: First version number
            v2: Second version number

        Returns:
            Comparison dictionary with metrics diff
        """
        try:
            # Get both versions
            version1 = await to_thread.run_sync(self.client.get_model_version, model_name, str(v1))
            version2 = await to_thread.run_sync(self.client.get_model_version, model_name, str(v2))

            # Extract metrics from tags
            metrics1 = self._extract_metrics_from_tags(version1.tags)
            metrics2 = self._extract_metrics_from_tags(version2.tags)

            # Calculate metric differences
            differences: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            all_metrics = set(metrics1.keys()) | set(metrics2.keys())
            for metric in all_metrics:
                val1 = metrics1.get(metric, 0.0)
                val2 = metrics2.get(metric, 0.0)
                diff = val2 - val1
                pct_change = (diff / val1 * 100) if val1 != 0 else 0

                differences[metric] = {
                    "v1_value": val1,
                    "v2_value": val2,
                    "absolute_diff": diff,
                    "percent_change": pct_change,
                    "better": val2 > val1,
                }

            comparison = {
                "model_name": model_name,
                "version_1": {
                    "version": v1,
                    "stage": version1.current_stage,
                    "metrics": metrics1,
                },
                "version_2": {
                    "version": v2,
                    "stage": version2.current_stage,
                    "metrics": metrics2,
                },
                "differences": differences,
            }

            return comparison

        except Exception as e:
            self.logger.error(f"Version comparison failed: {e}", exc_info=True)
            return {"error": str(e)}

    def _extract_metrics_from_tags(self, tags: dict[str, str]) -> dict[str, float]:
        """Extract metrics from version tags."""
        metrics: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key, value in tags.items():
            if key.startswith("metric_"):
                metric_name = key.replace("metric_", "")
                try:
                    metrics[metric_name] = float(value)
                except ValueError:
                    pass
        return metrics

    async def archive_old_versions(self, model_name: str, keep_last_n: int = 5) -> int:
        """
        Archive old model versions.

        Args:
            model_name: Name of registered model
            keep_last_n: Number of recent versions to keep

        Returns:
            Number of versions archived
        """
        try:
            # Get all versions
            versions = await to_thread.run_sync(
                self.client.search_model_versions, f"name='{model_name}'"
            )

            # Sort by version number (descending)
            versions = sorted(versions, key=lambda v: int(v.version), reverse=True)

            # Archive old versions (skip production/staging and recent)
            archived_count = 0
            for version in versions[keep_last_n:]:
                if version.current_stage not in [
                    ModelStage.PRODUCTION.value,
                    ModelStage.STAGING.value,
                ]:
                    await self._transition_version(
                        model_name, int(version.version), ModelStage.ARCHIVED.value
                    )
                    archived_count += 1

            self.logger.info(f"Archived {archived_count} old versions of {model_name}")
            return archived_count

        except Exception as e:
            self.logger.error(f"Failed to archive old versions: {e}", exc_info=True)
            return 0

    async def get_production_model(self, model_name: str) -> Optional["ModelVersion"]:
        """
        Get current production model version.

        Args:
            model_name: Name of registered model

        Returns:
            Production ModelVersion or None
        """
        try:
            versions = await to_thread.run_sync(
                self.client.search_model_versions, f"name='{model_name}'"
            )

            # Find production version
            for version in versions:
                if version.current_stage == ModelStage.PRODUCTION.value:
                    return cast("ModelVersion", version)

            return None

        except Exception as e:
            self.logger.error(f"Failed to get production model: {e}", exc_info=True)
            return None

    async def get_lifecycle_history(
        self, model_name: str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get complete promotion history.

        Args:
            model_name: Name of registered model

        Returns: List[Any] of lifecycle events  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # Get all versions
            versions = await to_thread.run_sync(
                self.client.search_model_versions, f"name='{model_name}'"
            )

            # Build history
            history: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for version in sorted(versions, key=lambda v: int(v.version)):
                event = {
                    "version": int(version.version),
                    "current_stage": version.current_stage,
                    "creation_timestamp": version.creation_timestamp,
                    "last_updated_timestamp": version.last_updated_timestamp,
                    "tags": version.tags,
                }

                # Extract promotion timestamps from tags
                if "promoted_to_staging_at" in version.tags:
                    event["promoted_to_staging_at"] = version.tags["promoted_to_staging_at"]
                if "promoted_to_production_at" in version.tags:
                    event["promoted_to_production_at"] = version.tags["promoted_to_production_at"]
                if "rolled_back_at" in version.tags:
                    event["rolled_back_at"] = version.tags["rolled_back_at"]

                history.append(event)

            return history

        except Exception as e:
            self.logger.error(f"Failed to get lifecycle history: {e}", exc_info=True)
            return []
