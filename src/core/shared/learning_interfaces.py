"""Shared interfaces for learning data access -- infra-layer boundary.

Defines the protocol and data type for reading LearningExperience records without
importing the SQLAlchemy ORM model (which lives in agent_runtime layer).

The concrete implementation is LearningExperienceRepository in
src/core/learning/experience_reader.py.

NOTE: do not add 'from __future__ import annotations' -- breaks runtime Protocol checks.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class LearningExperienceData:
    """Plain data container for a learning experience record.

    Fields match the LearningExperience ORM model columns.
    created_at is always timezone-aware (UTC).
    """

    tenant_id: int
    created_at: datetime
    success: bool | None
    duration: float | None
    confidence: float
    event_type: str
    task_type: str | None
    agent_id: str | None


class ILearningExperienceReader(Protocol):
    """Protocol for reading learning experience records.

    All call sites must pass tenant_id to enforce per-tenant data isolation.
    Passing tenant_id=None returns cross-tenant data and is intentionally
    not supported by DriftDetector.
    """

    async def get_experiences(
        self,
        start_time: datetime,
        end_time: datetime,
        tenant_id: int | None = None,
        require_success_value: bool = False,
    ) -> list[LearningExperienceData]:
        """Return experiences in [start_time, end_time).

        Args:
            start_time: Window start (inclusive), must be timezone-aware.
            end_time: Window end (exclusive), must be timezone-aware.
            tenant_id: Scope to this tenant. Pass self.tenant_id from DriftDetector.
            require_success_value: If True, only records where success is not None.
                Caller may assume item.success is not None for all returned items.
        """
        ...


__all__ = ["LearningExperienceData", "ILearningExperienceReader"]
