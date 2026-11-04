import logging
from typing import Optional, Protocol

from src.domains.agentic.services.analytics_service import PromptAnalyticsService

logger = logging.getLogger(__name__)


# Protocol for DB interaction (to be implemented with SQLAlchemy later)
class PromptRepository(Protocol):
    async def get_variant_content(
        self, experiment_id: str, variant_id: str, tenant_id: int
    ) -> str: ...

    async def update_template_content(
        self, template_id: int, new_content: str, commit_message: str, tenant_id: int
    ) -> None: ...

    async def close_experiment(self, experiment_id: str, winner_id: str, tenant_id: int) -> None: ...


class AutoPromotionService:
    """
    Service to automate the promotion of winning prompt variants.
    """

    def __init__(
        self,
        analytics: PromptAnalyticsService,
        repository: PromptRepository | None = None,
    ) -> None:
        self.analytics = analytics
        self.repository = repository  # Injected

    async def check_and_promote(
        self,
        experiment_id: str,
        prompt_template_id: int,
        tenant_id: int,
    ) -> bool:
        """
        Check if an experiment has a winner and promote it.
        Returns True if promoted.
        """
        if not self.repository:
            logger.warning("No repository configured for AutoPromotionService")
            return False

        winner_id = await self.analytics.get_winning_variant(experiment_id)

        if not winner_id:
            logger.info(f"No winner found yet for {experiment_id}")
            return False

        logger.info(
            f"Winner found: {winner_id}. Initiating promotion for template {prompt_template_id}."
        )

        try:
            # 1. Get content
            content = await self.repository.get_variant_content(
                experiment_id,
                winner_id,
                tenant_id,
            )

            # 2. Update Template
            msg = f"Auto-promoted winner {winner_id} from experiment {experiment_id}"
            await self.repository.update_template_content(
                prompt_template_id,
                content,
                msg,
                tenant_id,
            )

            # 3. Close Experiment
            await self.repository.close_experiment(experiment_id, winner_id, tenant_id)

            logger.info(f"Successfully promoted {winner_id} to template {prompt_template_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to promote winner {winner_id}: {e}")
            raise
