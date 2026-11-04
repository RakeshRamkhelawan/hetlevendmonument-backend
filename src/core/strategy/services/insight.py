"""Insight Management Service."""

import logging
import uuid
from typing import Any, Optional

from src.core.strategy.types import StrategicInsight, StrategyType

logger = logging.getLogger(__name__)


class InsightService:
    """Service for managing strategic insights."""

    def __init__(
        self,
        tenant_id: int | None = None,
        repository: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.tenant_id = tenant_id
        self._repository = repository
        self.insights: dict[str, StrategicInsight] = {}

    async def record(self, insight: StrategicInsight) -> None:
        """Record a strategic insight with transactional consistency."""
        # P1 FIX: Write-ahead pattern - persist to DB first
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_insight(self.tenant_id, insight)
            except Exception as exc:
                logger.error("Failed to persist strategic insight %s: %s", insight.id, exc)
                raise RuntimeError(f"Failed to persist strategic insight: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.insights[insight.id] = insight
        logger.info("Strategic insight recorded: %s (%s)", insight.title, insight.id)

    async def analyze_opportunity(
        self, opportunity_description: str, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> StrategicInsight:
        """Analyze a specific strategic opportunity."""
        import asyncio
        from datetime import datetime, timezone
        insight_id = str(uuid.uuid4())

        # Create strategic context if not provided
        if not context:
            context = {
                "market_conditions": {"growth": "stable"},
                "competitive_landscape": {"intensity": "moderate"},
                "internal_capabilities": {"resources": "adequate"},
            }

        await asyncio.sleep(0.05)  # Simulate analysis work

        insight = StrategicInsight(
            id=insight_id,
            type=StrategyType.OPPORTUNITY_ANALYSIS,
            title=f"Opportunity Analysis: {opportunity_description[:50]}...",
            description=f"Strategic analysis of opportunity: {opportunity_description}",
            confidence=0.8,
            impact_score=7.5,
            urgency_score=6.0,
            supporting_evidence=[
                "Market demand indicators",
                "Competitive gap analysis",
                "Internal capability assessment",
            ],
            recommended_actions=[
                "Conduct detailed feasibility study",
                "Develop pilot program",
                "Allocate resources for exploration",
            ],
            risks=[
                "Market timing uncertainty",
                "Resource allocation conflicts",
                "Competitive response",
            ],
            opportunities=[
                "First mover advantage",
                "Market share expansion",
                "Revenue growth potential",
            ],
            created_at=datetime.now(timezone.utc),
        )

        # P1 FIX: Write-ahead pattern - persist to DB first
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_insight(self.tenant_id, insight)
            except Exception as exc:
                logger.error("Failed to persist strategic insight %s: %s", insight_id, exc)
                raise RuntimeError(f"Failed to persist strategic insight: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.insights[insight_id] = insight
        logger.info("Strategic opportunity analyzed: %s", insight_id)
        return insight

    def get(self, insight_id: str) -> StrategicInsight | None:
        """Get a specific insight by ID."""
        return self.insights.get(insight_id)

    def list_all(self, strategy_type: StrategyType | None = None) -> list[StrategicInsight]:
        """Get strategic insights, optionally filtered by type."""
        insights = list(self.insights.values())
        if strategy_type:
            insights = [i for i in insights if i.type == strategy_type]
        return sorted(insights, key=lambda x: x.impact_score, reverse=True)

    def list_by_confidence(self, min_confidence: float = 0.5) -> list[StrategicInsight]:
        """List insights with minimum confidence."""
        return [i for i in self.insights.values() if i.confidence >= min_confidence]

    def list_high_impact(self, threshold: float = 7.0) -> list[StrategicInsight]:
        """List high impact insights."""
        return [i for i in self.insights.values() if i.impact_score >= threshold]

    async def remove(self, insight_id: str) -> bool:
        """Remove an insight."""
        if insight_id not in self.insights:
            return False

        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.delete_insight(self.tenant_id, insight_id)
            except Exception as exc:
                logger.error("Failed to delete insight %s: %s", insight_id, exc)
                raise RuntimeError(f"Failed to delete insight: {exc}") from exc

        del self.insights[insight_id]
        logger.info("Strategic insight removed: %s", insight_id)
        return True

    async def load_from_repository(self) -> None:
        """Load insights from repository."""
        if self._repository is None or self.tenant_id is None:
            return

        try:
            insights = await self._repository.get_insights(self.tenant_id)
            self.insights.clear()
            for ins in insights:
                self.insights[ins.id] = ins
            logger.info("Loaded %d insights for tenant %s", len(self.insights), self.tenant_id)
        except Exception as exc:
            logger.error("Failed to load insights: %s", exc)
