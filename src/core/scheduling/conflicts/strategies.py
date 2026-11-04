"""
Conflict resolution strategies for calendar synchronization.

Implements multiple strategies for resolving conflicts between local
and external calendar events.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from src.core.scheduling.integrations.base_provider import ExternalEvent
from src.core.scheduling.models import CalendarEvent


@dataclass
class ResolutionResult:
    """Result of a conflict resolution."""

    success: bool
    strategy: str
    local_event_id: str
    external_event_id: str
    action_taken: str  # description of what was done
    error_message: str | None = None


class ConflictResolutionStrategy(ABC):
    """Abstract base class for conflict resolution strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the strategy name."""
        pass

    @abstractmethod
    async def resolve(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        local_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """
        Resolve the conflict using this strategy.

        Args:
            local_event: The local CalendarEvent
            external_event: The external ExternalEvent
            local_data: Additional local event data
            external_data: Additional external event data

        Returns:
            ResolutionResult indicating success/failure
        """
        pass


class KeepLocalStrategy(ConflictResolutionStrategy):
    """
    Keep the local version, discard external changes.

    Use when local changes are authoritative.
    """

    @property
    def name(self) -> str:
        return "keep_local"

    async def resolve(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        local_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """Keep local event, optionally push to external."""
        # Local event remains unchanged
        # Optionally: Push local state to external calendar

        return ResolutionResult(
            success=True,
            strategy=self.name,
            local_event_id=str(local_event.id),
            external_event_id=external_event.external_id,
            action_taken="Kept local event unchanged; external changes ignored",
        )


class KeepExternalStrategy(ConflictResolutionStrategy):
    """
    Keep the external version, overwrite local.

    Use when external calendar is authoritative.
    """

    @property
    def name(self) -> str:
        return "keep_external"

    async def resolve(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        local_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """Overwrite local event with external data."""
        # Update local event with external data
        local_event.title = external_event.title
        local_event.description = external_event.description
        local_event.start_time = external_event.start_time
        local_event.end_time = external_event.end_time
        local_event.location = external_event.location

        return ResolutionResult(
            success=True,
            strategy=self.name,
            local_event_id=str(local_event.id),
            external_event_id=external_event.external_id,
            action_taken="Local event overwritten with external data",
        )


class MergeStrategy(ConflictResolutionStrategy):
    """
    Merge local and external changes intelligently.

    Combines non-conflicting fields from both versions.
    """

    @property
    def name(self) -> str:
        return "merge"

    async def resolve(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        local_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """Merge local and external event data."""
        # Merge strategy: keep most recent changes per field
        local_updated = local_data.get("updated_at")
        external_updated = external_data.get("updated_at")

        # Use titles from whichever was updated more recently
        if external_updated and (not local_updated or external_updated > local_updated):
            local_event.title = external_event.title
            local_event.description = external_event.description
        # else: keep local title/description

        # Always use external time if different (external is authoritative for time)
        if external_event.start_time != local_event.start_time:
            local_event.start_time = external_event.start_time
        if external_event.end_time != local_event.end_time:
            local_event.end_time = external_event.end_time

        # Merge location: prefer external if local is empty
        if external_event.location and not local_event.location:
            local_event.location = external_event.location

        return ResolutionResult(
            success=True,
            strategy=self.name,
            local_event_id=str(local_event.id),
            external_event_id=external_event.external_id,
            action_taken="Merged local and external changes (title/desc from most recent, times from external)",
        )


class CreateDuplicateStrategy(ConflictResolutionStrategy):
    """
    Create a duplicate event rather than merging.

    Use when both versions should be preserved.
    """

    @property
    def name(self) -> str:
        return "create_duplicate"

    async def resolve(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        local_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """Mark conflict for manual resolution by creating duplicate."""
        # This strategy doesn't auto-resolve; it flags for manual intervention
        return ResolutionResult(
            success=False,
            strategy=self.name,
            local_event_id=str(local_event.id),
            external_event_id=external_event.external_id,
            action_taken="Flagged for manual resolution - both versions preserved",
        )


class AutoResolveStrategy(ConflictResolutionStrategy):
    """
    Automatically choose resolution strategy based on conflict type.

    Uses heuristics to determine best resolution:
    - If external deleted -> keep_local (recreate)
    - If times differ by < 5 min -> merge (likely drift)
    - If titles differ but times match -> merge (keep both)
    - If both times and titles differ -> flag for manual
    """

    @property
    def name(self) -> str:
        return "auto_resolve"

    async def resolve(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        local_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """Automatically resolve based on heuristics."""

        # Check if external was deleted
        if external_event.status in ("cancelled", "deleted"):
            # External deleted - keep local, mark for push
            return ResolutionResult(
                success=True,
                strategy=self.name,
                local_event_id=str(local_event.id),
                external_event_id=external_event.external_id,
                action_taken="External deleted; keeping local event",
            )

        # Check time difference
        time_diff_start = abs((external_event.start_time - local_event.start_time).total_seconds())
        time_diff_end = abs((external_event.end_time - local_event.end_time).total_seconds())

        # Small time drift (< 5 minutes) - likely just clock skew
        if time_diff_start < 300 and time_diff_end < 300:
            # Use merge strategy for small time differences
            merge = MergeStrategy()
            result = await merge.resolve(local_event, external_event, local_data, external_data)
            result.strategy = self.name  # Override strategy name
            return result

        # Significant differences - flag for manual resolution
        return ResolutionResult(
            success=False,
            strategy=self.name,
            local_event_id=str(local_event.id),
            external_event_id=external_event.external_id,
            action_taken="Significant differences detected; flagged for manual resolution",
        )
