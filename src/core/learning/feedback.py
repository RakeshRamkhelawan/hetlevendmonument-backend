"""
Feedback collection and processing for learning system.

Provides:
- Feedback collection
- Async processing
- A/B testing support
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """Collects and processes user feedback."""

    def __init__(self) -> None:
        self._queue: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    async def collect(self, feedback: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Collect feedback and return ID."""
        feedback_id = f"fb_{datetime.now(timezone.utc).timestamp()}"
        feedback["id"] = feedback_id
        feedback["collected_at"] = datetime.now(timezone.utc).isoformat()

        self._queue.append(feedback)
        logger.info(f"Collected feedback: {feedback_id}")
        return feedback_id

    async def process_queue(self) -> int:
        """Process all queued feedback."""
        count = len(self._queue)
        self._queue.clear()
        return count


async def collect_routing_feedback(
    message_id: str, routing_decision: str, user_rating: int, tenant_id: str | None = None
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Collect feedback about routing decisions.

    Args:
        message_id: ID of the message/conversation
        routing_decision: Which supervisor handled it
        user_rating: 1-5 rating
        tenant_id: Optional tenant identifier

    Returns:
        Feedback record
    """
    feedback = {
        "id": f"routing_fb_{datetime.now(timezone.utc).timestamp()}",
        "type": "routing_feedback",
        "message_id": message_id,
        "routing_decision": routing_decision,
        "user_rating": user_rating,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"Collected routing feedback for {message_id}: {user_rating}/5")
    return feedback


async def store_async(feedback: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
    """
    Store feedback for async processing.

    Args:
        feedback: Feedback data

    Returns:
        True if queued successfully
    """
    # In production, this would queue to Redis/Dramatiq
    # For now, just log it
    logger.info(f"Queued feedback for async processing: {feedback.get('id', 'unknown')}")
    return True


# A/B Testing support
class ABTestConfig:
    """Configuration for A/B testing."""

    def __init__(
        self, test_name: str, variant_a: str, variant_b: str, split_ratio: float = 0.5
    ) -> None:
        self.test_name = test_name
        self.variant_a = variant_a
        self.variant_b = variant_b
        self.split_ratio = split_ratio


def assign_variant(user_id: str, test_config: ABTestConfig) -> str:
    """
    Assign user to A/B test variant.

    Args:
        user_id: User identifier
        test_config: Test configuration

    Returns:
        Variant name (a or b)
    """
    import hashlib

    # Deterministic assignment based on user_id
    hash_val = int(
        hashlib.md5(
            f"{user_id}:{test_config.test_name}".encode(), usedforsecurity=False
        ).hexdigest(),
        16,
    )
    return (
        test_config.variant_a
        if (hash_val % 100) < (test_config.split_ratio * 100)
        else test_config.variant_b
    )
