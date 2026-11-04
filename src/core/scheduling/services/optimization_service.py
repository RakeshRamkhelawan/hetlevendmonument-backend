"""Optimization service for multi-constraint slot scoring and ranking.

This service provides advanced scoring algorithms for scheduling options,
taking into account multiple constraints and preferences.
"""

import logging
from datetime import datetime
from typing import Optional

from src.core.scheduling.schemas import SchedulingOption

logger = logging.getLogger(__name__)


class OptimizationService:
    """Multi-constraint optimization for scheduling slots.

    Scores candidates based on:
    - Working hours alignment (higher score for business hours)
    - Participant availability (penalty for conflicts)
    - Prefered duration match (bonus for matching user's preferred duration)
    - Buffer time feasibility (ensure adequate gaps between meetings)
    """

    def __init__(self) -> None:
        """Initialize optimization service with default weights."""
        self.weights = {
            "working_hours": 0.3,
            "participant_availability": 0.4,
            "duration_match": 0.15,
            "buffer_feasibility": 0.15,
        }

    def score_options(
        self,
        options: list[SchedulingOption],
        preferred_duration_minutes: int | None = None,
        work_start_hour: int = 9,
        work_end_hour: int = 17,
    ) -> list[SchedulingOption]:
        """Score and rank scheduling options.

        Args:
            options: List of candidate scheduling options
            preferred_duration_minutes: User's preferred meeting duration
            work_start_hour: Start of working hours (default 9)
            work_end_hour: End of working hours (default 17)

        Returns:
            Options sorted by confidence score (highest first)
        """
        scored: list[SchedulingOption] = []

        for opt in options:
            score_breakdown: dict[str, float] = {}

            # 1. Working hours alignment
            start_hour = opt.start_time.hour
            end_hour = opt.end_time.hour

            starts_in_work_hours = work_start_hour <= start_hour < work_end_hour
            ends_in_work_hours = work_start_hour < end_hour <= work_end_hour

            if starts_in_work_hours and ends_in_work_hours:
                wh_score = 1.0
            elif starts_in_work_hours or ends_in_work_hours:
                wh_score = 0.6
            else:
                wh_score = 0.2

            score_breakdown["working_hours"] = wh_score

            # 2. Participant availability (already factored into conflicts)
            pa_score = 1.0 - (len(opt.conflicts) * 0.1)
            pa_score = max(0.0, pa_score)
            score_breakdown["participant_availability"] = pa_score

            # 3. Duration match (if preference provided)
            if preferred_duration_minutes:
                actual_duration = int((opt.end_time - opt.start_time).total_seconds() / 60)
                diff = abs(actual_duration - preferred_duration_minutes)
                dm_score = max(0.0, 1.0 - (diff / 30.0))  # Penalty per 30 min diff
            else:
                dm_score = 0.5  # Neutral when no preference

            score_breakdown["duration_match"] = dm_score

            # 4. Buffer feasibility (prefer slots with natural gaps)
            bf_score = 1.0 if opt.conflicts else 0.8
            score_breakdown["buffer_feasibility"] = bf_score

            # Calculate weighted total
            total_score = sum(score_breakdown[key] * self.weights[key] for key in self.weights)

            # Create updated option with new scores
            updated = SchedulingOption(
                start_time=opt.start_time,
                end_time=opt.end_time,
                confidence_score=round(total_score, 2),
                conflicts=opt.conflicts,
                score_breakdown=score_breakdown,
            )
            scored.append(updated)

        # Sort by confidence score (highest first)
        scored.sort(key=lambda x: x.confidence_score, reverse=True)
        return scored

    def select_best_option(
        self,
        options: list[SchedulingOption],
        min_confidence: float = 0.5,
    ) -> SchedulingOption | None:
        """Select the best option meeting minimum confidence threshold.

        Args:
            options: List of scored scheduling options
            min_confidence: Minimum acceptable confidence score

        Returns:
            Best option or None if none meet threshold
        """
        if not options:
            return None

        # Return first option meeting threshold
        for opt in options:
            if opt.confidence_score >= min_confidence:
                return opt

        # If no option meets threshold, return the highest scored
        logger.warning(
            "No option meets min_confidence %s, returning best available",
            min_confidence,
        )
        return options[0]

    def filter_by_constraints(
        self,
        options: list[SchedulingOption],
        min_start_time: datetime | None = None,
        max_end_time: datetime | None = None,
        exclude_conflicts: bool = False,
    ) -> list[SchedulingOption]:
        """Filter options by hard constraints.

        Args:
            options: List of scheduling options
            min_start_time: Exclude options starting before this time
            max_end_time: Exclude options ending after this time
            exclude_conflicts: If True, exclude options with any conflicts

        Returns:
            Filtered list of options
        """
        filtered: list[SchedulingOption] = []

        for opt in options:
            # Check time constraints
            if min_start_time and opt.start_time < min_start_time:
                continue

            if max_end_time and opt.end_time > max_end_time:
                continue

            # Check conflict constraint
            if exclude_conflicts and opt.conflicts:
                continue

            filtered.append(opt)

        return filtered

    def balance_participants(
        self,
        options: list[SchedulingOption],
        participant_count: int,
        target_balance: float = 0.5,
    ) -> list[SchedulingOption]:
        """Adjust scores to balance meeting load across participants.

        This is a placeholder for future load-balancing logic that would
        integrate with participant availability history.

        Args:
            options: List of scheduling options
            participant_count: Number of participants
            target_balance: Target balance ratio (0-1)

        Returns:
            Options with adjusted scores
        """
        # Placeholder: in production, this would query participant
        # meeting history and adjust scores to avoid overloading
        # heavy users or consistently selecting the same slots
        return options
