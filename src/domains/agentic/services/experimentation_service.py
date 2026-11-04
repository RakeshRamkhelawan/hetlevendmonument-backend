import logging
import uuid
from inspect import isawaitable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.production_integration import (
    ABTestConfiguration,
    ab_testing_framework,
)
from src.domains.agentic.repositories.prompt_repository import SQLAlchemyPromptRepository

logger = logging.getLogger(__name__)


class ExperimentationService:
    """
    Service to manage prompt experiments, bridging the Agentic Domain
    and the Core Learning ABTestingFramework.
    """

    def __init__(self) -> None:
        # We access the singleton instance from core
        self.ab_framework = ab_testing_framework
        self.traffic_router = self.ab_framework.traffic_router

    async def create_experiment(
        self,
        db: AsyncSession,
        name: str,
        description: str,
        prompt_template_id: int,
        variants: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        min_sample_size: int = 100,
        tenant_id: int | None = None,
    ) -> str:
        """
        Create a new A/B experiment for a prompt template.
        """
        # Generate a unique test ID
        test_id = f"exp_prompt_{prompt_template_id}_{uuid.uuid4().hex[:8]}"

        # Identify control and treatments
        control_group_id = next((v["name"] for v in variants if v.get("is_control")), None)
        if not control_group_id:
            # Fallback to first if schema validation didn't catch it (it should)
            control_group_id = variants[0]["name"]

        treatment_groups = [v["name"] for v in variants if v["name"] != control_group_id]

        # Traffic map
        traffic_allocation = {v["name"]: v["traffic"] for v in variants}

        config = ABTestConfiguration(
            test_id=test_id,
            test_name=name,
            description=description,
            control_group=control_group_id,
            treatment_groups=treatment_groups,
            traffic_allocation=traffic_allocation,
            success_metrics=["user_satisfaction", "task_completion"],
            minimum_sample_size=min_sample_size,
            maximum_duration_days=14,
            early_stopping_enabled=True,
        )

        # Persist experiment metadata and content
        repo = SQLAlchemyPromptRepository(db)
        await repo.save_experiment(
            experiment_id=test_id,
            name=name,
            description=description,
            prompt_template_id=prompt_template_id,
            tenant_id=tenant_id or 0,
            variants=variants,
        )

        # Delegate to core framework
        created: Any = self.ab_framework.create_ab_test(  # TODO(TYPE): replace Any with concrete type
            config
        )  # TODO(TYPE): replace Any with concrete type
        if isawaitable(created):
            created = await created

        started: Any = self.ab_framework.start_ab_test(  # TODO(TYPE): replace Any with concrete type
            test_id
        )  # TODO(TYPE): replace Any with concrete type
        if isawaitable(started):
            await started

        logger.info(f"Initialized prompt experiment {test_id} for template {prompt_template_id}")
        return created if isinstance(created, str) and created else test_id

    async def get_assigned_variant(self, experiment_id: str, user_id: str) -> str:
        """
        Get the variant assigned to a user for a specific experiment.
        Delegates to core framework ABTestingFramework.assign_variant which uses TrafficRouter.
        """
        result: Any = self.ab_framework.assign_variant(  # TODO(TYPE): replace Any with concrete type
            experiment_id, user_id
        )  # TODO(TYPE): replace Any with concrete type
        if isawaitable(result):
            result = await result
        return str(result)

    async def record_experiment_feedback(
        self,
        db: AsyncSession,
        experiment_id: str,
        variant_id: str,
        user_id: str,
        score: float,
    ) -> None:
        """
        Record user feedback as a metric for the experiment.
        """
        recorded = self.ab_framework.record_metric(
            experiment_id,
            str(user_id),
            variant_id,
            "user_satisfaction",
            float(score),
        )
        if isawaitable(recorded):
            await recorded
