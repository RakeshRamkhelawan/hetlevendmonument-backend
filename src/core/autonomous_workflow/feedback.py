"""Feedback service for autonomous workflow."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from prometheus_client import Counter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WorkflowExperience

# Metrics
FEEDBACK_PROCESSED = Counter("feedback_processed_total", "Total feedback items processed")
FEEDBACK_ERRORS = Counter("feedback_errors_total", "Total feedback processing errors")


class FeedbackService:
    """Service for handling workflow feedback and experience collection."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def process_feedback(
        self,
        workflow_type: str,
        input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        output_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        feedback_score: float | None = None,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Process and store feedback for a workflow execution."""
        try:
            experience = WorkflowExperience(
                workflow_type=workflow_type,
                input_data=input_data,
                output_data=output_data,
                feedback_score=feedback_score,
                is_processed=False,
            )

            self.session.add(experience)
            await self.session.commit()

            FEEDBACK_PROCESSED.inc()
            self.logger.info(f"Stored feedback for {workflow_type} workflow")

            return experience

        except Exception as e:
            FEEDBACK_ERRORS.inc()
            self.logger.error(f"Error processing feedback: {str(e)}")
            await self.session.rollback()
            raise

    async def get_unprocessed_experiences(self, limit: int = 100) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Retrieve unprocessed experiences for training."""
        query = (
            select(WorkflowExperience)
            .where(WorkflowExperience.is_processed.is_(False))
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_experiences_processed(self, experience_ids: list[int]) -> None:
        """Mark experiences as processed after training."""
        try:
            query = select(WorkflowExperience).where(WorkflowExperience.id.in_(experience_ids))
            result = await self.session.execute(query)
            experiences = result.scalars().all()

            for exp in experiences:
                exp.is_processed = True
                exp.updated_at = datetime.now(timezone.utc)

            await self.session.commit()

        except Exception as e:
            self.logger.error(f"Error marking experiences as processed: {str(e)}")
            await self.session.rollback()
            raise

    async def get_feedback_statistics(self, workflow_type: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get statistics about stored feedback."""
        try:
            base_query = select(WorkflowExperience)
            if workflow_type:
                base_query = base_query.where(WorkflowExperience.workflow_type == workflow_type)

            # Total count
            total = await self.session.scalar(
                select(func.count()).select_from(base_query.subquery())
            )

            # Average feedback score
            avg_score = await self.session.scalar(
                select(func.avg(WorkflowExperience.feedback_score)).select_from(
                    base_query.subquery()
                )
            )

            # Processed count
            processed = await self.session.scalar(
                select(func.count()).select_from(
                    base_query.where(WorkflowExperience.is_processed.is_(True)).subquery()
                )
            )

            # Ensure non-None values for arithmetic
            total_count: int = total if total is not None else 0
            processed_count: int = processed if processed is not None else 0

            return {
                "total_experiences": total_count,
                "average_feedback_score": float(avg_score) if avg_score else None,
                "processed_experiences": processed_count,
                "unprocessed_experiences": total_count - processed_count,
            }

        except Exception as e:
            self.logger.error(f"Error getting feedback statistics: {str(e)}")
            raise
