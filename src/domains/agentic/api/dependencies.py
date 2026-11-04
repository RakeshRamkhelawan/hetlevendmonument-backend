from typing import Optional, cast

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db
from src.domains.agentic.repositories.prompt_repository import SQLAlchemyPromptRepository
from src.domains.agentic.services.analytics_service import PromptAnalyticsService
from src.domains.agentic.services.experimentation_service import ExperimentationService
from src.domains.agentic.services.promotion_service import AutoPromotionService, PromptRepository


def get_experimentation_service() -> ExperimentationService:
    """Dependency for ExperimentationService"""
    return ExperimentationService()


def get_experiment_repository(
    db: AsyncSession = Depends(get_db),
) -> SQLAlchemyPromptRepository:
    """Dependency for PromptRepository with DB session"""
    return SQLAlchemyPromptRepository(db)


def get_promotion_service(
    repo: SQLAlchemyPromptRepository = Depends(get_experiment_repository),
) -> AutoPromotionService:
    """Dependency for AutoPromotionService"""
    analytics = PromptAnalyticsService()
    # Cast to Protocol type due to signature differences (tenant_id parameter)
    repository = cast(Optional[PromptRepository], repo)
    return AutoPromotionService(analytics=analytics, repository=repository)
