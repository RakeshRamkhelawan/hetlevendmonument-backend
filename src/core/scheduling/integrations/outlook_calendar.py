"""
Microsoft Outlook calendar provider using the Microsoft Graph API.

Requires ``msgraph-sdk`` for typed API access and uses ``httpx`` for
the OAuth2 token exchange (via Microsoft identity platform v2.0).

Includes retry logic for transient failures.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.scheduling.integrations.base_provider import (
    BaseCalendarProvider,
    ExternalEvent,
    OAuthTokens,
)

logger = logging.getLogger(__name__)

_MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MS_ME_URL = f"{_MS_GRAPH_BASE}/me"


class OutlookCalendarProvider(BaseCalendarProvider):
    """Microsoft Graph calendar integration."""

    provider_name = "outlook"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id or os.getenv("MICROSOFT_CALENDAR_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("MICROSOFT_CALENDAR_CLIENT_SECRET", "")

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _MS_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "scope": ("openid profile email Calendars.ReadWrite offline_access"),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_at = self._calc_expires(data.get("expires_in"))
        user_info = await self.get_user_info(data["access_token"])

        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scope=data.get("scope"),
            account_id=user_info.get("id", ""),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _MS_TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "scope": ("openid profile email Calendars.ReadWrite offline_access"),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=self._calc_expires(data.get("expires_in")),
            scope=data.get("scope"),
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def list_events(
        self,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        sync_token: str | None = None,
        calendar_id: str = "primary",
    ) -> tuple[list[ExternalEvent], str | None]:
        headers = {"Authorization": f"Bearer {access_token}"}
        events: list[ExternalEvent] = []
        next_delta: str | None = None

        if sync_token:
            url = sync_token  # deltaLink is a full URL
        else:
            url = (
                f"{_MS_GRAPH_BASE}/me/calendarView"
                f"?startDateTime={time_min.isoformat()}"
                f"&endDateTime={time_max.isoformat()}"
                f"&$top=100"
            )

        async with httpx.AsyncClient() as client:
            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("value", []):
                    events.append(self._parse_event(item))

                url = data.get("@odata.nextLink")
                if not url:
                    next_delta = data.get("@odata.deltaLink")

        return events, next_delta

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def create_event(
        self,
        access_token: str,
        event: ExternalEvent,
        calendar_id: str = "primary",
    ) -> str:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body = self._build_event_body(event)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_MS_GRAPH_BASE}/me/events",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            return cast(str, resp.json()["id"])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def update_event(
        self,
        access_token: str,
        external_id: str,
        event: ExternalEvent,
        calendar_id: str = "primary",
    ) -> None:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body = self._build_event_body(event)
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{_MS_GRAPH_BASE}/me/events/{external_id}",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def delete_event(
        self,
        access_token: str,
        external_id: str,
        calendar_id: str = "primary",
    ) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{_MS_GRAPH_BASE}/me/events/{external_id}",
                headers=headers,
            )
            resp.raise_for_status()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def get_user_info(self, access_token: str) -> dict[str, str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _MS_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "id": data.get("id", ""),
            "email": data.get("mail") or data.get("userPrincipalName", ""),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_expires(expires_in: Any) -> datetime | None:  # TODO(TYPE): replace Any with concrete type
        if not expires_in:
            return None
        return datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))

    @staticmethod
    def _parse_event(item: dict[str, Any]) -> ExternalEvent:  # TODO(TYPE): replace Any with concrete type
        start_raw = item.get("start", {})
        end_raw = item.get("end", {})

        start_str = start_raw.get("dateTime", "")
        end_str = end_raw.get("dateTime", "")
        tz_str = start_raw.get("timeZone", "UTC")

        start_dt = datetime.fromisoformat(start_str) if start_str else datetime.now(tz=timezone.utc)
        end_dt = datetime.fromisoformat(end_str) if end_str else start_dt

        # Ensure UTC
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        attendees = [
            a.get("emailAddress", {}).get("address", "")
            for a in item.get("attendees", [])
            if a.get("emailAddress", {}).get("address")
        ]

        return ExternalEvent(
            external_id=item.get("id", ""),
            title=item.get("subject", "(no title)"),
            start_time=start_dt,
            end_time=end_dt,
            description=item.get("bodyPreview"),
            location=(
                item.get("location", {}).get("displayName") if item.get("location") else None
            ),
            organizer_email=(item.get("organizer", {}).get("emailAddress", {}).get("address")),
            attendees=attendees,
            status=item.get("showAs", "busy"),
            is_all_day=item.get("isAllDay", False),
            raw=item,
        )

    @staticmethod
    def _build_event_body(event: ExternalEvent) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        body: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "subject": event.title,
            "start": {
                "dateTime": event.start_time.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": event.end_time.isoformat(),
                "timeZone": "UTC",
            },
        }
        if event.description:
            body["body"] = {
                "contentType": "text",
                "content": event.description,
            }
        if event.location:
            body["location"] = {"displayName": event.location}
        if event.attendees:
            body["attendees"] = [
                {
                    "emailAddress": {"address": e},
                    "type": "required",
                }
                for e in event.attendees
            ]
        return body
