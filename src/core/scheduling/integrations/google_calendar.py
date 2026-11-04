"""
Google Calendar provider using the Google Calendar API v3.

Requires ``google-api-python-client`` and uses ``authlib`` (already in
requirements) for the OAuth2 code exchange.

Includes retry logic for transient failures.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional, cast

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.scheduling.integrations.base_provider import (
    BaseCalendarProvider,
    ExternalEvent,
    OAuthTokens,
)
from src.core.scheduling.integrations.exceptions import raise_for_oauth_error

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_GOOGLE_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarProvider(BaseCalendarProvider):
    """Google Calendar API v3 integration."""

    provider_name = "google"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id or os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")

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
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if resp.status_code != 200:
                error_data = resp.json() if resp.text else {}
                raise_for_oauth_error(resp.status_code, error_data, self.provider_name)
            data = resp.json()

        expires_in = data.get("expires_in")
        expires_at = None
        if expires_in:
            expires_at = datetime.now(tz=timezone.utc).__class__.fromtimestamp(
                datetime.now(tz=timezone.utc).timestamp() + int(expires_in),
                tz=timezone.utc,
            )

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
                _GOOGLE_TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                error_data = resp.json() if resp.text else {}
                raise_for_oauth_error(resp.status_code, error_data, self.provider_name)
            data = resp.json()

        expires_in = data.get("expires_in")
        expires_at = None
        if expires_in:
            from datetime import timedelta

            expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))

        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
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
        params: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        }

        if sync_token:
            params["syncToken"] = sync_token
        else:
            params["timeMin"] = time_min.isoformat()
            params["timeMax"] = time_max.isoformat()

        events: list[ExternalEvent] = []
        next_page = None
        next_sync_token = None

        async with httpx.AsyncClient() as client:
            while True:
                if next_page:
                    params["pageToken"] = next_page
                url = f"{_GOOGLE_CALENDAR_BASE}/calendars/{calendar_id}/events"
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    events.append(self._parse_event(item))

                next_page = data.get("nextPageToken")
                next_sync_token = data.get("nextSyncToken")
                if not next_page:
                    break

        return events, next_sync_token

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
            url = f"{_GOOGLE_CALENDAR_BASE}/calendars/{calendar_id}/events"
            resp = await client.post(url, headers=headers, json=body)
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
        url = f"{_GOOGLE_CALENDAR_BASE}/calendars/{calendar_id}/events/{external_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, headers=headers, json=body)
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
        url = f"{_GOOGLE_CALENDAR_BASE}/calendars/{calendar_id}/events/{external_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.delete(url, headers=headers)
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
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return {"id": data.get("id", ""), "email": data.get("email", "")}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_event(item: dict[str, Any]) -> ExternalEvent:  # TODO(TYPE): replace Any with concrete type
        start_raw = item.get("start", {})
        end_raw = item.get("end", {})

        start_str = start_raw.get("dateTime") or start_raw.get("date", "")
        end_str = end_raw.get("dateTime") or end_raw.get("date", "")
        is_all_day = "date" in start_raw and "dateTime" not in start_raw

        start_dt = datetime.fromisoformat(start_str) if start_str else datetime.now(tz=timezone.utc)
        end_dt = datetime.fromisoformat(end_str) if end_str else start_dt

        attendees = [a.get("email", "") for a in item.get("attendees", []) if a.get("email")]

        return ExternalEvent(
            external_id=item.get("id", ""),
            title=item.get("summary", "(no title)"),
            start_time=start_dt,
            end_time=end_dt,
            description=item.get("description"),
            location=item.get("location"),
            organizer_email=item.get("organizer", {}).get("email"),
            attendees=attendees,
            status=item.get("status", "confirmed"),
            is_all_day=is_all_day,
            raw=item,
        )

    @staticmethod
    def _build_event_body(event: ExternalEvent) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        body: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "summary": event.title,
            "start": {"dateTime": event.start_time.isoformat()},
            "end": {"dateTime": event.end_time.isoformat()},
        }
        if event.description:
            body["description"] = event.description
        if event.location:
            body["location"] = event.location
        if event.attendees:
            body["attendees"] = [{"email": e} for e in event.attendees]
        return body
