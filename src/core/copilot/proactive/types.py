"""
Core data types for proactive monitors.

Signal is an immutable frozen dataclass (NOT hashable due to list/dict fields).
Serialization via to_dict / from_dict for Redis caching and event bus transport.

Per CLAUDE.md regel 3: all datetimes are timezone-aware UTC.
Per CLAUDE.md regel 10: all source code is ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from src.core.copilot.council.types import DataClassification, Severity


@dataclass(frozen=True)
class Signal:
    """A proactively detected condition. NOT hashable (lists/dicts in fields)."""

    # Non-default fields FIRST (dataclass requirement)
    tenant_id: int
    affected_user_id: int
    monitor_name: str
    title: str
    body: str
    severity: Severity
    data_classification: DataClassification
    suggested_actions: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    detection_reasoning: str
    confidence: float
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    # Default fields LAST
    signal_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not self.title or not self.body:
            raise ValueError("title and body are required")
        if self.tenant_id <= 0:
            raise ValueError("tenant_id must be > 0")
        if self.affected_user_id <= 0:
            raise ValueError("affected_user_id must be > 0")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    @property
    def bypasses_budget(self) -> bool:
        """CRITICAL severity bypasses notification budget (ADR-027 sec 9.1)."""
        return self.severity == Severity.CRITICAL

    def dedup_key(self, entity_id: str) -> str:
        """String projection for Redis dedup (Signal itself is not hashable)."""
        return f"monitor_dedup:{self.monitor_name}:{self.tenant_id}:{entity_id}"

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "signal_id": str(self.signal_id),
            "tenant_id": self.tenant_id,
            "affected_user_id": self.affected_user_id,
            "monitor_name": self.monitor_name,
            "title": self.title,
            "body": self.body,
            "severity": self.severity.value,
            "data_classification": self.data_classification.value,
            "suggested_actions": self.suggested_actions,
            "detection_reasoning": self.detection_reasoning,
            "confidence": self.confidence,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Signal":  # TODO(TYPE): replace Any with concrete type
        return cls(
            signal_id=UUID(data["signal_id"]),
            tenant_id=data["tenant_id"],
            affected_user_id=data["affected_user_id"],
            monitor_name=data["monitor_name"],
            title=data["title"],
            body=data["body"],
            severity=Severity(data["severity"]),
            data_classification=DataClassification(data["data_classification"]),
            suggested_actions=data["suggested_actions"],
            detection_reasoning=data["detection_reasoning"],
            confidence=data["confidence"],
            context=data["context"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )
