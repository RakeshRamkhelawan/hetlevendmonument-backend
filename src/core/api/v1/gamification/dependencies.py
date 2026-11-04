"""Gamification domain dependencies (ADR-033 Laag 1)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db as get_db  # noqa: F401
from src.core.services.gamification_service import GamificationService as GamificationService  # noqa: F401


def get_gamification_service(
    db: AsyncSession = Depends(get_db),
) -> GamificationService:
    return GamificationService(db)
