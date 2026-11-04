"""
Insight Service - Handles insight generation and management.

This service is responsible for:
- Generating insights from patterns and observations
- Managing insight lifecycle
- Prioritizing actionable insights
- Tracking insight application
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from src.core.shared.config import get_feature_flag

if TYPE_CHECKING:
    from src.core.agents.learning_loop import LearningInsight, LearningType
    from src.core.learning.learning_repository import LearningRepository

logger = logging.getLogger(__name__)


class InsightService:
    """Service for managing learning insights."""

    def __init__(
        self,
        tenant_id: int,
        repository: Optional["LearningRepository"] = None,
    ) -> None:
        self.tenant_id = tenant_id
        self._repository = repository

        # In-memory storage
        self.insights: dict[str, "LearningInsight"] = {}

        # Metrics
        self.insights_generated = 0

    async def generate(
        self,
        title: str,
        description: str,
        insight_type: "LearningType",
        supporting_observations: list[str],
        confidence_score: float = 0.5,
        impact_assessment: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        recommended_actions: list[str] | None = None,
        is_actionable: bool = True,
    ) -> "LearningInsight":
        """Generate and store a new insight.

        P1 FIX: Uses write-ahead pattern - database write happens BEFORE
        in-memory update to ensure consistency.

        Args:
            title: Brief title of the insight
            description: Detailed description
            insight_type: Type of insight
            supporting_observations: IDs of supporting observations
            confidence_score: Confidence in this insight (0-1)
            impact_assessment: Assessment of potential impact
            recommended_actions: list[Any] of recommended actions  # TODO(TYPE): replace Any with concrete type
            is_actionable: Whether this insight can be acted upon

        Returns:
            The generated LearningInsight

        Raises:
            RuntimeError: If database persistence fails
        """
        from src.core.agents.learning_loop import LearningInsight

        insight_id = str(uuid.uuid4())

        insight = LearningInsight(
            id=insight_id,
            title=title,
            description=description,
            learning_type=insight_type,
            supporting_observations=supporting_observations,
            confidence_score=confidence_score,
            impact_assessment=impact_assessment or {},
            recommended_actions=recommended_actions or [],
            created_at=datetime.now(timezone.utc),
        )

        # P1 FIX: Write-ahead pattern - persist to database FIRST
        if self._repository:
            try:
                await self._repository.save_insight(self.tenant_id, insight)
            except Exception as exc:
                logger.error("Failed to persist insight %s: %s", insight_id, exc)
                raise RuntimeError(f"Failed to persist insight: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.insights[insight_id] = insight
        self.insights_generated += 1

        logger.info("Insight generated: %s (%s)", insight_id, title)
        return insight

    def get_actionable(self, limit: int = 10) -> list["LearningInsight"]:
        """Get actionable insights sorted by confidence."""
        actionable = [i for i in self.insights.values() if getattr(i, "is_actionable", True)]
        return sorted(
            actionable,
            key=lambda i: i.confidence_score,
            reverse=True,
        )[:limit]

    def get_by_type(self, insight_type: "LearningType") -> list["LearningInsight"]:
        """Get insights by type."""
        return [i for i in self.insights.values() if i.learning_type == insight_type]

    def get_by_id(self, insight_id: str) -> Optional["LearningInsight"]:
        """Get a specific insight by ID."""
        return self.insights.get(insight_id)

    async def mark_applied(self, insight_id: str) -> bool:
        """Mark an insight as applied."""
        if not get_feature_flag("learning_enabled"):
            return False

        insight = self.insights.get(insight_id)
        if insight:
            # Add application timestamp using object dict to store dynamic attribute
            if not hasattr(insight, "applications"):
                object.__setattr__(insight, "applications", [])
            getattr(insight, "applications").append(datetime.now(timezone.utc).isoformat())
            object.__setattr__(insight, "processed", True)
            object.__setattr__(insight, "adaptation_applied", True)

            # Persist if repository available
            if self._repository:
                try:
                    await self._repository.save_insight(self.tenant_id, insight)
                except Exception as exc:
                    logger.error("Failed to update insight: %s", exc)
                    raise

            return True
        return False

    async def load_from_db(self) -> None:
        """Load insights from database."""
        if not self._repository:
            return

        try:
            insights = await self._repository.get_recent_insights(self.tenant_id, limit=50)
            for insight in insights:
                self.insights[insight.id] = insight
            logger.info(
                "Loaded %d insights from database for tenant %s",
                len(insights),
                self.tenant_id,
            )
        except Exception as exc:
            logger.error("Failed to load insights from database: %s", exc)
            raise
