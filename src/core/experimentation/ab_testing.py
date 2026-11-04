"""
A/B Testing Framework for Autonomous Workflow Training Experiments

Provides statistical experiment management with traffic splitting,
variant assignment, and significance testing.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast
from collections.abc import Sequence
from uuid import UUID, uuid4

import numpy as np
from scipy import stats
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.models import LearningExperience  # Phase 6 Task 6: Migrated to domain module
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class ExperimentStatus(str, Enum):
    """Experiment lifecycle states."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class AssignmentStrategy(str, Enum):
    """Traffic allocation strategies."""

    RANDOM = "random"
    STRATIFIED = "stratified"
    DETERMINISTIC = "deterministic"


@dataclass
class ExperimentVariant:
    """Configuration for an experiment variant."""

    name: str
    description: str
    config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    traffic_weight: float = 0.5

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "name": self.name,
            "description": self.description,
            "config": self.config,
            "traffic_weight": self.traffic_weight,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> "ExperimentVariant":  # TODO(TYPE): replace Any with concrete type
        return cls(
            name=data["name"],
            description=data["description"],
            config=data["config"],
            traffic_weight=data.get("traffic_weight", 0.5),
        )


@dataclass
class StatisticalResults:
    """Results from statistical significance testing."""

    test_name: str
    statistic: float
    p_value: float
    is_significant: bool
    confidence_level: float = 0.95
    effect_size: float | None = None
    sample_size_control: int = 0
    sample_size_treatment: int = 0
    power: float | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "test_name": self.test_name,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "is_significant": self.is_significant,
            "confidence_level": self.confidence_level,
            "effect_size": self.effect_size,
            "sample_size_control": self.sample_size_control,
            "sample_size_treatment": self.sample_size_treatment,
            "power": self.power,
        }


@dataclass
class ExperimentMetrics:
    """Aggregated metrics per variant."""

    variant_name: str
    total_experiences: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    avg_duration: float = 0.0
    avg_confidence: float = 0.0
    task_type_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "variant_name": self.variant_name,
            "total_experiences": self.total_experiences,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "avg_duration": self.avg_duration,
            "avg_confidence": self.avg_confidence,
            "task_type_distribution": self.task_type_distribution,
        }


class ExperimentManager:
    """
    Manages A/B test experiments for autonomous workflow training.

    Provides:
    - Experiment lifecycle management (create, start, pause, stop)
    - Traffic splitting and variant assignment
    - Statistical significance testing
    - Integration with LearningExperience tracking
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """
        Initialize ExperimentManager.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self._assignment_lock = asyncio.Lock()
        self._experiments_cache: dict[
            str, dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type

    async def create_experiment(
        self,
        name: str,
        description: str,
        variants: list[ExperimentVariant],
        assignment_strategy: AssignmentStrategy = AssignmentStrategy.RANDOM,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> UUID:
        """
        Create a new A/B test experiment.

        Args:
            name: Unique experiment name
            description: Experiment description
            variants: List of experiment variants (must include control)
            assignment_strategy: Traffic allocation strategy
            metadata: Additional experiment metadata

        Returns:
            UUID of created experiment

        Raises:
            ValueError: If variants invalid or weights don't sum to 1.0
        """
        # Validate variants
        if len(variants) < 2:
            raise ValueError("Experiment must have at least 2 variants")

        variant_names = [v.name for v in variants]
        if "control" not in variant_names:
            raise ValueError("Experiment must include a 'control' variant")

        total_weight = sum(v.traffic_weight for v in variants)
        if not (0.99 <= total_weight <= 1.01):
            raise ValueError(f"Traffic weights must sum to 1.0, got {total_weight}")

        experiment_id = uuid4()

        experiment_data = {
            "id": experiment_id,
            "name": name,
            "description": description,
            "status": ExperimentStatus.DRAFT.value,
            "assignment_strategy": assignment_strategy.value,
            "variants": [v.to_dict() for v in variants],
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
            "start_date": None,
            "end_date": None,
        }

        # Store in cache (in production, use database table)
        self._experiments_cache[str(experiment_id)] = experiment_data

        logger.info(f"Created experiment: {name} (ID: {experiment_id})")
        return experiment_id

    async def start_experiment(self, experiment_id: UUID) -> bool:
        """
        Start an experiment (activate traffic allocation).

        Args:
            experiment_id: Experiment UUID

        Returns:
            True if started successfully
        """
        exp_key = str(experiment_id)
        if exp_key not in self._experiments_cache:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment = self._experiments_cache[exp_key]

        if experiment["status"] != ExperimentStatus.DRAFT.value:
            raise ValueError(
                f"Can only start DRAFT experiments, current status: {experiment['status']}"
            )

        experiment["status"] = ExperimentStatus.ACTIVE.value
        experiment["start_date"] = datetime.now(timezone.utc)

        logger.info(f"Started experiment: {experiment['name']}")
        return True

    async def pause_experiment(self, experiment_id: UUID) -> bool:
        """Pause an active experiment."""
        exp_key = str(experiment_id)
        if exp_key not in self._experiments_cache:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment = self._experiments_cache[exp_key]

        if experiment["status"] != ExperimentStatus.ACTIVE.value:
            raise ValueError("Can only pause ACTIVE experiments")

        experiment["status"] = ExperimentStatus.PAUSED.value
        logger.info(f"Paused experiment: {experiment['name']}")
        return True

    async def stop_experiment(self, experiment_id: UUID) -> bool:
        """Stop and complete an experiment."""
        exp_key = str(experiment_id)
        if exp_key not in self._experiments_cache:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment = self._experiments_cache[exp_key]

        if experiment["status"] not in [
            ExperimentStatus.ACTIVE.value,
            ExperimentStatus.PAUSED.value,
        ]:
            raise ValueError("Can only stop ACTIVE or PAUSED experiments")

        experiment["status"] = ExperimentStatus.COMPLETED.value
        experiment["end_date"] = datetime.now(timezone.utc)

        logger.info(f"Stopped experiment: {experiment['name']}")
        return True

    async def assign_variant(
        self,
        experiment_id: UUID,
        experience_id: int,
        stratification_key: str | None = None,
    ) -> str:
        """
        Assign an experience to an experiment variant.

        Args:
            experiment_id: Experiment UUID
            experience_id: LearningExperience UUID
            stratification_key: Optional key for stratified assignment

        Returns:
            Assigned variant name
        """
        async with self._assignment_lock:
            exp_key = str(experiment_id)
            if exp_key not in self._experiments_cache:
                raise ValueError(f"Experiment {experiment_id} not found")

            experiment = self._experiments_cache[exp_key]

            if experiment["status"] != ExperimentStatus.ACTIVE.value:
                raise ValueError(
                    f"Cannot assign to non-ACTIVE experiment (status: {experiment['status']})"
                )

            variants = [ExperimentVariant.from_dict(v) for v in experiment["variants"]]
            strategy = AssignmentStrategy(experiment["assignment_strategy"])

            # Assign based on strategy
            if strategy == AssignmentStrategy.RANDOM:
                variant = self._random_assignment(variants)
            elif strategy == AssignmentStrategy.STRATIFIED:
                variant = self._stratified_assignment(variants, stratification_key or "default")
            else:  # DETERMINISTIC
                variant = self._deterministic_assignment(variants, str(experience_id))

            # Store assignment (in production, use database table)
            if "assignments" not in experiment:
                experiment["assignments"] = {}
            experiment["assignments"][str(experience_id)] = {
                "variant": variant.name,
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.debug(f"Assigned experience {experience_id} to variant '{variant.name}'")
            return variant.name

    def _random_assignment(self, variants: list[ExperimentVariant]) -> ExperimentVariant:
        """Random weighted assignment."""
        weights = [v.traffic_weight for v in variants]
        # Use random.choices for weighted selection to avoid numpy type issues
        import random

        selected = random.choices(variants, weights=weights, k=1)[0]
        return selected

    def _stratified_assignment(
        self, variants: list[ExperimentVariant], stratum: str
    ) -> ExperimentVariant:
        """Stratified assignment based on key."""
        # Hash stratum to index
        hash_val = hash(stratum)
        weights = [v.traffic_weight for v in variants]
        cumsum = np.cumsum(weights)

        # Map hash to [0, 1] and select variant
        normalized = (hash_val % 10000) / 10000.0
        idx = int(np.searchsorted(cumsum, normalized))
        return variants[min(idx, len(variants) - 1)]

    def _deterministic_assignment(
        self, variants: list[ExperimentVariant], key: str
    ) -> ExperimentVariant:
        """Deterministic assignment based on key hash."""
        hash_val = hash(key)
        idx = hash_val % len(variants)
        return variants[idx]

    async def get_variant_metrics(
        self, experiment_id: UUID, since: datetime | None = None
    ) -> dict[str, ExperimentMetrics]:
        """
        Get aggregated metrics per variant.

        Args:
            experiment_id: Experiment UUID
            since: Optional start time for metric calculation

        Returns:
            Dict mapping variant name to ExperimentMetrics
        """
        exp_key = str(experiment_id)
        if exp_key not in self._experiments_cache:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment = self._experiments_cache[exp_key]
        assignments = experiment.get("assignments", {})

        if not assignments:
            return {}

        # Map experience IDs to variants
        experience_ids = [int(eid) for eid in assignments.keys()]

        # Query LearningExperience data
        query = select(LearningExperience).where(LearningExperience.id.in_(experience_ids))

        if since:
            query = query.where(LearningExperience.created_at >= since)

        result = await self.db.execute(query)
        experiences = result.scalars().all()

        # Aggregate metrics per variant
        variant_data: dict[str, list[LearningExperience]] = {}

        for exp in experiences:
            variant_name = assignments[str(exp.id)]["variant"]
            if variant_name not in variant_data:
                variant_data[variant_name] = []
            variant_data[variant_name].append(exp)

        # Calculate metrics
        metrics = {}
        for variant_name, exps in variant_data.items():
            total = len(exps)
            success_count = sum(1 for e in exps if e.success)
            success_rate = success_count / total if total > 0 else 0.0

            avg_duration = float(np.mean([e.duration for e in exps if e.duration])) if exps else 0.0
            avg_confidence = (
                float(np.mean([e.confidence for e in exps if e.confidence])) if exps else 0.0
            )

            # Task type distribution
            task_dist: dict[str, int] = {}
            for e in exps:
                task_type = e.task_type or "unknown"
                task_dist[task_type] = task_dist.get(task_type, 0) + 1

            metrics[variant_name] = ExperimentMetrics(
                variant_name=variant_name,
                total_experiences=total,
                success_count=success_count,
                success_rate=success_rate,
                avg_duration=avg_duration,
                avg_confidence=avg_confidence,
                task_type_distribution=task_dist,
            )

        return metrics

    async def calculate_significance(
        self,
        experiment_id: UUID,
        primary_metric: str = "success_rate",
        confidence_level: float = 0.95,
    ) -> list[StatisticalResults]:
        """
        Calculate statistical significance for experiment variants.

        Args:
            experiment_id: Experiment UUID
            primary_metric: Metric to test (success_rate, avg_duration, avg_confidence)
            confidence_level: Confidence level for tests (default 0.95)

        Returns:
            List of StatisticalResults for each variant vs control
        """
        metrics = await self.get_variant_metrics(experiment_id)

        if "control" not in metrics:
            raise ValueError("No control variant found")

        metrics["control"]
        results = []

        for variant_name, variant_metrics in metrics.items():
            if variant_name == "control":
                continue

            # Get raw data for statistical tests
            exp_key = str(experiment_id)
            experiment = self._experiments_cache[exp_key]
            assignments = experiment.get("assignments", {})

            control_ids = [int(eid) for eid, a in assignments.items() if a["variant"] == "control"]
            variant_ids = [
                int(eid) for eid, a in assignments.items() if a["variant"] == variant_name
            ]

            # Query experiences
            control_query = select(LearningExperience).where(LearningExperience.id.in_(control_ids))
            variant_query = select(LearningExperience).where(LearningExperience.id.in_(variant_ids))

            control_result = await self.db.execute(control_query)
            variant_result = await self.db.execute(variant_query)

            control_exps = control_result.scalars().all()
            variant_exps = variant_result.scalars().all()

            # Perform appropriate statistical test
            if primary_metric == "success_rate":
                result = self._chi_square_test(control_exps, variant_exps, confidence_level)
            elif primary_metric in ["avg_duration", "avg_confidence"]:
                result = self._t_test(control_exps, variant_exps, primary_metric, confidence_level)
            else:
                raise ValueError(f"Unknown metric: {primary_metric}")

            results.append(result)

        return results

    def _chi_square_test(
        self,
        control: Sequence[LearningExperience],
        treatment: Sequence[LearningExperience],
        confidence_level: float,
    ) -> StatisticalResults:
        """Chi-square test for success rate differences."""
        control_success = sum(1 for e in control if e.success)
        control_fail = len(control) - control_success

        treatment_success = sum(1 for e in treatment if e.success)
        treatment_fail = len(treatment) - treatment_success

        # Contingency table
        observed = np.array([[control_success, control_fail], [treatment_success, treatment_fail]])

        _chi2, _p_value, _dof, _expected = stats.chi2_contingency(observed)
        chi2 = float(_chi2)  # pyright: ignore[reportArgumentType]
        p_value = float(_p_value)  # pyright: ignore[reportArgumentType]

        # Effect size (Cramer's V)
        n = observed.sum()
        effect_size = float(np.sqrt(chi2 / n)) if n > 0 else 0.0

        alpha = 1 - confidence_level
        is_significant = p_value < alpha

        return StatisticalResults(
            test_name="chi_square",
            statistic=chi2,
            p_value=p_value,
            is_significant=is_significant,
            confidence_level=confidence_level,
            effect_size=effect_size,
            sample_size_control=len(control),
            sample_size_treatment=len(treatment),
        )

    def _t_test(
        self,
        control: Sequence[LearningExperience],
        treatment: Sequence[LearningExperience],
        metric: str,
        confidence_level: float,
    ) -> StatisticalResults:
        """Independent t-test for continuous metrics."""
        if metric == "avg_duration":
            control_values = [e.duration for e in control if e.duration]
            treatment_values = [e.duration for e in treatment if e.duration]
        elif metric == "avg_confidence":
            control_values = [e.confidence for e in control if e.confidence]
            treatment_values = [e.confidence for e in treatment if e.confidence]
        else:
            raise ValueError(f"Invalid metric for t-test: {metric}")

        if not control_values or not treatment_values:
            return StatisticalResults(
                test_name="t_test",
                statistic=0.0,
                p_value=1.0,
                is_significant=False,
                confidence_level=confidence_level,
                sample_size_control=len(control),
                sample_size_treatment=len(treatment),
            )

        # Independent t-test
        _stat, _pval = stats.ttest_ind(control_values, treatment_values)
        statistic = float(_stat)  # pyright: ignore[reportArgumentType]
        p_value = float(_pval)  # pyright: ignore[reportArgumentType]

        # Cohen's d effect size
        pooled_std = np.sqrt(
            (
                (len(control_values) - 1) * np.var(control_values, ddof=1)
                + (len(treatment_values) - 1) * np.var(treatment_values, ddof=1)
            )
            / (len(control_values) + len(treatment_values) - 2)
        )

        effect_size = (
            float(np.mean(treatment_values) - np.mean(control_values)) / pooled_std
            if pooled_std > 0
            else 0.0
        )

        alpha = 1 - confidence_level
        is_significant = p_value < alpha

        return StatisticalResults(
            test_name="t_test",
            statistic=statistic,
            p_value=p_value,
            is_significant=is_significant,
            confidence_level=confidence_level,
            effect_size=effect_size,
            sample_size_control=len(control),
            sample_size_treatment=len(treatment),
        )

    async def get_experiment(
        self, experiment_id: UUID
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get experiment details."""
        exp_key = str(experiment_id)
        return self._experiments_cache.get(exp_key)

    async def list_experiments(
        self, status: ExperimentStatus | None = None
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """List experiments, optionally filtered by status."""
        experiments = list(self._experiments_cache.values())

        if status:
            experiments = [e for e in experiments if e["status"] == status.value]

        return experiments
