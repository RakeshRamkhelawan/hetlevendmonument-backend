"""Integration tests for Foundation Portal tenant resolution endpoint."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Tenant


@pytest.mark.asyncio
@pytest.mark.integration
class TestTenantResolutionEndpoint:
    """Tests for GET /api/v1/foundation/tenant/resolve."""

    async def test_resolve_tenant_via_host_subdomain(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Resolve active tenant via subdomain Host header."""
        tenant = Tenant(name="Ketikoti Subdomain Test", slug="ketikoti-resolve", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        response = await integration_client.get(
            "/api/v1/foundation/tenant/resolve",
            headers={"Host": "ketikoti-resolve.levend-monument.nl:5174"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["slug"] == "ketikoti-resolve"
        assert data["name"] == "Ketikoti Subdomain Test"
        assert data["is_active"] is True

    async def test_resolve_tenant_via_custom_domain(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Resolve active tenant via custom domain Host header."""
        tenant = Tenant(
            name="Vlaardingen Custom Domain",
            slug="vlaardingen-custom",
            domain="herdenking-vlaardingen.nl",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        response = await integration_client.get(
            "/api/v1/foundation/tenant/resolve",
            headers={"Host": "herdenking-vlaardingen.nl"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["slug"] == "vlaardingen-custom"
        assert data["domain"] == "herdenking-vlaardingen.nl"

    async def test_resolve_tenant_via_slug_query_param(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Resolve active tenant via ?slug= query parameter."""
        tenant = Tenant(name="Query Param Slug", slug="slug-query-test", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        response = await integration_client.get(
            "/api/v1/foundation/tenant/resolve?slug=slug-query-test"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["slug"] == "slug-query-test"

    async def test_resolve_tenant_via_domain_query_param(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Resolve active tenant via ?domain= query parameter."""
        tenant = Tenant(
            name="Query Param Domain",
            slug="domain-query-test",
            domain="query-domain.nl",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        response = await integration_client.get(
            "/api/v1/foundation/tenant/resolve?domain=query-domain.nl"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["domain"] == "query-domain.nl"

    async def test_resolve_unknown_tenant_returns_404(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Unknown domain or subdomain returns HTTP 404 with TENANT_NOT_FOUND."""
        response = await integration_client.get(
            "/api/v1/foundation/tenant/resolve",
            headers={"Host": "completely-unknown.levend-monument.nl"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["error_code"] == "TENANT_NOT_FOUND"

    async def test_resolve_inactive_tenant_returns_404(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Inactive tenant returns identical 404 (anti-enumeration)."""
        tenant = Tenant(
            name="Inactive Host Test",
            slug="inactive-host-test",
            domain="inactive-host.nl",
            is_active=False,
        )
        db_session.add(tenant)
        await db_session.flush()

        response = await integration_client.get(
            "/api/v1/foundation/tenant/resolve",
            headers={"Host": "inactive-host.nl"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["error"]["error_code"] == "TENANT_NOT_FOUND"
