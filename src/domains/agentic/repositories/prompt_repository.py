import logging
from typing import Any, Optional
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import PromptExperiment, PromptExperimentVariant, PromptTemplate

logger = logging.getLogger(__name__)


class SQLAlchemyPromptRepository:
    """
    SQLAlchemy implementation of PromptRepository.
    Handles persistence for Prompt Experiments and Templates.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save_experiment(
        self,
        experiment_id: str,
        name: str,
        description: str,
        prompt_template_id: int,
        tenant_id: int,
        variants: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Save experiment metadata and variants to database.

        NEO AUDIT FIX (P0): Added tenant_id parameter to prevent orphaned experiments.

        Args:
            experiment_id: Unique experiment identifier
            name: Experiment name
            description: Experiment description
            prompt_template_id: FK to prompt_templates
            tenant_id: FK to tenants (REQUIRED for multi-tenant isolation)
            variants: list of dict: {name, content, traffic, is_control}
        """
        exp = PromptExperiment(
            id=experiment_id,
            prompt_template_id=prompt_template_id,
            tenant_id=tenant_id,  # NEO FIX: set[Any] tenant ownership  # TODO(TYPE): replace Any with concrete type
            name=name,
            description=description,
            status="active",
        )
        self.db.add(exp)

        for v in variants:
            variant = PromptExperimentVariant(
                experiment_id=experiment_id,
                variant_id=v["name"],  # Identifying name usually matches ID
                content=v.get("content", ""),  # Critical: content required
                is_control=v.get("is_control", False),
                traffic_allocation=v.get("traffic", 0.0),
            )
            self.db.add(variant)

        await self.db.flush()

    async def get_variant_content(self, experiment_id: str, variant_id: str, tenant_id: int) -> str:
        """
        Get variant content with tenant ownership validation.

        NEO AUDIT FIX (P0): Added tenant_id validation to prevent IDOR.
        Without this, any user can read variants by guessing experiment_id + variant_id.

        Args:
            experiment_id: Experiment ID to load variant from
            variant_id: Variant identifier
            tenant_id: Current user's tenant (for ownership validation)

        Returns:
            Variant content string

        Raises:
            NoResultFound: If variant not found or not owned by tenant
        """
        # Step 1: Verify experiment belongs to current tenant
        exp_stmt = select(PromptExperiment).where(
            PromptExperiment.id == experiment_id,
            PromptExperiment.tenant_id == tenant_id,
        )
        exp_result = await self.db.execute(exp_stmt)
        experiment = exp_result.scalar_one_or_none()
        if not experiment:
            logger.warning(
                f"Experiment {experiment_id} not found for tenant {tenant_id} (IDOR attempt?)"
            )
            raise NoResultFound(f"Experiment {experiment_id} not accessible")

        # Step 2: Get variant content (now safe due to experiment ownership check)
        stmt = select(PromptExperimentVariant.content).where(
            PromptExperimentVariant.experiment_id == experiment_id,
            PromptExperimentVariant.variant_id == variant_id,
        )
        result = await self.db.execute(stmt)
        try:
            return result.scalar_one()
        except NoResultFound:
            logger.error(f"Variant {variant_id} content not found for experiment {experiment_id}")
            raise

    async def update_template_content(
        self,
        template_id: int,
        new_content: str,
        commit_message: str,
        tenant_id: int,
    ) -> None:
        stmt = (
            update(PromptTemplate)
            .where(
                PromptTemplate.id == template_id,
                PromptTemplate.tenant_id == tenant_id,
            )
            .values(
                system_prompt=new_content,
                updated_at=func.now(),
                # could append to description or log history if table existed
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()  # Commit this action as it's a mutation of core state

    async def close_experiment(self, experiment_id: str, winner_id: str, tenant_id: int) -> None:
        stmt = (
            update(PromptExperiment)
            .where(
                PromptExperiment.id == experiment_id,
                PromptExperiment.tenant_id == tenant_id,
            )
            .values(
                status="completed",
                end_time=func.now(),
                description=func.coalesce(PromptExperiment.description, "")
                + f" [Winner: {winner_id}]",
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def list_experiments(self, tenant_id: int) -> Sequence[PromptExperiment]:
        """List all experiments ordered by start time (newest first)."""
        stmt = (
            select(PromptExperiment)
            .where(PromptExperiment.tenant_id == tenant_id)
            .order_by(PromptExperiment.start_time.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_experiment(
        self, experiment_id: str, tenant_id: int
    ) -> PromptExperiment | None:
        """Get experiment by ID scoped to tenant."""
        stmt = select(PromptExperiment).where(
            PromptExperiment.id == experiment_id,
            PromptExperiment.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
