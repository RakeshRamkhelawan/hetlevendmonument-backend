"""Integration tests for Foundation Portal Notice & Takedown curator moderation (BE-EP-051)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    FoundationContent,
    PortalUser,
    TakedownRequest,
    TakedownStatus,
)


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest.fixture
async def takedown_fixture(
    postgres_session: AsyncSession,
    approved_public_content: FoundationContent,
    portal_visitor_user: PortalUser,
) -> TakedownRequest:
    """Create a test takedown request against the approved public content."""
    takedown = TakedownRequest(
        tenant_id=approved_public_content.tenant_id,
        content_id=approved_public_content.id,
        requester_name="Pieter Post",
        requester_email="juridisch@rechtenhouder.nl",
        legal_basis="Auteursrechtinbreuk op historisch archiefmateriaal",
        status=TakedownStatus.PENDING,
    )
    postgres_session.add(takedown)
    await postgres_session.commit()
    await postgres_session.refresh(takedown)
    return takedown


@pytest.mark.asyncio
@pytest.mark.integration
class TestCuratieTakedownsIntegration:
    """End-to-end integration tests for curator takedown workflow against PostgreSQL."""

    async def test_curator_can_list_takedowns(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        takedown_fixture: TakedownRequest,
    ) -> None:
        """Curator can list and filter takedown reports."""
        response = await integration_client.get(
            _url("default", "/admin/curatie/takedowns"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1
        assert any(item["id"] == takedown_fixture.id for item in data["items"])

        item = next(x for x in data["items"] if x["id"] == takedown_fixture.id)
        assert item["content_id"] == takedown_fixture.content_id
        assert item["status"] == "pending"
        assert item["requester_email"] == "juridisch@rechtenhouder.nl"

    async def test_visitor_cannot_access_takedowns(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Visitor role receives 403 Forbidden on curator takedown endpoints."""
        response = await integration_client.get(
            _url("default", "/admin/curatie/takedowns"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_curator_can_get_takedown_detail(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        takedown_fixture: TakedownRequest,
    ) -> None:
        """Curator can inspect full takedown details."""
        response = await integration_client.get(
            _url("default", f"/admin/curatie/takedowns/{takedown_fixture.id}"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == takedown_fixture.id
        assert data["content_id"] == takedown_fixture.content_id
        assert data["legal_basis"] == "Auteursrechtinbreuk op historisch archiefmateriaal"
        assert "content_title" in data
        assert "content_status" in data

    async def test_curator_resolve_approve_sets_content_removed(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        takedown_fixture: TakedownRequest,
        postgres_session: AsyncSession,
    ) -> None:
        """Approving takedown sets content status to REMOVED and populates takedown metadata."""
        resolve_payload = {
            "status": "approved",
            "resolution_note": "Auteursrechtclaim geverifieerd; content offline gehaald conform NTD gedragscode.",
            "notify_requester": False,
        }
        response = await integration_client.put(
            _url("default", f"/admin/curatie/takedowns/{takedown_fixture.id}"),
            json=resolve_payload,
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "approved"
        assert data["content_status"] == "removed"

        # Verify in PostgreSQL
        stmt_td = select(TakedownRequest).where(TakedownRequest.id == takedown_fixture.id)
        td_db = (await postgres_session.execute(stmt_td)).scalar_one()
        assert td_db.status == TakedownStatus.APPROVED
        assert td_db.resolution_note is not None
        assert td_db.resolved_at is not None

        stmt_c = select(FoundationContent).where(
            FoundationContent.id == takedown_fixture.content_id
        )
        c_db = (await postgres_session.execute(stmt_c)).scalar_one()
        assert c_db.status == ContentStatus.REMOVED
        assert c_db.takedown_reason == resolve_payload["resolution_note"]
        assert c_db.takedown_at is not None

    async def test_curator_can_restore_removed_content(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        takedown_fixture: TakedownRequest,
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can restore content that was previously removed after a successful counter-notice."""
        # First approve takedown so it's REMOVED
        resolve_payload = {
            "status": "approved",
            "resolution_note": "Tijdelijk offline gehaald in afwachting van bewijs.",
            "notify_requester": False,
        }
        await integration_client.put(
            _url("default", f"/admin/curatie/takedowns/{takedown_fixture.id}"),
            json=resolve_payload,
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )

        # Now restore content
        restore_res = await integration_client.post(
            _url("default", f"/admin/curatie/{takedown_fixture.content_id}/restore"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert restore_res.status_code == status.HTTP_200_OK
        restore_data = restore_res.json()
        assert restore_data["status"] == "approved"
        assert restore_data["id"] == takedown_fixture.content_id

        # Verify in DB
        stmt_c = select(FoundationContent).where(
            FoundationContent.id == takedown_fixture.content_id
        )
        c_db = (await postgres_session.execute(stmt_c)).scalar_one()
        assert c_db.status == ContentStatus.APPROVED
        assert c_db.takedown_reason is None
        assert c_db.takedown_at is None

    async def test_curator_cannot_restore_already_approved_content(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        approved_public_content: FoundationContent,
    ) -> None:
        """Attempting to restore content that is not REMOVED returns 404 Not Found."""
        res = await integration_client.post(
            _url("default", f"/admin/curatie/{approved_public_content.id}/restore"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert "not in removed status" in res.json()["detail"].lower()

    async def test_curator_resolve_requires_valid_note(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        takedown_fixture: TakedownRequest,
    ) -> None:
        """Resolution requires a note of at least 5 characters."""
        res = await integration_client.put(
            _url("default", f"/admin/curatie/takedowns/{takedown_fixture.id}"),
            json={"status": "approved", "resolution_note": "kort"},
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_cross_tenant_takedown_access_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        takedown_fixture: TakedownRequest,
    ) -> None:
        """Curator/User from another tenant cannot access takedowns of default tenant."""
        res = await integration_client.get(
            _url("default", f"/admin/curatie/takedowns/{takedown_fixture.id}"),
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
