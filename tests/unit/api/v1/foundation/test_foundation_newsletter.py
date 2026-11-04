"""Unit tests for Foundation newsletter endpoints (src/core/api/v1/foundation/newsletter.py)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.foundation.dependencies import (
    get_db,
    require_portal_newsletter_rate_limit,
)
from src.core.api.v1.foundation.newsletter import router
from src.core.models.foundation_content import NewsletterStatus, NewsletterSubscription

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(router)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[require_portal_newsletter_rate_limit] = lambda: None
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_subscribe_newsletter_new_subscription(client: TestClient, mock_session: AsyncMock) -> None:
    mock_tenant = MagicMock(id=1, slug="acme")

    @asynccontextmanager
    async def mock_public_tenant_scope(slug: str, session: AsyncMock):
        yield mock_tenant

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("src.core.api.v1.foundation.newsletter.public_tenant_scope", mock_public_tenant_scope):
        response = client.post(
            "/newsletter/subscribe?tenantSlug=acme",
            json={"email": "reader@example.com"},
        )

    assert response.status_code == 201
    assert response.json() == {"message": "Subscription request received."}
    assert mock_session.add.called
    assert mock_session.flush.called


def test_subscribe_newsletter_already_subscribed(client: TestClient, mock_session: AsyncMock) -> None:
    mock_tenant = MagicMock(id=1, slug="acme")

    @asynccontextmanager
    async def mock_public_tenant_scope(slug: str, session: AsyncMock):
        yield mock_tenant

    existing = MagicMock(spec=NewsletterSubscription)
    existing.status = NewsletterStatus.SUBSCRIBED

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = mock_result

    with patch("src.core.api.v1.foundation.newsletter.public_tenant_scope", mock_public_tenant_scope):
        response = client.post(
            "/newsletter/subscribe?tenantSlug=acme",
            json={"email": "reader@example.com"},
        )

    assert response.status_code == 201
    assert response.json() == {"message": "Subscription request received."}


def test_subscribe_newsletter_resubscribe(client: TestClient, mock_session: AsyncMock) -> None:
    mock_tenant = MagicMock(id=1, slug="acme")

    @asynccontextmanager
    async def mock_public_tenant_scope(slug: str, session: AsyncMock):
        yield mock_tenant

    existing = MagicMock(spec=NewsletterSubscription)
    existing.status = NewsletterStatus.UNSUBSCRIBED

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = mock_result

    with patch("src.core.api.v1.foundation.newsletter.public_tenant_scope", mock_public_tenant_scope):
        response = client.post(
            "/newsletter/subscribe?tenantSlug=acme",
            json={"email": "reader@example.com"},
        )

    assert response.status_code == 201
    assert response.json() == {"message": "Subscription request received."}
    # Double opt-in (AVG): een her-inschrijving gaat opnieuw door de bevestigingsmail,
    # met verse tokens en zonder bevestigingsmoment. Zie newsletter.py (PENDING_OPT_IN).
    assert existing.status == NewsletterStatus.PENDING_OPT_IN
    assert existing.confirmed_at is None


def test_unsubscribe_newsletter_success(client: TestClient, mock_session: AsyncMock) -> None:
    mock_tenant = MagicMock(id=1, slug="acme")

    @asynccontextmanager
    async def mock_public_tenant_scope(slug: str, session: AsyncMock):
        yield mock_tenant

    subscription = MagicMock(spec=NewsletterSubscription)
    subscription.status = NewsletterStatus.SUBSCRIBED

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = subscription
    mock_session.execute.return_value = mock_result

    with patch("src.core.api.v1.foundation.newsletter.public_tenant_scope", mock_public_tenant_scope):
        response = client.post(
            "/newsletter/unsubscribe?tenantSlug=acme",
            json={"email": "reader@example.com", "token": "testtoken123"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Unsubscribe request received."}
    assert subscription.status == NewsletterStatus.UNSUBSCRIBED


def test_unsubscribe_newsletter_not_found_returns_generic(client: TestClient, mock_session: AsyncMock) -> None:
    mock_tenant = MagicMock(id=1, slug="acme")

    @asynccontextmanager
    async def mock_public_tenant_scope(slug: str, session: AsyncMock):
        yield mock_tenant

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("src.core.api.v1.foundation.newsletter.public_tenant_scope", mock_public_tenant_scope):
        response = client.post(
            "/newsletter/unsubscribe?tenantSlug=acme",
            json={"email": "unknown@example.com", "token": "badtoken"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Unsubscribe request received."}
