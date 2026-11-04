"""
Slot finder: generates candidate time slots within a window and scores them.

Uses working-hour preferences and buffer time to produce ranked options.
"""

import logging
from datetime import datetime, timedelta

from src.core.scheduling.repository import PreferenceRepository
from src.core.scheduling.schemas import SchedulingOption
from src.core.scheduling.services.conflict_service import ConflictDetectionService

logger = logging.getLogger(__name__)

# Defaults when no preferences exist
_DEFAULT_WORK_START_HOUR = 9
_DEFAULT_WORK_END_HOUR = 17
_DEFAULT_BUFFER_MINUTES = 5
_SLOT_STEP_MINUTES = 15


class SlotFinder:
    """Finds available scheduling slots within a time window."""

    def __init__(
        self,
        conflict_service: ConflictDetectionService,
        preference_repo: PreferenceRepository,
    ) -> None:
        self._conflict_svc = conflict_service
        self._pref_repo = preference_repo

    async def find_slots(
        self,
        tenant_id: int,
        organizer_id: str,
        participant_ids: list[str],
        duration_minutes: int,
        earliest_start: datetime,
        latest_end: datetime,
        max_options: int = 5,
    ) -> list[SchedulingOption]:
        """Generate and rank available time slots.

        Scans the window in 15-minute increments, skips slots with hard
        conflicts, and scores remaining ones based on working-hour alignment
        and conflict count.
        """
        prefs = await self._pref_repo.get_by_user(tenant_id, organizer_id)
        work_start_hour = _DEFAULT_WORK_START_HOUR
        work_end_hour = _DEFAULT_WORK_END_HOUR
        buffer = _DEFAULT_BUFFER_MINUTES

        if prefs:
            if prefs.working_hours_start:
                whs = prefs.working_hours_start
                if isinstance(whs, str):
                    work_start_hour = int(whs.split(":")[0])
                else:
                    work_start_hour = whs.hour
            if prefs.working_hours_end:
                whe = prefs.working_hours_end
                if isinstance(whe, str):
                    work_end_hour = int(whe.split(":")[0])
                else:
                    work_end_hour = whe.hour
            buffer = prefs.buffer_minutes

        duration = timedelta(minutes=duration_minutes)
        step = timedelta(minutes=_SLOT_STEP_MINUTES)
        buffered_duration = duration + timedelta(minutes=buffer)

        candidates: list[SchedulingOption] = []
        current = earliest_start

        while current + buffered_duration <= latest_end:
            slot_end = current + duration

            # Score based on working hours
            hour = current.hour
            in_working_hours = work_start_hour <= hour < work_end_hour
            wh_score = 0.5 if in_working_hours else 0.1

            # Check for conflicts
            conflicts = await self._conflict_svc.check_conflicts(
                tenant_id=tenant_id,
                organizer_id=organizer_id,
                participant_ids=participant_ids,
                start=current,
                end=slot_end,
            )

            hard_conflicts = [c for c in conflicts if c.severity == "hard"]
            if hard_conflicts:
                current += step
                continue

            soft_conflicts = [c for c in conflicts if c.severity == "soft"]
            conflict_penalty = len(soft_conflicts) * 0.1
            score = max(0.0, min(1.0, wh_score - conflict_penalty))

            candidates.append(
                SchedulingOption(
                    start_time=current,
                    end_time=slot_end,
                    confidence_score=round(score, 2),
                    conflicts=[c.event_id for c in soft_conflicts],
                    score_breakdown={
                        "working_hours": wh_score,
                        "conflict_penalty": -conflict_penalty,
                    },
                )
            )

            current += step

        # Return top N by confidence
        candidates.sort(key=lambda o: o.confidence_score, reverse=True)
        return candidates[:max_options]
