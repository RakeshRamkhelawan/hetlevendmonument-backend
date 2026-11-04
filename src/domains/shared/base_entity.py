"""
Base Entity and Aggregate Root - DDD Building Blocks
"""

from abc import ABC
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Entity(BaseModel, ABC):
    """
    Base entity class
    All domain entities inherit from this
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class AggregateRoot(Entity, ABC):
    """
    Aggregate root base class
    Coordinates domain events and maintains consistency boundaries
    """

    _domain_events: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    def add_domain_event(self, event: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add domain event to be published"""
        self._domain_events.append(event)

    def clear_domain_events(self) -> None:
        """Clear all domain events"""
        self._domain_events.clear()

    def get_domain_events(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all domain events"""
        return self._domain_events.copy()
