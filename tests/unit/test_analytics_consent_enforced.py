"""Dag 8 -- GDPR-004: analytics-consent enforced at the ingest write-point.

POST /events must NOT persist an AnalyticsEvent for a user without stored `analytics`
consent. The consent decision is made by the `analytics_consent_allowed` dependency
(ADR-033 facade), which reads consent for the AUTHENTICATED user with the SAME key as the
consent writer (str(current_user.id) + current_user.tenant_id -- attribute access, never
`sub`/email or a body field), fail-closed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.api.v1.analytics_ingest import dependencies as deps
from src.core.api.v1.analytics_ingest import events_router


def _batch():
    event = MagicMock()
    event.timestamp = "2026-07-12T10:00:00Z"
    event.userId = "body-user-999"  # body identity -- must NOT drive consent
    event.type = MagicMock(value="page_view")
    event.severity = MagicMock(value="info")
    event.actionType = None
    event.model_dump.return_value = {"type": "page_view"}
    batch = MagicMock()
    batch.sessionId = "sess-1"
    batch.events = [event]
    batch.batchTimestamp = "2026-07-12T10:00:00Z"
    batch.clientVersion = "1.0"
    return batch


def _db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# submit_events -- honours the resolved analytics_allowed flag
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
async def test_no_consent_event_not_persisted():
    db = _db()
    resp = await events_router.submit_events(
        batch=_batch(),
        db=db,
        current_user=SimpleNamespace(id=1),
        tenant_id="7",
        analytics_allowed=False,
    )
    db.add.assert_not_called()
    assert resp.eventsRejected == 1
    assert resp.eventsProcessed == 0


@pytest.mark.unit
@pytest.mark.security
async def test_with_consent_event_persisted():
    db = _db()
    resp = await events_router.submit_events(
        batch=_batch(),
        db=db,
        current_user=SimpleNamespace(id=1),
        tenant_id="7",
        analytics_allowed=True,
    )
    db.add.assert_called_once()
    assert resp.eventsProcessed == 1


# ---------------------------------------------------------------------------
# analytics_consent_allowed dependency -- the actual consent keying
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
async def test_consent_dependency_uses_user_id_key_not_sub():
    """Consent is read with str(current_user.id) + current_user.tenant_id (attribute
    access, like the writer) -- NOT `sub`/email, and NOT any body userId."""
    instance = MagicMock()
    instance.get_consent = AsyncMock(return_value=MagicMock(analytics=True))
    # SimpleNamespace has no .get() -> proves attribute access, not dict access.
    user = SimpleNamespace(id=42, tenant_id=7, email="user@example.com")

    with patch.object(deps, "CookieConsentManager", MagicMock(return_value=instance)):
        allowed = await deps.analytics_consent_allowed(current_user=user, db=AsyncMock())

    assert allowed is True
    instance.get_consent.assert_awaited_once_with(user_id="42", tenant_id=7)


@pytest.mark.unit
@pytest.mark.security
async def test_consent_dependency_false_blocks():
    instance = MagicMock()
    instance.get_consent = AsyncMock(return_value=MagicMock(analytics=False))
    user = SimpleNamespace(id=42, tenant_id=7)
    with patch.object(deps, "CookieConsentManager", MagicMock(return_value=instance)):
        allowed = await deps.analytics_consent_allowed(current_user=user, db=AsyncMock())
    assert allowed is False


@pytest.mark.unit
@pytest.mark.security
async def test_consent_dependency_fail_closed_on_error():
    """A consent-read error must yield False (no tracking) -- privacy-safe default."""
    instance = MagicMock()
    instance.get_consent = AsyncMock(side_effect=RuntimeError("db down"))
    user = SimpleNamespace(id=42, tenant_id=7)
    with patch.object(deps, "CookieConsentManager", MagicMock(return_value=instance)):
        allowed = await deps.analytics_consent_allowed(current_user=user, db=AsyncMock())
    assert allowed is False
