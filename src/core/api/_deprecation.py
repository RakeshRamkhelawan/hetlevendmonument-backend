"""Deprecation header helpers for legacy endpoints.

Per ADR-027 paragraaf 9 and RFC 8594 (Sunset) + IETF Deprecation draft.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Final

from fastapi import Response

logger = logging.getLogger(__name__)

# Sprint 4 dag 5: deprecation horizon = 4 weken na publicatie.
# Beide endpoints krijgen dezelfde Sunset-datum.
DEFAULT_SUNSET_DATE: Final[datetime] = datetime(2026, 7, 17, 0, 0, 0, tzinfo=timezone.utc)


def build_deprecation_headers(
    *,
    successor: str,
    sunset_date: datetime = DEFAULT_SUNSET_DATE,
    deprecation_date: datetime | None = None,
    link_rel: str = "successor-version",
) -> dict[str, str]:
    """Return RFC 8594 Sunset + IETF Deprecation + RFC 5988 Link headers as a dict.

    Use this for StreamingResponse and other handlers that pre-build a headers
    dict instead of mutating a Response object. For regular endpoints prefer
    emit_deprecation_headers() with an injected Response.
    """
    if deprecation_date is None:
        deprecation_date = datetime.now(timezone.utc)
    return {
        "Deprecation": format_datetime(deprecation_date, usegmt=True),
        "Sunset": format_datetime(sunset_date, usegmt=True),
        "Link": f'<{successor}>; rel="{link_rel}"',
    }


def emit_deprecation_headers(
    response: Response,
    *,
    successor: str,
    sunset_date: datetime = DEFAULT_SUNSET_DATE,
    deprecation_date: datetime | None = None,
    link_rel: str = "successor-version",
) -> None:
    """Set RFC 8594 Sunset + IETF Deprecation + RFC 5988 Link headers.

    Args:
        response: FastAPI Response object (injected via Depends).
        successor: Path of the replacement endpoint.
        sunset_date: Absolute removal date (UTC); default 2026-07-17.
        deprecation_date: When deprecation became effective; defaults to now.
        link_rel: rel-type for the Link header. Default "successor-version".
    """
    for key, value in build_deprecation_headers(
        successor=successor,
        sunset_date=sunset_date,
        deprecation_date=deprecation_date,
        link_rel=link_rel,
    ).items():
        response.headers[key] = value


def log_deprecated_call(
    endpoint_path: str,
    *,
    tenant_id: int | None,
    user_id: int | None,
    successor: str,
) -> None:
    """Server-side warning log for monitoring usage of deprecated endpoints."""
    logger.warning(
        "deprecated_endpoint_called",
        extra={
            "endpoint_path": endpoint_path,
            "successor": successor,
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
    )
