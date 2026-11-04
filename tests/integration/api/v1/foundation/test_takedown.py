"""Integration tests for Foundation Portal takedown endpoint."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    FoundationContent,
    PortalUser,
    TakedownRequest,
    TakedownStatus,
)


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# ============================================================================
# Takedown endpoint (POST /{tenantSlug}/foundation/takedown)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestTakedown:
    """Tests for the takedown request endpoint."""

    async def test_create_takedown_success(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        approved_public_content: FoundationContent,
        postgres_session: AsyncSession,
    ) -> None:
        """Authenticated user can submit takedown request."""
        payload = {
            "content_id": approved_public_content.id,
            "reason": "This content violates my copyright",
            "contact_email": "claimant@example.com",
        }
        response = await integration_client.post(
            _url("default", "/takedown"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "pending"
        assert "id" in data

        # Verify in DB
        stmt = select(TakedownRequest).where(TakedownRequest.id == data["id"])
        result = await postgres_session.execute(stmt)
        takedown = result.scalar_one_or_none()
        assert takedown is not None
        assert takedown.status == TakedownStatus.PENDING
        assert takedown.content_id == approved_public_content.id

    async def test_create_takedown_unauthorized(
        self,
        integration_client: AsyncClient,
        approved_public_content: FoundationContent,
    ) -> None:
        """Anonymous users cannot submit takedown requests."""
        payload = {
            "content_id": approved_public_content.id,
            "reason": "Copyright violation",
            "contact_email": "claimant@example.com",
        }
        response = await integration_client.post(
            _url("default", "/takedown"),
            json=payload,
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_takedown_cross_tenant_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        approved_public_content: FoundationContent,
    ) -> None:
        """User from other tenant cannot submit takedown."""
        payload = {
            "content_id": approved_public_content.id,
            "reason": "Copyright violation",
            "contact_email": "claimant@example.com",
        }
        response = await integration_client.post(
            _url("default", "/takedown"),
            json=payload,
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_create_takedown_content_not_found(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Takedown for non-existent content returns 404."""
        payload = {
            "content_id": 99999,
            "reason": "Copyright violation",
            "contact_email": "claimant@example.com",
        }
        response = await integration_client.post(
            _url("default", "/takedown"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_create_takedown_invalid_content_id(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Invalid content_id (zero/negative) returns 422."""
        payload = {
            "content_id": 0,
            "reason": "Copyright violation",
            "contact_email": "claimant@example.com",
        }
        response = await integration_client.post(
            _url("default", "/takedown"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
