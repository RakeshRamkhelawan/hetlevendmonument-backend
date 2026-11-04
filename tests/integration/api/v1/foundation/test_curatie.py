"""Integration tests for Foundation Portal admin curatie endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    FoundationContent,
    PortalUser,
)


# Base URL helper


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# ============================================================================
# Curatie queue endpoint (GET /{tenantSlug}/foundation/admin/curatie)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieQueue:
    """Tests for the moderation queue endpoint."""

    async def test_curator_can_view_queue(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Curator can view the moderation queue."""
        response = await integration_client.get(
            _url("default", "/admin/curatie"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status_filter"] == "pending"
        assert any(item["id"] == pending_content.id for item in data["items"])

    async def test_admin_can_view_queue(
        self,
        integration_client: AsyncClient,
        portal_admin_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Admin can also view the moderation queue."""
        response = await integration_client.get(
            _url("default", "/admin/curatie"),
            headers={"Authorization": f"Bearer {portal_admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1

    async def test_visitor_cannot_view_queue(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Regular visitor cannot access the moderation queue."""
        response = await integration_client.get(
            _url("default", "/admin/curatie"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_unauthenticated_cannot_view_queue(self, integration_client: AsyncClient) -> None:
        """Anonymous users cannot access the moderation queue."""
        response = await integration_client.get(_url("default", "/admin/curatie"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_queue_filters_by_status(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        approved_public_content: FoundationContent,
        pending_content: FoundationContent,
    ) -> None:
        """Queue can be filtered by status."""
        # Get approved items
        response = await integration_client.get(
            _url("default", "/admin/curatie?status=approved"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status_filter"] == "approved"
        assert any(item["id"] == approved_public_content.id for item in data["items"])

    async def test_cross_tenant_curator_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
    ) -> None:
        """Curator from other tenant cannot access this tenant's queue."""
        response = await integration_client.get(
            _url("default", "/admin/curatie"),
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_invalid_status_filter(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
    ) -> None:
        """Invalid status filter returns 400."""
        response = await integration_client.get(
            _url("default", "/admin/curatie?status=invalid"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Approve endpoint (POST /{tenantSlug}/foundation/admin/curatie/{id}/approve)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieApprove:
    """Tests for the content approval endpoint."""

    async def test_curator_can_approve(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content: FoundationContent,
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can approve pending content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == pending_content.id
        assert data["status"] == "approved"

        # Verify in DB
        await postgres_session.refresh(pending_content)
        assert pending_content.status == ContentStatus.APPROVED

    async def test_admin_can_approve(
        self,
        integration_client: AsyncClient,
        portal_admin_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Admin can approve pending content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/approve"),
            headers={"Authorization": f"Bearer {portal_admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "approved"

    async def test_visitor_cannot_approve(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Visitor cannot approve content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/approve"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_approve_non_pending_returns_404(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        approved_public_content: FoundationContent,
    ) -> None:
        """Approving already-approved content returns 404."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{approved_public_content.id}/approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_approve_nonexistent_content(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
    ) -> None:
        """Approving non-existent content returns 404."""
        response = await integration_client.post(
            _url("default", "/admin/curatie/99999/approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_cross_tenant_approve_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Curator from other tenant cannot approve this tenant's content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/approve"),
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Reject endpoint (POST /{tenantSlug}/foundation/admin/curatie/{id}/reject)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieReject:
    """Tests for the content rejection endpoint."""

    async def test_curator_can_reject(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content: FoundationContent,
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can reject pending content with a reason."""
        payload = {"rejection_reason": "Bevat ongepaste taal"}
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/reject"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == pending_content.id
        assert data["status"] == "rejected"

    async def test_reject_dispatches_dsa_art17_email_to_uploader(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content: FoundationContent,
        postgres_session: AsyncSession,
    ) -> None:
        """Rejecting content with a reason dispatches a DSA Art. 17 notification to the uploader."""
        # Create uploader user and link to pending_content
        uploader = PortalUser(
            tenant_id=1,
            email="uploader.dsa@voorbeeld.nl",
            display_name="Inzender Jan",
            is_verified=True,
        )
        postgres_session.add(uploader)
        await postgres_session.flush()

        pending_content.uploader_id = uploader.id
        await postgres_session.flush()

        payload = {"rejection_reason": "In strijd met de redactionele richtlijnen art. 4."}
        with patch(
            "src.core.api.v1.foundation.admin.curatie.brevo_email_service.send_curation_rejection_notification",
            new_callable=AsyncMock,
        ) as mock_send:
            response = await integration_client.post(
                _url("default", f"/admin/curatie/{pending_content.id}/reject"),
                json=payload,
                headers={"Authorization": f"Bearer {portal_curator_token}"},
            )
            assert response.status_code == status.HTTP_200_OK
            mock_send.assert_awaited_once()
            call_kwargs = mock_send.await_args[1]
            assert call_kwargs["to_email"] == "uploader.dsa@voorbeeld.nl"
            assert "In strijd met de redactionele richtlijnen" in call_kwargs["rejection_reason"]

    async def test_reject_without_reason(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Curator can reject without providing a reason."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/reject"),
            json={},
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "rejected"

    async def test_visitor_cannot_reject(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Visitor cannot reject content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/reject"),
            json={},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_reject_non_pending_returns_404(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        approved_public_content: FoundationContent,
    ) -> None:
        """Rejecting already-approved content returns 404."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{approved_public_content.id}/reject"),
            json={},
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_cross_tenant_reject_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Curator from other tenant cannot reject this tenant's content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/reject"),
            json={},
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Re-tag endpoint (POST /{tenantSlug}/foundation/admin/curatie/{id}/re-tag)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestReTagContent:
    """Tests for the AI re-tagging endpoint (ADR-029 P1-1)."""

    async def test_curator_can_retag_content(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Curator can re-trigger AI tagging for a content item."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/re-tag"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["content_id"] == pending_content.id
        assert data["status"] == "queued"

    async def test_visitor_cannot_retag(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Visitor cannot re-trigger AI tagging."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/re-tag"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_retag_nonexistent_returns_404(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
    ) -> None:
        """Re-tagging a non-existent item returns 404."""
        response = await integration_client.post(
            _url("default", "/admin/curatie/999999/re-tag"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_cross_tenant_retag_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        pending_content: FoundationContent,
    ) -> None:
        """Curator from other tenant cannot re-tag this tenant's content."""
        response = await integration_client.post(
            _url("default", f"/admin/curatie/{pending_content.id}/re-tag"),
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
