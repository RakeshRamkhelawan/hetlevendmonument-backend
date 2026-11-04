"""Integration tests for BE-EP-038 anonymous masking.

Verifies that is_anonymous=True is honored platform-wide:
- public content list: creator_name masked
- public content detail: creator_name masked
- moderation queue (curator/admin): creator_name NOT masked (spec O4,
  moderators need the name to do their job)

Runs against Postgres 5435 + Redis like the other foundation tests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    Privacy,
)


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest_asyncio.fixture(scope="function")
async def anonymous_approved_content(postgres_session: AsyncSession) -> FoundationContent:
    """Approved public anonymous content with a real name stored (tenant 1)."""
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.STORY,
        title_nl="Anonieme getuigenis",
        creator_name="Echte Naam Van Maker",
        is_anonymous=True,
        privacy=Privacy.PUBLIC,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
        category="herinnering",
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def named_approved_content(postgres_session: AsyncSession) -> FoundationContent:
    """Approved public non-anonymous content (tenant 1)."""
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.ARTWORK,
        title_nl="Getekend kunstwerk",
        creator_name="Kunstenaar Met Naam",
        is_anonymous=False,
        privacy=Privacy.PUBLIC,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
        category="kunst",
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def anonymous_pending_content(postgres_session: AsyncSession) -> FoundationContent:
    """Pending anonymous content, visible in the moderation queue."""
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.POETRY,
        title_nl="Anoniem gedicht",
        creator_name="Verborgen Dichter",
        is_anonymous=True,
        privacy=Privacy.PUBLIC,
        status=ContentStatus.PENDING,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


# ============================================================================
# Public list endpoint
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestListMasking:
    """GET /{tenantSlug}/foundation/content masks anonymous creator names."""

    async def test_anonymous_item_masked_in_list(
        self,
        integration_client: AsyncClient,
        anonymous_approved_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        items = {item["id"]: item for item in response.json()["items"]}
        item = items[anonymous_approved_content.id]
        assert item["creator_name"] is None
        assert item["is_anonymous"] is True

    async def test_non_anonymous_item_keeps_name_in_list(
        self,
        integration_client: AsyncClient,
        named_approved_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        items = {item["id"]: item for item in response.json()["items"]}
        item = items[named_approved_content.id]
        assert item["creator_name"] == "Kunstenaar Met Naam"
        assert item["is_anonymous"] is False


# ============================================================================
# Public detail endpoint
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestDetailMasking:
    """GET /{tenantSlug}/foundation/content/{id} masks anonymous names."""

    async def test_anonymous_item_masked_in_detail(
        self,
        integration_client: AsyncClient,
        anonymous_approved_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(
            _url("default", f"/content/{anonymous_approved_content.id}")
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["creator_name"] is None
        assert data["is_anonymous"] is True

    async def test_non_anonymous_item_keeps_name_in_detail(
        self,
        integration_client: AsyncClient,
        named_approved_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(
            _url("default", f"/content/{named_approved_content.id}")
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["creator_name"] == "Kunstenaar Met Naam"


# ============================================================================
# Moderation queue: NOT masked (spec O4)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieQueueNotMasked:
    """GET /{tenantSlug}/foundation/admin/curatie keeps names for curators."""

    async def test_curator_sees_real_name_of_anonymous_content(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        anonymous_pending_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(
            _url("default", "/admin/curatie"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        items = {item["id"]: item for item in response.json()["items"]}
        item = items[anonymous_pending_content.id]
        assert item["creator_name"] == "Verborgen Dichter"
        assert item["is_anonymous"] is True
