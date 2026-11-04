"""Integration tests for Foundation Portal content endpoints."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    PortalUser,
    Privacy,
)


# Base URL helper


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# ============================================================================
# Public list endpoint (GET /{tenantSlug}/foundation/content)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentList:
    """Tests for the public content list endpoint."""

    async def test_list_content_public_no_auth(
        self,
        integration_client: AsyncClient,
        approved_public_content: FoundationContent,
    ) -> None:
        """Anonymous users can see approved public content."""
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1
        assert any(item["id"] == approved_public_content.id for item in data["items"])

    async def test_list_content_public_with_auth(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        approved_public_content: FoundationContent,
    ) -> None:
        """Authenticated users can also see approved public content."""
        response = await integration_client.get(
            _url("default", "/content"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1

    async def test_list_content_pagination(
        self, integration_client: AsyncClient, approved_public_content: FoundationContent
    ) -> None:
        """Pagination parameters work correctly."""
        response = await integration_client.get(_url("default", "/content?page=1&page_size=5"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    async def test_list_content_category_filter(
        self,
        integration_client: AsyncClient,
        approved_public_content: FoundationContent,
    ) -> None:
        """Category filter returns only matching content."""
        response = await integration_client.get(
            _url("default", f"/content?category={approved_public_content.category}")
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(
            item.get("category") == approved_public_content.category for item in data["items"]
        )

    async def test_list_content_excludes_pending(
        self,
        integration_client: AsyncClient,
        pending_content: FoundationContent,
    ) -> None:
        """Pending content is NOT visible in the public list."""
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert not any(item["id"] == pending_content.id for item in data["items"])

    async def test_list_content_excludes_community_for_anon(
        self,
        integration_client: AsyncClient,
        approved_community_content: FoundationContent,
    ) -> None:
        """Anonymous users do NOT see community privacy content."""
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert not any(item["id"] == approved_community_content.id for item in data["items"])

    async def test_list_content_includes_community_for_auth(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        approved_community_content: FoundationContent,
    ) -> None:
        """Authenticated users CAN see community privacy content."""
        response = await integration_client.get(
            _url("default", "/content"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert any(item["id"] == approved_community_content.id for item in data["items"])

    async def test_list_content_excludes_community_for_other_tenant(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        approved_community_content: FoundationContent,
    ) -> None:
        """Other-tenant authenticated users do NOT see community privacy content."""
        response = await integration_client.get(
            _url("default", "/content"),
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert not any(item["id"] == approved_community_content.id for item in data["items"])

    async def test_list_content_tenant_isolation(
        self,
        integration_client: AsyncClient,
        other_tenant_content: FoundationContent,
    ) -> None:
        """Content from other tenants is NOT visible."""
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert not any(item["id"] == other_tenant_content.id for item in data["items"])

    async def test_list_content_invalid_tenant_slug(self, integration_client: AsyncClient) -> None:
        """Invalid tenant slug returns 404."""
        response = await integration_client.get(_url("nonexistent", "/content"))
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Public detail endpoint (GET /{tenantSlug}/foundation/content/{id})
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentDetail:
    """Tests for the public content detail endpoint."""

    async def test_get_content_detail_public(
        self,
        integration_client: AsyncClient,
        approved_public_content: FoundationContent,
    ) -> None:
        """Anyone can view approved public content detail."""
        response = await integration_client.get(
            _url("default", f"/content/{approved_public_content.id}")
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == approved_public_content.id
        assert data["title_nl"] == approved_public_content.title_nl

    async def test_get_content_detail_community_requires_auth(
        self,
        integration_client: AsyncClient,
        approved_community_content: FoundationContent,
    ) -> None:
        """Community content detail requires authentication."""
        response = await integration_client.get(
            _url("default", f"/content/{approved_community_content.id}")
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_content_detail_community_with_auth(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        approved_community_content: FoundationContent,
    ) -> None:
        """Authenticated users can view community content detail."""
        response = await integration_client.get(
            _url("default", f"/content/{approved_community_content.id}"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == approved_community_content.id

    async def test_get_content_detail_not_found(self, integration_client: AsyncClient) -> None:
        """Non-existent content returns 404."""
        response = await integration_client.get(_url("default", "/content/99999"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_content_detail_pending_not_visible(
        self,
        integration_client: AsyncClient,
        pending_content: FoundationContent,
    ) -> None:
        """Pending content is not visible in public detail."""
        response = await integration_client.get(_url("default", f"/content/{pending_content.id}"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_content_detail_cross_tenant(
        self,
        integration_client: AsyncClient,
        other_tenant_content: FoundationContent,
    ) -> None:
        """Content from other tenant is not accessible."""
        response = await integration_client.get(
            _url("default", f"/content/{other_tenant_content.id}")
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Create content endpoint (POST /{tenantSlug}/foundation/content)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentCreate:
    """Tests for the content upload endpoint."""

    async def test_create_content_success(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Authenticated portal user can upload content."""
        payload = {
            "type": "story",
            "title_nl": "Mijn verhaal",
            "title_en": "My story",
            "description_nl": "Een kort verhaal",
            "body_nl": "Dit is de inhoud van mijn verhaal.",
            "creator_name": "Test Auteur",
            "privacy": "public",
            "rights_confirmed": True,
            "category": "herinnering",
        }
        response = await integration_client.post(
            _url("default", "/content"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title_nl"] == "Mijn verhaal"
        assert data["status"] == "pending"
        assert data["type"] == "story"

    async def test_create_content_unauthorized(self, integration_client: AsyncClient) -> None:
        """Anonymous users cannot upload content."""
        payload = {
            "type": "story",
            "title_nl": "Mijn verhaal",
            "privacy": "public",
            "rights_confirmed": True,
        }
        response = await integration_client.post(
            _url("default", "/content"),
            json=payload,
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_content_invalid_token_audience(
        self,
        integration_client: AsyncClient,
        admin_token: str,
    ) -> None:
        """Non-portal token (e.g., admin token) is rejected."""
        payload = {
            "type": "story",
            "title_nl": "Mijn verhaal",
            "privacy": "public",
            "rights_confirmed": True,
        }
        response = await integration_client.post(
            _url("default", "/content"),
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Admin token has no aud="portal", so it should be rejected
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_create_content_cross_tenant_blocked(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
    ) -> None:
        """User from other tenant cannot upload to this tenant."""
        payload = {
            "type": "story",
            "title_nl": "Mijn verhaal",
            "privacy": "public",
            "rights_confirmed": True,
        }
        response = await integration_client.post(
            _url("default", "/content"),
            json=payload,
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_create_content_validation_error(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Missing required fields returns validation error."""
        payload = {
            "type": "story",
            # missing title_nl
            "privacy": "public",
            "rights_confirmed": True,
        }
        response = await integration_client.post(
            _url("default", "/content"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_create_content_starts_pending(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        postgres_session: AsyncSession,
    ) -> None:
        """Uploaded content always starts as PENDING."""
        payload = {
            "type": "artwork",
            "title_nl": "Nieuw kunstwerk",
            "privacy": "public",
            "rights_confirmed": True,
        }
        response = await integration_client.post(
            _url("default", "/content"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "pending"
        assert data["privacy"] == "public"


# ============================================================================
# Rate limiter on create_content (audit N-4, BE-EP-036)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentCreateRateLimit:
    """Proof that portal_public_write_limit actually engages on create_content.

    The decorator no-ops SILENTLY when the endpoint has no Request parameter;
    this test guards that coupling. The foundation conftest resets the
    rate-limit keys per test, so the 11th request from the same IP within the
    60s window deterministically hits the 10/min limit.
    """

    async def test_create_content_11th_request_gets_429(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        headers = {"Authorization": f"Bearer {portal_visitor_token}"}
        for i in range(10):
            response = await integration_client.post(
                _url("default", "/content"),
                json={
                    "type": "story",
                    "title_nl": f"Verhaal {i}",
                    "privacy": "public",
                    "rights_confirmed": True,
                },
                headers=headers,
            )
            assert response.status_code == status.HTTP_201_CREATED

        response = await integration_client.post(
            _url("default", "/content"),
            json={
                "type": "story",
                "title_nl": "Verhaal 11",
                "privacy": "public",
                "rights_confirmed": True,
            },
            headers=headers,
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ============================================================================
# Update endpoint (PUT /{tenantSlug}/foundation/content/{content_id}) - ADR-029 P1-2
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentUpdate:
    """Tests for updating foundation content."""

    async def test_update_content_by_owner_success(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Owner can update their own content."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Originele Titel",
            body_nl="Origineel verhaal",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        payload = {
            "title_nl": "Gewijzigde Titel",
            "body_nl": "Aangepast verhaal met meer context",
            "location_name": "Nieuw Nickerie",
            "lat": 5.94,
            "lng": -56.98,
        }
        response = await integration_client.put(
            _url("default", f"/content/{content.id}"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title_nl"] == "Gewijzigde Titel"
        assert data["body_nl"] == "Aangepast verhaal met meer context"
        assert data["location_name"] == "Nieuw Nickerie"
        assert data["lat"] == 5.94
        assert data["lng"] == -56.98

    async def test_update_content_by_curator_success(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can edit content uploaded by another user."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Inzending Titel",
            body_nl="Tekst",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.PENDING,
            rights_confirmed=True,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        payload = {"title_nl": "Geredigeerde Titel door Curator"}
        response = await integration_client.put(
            _url("default", f"/content/{content.id}"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["title_nl"] == "Geredigeerde Titel door Curator"

    async def test_update_content_unauthorized_user(
        self,
        integration_client: AsyncClient,
        portal_curator_user: PortalUser,
        portal_visitor_token: str,
        postgres_session: AsyncSession,
    ) -> None:
        """A normal visitor cannot edit content uploaded by someone else."""
        content = FoundationContent(
            tenant_id=portal_curator_user.tenant_id,
            uploader_id=portal_curator_user.id,
            type=ContentType.STORY,
            title_nl="Curator Document",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.put(
            _url("default", f"/content/{content.id}"),
            json={"title_nl": "Ongeautoriseerde Wijziging"},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_update_content_not_found(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """404 when content does not exist."""
        response = await integration_client.put(
            _url("default", "/content/999999"),
            json={"title_nl": "Niet Bestaand"},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Delete endpoint (DELETE /{tenantSlug}/foundation/content/{content_id}) - ADR-029 P1-2
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentDelete:
    """Tests for soft-deleting foundation content."""

    async def test_delete_content_by_owner_soft_deletes(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Owner can soft-delete their own content."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Te Verwijderen Verhaal",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.delete(
            _url("default", f"/content/{content.id}"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == content.id
        assert data["status"] == "removed"

        # Verify in DB that status is REMOVED
        await postgres_session.refresh(content)
        assert content.status == ContentStatus.REMOVED

        # And detail view now returns 404
        get_res = await integration_client.get(_url("default", f"/content/{content.id}"))
        assert get_res.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_content_by_curator_soft_deletes(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Curator can soft-delete content uploaded by any user."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Inzending Verwijderen door Curator",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.PENDING,
            rights_confirmed=True,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.delete(
            _url("default", f"/content/{content.id}"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "removed"

    async def test_delete_content_unauthorized_user(
        self,
        integration_client: AsyncClient,
        portal_curator_user: PortalUser,
        portal_visitor_token: str,
        postgres_session: AsyncSession,
    ) -> None:
        """A normal visitor cannot delete content uploaded by someone else."""
        content = FoundationContent(
            tenant_id=portal_curator_user.tenant_id,
            uploader_id=portal_curator_user.id,
            type=ContentType.STORY,
            title_nl="Beschermde Inzending",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.delete(
            _url("default", f"/content/{content.id}"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
