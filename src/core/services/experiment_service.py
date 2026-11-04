"""
Experiment Service for A/B Testing

Manages experiment lifecycle, variant assignment, and event tracking.
Used by the Pack Selector for A/B testing different scoring strategies.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models.experiment import (
    Experiment,
    ExperimentAssignment,
    ExperimentEvent,
    ExperimentVariant,
)

logger = logging.getLogger(__name__)


class ExperimentService:
    """Service for managing A/B testing experiments."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def create_experiment(
        self,
        tenant_id: int,
        name: str,
        description: str,
        variants: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        traffic_split: float = 0.5,
        created_by: UUID | None = None,
    ) -> Experiment:
        """Create new experiment with variants.

        Args:
            tenant_id: Tenant that owns this experiment (ADR-005: NOT NULL)
            name: Experiment name
            description: Experiment description
            variants: List of variant configs (e.g., [{"name": "control"}, ...])
            traffic_split: Traffic split for treatment (default 0.5 = 50/50)
            created_by: UUID of creator

        Returns:
            Created Experiment instance
        """
        experiment = Experiment(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            start_date=datetime.now(timezone.utc),
            status="draft",
            traffic_split=traffic_split,
            created_by=created_by or uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self.session.add(experiment)
        await self.session.flush()

        # Create variants
        for variant_config in variants:
            variant = ExperimentVariant(
                id=uuid4(),
                experiment_id=experiment.id,
                name=variant_config["name"],
                config=variant_config.get("config"),
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(variant)

        await self.session.commit()
        await self.session.refresh(experiment)

        logger.info(
            f"Created experiment '{name}' with {len(variants)} variants, "
            f"traffic_split={traffic_split}"
        )

        return experiment

    def assign_variant(self, experiment_id: UUID, company_id: UUID) -> str:
        """Consistent variant assignment using deterministic hash.

        Uses a hash of company_id + experiment_id to ensure the same
        company always gets the same variant for a given experiment.

        Args:
            experiment_id: UUID of the experiment
            company_id: UUID of the company

        Returns:
            Variant name ("control" or "treatment")
        """
        # Create deterministic hash from company_id + experiment_id
        # Note: MD5 is used for consistent bucketing, not security
        hash_input = f"{str(company_id)}:{str(experiment_id)}"
        hash_value = int(hashlib.md5(hash_input.encode(), usedforsecurity=False).hexdigest(), 16)

        # Get experiment traffic split (default 50/50)
        # Note: This method is synchronous, traffic_split should be
        # fetched before calling if needed from async context
        # For now, return hash-based assignment logic

        # Use modulo 100 for percentage-based assignment
        bucket = hash_value % 100

        # Traffic split percentage (50 = 50% to treatment)
        # For simple A/B, 0-49 = control, 50-99 = treatment (when split=0.5)
        split_percentage = int(0.5 * 100)  # Default 50%

        if bucket < split_percentage:
            return "treatment"
        else:
            return "control"

    async def assign_variant_with_split(self, experiment_id: UUID, company_id: UUID) -> str:
        """Assign variant with actual traffic split from experiment config.

        Args:
            experiment_id: UUID of the experiment
            company_id: UUID of the company

        Returns:
            Variant name ("control" or "treatment")
        """
        # Get experiment to check traffic split
        result = await self.session.execute(
            select(Experiment).where(Experiment.id == experiment_id)
        )
        experiment = result.scalar_one_or_none()

        if not experiment:
            logger.warning(f"Experiment {experiment_id} not found, defaulting to control")
            return "control"

        # Create deterministic hash
        # Note: MD5 is used for consistent bucketing, not security
        hash_input = f"{str(company_id)}:{str(experiment_id)}"
        hash_value = int(hashlib.md5(hash_input.encode(), usedforsecurity=False).hexdigest(), 16)
        bucket = hash_value % 100

        # Use experiment's traffic split
        split_percentage = int(experiment.traffic_split * 100)

        variant = "treatment" if bucket < split_percentage else "control"

        # Check if assignment already exists
        existing = await self.session.execute(
            select(ExperimentAssignment).where(
                and_(
                    ExperimentAssignment.experiment_id == experiment_id,
                    ExperimentAssignment.company_id == company_id,
                )
            )
        )
        assignment = existing.scalar_one_or_none()

        if not assignment:
            # Create new assignment record
            assignment = ExperimentAssignment(
                id=uuid4(),
                experiment_id=experiment_id,
                company_id=company_id,
                variant=variant,
                assigned_at=datetime.now(timezone.utc),
            )
            self.session.add(assignment)
            await self.session.commit()
            logger.debug(
                f"New assignment: company={company_id}, experiment={experiment_id}, "
                f"variant={variant}"
            )
        else:
            # Return existing assignment for consistency
            variant = assignment.variant
            logger.debug(f"Existing assignment: company={company_id}, variant={variant}")

        return variant

    async def get_active_experiments(self) -> list[Experiment]:
        """Get running experiments.

        Returns:
            List of active experiments with status 'running'
        """
        result = await self.session.execute(
            select(Experiment).where(
                and_(
                    Experiment.status == "running",
                    Experiment.start_date <= datetime.now(timezone.utc),
                )
            )
        )
        experiments = list(result.scalars().all())

        logger.debug(f"Found {len(experiments)} active experiments")
        return experiments

    async def get_experiment_by_name(self, name: str) -> Experiment | None:
        """Get experiment by name.

        Args:
            name: Experiment name

        Returns:
            Experiment or None
        """
        result = await self.session.execute(select(Experiment).where(Experiment.name == name))
        return result.scalar_one_or_none()

    async def track_event(
        self,
        experiment_id: UUID,
        company_id: UUID,
        event_type: str,
        variant: str,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ExperimentEvent:
        """Track experiment event.

        Args:
            experiment_id: UUID of the experiment
            company_id: UUID of the company
            event_type: Type of event (e.g., "exposed", "converted")
            variant: Variant assigned ("control" or "treatment")
            metadata: Optional event metadata

        Returns:
            Created ExperimentEvent
        """
        event = ExperimentEvent(
            id=uuid4(),
            experiment_id=experiment_id,
            company_id=company_id,
            event_type=event_type,
            variant=variant,
            event_metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )

        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)

        logger.debug(
            f"Tracked event: {event_type} for company={company_id}, "
            f"experiment={experiment_id}, variant={variant}"
        )

        return event

    async def calculate_metrics(
        self, experiment_id: UUID
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Calculate conversion rates per variant.

        Args:
            experiment_id: UUID of the experiment

        Returns:
            Dict with metrics per variant including:
            - exposures: Number of times variant was exposed
            - conversions: Number of conversions for variant
            - conversion_rate: conversions / exposures
        """
        # Get all events for this experiment
        result = await self.session.execute(
            select(
                ExperimentEvent.variant,
                ExperimentEvent.event_type,
                func.count(ExperimentEvent.id).label("count"),
            )
            .where(ExperimentEvent.experiment_id == experiment_id)
            .group_by(ExperimentEvent.variant, ExperimentEvent.event_type)
        )

        # Initialize metrics dict
        metrics: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

        for row in result:
            variant = row.variant
            event_type = row.event_type
            count = row.count

            if variant not in metrics:
                metrics[variant] = {"exposures": 0, "conversions": 0}

            if event_type == "exposed":
                metrics[variant]["exposures"] = count
            elif event_type == "converted":
                metrics[variant]["conversions"] = count

        # Calculate conversion rates
        for variant, data in metrics.items():
            exposures = data["exposures"]
            conversions = data["conversions"]
            rate = conversions / exposures if exposures > 0 else 0.0
            data["conversion_rate"] = round(rate, 4)

        logger.info(f"Calculated metrics for experiment {experiment_id}: {metrics}")

        return {
            "experiment_id": str(experiment_id),
            "metrics": metrics,
            "total_exposures": sum(m["exposures"] for m in metrics.values()),
            "total_conversions": sum(m["conversions"] for m in metrics.values()),
        }

    async def check_statistical_significance(
        self, experiment_id: UUID
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Chi-square test for statistical significance.

        Uses a simplified chi-square calculation to determine if the
        difference between control and treatment is significant.

        Args:
            experiment_id: UUID of the experiment

        Returns:
            Dict with statistical test results:
            - chi2_stat: Chi-square statistic
            - p_value: P-value for significance
            - is_significant: Whether p < 0.05
            - recommendation: "continue" or "stop"
        """
        # Get metrics
        metrics_result = await self.calculate_metrics(experiment_id)
        metrics = metrics_result.get("metrics", {})

        if "control" not in metrics or "treatment" not in metrics:
            return {
                "experiment_id": str(experiment_id),
                "error": "Missing control or treatment variant data",
                "is_significant": False,
                "chi2_stat": 0.0,
                "p_value": 1.0,
            }

        control = metrics["control"]
        treatment = metrics["treatment"]

        # Create contingency table
        # [conversions, non_conversions]
        control_data = [
            control["conversions"],
            control["exposures"] - control["conversions"],
        ]
        treatment_data = [
            treatment["conversions"],
            treatment["exposures"] - treatment["conversions"],
        ]

        # Calculate chi-square manually (simplified)
        # Expected values under null hypothesis (no difference)
        total_conversions = control["conversions"] + treatment["conversions"]
        total_exposures = control["exposures"] + treatment["exposures"]

        if total_exposures == 0:
            return {
                "experiment_id": str(experiment_id),
                "error": "No exposures recorded",
                "is_significant": False,
                "chi2_stat": 0.0,
                "p_value": 1.0,
            }

        # Expected conversion rate overall
        expected_rate = total_conversions / total_exposures

        # Expected values
        expected_control_conversions = control["exposures"] * expected_rate
        expected_treatment_conversions = treatment["exposures"] * expected_rate

        # Chi-square calculation: sum((observed - expected)^2 / expected)
        def chi_sq_cell(observed: float, expected: float) -> float:
            if expected == 0:
                return 0.0
            return ((observed - expected) ** 2) / expected

        chi2_stat = (
            chi_sq_cell(control["conversions"], expected_control_conversions)
            + chi_sq_cell(
                control["exposures"] - control["conversions"],
                control["exposures"] - expected_control_conversions,
            )
            + chi_sq_cell(treatment["conversions"], expected_treatment_conversions)
            + chi_sq_cell(
                treatment["exposures"] - treatment["conversions"],
                treatment["exposures"] - expected_treatment_conversions,
            )
        )

        # Simplified p-value approximation for chi-square with 1 df
        # For df=1, critical values: 3.84 (p=0.05), 6.63 (p=0.01)
        # Using exponential decay approximation
        import math

        if chi2_stat > 10:
            p_value = 0.001
        elif chi2_stat > 6.63:
            p_value = 0.01
        elif chi2_stat > 3.84:
            p_value = 0.05
        else:
            p_value = min(1.0, math.exp(-chi2_stat / 2))

        is_significant = p_value < 0.05

        result = {
            "experiment_id": str(experiment_id),
            "chi2_stat": round(chi2_stat, 4),
            "p_value": round(p_value, 4),
            "is_significant": is_significant,
            "degrees_of_freedom": 1,
            "sample_size": total_exposures,
            "recommendation": "stop" if is_significant else "continue",
            "control_conversion_rate": control.get("conversion_rate", 0),
            "treatment_conversion_rate": treatment.get("conversion_rate", 0),
            "lift": round(
                treatment.get("conversion_rate", 0) - control.get("conversion_rate", 0),
                4,
            ),
        }

        logger.info(
            f"Statistical significance check for experiment {experiment_id}: "
            f"chi2={chi2_stat:.4f}, p={p_value:.4f}, significant={is_significant}"
        )

        return result

    async def start_experiment(self, experiment_id: UUID) -> Experiment | None:
        """Start an experiment by setting status to 'running'.

        Args:
            experiment_id: UUID of the experiment

        Returns:
            Updated Experiment or None if not found
        """
        result = await self.session.execute(
            select(Experiment).where(Experiment.id == experiment_id)
        )
        experiment = result.scalar_one_or_none()

        if not experiment:
            return None

        experiment.status = "running"
        experiment.start_date = datetime.now(timezone.utc)
        experiment.updated_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(experiment)

        logger.info(f"Started experiment {experiment_id}")

        return experiment

    async def stop_experiment(
        self, experiment_id: UUID, reason: str = "manual"
    ) -> Experiment | None:
        """Stop an experiment by setting status to 'completed'.

        Args:
            experiment_id: UUID of the experiment
            reason: Reason for stopping

        Returns:
            Updated Experiment or None if not found
        """
        result = await self.session.execute(
            select(Experiment).where(Experiment.id == experiment_id)
        )
        experiment = result.scalar_one_or_none()

        if not experiment:
            return None

        experiment.status = "completed"
        experiment.end_date = datetime.now(timezone.utc)
        experiment.updated_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(experiment)

        logger.info(f"Stopped experiment {experiment_id}, reason: {reason}")

        return experiment

    async def create_ml_recommendation_experiment(self, tenant_id: int) -> Experiment:
        """Create or get the ML recommendations A/B test experiment.

        Control: Heuristic scoring only
        Treatment: ML + Heuristic blended scoring

        Args:
            tenant_id: Tenant that owns this experiment (ADR-005: NOT NULL)

        Returns:
            Existing or newly created Experiment instance
        """
        # Check if experiment already exists
        existing = await self.get_experiment_by_name("ML Pack Recommendations")
        if existing:
            return existing

        # Create new experiment
        experiment = await self.create_experiment(
            tenant_id=tenant_id,
            name="ML Pack Recommendations",
            description="Compare ML-enhanced recommendations vs heuristic-only",
            variants=[
                {
                    "name": "control",
                    "config": {
                        "use_ml": False,
                        "description": "Heuristic scoring only",
                    },
                },
                {
                    "name": "treatment",
                    "config": {"use_ml": True, "description": "ML + Heuristic blend"},
                },
            ],
            traffic_split=0.5,
        )

        logger.info(f"Created ML recommendation experiment: {experiment.id}")
        return experiment


# Singleton instance holder
_service_instance: ExperimentService | None = None


async def get_experiment_service(session: AsyncSession) -> ExperimentService:
    """Factory function to create ExperimentService.

    Args:
        session: Database session

    Returns:
        ExperimentService instance
    """
    return ExperimentService(session)
