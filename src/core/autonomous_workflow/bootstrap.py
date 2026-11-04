"""
Integration bootstrap for autonomous workflow.

Updated: 2025-10-17
Status: Production-Ready with TrainingService
Protocol: Generale Repetitie - 100% Production Code
"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.training_service import TrainingService

logger = logging.getLogger(__name__)


async def initialize_autonomous_workflow(
    db_session: AsyncSession,
    tenant_id: int = 0,
) -> TrainingService | None:
    """
    Initialize autonomous workflow training service.

    This function sets up the production TrainingService which uses:
    - DynamicTrainingPipeline (12/12 tests passing)
    - Real LearningExperience data from database
    - Production error handling and logging

    Args:
        db_session: Database session for fetching experiences

    Returns:
        TrainingService instance or None if initialization fails
    """
    try:
        logger.info("Initializing Autonomous Workflow Training Service")

        # Create training service with production config
        training_service = TrainingService(db_session)

        # Get current status
        status = await training_service.get_training_status(tenant_id=tenant_id)
        logger.info(
            f"Training service initialized: "
            f"{status['available_experiences']} experiences available, "
            f"ready={status['ready']}"
        )

        # Run initial training if enough data available
        if status["ready"]:
            logger.info("Running initial training session")
            result: dict[str, Any] = await training_service.train(days=7, min_experiences=10)  # type: ignore[assignment]

            if result["status"] == "success":
                logger.info(
                    f"Initial training completed: "
                    f"loss={result['metrics'].get('average_loss', 'N/A')}, "
                    f"processed={result['experiences_count']}"
                )
            elif result["status"] == "skipped":
                logger.warning(f"Initial training skipped: {result.get('reason', 'unknown')}")
            else:
                logger.error(f"Initial training failed: {result.get('error', 'unknown')}")
        else:
            logger.info(
                f"Skipping initial training: "
                f"only {status['available_experiences']} experiences "
                f"(minimum 10 required)"
            )

        return training_service

    except Exception as e:
        logger.error(f"Failed to initialize autonomous workflow: {e}", exc_info=True)
        return None
