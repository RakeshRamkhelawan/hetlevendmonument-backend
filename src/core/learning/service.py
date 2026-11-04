"""
Service layer for Learning and Feedback processing.

Provides business logic for:
- Feedback processing with database persistence
- Adaptation rule application to routing
- Batch operations and analytics
- Performance metrics collection
- Async processing via Dramatiq
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthError
from src.core.learning.loop import (
    AdaptationRule,
    FeedbackLoopProcessor,
    FeedbackRating,
    LearningInsight,
)
from src.core.learning.metrics import LearningMetricsCollector
from src.core.learning.repository import AdaptationRuleRepository, LearningInsightRepository
from src.core.shared.config import get_feature_flag

# Async processing flag
ASYNC_FEEDBACK_PROCESSING = os.getenv("ASYNC_FEEDBACK_PROCESSING", "false").lower() == "true"


class FeedbackProcessingService:
    """
    Service for processing feedback with database persistence.

    Usage:
        service = FeedbackProcessingService(db_session)
        result = await service.process_feedback(data)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._insight_repo = LearningInsightRepository(session)
        self._rule_repo = AdaptationRuleRepository(session)
        self._processor = FeedbackLoopProcessor()
        self._metrics = LearningMetricsCollector()

    async def process_feedback(self, data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Process feedback and persist results to database.

        Transaction scope: Everything succeeds or fails together.

        Args:
            data: {
                "conversation_id": str,
                "tenant_id": str,
                "rating": int (1-5),
                "comment": str (optional),
                "corrected_supervisor": str (optional),
                "confidence": float,
                "context": dict (optional)
            }

        Returns:
            {
                "processed": bool,
                "insight_id": str,
                "insight_created": bool,
                "adaptation_created": bool,
                "rule_id": str (optional)
            }
        """
        start_time = time.time()
        tenant_id = data.get("tenant_id")
        if not tenant_id:
            raise AuthError("tenant_id is required for feedback processing")

        if not get_feature_flag("learning_enabled"):
            return {
                "processed": False,
                "insight_created": False,
                "adaptation_created": False,
                "reason": "Learning disabled",
            }

        try:
            # 1. Use existing logic for analysis
            rating = data.get("rating", 3)
            feedback_rating = (
                FeedbackRating(rating) if isinstance(rating, int) else FeedbackRating.NEUTRAL
            )

            insight = await self._processor._create_insight(
                conversation_id=data["conversation_id"],
                rating=feedback_rating,
                context=data.get("context", {}),
                tenant_id=tenant_id,
                comment=data.get("comment"),
            )

            # 2. Store insight
            await self._insight_repo.save(insight, tenant_id)

            result = {
                "processed": True,
                "insight_id": insight.id,
                "insight_created": True,
                "adaptation_created": False,
            }

            # 3. Generate and store rule if applicable
            if data.get("corrected_supervisor"):
                # Generate rule from insight
                rule = await self._processor._generate_adaptation_rule(insight)  # type: ignore[attr-defined]

                if rule:
                    # Override with user input
                    rule.target_supervisor = data["corrected_supervisor"]
                    rule.confidence = data.get("confidence", 0.8)
                    rule.priority = min(int(rule.confidence * 10), 10)

                    await self._rule_repo.save(rule, tenant_id)
                    result["adaptation_created"] = True
                    result["rule_id"] = rule.id

                    # Mark insight as having adaptation applied
                    insight.adaptation_applied = True
                    await self._insight_repo.save(insight, tenant_id)

            await self._session.commit()

            # Record metrics
            duration = time.time() - start_time
            self._metrics.record_feedback_processing(tenant_id, duration, success=True)
            self._metrics.record_insight_processed(tenant_id, insight.category or "general")

            # Trigger async follow-up tasks if needed
            if ASYNC_FEEDBACK_PROCESSING and result.get("adaptation_created"):
                try:
                    from src.core.learning.worker import enqueue_feedback_processing

                    # Re-enqueue for any additional async processing
                    enqueue_feedback_processing(data)
                except Exception as e:
                    logger.warning(f"Failed to enqueue async processing: {e}")

            return result

        except Exception as e:
            await self._session.rollback()

            # Record error metrics
            duration = time.time() - start_time
            self._metrics.record_feedback_processing(tenant_id, duration, success=False)

            raise

    async def batch_process_feedback(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Process multiple feedback items in batch."""
        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in items:
            try:
                result = await self.process_feedback(item)
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "processed": False,
                        "error": str(e),
                        "conversation_id": item.get("conversation_id"),
                    }
                )
        return results

    async def get_insight_stats(self, tenant_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get statistics about insights for a tenant."""
        unprocessed = await self._insight_repo.get_unprocessed(tenant_id, limit=1000)

        return {
            "unprocessed_count": len(unprocessed),
            "tenant_id": tenant_id,
        }


class AdaptationRuleService:
    """
    Service for retrieving and applying adaptation rules.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AdaptationRuleRepository(session)
        self._metrics = LearningMetricsCollector()

    async def get_rules_for_routing(self, tenant_id: str, query: str) -> AdaptationRule | None:
        """
        Find best matching rule for a query.

        Args:
            tenant_id: Tenant isolation key
            query: User query string

        Returns:
            Best matching rule or None if no match.
        """
        rules = await self._repo.get_active_rules(tenant_id)

        if not rules:
            return None

        query_lower = query.lower()
        best_rule = None
        best_score = 0.0

        for rule in rules:
            score = self._calculate_match_score(rule, query_lower)
            if score > best_score and score >= 0.5:  # Minimum threshold
                best_score = score
                best_rule = rule

        return best_rule

    def _calculate_match_score(self, rule: AdaptationRule, query: str) -> float:
        """
        Calculate how well a rule matches a query.

        Returns score between 0.0 and 1.0
        """
        if not rule.trigger_keywords:
            return 0.0

        # Count matching keywords
        matches = sum(1 for kw in rule.trigger_keywords if kw.lower() in query)
        if matches == 0:
            return 0.0

        # Calculate coverage (what % of rule keywords are in query)
        coverage = matches / len(rule.trigger_keywords)

        # Weight by rule confidence and priority
        priority_weight = (rule.priority or 5) / 10.0  # Normalize 1-10 to 0.1-1.0

        # Combined score
        score = coverage * (rule.confidence or 0.5) * (0.5 + 0.5 * priority_weight)

        return min(score, 1.0)  # Cap at 1.0

    async def apply_rule_to_routing(
        self, tenant_id: str, query: str, original_supervisor: str, original_confidence: float
    ) -> tuple[str, float, str | None]:
        """
        Apply adaptation rules to routing decision.

        Returns:
            (supervisor_id, confidence, rule_id or None)
        """
        if not get_feature_flag("learning_enabled"):
            return original_supervisor, original_confidence, None

        import time

        start_time = time.time()

        rule = await self.get_rules_for_routing(tenant_id, query)

        if not rule:
            return original_supervisor, original_confidence, None

        # Apply the rule
        new_confidence = max(original_confidence, rule.confidence or 0.0)

        # Track usage (fire and forget)
        try:
            if rule.id:
                await self._repo.increment_usage(rule.id, success=True)
        except Exception:
            # Don't fail routing if tracking fails
            pass

        # Record metrics
        duration = time.time() - start_time
        if rule.id:
            self._metrics.record_rule_application(
                tenant_id=tenant_id, rule_id=rule.id, duration=duration, success=True
            )

        return rule.target_supervisor or original_supervisor, new_confidence, rule.id

    async def create_rule(
        self,
        tenant_id: str,
        rule_type: str,
        trigger_keywords: list[str],
        target_supervisor: str,
        confidence: float = 0.8,
        priority: int = 5,
    ) -> AdaptationRule:
        """
        Create a new adaptation rule.
        """
        import uuid

        rule = AdaptationRule(
            id=f"rule_{uuid.uuid4().hex[:8]}",
            rule_type=rule_type,
            trigger_keywords=trigger_keywords,
            target_supervisor=target_supervisor,
            confidence=confidence,
            priority=priority,
            active=True,
        )

        await self._repo.save(rule, tenant_id)
        return rule

    async def get_active_rules(self, tenant_id: str, limit: int = 100) -> list[AdaptationRule]:
        """Get all active rules for tenant."""
        return await self._repo.get_active_rules(tenant_id, limit)

    async def deactivate_rule(self, rule_id: str, tenant_id: str) -> bool:
        """Deactivate a rule."""
        return await self._repo.deactivate(rule_id, tenant_id)

    async def activate_rule(self, rule_id: str, tenant_id: str) -> bool:
        """Activate a rule."""
        return await self._repo.activate(rule_id, tenant_id)

    async def get_rule_stats(self, tenant_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get statistics about rules."""
        active_rules = await self._repo.get_active_rules(tenant_id, limit=1000)

        total_applications = sum((r.times_applied or 0) for r in active_rules)
        avg_success_rate = (
            sum((r.success_rate or 0.0) for r in active_rules) / len(active_rules)
            if active_rules
            else 0.0
        )

        return {
            "active_rules_count": len(active_rules),
            "total_applications": total_applications,
            "average_success_rate": round(avg_success_rate, 2),
            "high_priority_rules": len([r for r in active_rules if (r.priority or 0) >= 8]),
        }


class LearningAnalyticsService:
    """
    Service for learning analytics and reporting.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._insight_repo = LearningInsightRepository(session)
        self._rule_repo = AdaptationRuleRepository(session)

    async def get_dashboard_metrics(self, tenant_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get metrics for learning dashboard."""
        # This would include more complex aggregations in a real implementation
        unprocessed = await self._insight_repo.get_unprocessed(tenant_id)
        active_rules = await self._rule_repo.get_active_rules(tenant_id, limit=1000)

        return {
            "insights_pending": len(unprocessed),
            "active_adaptations": len(active_rules),
            "total_rule_applications": sum((r.times_applied or 0) for r in active_rules),
            "average_rule_confidence": (
                round(sum((r.confidence or 0.0) for r in active_rules) / len(active_rules), 2)
                if active_rules
                else 0.0
            ),
        }
