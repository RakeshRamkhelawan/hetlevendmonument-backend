"""
Abstract base class for external calendar providers.

Each provider (Google, Outlook) implements this protocol so that
the sync service and scheduling service can work provider-agnostically.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ExternalEvent:
    """Normalised representation of an external calendar event."""

    external_id: str
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None
    organizer_email: str | None = None
    attendees: list[str] = field(default_factory=list)
    status: str = "confirmed"
    is_all_day: bool = False
    raw: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


@dataclass
class SyncResult:
    """Result of a calendar sync operation."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    next_sync_token: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class OAuthTokens:
    """Token set returned from an OAuth exchange."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str = "Bearer"
    account_id: str | None = None


class BaseCalendarProvider(ABC):
    """Abstract calendar provider.

    Implementations must handle:
    - OAuth token exchange & refresh
    - Listing events (full or incremental via sync token)
    - Creating / updating / deleting events on the external calendar
    """

    provider_name: str = ""

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange an authorization code for tokens."""

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Refresh an expired access token."""

    @abstractmethod
    async def list_events(
        self,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        sync_token: str | None = None,
        calendar_id: str = "primary",
    ) -> tuple[list[ExternalEvent], str | None]:
        """List events, optionally incremental via *sync_token*.

        Returns (events, next_sync_token).
        """

    @abstractmethod
    async def create_event(
        self,
        access_token: str,
        event: ExternalEvent,
        calendar_id: str = "primary",
    ) -> str:
        """Create an event on the external calendar.

        Returns the external event ID.
        """

    @abstractmethod
    async def update_event(
        self,
        access_token: str,
        external_id: str,
        event: ExternalEvent,
        calendar_id: str = "primary",
    ) -> None:
        """Update an existing event on the external calendar."""

    @abstractmethod
    async def delete_event(
        self,
        access_token: str,
        external_id: str,
        calendar_id: str = "primary",
    ) -> None:
        """Delete an event from the external calendar."""

    @abstractmethod
    async def get_user_info(self, access_token: str) -> dict[str, str]:
        """Return provider account id and email for the authenticated user."""
