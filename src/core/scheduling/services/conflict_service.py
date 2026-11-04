"""
SQL-based conflict detection service.

No IntervalTree -- the composite index on (tenant_id, start_time, end_time)
already gives O(log n) overlap queries. Adding an in-memory tree on top of
that adds complexity without measurable benefit at current scale.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.core.scheduling.repository import CalendarEventRepository, TimeBlockRepository

logger = logging.getLogger(__name__)


@dataclass
class ConflictResult:
    """Result of a conflict check."""

    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    severity: str  # "hard" (same person) | "soft" (resource)
    participant_id: str


class ConflictDetectionService:
    """Detects scheduling conflicts using SQL range-overlap queries."""

    def __init__(
        self,
        event_repo: CalendarEventRepository,
        block_repo: TimeBlockRepository,
    ) -> None:
        self._event_repo = event_repo
        self._block_repo = block_repo

    async def check_conflicts(
        self,
        tenant_id: int,
        organizer_id: str,
        participant_ids: list[str],
        start: datetime,
        end: datetime,
        exclude_event_id: str | None = None,
    ) -> list[ConflictResult]:
        """Check for conflicts with existing events and hard time blocks.

        1. Organizer direct overlap (hard conflict)
        2. Participant overlap (hard conflict)
        3. Hard time-block overlap for organizer (hard conflict)
        """
        conflicts: list[ConflictResult] = []

        # 1. Organizer conflicts
        organizer_overlaps = await self._event_repo.find_overlapping(
            tenant_id=tenant_id,
            user_id=organizer_id,
            start=start,
            end=end,
            exclude_event_id=exclude_event_id,
        )
        for ev in organizer_overlaps:
            conflicts.append(
                ConflictResult(
                    event_id=ev.id,
                    title=ev.title,
                    start_time=ev.start_time,
                    end_time=ev.end_time,
                    severity="hard",
                    participant_id=organizer_id,
                )
            )

        # 2. Participant conflicts
        other_participants = [p for p in participant_ids if p != organizer_id]
        if other_participants:
            participant_overlaps = await self._event_repo.find_participant_overlapping(
                tenant_id=tenant_id,
                participant_ids=other_participants,
                start=start,
                end=end,
                exclude_event_id=exclude_event_id,
            )
            for ev in participant_overlaps:
                conflicts.append(
                    ConflictResult(
                        event_id=ev.id,
                        title=ev.title,
                        start_time=ev.start_time,
                        end_time=ev.end_time,
                        severity="hard",
                        participant_id=ev.organizer_id,
                    )
                )

        # 3. Hard time-block conflicts for organizer
        hard_blocks = await self._block_repo.find_hard_blocks_in_range(
            tenant_id=tenant_id,
            user_id=organizer_id,
            start=start,
            end=end,
        )
        for block in hard_blocks:
            conflicts.append(
                ConflictResult(
                    event_id=block.id,
                    title=block.label or f"Time block ({block.block_type})",
                    start_time=block.start_time,
                    end_time=block.end_time,
                    severity="hard",
                    participant_id=organizer_id,
                )
            )

        return conflicts

    async def has_hard_conflicts(
        self,
        tenant_id: int,
        organizer_id: str,
        participant_ids: list[str],
        start: datetime,
        end: datetime,
        exclude_event_id: str | None = None,
    ) -> bool:
        """Quick check: are there any hard conflicts?"""
        conflicts = await self.check_conflicts(
            tenant_id=tenant_id,
            organizer_id=organizer_id,
            participant_ids=participant_ids,
            start=start,
            end=end,
            exclude_event_id=exclude_event_id,
        )
        return any(c.severity == "hard" for c in conflicts)
