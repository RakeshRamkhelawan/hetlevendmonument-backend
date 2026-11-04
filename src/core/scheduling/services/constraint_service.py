"""Constraint service for managing hard and soft scheduling constraints.

This service handles:
- Hard constraints: Must be respected (e.g., working hours, blocked times)
- Soft constraints: Preferred but can be violated with penalty (e.g., preferred duration)
- Constraint validation and scoring
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.core.scheduling.models import SchedulingConstraint
from src.core.scheduling.repository import ConstraintRepository, PreferenceRepository

logger = logging.getLogger(__name__)


@dataclass
class ConstraintViolation:
    """Represents a constraint violation with severity."""

    constraint_type: str
    message: str
    severity: str  # "hard" | "soft"
    penalty: float  # 0.0 to 1.0


@dataclass
class ConstraintCheckResult:
    """Result of checking constraints for a proposed time slot."""

    is_valid: bool
    violations: list[ConstraintViolation]
    total_penalty: float


class ConstraintService:
    """Service for managing and validating scheduling constraints."""

    def __init__(
        self,
        constraint_repo: ConstraintRepository,
        preference_repo: PreferenceRepository,
    ) -> None:
        self._constraint_repo = constraint_repo
        self._preference_repo = preference_repo

    async def get_constraints(
        self,
        tenant_id: int,
        user_id: str,
    ) -> list[SchedulingConstraint]:
        """Get all active constraints for a user.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            List of active scheduling constraints
        """
        return await self._constraint_repo.list_by_user(tenant_id, user_id)

    async def get_hard_constraints(
        self,
        tenant_id: int,
        user_id: str,
    ) -> list[SchedulingConstraint]:
        """Get only hard constraints for a user.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            List of hard scheduling constraints
        """
        return await self._constraint_repo.list_hard_constraints(tenant_id, user_id)

    async def check_constraints(
        self,
        tenant_id: int,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> ConstraintCheckResult:
        """Check if a proposed time slot violates any constraints.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            start_time: Proposed start time
            end_time: Proposed end time

        Returns:
            ConstraintCheckResult with violations and penalties
        """
        violations: list[ConstraintViolation] = []

        # Get user preferences for working hours
        prefs = await self._preference_repo.get_by_user(tenant_id, user_id)

        # Check working hours constraint
        if prefs and prefs.working_hours_start and prefs.working_hours_end:
            # Convert datetime to time for comparison
            start_time_only = start_time.time()
            end_time_only = end_time.time()

            # Check if outside working hours
            if (
                start_time_only < prefs.working_hours_start
                or end_time_only > prefs.working_hours_end
            ):
                wh_start_str = prefs.working_hours_start.strftime("%H:%M")
                wh_end_str = prefs.working_hours_end.strftime("%H:%M")
                violations.append(
                    ConstraintViolation(
                        constraint_type="working_hours",
                        message=f"Time outside working hours ({wh_start_str}-{wh_end_str})",
                        severity="soft",
                        penalty=0.3,
                    )
                )

        # Check custom constraints
        constraints = await self.get_constraints(tenant_id, user_id)
        for constraint in constraints:
            violation = self._check_constraint(constraint, start_time, end_time)
            if violation:
                violations.append(violation)

        # Calculate total penalty
        total_penalty = sum(v.penalty for v in violations)

        # Check if any hard constraints are violated
        has_hard_violation = any(v.severity == "hard" for v in violations)

        return ConstraintCheckResult(
            is_valid=not has_hard_violation,
            violations=violations,
            total_penalty=min(1.0, total_penalty),
        )

    def _check_constraint(
        self,
        constraint: SchedulingConstraint,
        start_time: datetime,
        end_time: datetime,
    ) -> ConstraintViolation | None:
        """Check a single constraint against a time slot.

        Args:
            constraint: The constraint to check
            start_time: Proposed start time
            end_time: Proposed end time

        Returns:
            ConstraintViolation if violated, None otherwise
        """
        params = constraint.parameters or {}

        if constraint.constraint_type == "blocked_time":
            # Check if time overlaps with blocked period
            blocked_start = params.get("start_time")
            blocked_end = params.get("end_time")
            if blocked_start and blocked_end:
                # Parse blocked times
                try:
                    bs = datetime.fromisoformat(blocked_start)
                    be = datetime.fromisoformat(blocked_end)
                    # Ensure timezone-aware comparison
                    if bs.tzinfo is None and start_time.tzinfo is not None:
                        bs = bs.replace(tzinfo=start_time.tzinfo)
                    if be.tzinfo is None and end_time.tzinfo is not None:
                        be = be.replace(tzinfo=end_time.tzinfo)
                    if start_time < be and end_time > bs:
                        return ConstraintViolation(
                            constraint_type="blocked_time",
                            message=params.get("message", "Time blocked"),
                            severity="hard" if constraint.is_hard else "soft",
                            penalty=1.0 if constraint.is_hard else 0.5,
                        )
                except (ValueError, TypeError):
                    pass

        elif constraint.constraint_type == "max_duration":
            # Check if duration exceeds maximum
            max_duration = params.get("max_minutes")
            if max_duration:
                duration = (end_time - start_time).total_seconds() / 60
                if duration > max_duration:
                    return ConstraintViolation(
                        constraint_type="max_duration",
                        message=f"Duration exceeds {max_duration} minutes",
                        severity="soft",
                        penalty=0.2,
                    )

        elif constraint.constraint_type == "min_duration":
            # Check if duration is below minimum
            min_duration = params.get("min_minutes")
            if min_duration:
                duration = (end_time - start_time).total_seconds() / 60
                if duration < min_duration:
                    return ConstraintViolation(
                        constraint_type="min_duration",
                        message=f"Duration below {min_duration} minutes",
                        severity="soft",
                        penalty=0.2,
                    )

        elif constraint.constraint_type == "preferred_time":
            # Check if time matches preferred time window
            preferred_start = params.get("start_hour")
            preferred_end = params.get("end_hour")
            if preferred_start is not None and preferred_end is not None:
                start_hour = start_time.hour + start_time.minute / 60
                if not (preferred_start <= start_hour <= preferred_end):
                    return ConstraintViolation(
                        constraint_type="preferred_time",
                        message="Outside preferred time window",
                        severity="soft",
                        penalty=0.15,
                    )

        return None

    async def validate_constraints(
        self,
        tenant_id: int,
        user_ids: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate constraints for multiple users.

        Args:
            tenant_id: Tenant ID
            user_ids: List of user IDs to check
            start_time: Proposed start time
            end_time: Proposed end time

        Returns:
            Dictionary with validation results per user
        """
        results = {}
        for user_id in user_ids:
            result = await self.check_constraints(tenant_id, user_id, start_time, end_time)
            results[user_id] = {
                "is_valid": result.is_valid,
                "violations": [
                    {
                        "type": v.constraint_type,
                        "message": v.message,
                        "severity": v.severity,
                        "penalty": v.penalty,
                    }
                    for v in result.violations
                ],
                "total_penalty": result.total_penalty,
            }
        return results

    def calculate_constraint_score(
        self,
        violations: list[ConstraintViolation],
    ) -> float:
        """Calculate a constraint satisfaction score.

        Args:
            violations: List of constraint violations

        Returns:
            Score between 0.0 (all violated) and 1.0 (none violated)
        """
        if not violations:
            return 1.0

        total_penalty = sum(v.penalty for v in violations)
        return max(0.0, 1.0 - total_penalty)
