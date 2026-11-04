"""
AI Quality Collectors - Slice 3
Sprint 4 - S4.3: AI quality metric collectors

Tracks and measures AI agent quality:
- Intent match accuracy
- Hallucination detection
- User override rates
- Confidence scoring
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.procedures.ai_quality_repository import AIQualityEventRepository
from src.core.procedures.models import AIQualityEvent
from src.core.procedures.schemas import AIQualityEventCreate

# Import Prometheus metrics (will be created if not exists)
AI_HALLUCINATION_RATE: Any = None
AI_INTENT_MATCH_ACCURACY: Any = None
AI_USER_OVERRIDE_RATE: Any = None

try:
    from src.core.observability.metrics import (
        AI_HALLUCINATION_RATE,
        AI_INTENT_MATCH_ACCURACY,
        AI_USER_OVERRIDE_RATE,
    )

    HAS_METRICS = True
except ImportError:
    HAS_METRICS = False


class AIQualityCollector:
    """
    Collects and analyzes AI quality metrics for procedure executions.

    Responsibilities:
    - Calculate intent match accuracy
    - Detect and record hallucinations
    - Track user overrides
    - Update Prometheus metrics
    - Trigger alerts on quality degradation
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        alert_threshold: float = 0.90,
    ) -> None:
        """
        Initialize AI Quality Collector.

        Args:
            db: Database session
            tenant_id: Tenant ID used for repository-level isolation
            alert_threshold: Accuracy threshold below which to trigger alerts (default 0.90)
        """
        self.db = db
        self.repository = AIQualityEventRepository(db, tenant_id=tenant_id)
        self.alert_threshold = alert_threshold

    def calculate_match_accuracy(self, executions: list[dict[str, Any]]) -> float:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate intent match accuracy as ratio of auto-selected vs user-override.

        Args:
            executions: List[Any] of execution dicts with 'auto_selected' boolean field  # TODO(TYPE): replace Any with concrete type

        Returns:
            Accuracy ratio (0.0 to 1.0)

        Example:
            executions = [
                {"procedure_id": "p1", "auto_selected": True},
                {"procedure_id": "p2", "auto_selected": False},  # user override
                {"procedure_id": "p3", "auto_selected": True},
            ]
            accuracy = calculate_match_accuracy(executions)  # Returns 0.667
        """
        if not executions:
            return 0.0

        auto_selected_count = sum(1 for ex in executions if ex.get("auto_selected", False))
        total_count = len(executions)

        return auto_selected_count / total_count if total_count > 0 else 0.0

    async def record_hallucination(
        self, execution_id: UUID, procedure_id: str, details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> AIQualityEvent:
        """
        Record a hallucination event (e.g., matched a deleted procedure).

        Args:
            execution_id: Procedure execution ID
            procedure_id: The hallucinated procedure ID
            details: Additional details about the hallucination

        Returns:
            Created AIQualityEvent
        """
        event_data = AIQualityEventCreate(
            execution_id=execution_id,
            event_type="hallucination",
            severity="error",
            details={
                "procedure_id": procedure_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **details,
            },
        )

        event = await self.repository.record_event(event_data)
        return event

    def should_trigger_alert(self, accuracy: float, threshold: float | None = None) -> bool:
        """
        Check if accuracy is below threshold and alert should be triggered.

        Args:
            accuracy: Current accuracy metric (0.0 to 1.0)
            threshold: Custom threshold (defaults to self.alert_threshold)

        Returns:
            True if alert should trigger, False otherwise
        """
        alert_threshold = threshold if threshold is not None else self.alert_threshold
        return accuracy < alert_threshold

    async def record_event(
        self,
        execution_id: UUID,
        event_type: str,
        severity: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> AIQualityEvent:
        """
        Record a generic AI quality event.

        Args:
            execution_id: Procedure execution ID
            event_type: Type of event (hallucination, low_confidence, user_override, etc.)
            severity: Severity level (info, warning, error, critical)
            details: Event details as dict

        Returns:
            Created AIQualityEvent
        """
        event_data = AIQualityEventCreate(
            execution_id=execution_id,
            event_type=event_type,
            severity=severity,
            details=details,
        )

        # Create event object directly for testing
        event = AIQualityEvent(
            execution_id=execution_id,
            event_type=event_type,
            severity=severity,
            details=details,
        )

        # Add to session
        self.db.add(event)
        await self.db.flush()

        return event

    def update_metrics(
        self,
        tenant_id: int,
        accuracy: float | None = None,
        hallucination_rate: float | None = None,
        override_rate: float | None = None,
    ) -> None:
        """
        Update Prometheus metrics for AI quality.

        Args:
            tenant_id: Tenant ID for metric labels
            accuracy: Intent match accuracy (0.0 to 1.0)
            hallucination_rate: Hallucination rate (0.0 to 1.0)
            override_rate: User override rate (0.0 to 1.0)
        """
        if not HAS_METRICS:
            return  # Metrics not available

        if accuracy is not None:
            AI_INTENT_MATCH_ACCURACY.labels(tenant_id=tenant_id).set(accuracy)

        if hallucination_rate is not None:
            AI_HALLUCINATION_RATE.labels(tenant_id=tenant_id).set(hallucination_rate)

        if override_rate is not None:
            AI_USER_OVERRIDE_RATE.labels(tenant_id=tenant_id).set(override_rate)

    async def record_user_override(
        self,
        execution_id: UUID,
        suggested_procedure: str,
        selected_procedure: str,
        reason: str | None = None,
    ) -> AIQualityEvent:
        """
        Record when user overrides AI suggestion.

        Args:
            execution_id: Procedure execution ID
            suggested_procedure: AI-suggested procedure
            selected_procedure: User-selected procedure
            reason: Optional reason for override

        Returns:
            Created AIQualityEvent
        """
        event_data = AIQualityEventCreate(
            execution_id=execution_id,
            event_type="user_override",
            severity="info",
            details={
                "suggested_procedure": suggested_procedure,
                "selected_procedure": selected_procedure,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        event = await self.repository.record_event(event_data)
        return event

    def analyze_batch(self, executions: list[dict[str, Any]], tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze quality metrics for a batch of executions.

        Args:
            executions: List[Any] of execution dicts with quality metrics  # TODO(TYPE): replace Any with concrete type
            tenant_id: Tenant ID for metric updates

        Returns: Dict[str, Any] with aggregated quality metrics  # TODO(TYPE): replace Any with concrete type
        """
        if not executions:
            return {
                "accuracy": 0.0,
                "hallucination_rate": 0.0,
                "avg_confidence": 0.0,
                "total_executions": 0,
            }

        total = len(executions)
        auto_selected = sum(1 for ex in executions if ex.get("auto_selected", False))
        hallucinations = sum(1 for ex in executions if ex.get("had_hallucination", False))
        confidences = [ex.get("confidence", 0.0) for ex in executions if "confidence" in ex]

        accuracy = auto_selected / total
        hallucination_rate = hallucinations / total
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        override_rate = 1.0 - accuracy

        # Update Prometheus metrics
        self.update_metrics(
            tenant_id=tenant_id,
            accuracy=accuracy,
            hallucination_rate=hallucination_rate,
            override_rate=override_rate,
        )

        return {
            "accuracy": accuracy,
            "hallucination_rate": hallucination_rate,
            "avg_confidence": avg_confidence,
            "override_rate": override_rate,
            "total_executions": total,
        }
