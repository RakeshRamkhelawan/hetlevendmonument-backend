"""Deprecated compatibility models and feedback-loop utilities.

New learning integrations should prefer ``src.core.learning.learning_repository``
and the service-backed ``LearningMixin`` flow. This module remains available for
legacy repositories, APIs, and tests that still depend on its Pydantic models.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from sqlalchemy import text

from src.core.database.database import db_manager
from src.core.shared.config import get_feature_flag

logger = logging.getLogger(__name__)


class LearningInsight(BaseModel):
    """Data model for a captured learning insight."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: int | None = None
    task_id: str | None = None
    source_agent: str | None = None
    finding: str | None = None
    root_cause: str | None = None
    conversation_id: str | None = None
    category: str | None = None
    rating: Any | None = None  # TODO(TYPE): replace Any with concrete type
    comment: str | None = None
    confidence: float | None = None
    confidence_score: float | None = None
    context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    processed: bool | None = None
    adaptation_applied: bool | None = None
    applications: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AdaptationRule(BaseModel):
    """Data model for an active adaptation rule."""

    id: str | None = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: int | None = None
    trigger_condition: str | None = None
    adaptation_action: str | None = None
    rule_type: str | None = None
    trigger_keywords: list[str] | None = None
    trigger_patterns: list[str] | None = None
    target_supervisor: str | None = None
    target_agent: str | None = None
    confidence: float | None = None
    priority: int | None = None
    times_applied: int | None = None
    success_rate: float | None = None
    active: bool | None = True
    is_active: bool = True
    prompt_addition: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuleBasedAdaptation(BaseModel):
    """Encapsulates a rule-based change in system behavior."""

    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule: AdaptationRule


class FeedbackLearningCycle(BaseModel):
    """Represents a complete feedback-to-learning loop."""

    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    feedback_rating: int
    insight_generated: LearningInsight | None = None


class LearningLoop:
    """
    Continuous learning engine for SanskritiSetu.
    Converts feedback and execution failures into actionable adaptation rules.
    """

    async def record_adaptation_rule(
        self, tenant_id: int, trigger_pattern: str, suggested_agent: str
    ) -> None:
        """
        Stores a new routing rule learned from experience.
        """
        if not get_feature_flag("learning_enabled"):
            return

        logger.info(
            f"LearningLoop: Recording adaptation rule for tenant {tenant_id}: '{trigger_pattern}' -> {suggested_agent}"
        )

        async with db_manager.get_session() as db:
            stmt = text(
                """
                INSERT INTO adaptation_rules (tenant_id, trigger_condition, adaptation_action, is_active, created_at)
                VALUES (:tenant_id, :condition, :action, true, NOW())
                ON CONFLICT (tenant_id, trigger_condition)
                DO UPDATE SET adaptation_action = EXCLUDED.adaptation_action
            """
            )

            await db.execute(
                stmt,
                {
                    "tenant_id": tenant_id,
                    "condition": trigger_pattern.lower(),
                    "action": suggested_agent,
                },
            )
            await db.commit()

    async def _create_insight(
        self,
        conversation_id: str,
        rating: Any,  # TODO(TYPE): replace Any with concrete type
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
        comment: str | None = None,
    ) -> LearningInsight:
        """Create a LearningInsight from feedback data."""
        return LearningInsight(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            rating=rating,
            context=context,
            comment=comment,
            processed=False,
            adaptation_applied=False,
        )

    async def process_feedback(
        self, tenant_id: int, task_id: str, rating: int, feedback_text: str | None = None
    ) -> None:
        """
        Analyzes human feedback to trigger a learning cycle.
        """
        if rating < 3:  # Negative feedback
            logger.warning(
                f"Negative feedback received for task {task_id} (rating {rating}). Triggering Learning cycle."
            )
            # In production, this triggers an asynchronous analysis task
            pass


# Type aliases for backward compatibility
FeedbackLoopProcessor = LearningLoop


class FeedbackRating:
    """Rating scale for feedback."""

    POSITIVE = 5
    NEUTRAL = 3
    NEGATIVE = 1

    _value_to_name = {5: "POSITIVE", 3: "NEUTRAL", 1: "NEGATIVE"}

    def __init__(self, value: int) -> None:
        if value not in self._value_to_name:
            raise ValueError(f"Invalid rating value: {value}")
        self._value = value
        self._name = self._value_to_name[value]

    def __int__(self) -> int:
        return self._value

    def __repr__(self) -> str:
        return f"FeedbackRating.{self._name}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FeedbackRating):
            return self._value == other._value
        if isinstance(other, int):
            return self._value == other
        return NotImplemented


class UltimateLearningOrchestrator(LearningLoop):
    """The high-level orchestrator for the entire learning meta-layer."""

    pass


_orchestrator_instance: UltimateLearningOrchestrator | None = None


def get_learning_orchestrator() -> UltimateLearningOrchestrator:
    """Returns a singleton instance of the learning orchestrator."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = UltimateLearningOrchestrator()
    return _orchestrator_instance
