"""Integration tests for Foundation Portal bulk curatie endpoints (BE-EP-053).

Validates bulk approval, bulk rejection with mandatory DSA Art. 17 reason,
partial success envelope semantics, RBAC, and strict cross-tenant isolation
against live PostgreSQL.
"""

from __future__ import annotations

import pytest
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


@pytest.fixture
async def pending_content_items(
    postgres_session: AsyncSession,
) -> list[FoundationContent]:
    """Seed multiple pending content items for tenant_id=1."""
    items = []
    for i in range(3):
        content = FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl=f"Bulk Verhaal {i+1}",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.PENDING,
            rights_confirmed=True,
            category="verhalen",
        )
        postgres_session.add(content)
        items.append(content)

    await postgres_session.flush()
    for item in items:
        await postgres_session.refresh(item)
    return items


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieBulkApprove:
    """Tests for POST /{tenantSlug}/foundation/admin/curatie/bulk-approve."""

    async def test_curator_can_bulk_approve_all(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content_items: list[FoundationContent],
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can approve multiple pending items in a single request."""
        ids = [item.id for item in pending_content_items]
        response = await integration_client.post(
            _url("default", "/admin/curatie/bulk-approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
            json={"content_ids": ids},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_requested"] == len(ids)
        assert data["processed_count"] == len(ids)
        assert sorted(data["success_ids"]) == sorted(ids)
        assert data["failed_items"] == []
        assert "succesvol goedgekeurd" in data["message"]

        # Verify in DB
        for item in pending_content_items:
            await postgres_session.refresh(item)
            assert item.status == ContentStatus.APPROVED

    async def test_curator_bulk_approve_partial_success(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content_items: list[FoundationContent],
        postgres_session: AsyncSession,
    ) -> None:
        """Partial success when some items are not pending or do not exist."""
        item1 = pending_content_items[0]
        item2 = pending_content_items[1]
        item2.status = ContentStatus.APPROVED
        await postgres_session.flush()

        non_existent_id = 999999
        ids = [item1.id, item2.id, non_existent_id]

        response = await integration_client.post(
            _url("default", "/admin/curatie/bulk-approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
            json={"content_ids": ids},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_requested"] == 3
        assert data["success_ids"] == [item1.id]
        assert len(data["failed_items"]) == 2

        failed_dict = {f["id"]: f["reason"] for f in data["failed_items"]}
        assert item2.id in failed_dict
        assert "approved" in failed_dict[item2.id]
        assert non_existent_id in failed_dict

        # Verify in DB
        await postgres_session.refresh(item1)
        assert item1.status == ContentStatus.APPROVED

    async def test_visitor_cannot_bulk_approve(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        pending_content_items: list[FoundationContent],
    ) -> None:
        """Non-curators receive 403 Forbidden."""
        ids = [item.id for item in pending_content_items]
        response = await integration_client.post(
            _url("default", "/admin/curatie/bulk-approve"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
            json={"content_ids": ids},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieBulkReject:
    """Tests for POST /{tenantSlug}/foundation/admin/curatie/bulk-reject."""

    async def test_curator_can_bulk_reject_with_dsa_reason(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content_items: list[FoundationContent],
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can bulk reject pending items with mandatory DSA reason."""
        ids = [pending_content_items[0].id, pending_content_items[1].id]
        reason = "Inhoud bevat onbevestigde claims en schendt het erfgoedbeleid."

        response = await integration_client.post(
            _url("default", "/admin/curatie/bulk-reject"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
            json={"content_ids": ids, "rejection_reason": reason},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_requested"] == 2
        assert sorted(data["success_ids"]) == sorted(ids)
        assert data["failed_items"] == []

        # Verify in DB
        for item in [pending_content_items[0], pending_content_items[1]]:
            await postgres_session.refresh(item)
            assert item.status == ContentStatus.REJECTED
            assert item.rejection_reason == reason

    async def test_bulk_reject_requires_reason(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content_items: list[FoundationContent],
    ) -> None:
        """DSA Art. 17: rejection requires at least 5 chars reason."""
        response = await integration_client.post(
            _url("default", "/admin/curatie/bulk-reject"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
            json={"content_ids": [pending_content_items[0].id], "rejection_reason": "nee"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_cross_tenant_bulk_isolation(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        other_tenant_content: FoundationContent,
        postgres_session: AsyncSession,
    ) -> None:
        """Curator cannot moderate content from another tenant via bulk endpoints."""
        other_tenant_content.status = ContentStatus.PENDING
        await postgres_session.flush()

        response = await integration_client.post(
            _url("default", "/admin/curatie/bulk-approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
            json={"content_ids": [other_tenant_content.id]},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success_ids"] == []
        assert len(data["failed_items"]) == 1
        assert "niet gevonden" in data["failed_items"][0]["reason"].lower()

        await postgres_session.refresh(other_tenant_content)
        assert other_tenant_content.status == ContentStatus.PENDING
