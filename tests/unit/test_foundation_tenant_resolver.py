"""
Unit tests for Foundation tenant resolver (Task 9).

Covers: resolve by valid slug, unknown slug, inactive tenant,
invalid slug, ContextVar cleanup on normal exit and CancelledError.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.foundation import (
    FoundationTenantDomainNotFoundError,
    FoundationTenantSlugNotFoundError,
    InvalidDomainError,
    InvalidSlugError,
    ReservedSlugError,
)
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import Tenant
from src.core.services.foundation_tenant_resolver import (
    get_cached_tenant_by_host,
    invalidate_tenant_host_cache,
    normalize_host,
    public_tenant_scope,
    public_tenant_scope_by_host,
    resolve_tenant_by_domain,
    resolve_tenant_by_host,
    resolve_tenant_by_slug,
    set_cached_tenant_by_host,
    validate_foundation_slug,
)



class TestValidateFoundationSlug:
    @pytest.mark.unit
    def test_valid_slug(self) -> None:
        validate_foundation_slug("ketikoti")

    @pytest.mark.unit
    def test_reserved_slug_raises(self) -> None:
        with pytest.raises(ReservedSlugError):
            validate_foundation_slug("api")

    @pytest.mark.unit
    def test_invalid_slug_raises(self) -> None:
        with pytest.raises(InvalidSlugError):
            validate_foundation_slug("bad!")

    @pytest.mark.unit
    def test_too_short_raises(self) -> None:
        with pytest.raises(InvalidSlugError):
            validate_foundation_slug("ab")


class TestResolveTenantBySlug:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_slug_returns_tenant(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Test Tenant", slug="test-tenant-resolve")
        db_session.add(tenant)
        await db_session.flush()

        result = await resolve_tenant_by_slug("test-tenant-resolve", db_session)
        assert result.id == tenant.id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_slug_raises(self, db_session: AsyncSession) -> None:
        with pytest.raises(FoundationTenantSlugNotFoundError):
            await resolve_tenant_by_slug("nonexistent-tenant", db_session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_inactive_slug_raises_same_error(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Inactive Tenant", slug="inactive-tenant", is_active=False)
        db_session.add(tenant)
        await db_session.flush()

        with pytest.raises(FoundationTenantSlugNotFoundError):
            await resolve_tenant_by_slug("inactive-tenant", db_session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_slug_raises_400(self, db_session: AsyncSession) -> None:
        with pytest.raises(InvalidSlugError):
            await resolve_tenant_by_slug("bad!", db_session)


class TestPublicTenantScope:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_on_normal_exit(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Scope Tenant", slug="scope-tenant")
        db_session.add(tenant)
        await db_session.flush()

        async with public_tenant_scope("scope-tenant", db_session) as t:
            assert t.id == tenant.id
            assert get_tenant_id() == tenant.id

        assert get_tenant_id() is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Scope Tenant 2", slug="scope-tenant-2")
        db_session.add(tenant)
        await db_session.flush()

        with pytest.raises(ValueError, match="boom"):
            async with public_tenant_scope("scope-tenant-2", db_session):
                assert get_tenant_id() == tenant.id
                raise ValueError("boom")

        assert get_tenant_id() is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_on_cancelled_error(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Scope Tenant 3", slug="scope-tenant-3")
        db_session.add(tenant)
        await db_session.flush()

        async def inner() -> None:
            async with public_tenant_scope("scope-tenant-3", db_session):
                assert get_tenant_id() == tenant.id
                raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await inner()

        assert get_tenant_id() is None


class TestNormalizeHost:
    @pytest.mark.unit
    def test_strips_ports(self) -> None:
        assert normalize_host("ketikoti.levend-monument.nl:5174") == "ketikoti.levend-monument.nl"
        assert normalize_host("localhost:8000") == "localhost"
        assert normalize_host("stichting.org:443") == "stichting.org"

    @pytest.mark.unit
    def test_lowercases(self) -> None:
        assert normalize_host("KETIKOTI.Levend-Monument.NL") == "ketikoti.levend-monument.nl"

    @pytest.mark.unit
    def test_strips_trailing_dots(self) -> None:
        assert normalize_host("ketikoti.levend-monument.nl.") == "ketikoti.levend-monument.nl"

    @pytest.mark.unit
    def test_handles_forwarded_multiple_hosts(self) -> None:
        assert normalize_host("ketikoti.levend-monument.nl, proxy.internal") == "ketikoti.levend-monument.nl"

    @pytest.mark.unit
    def test_invalid_host_raises(self) -> None:
        with pytest.raises(InvalidDomainError):
            normalize_host("invalid$host!name")


class TestResolveTenantByDomain:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_domain_returns_tenant(self, db_session: AsyncSession) -> None:
        tenant = Tenant(
            name="Vlaardingen Foundation",
            slug="vlaardingen",
            domain="herdenkingvlaardingen.nl",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        result = await resolve_tenant_by_domain("herdenkingvlaardingen.nl", db_session)
        assert result.id == tenant.id
        assert result.domain == "herdenkingvlaardingen.nl"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_domain_raises_404(self, db_session: AsyncSession) -> None:
        with pytest.raises(FoundationTenantDomainNotFoundError):
            await resolve_tenant_by_domain("onbekenddomein.nl", db_session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_inactive_domain_raises_same_error(self, db_session: AsyncSession) -> None:
        tenant = Tenant(
            name="Inactive Domain Tenant",
            slug="inactive-domain",
            domain="inactiefdomein.nl",
            is_active=False,
        )
        db_session.add(tenant)
        await db_session.flush()

        with pytest.raises(FoundationTenantDomainNotFoundError):
            await resolve_tenant_by_domain("inactiefdomein.nl", db_session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_www_fallback_resolves_tenant(self, db_session: AsyncSession) -> None:
        tenant = Tenant(
            name="WWW Test Foundation",
            slug="www-test",
            domain="monument-test.nl",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        # Querying with www. when registered without www.
        result = await resolve_tenant_by_domain("www.monument-test.nl", db_session)
        assert result.id == tenant.id


class TestResolveTenantByHost:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subdomain_of_root_resolves_via_slug(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Ketikoti Subdomain", slug="ketikoti-sub", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        result = await resolve_tenant_by_host(
            "ketikoti-sub.levend-monument.nl:5174",
            db_session,
            root_domains=("levend-monument.nl", "localhost"),
        )
        assert result.id == tenant.id
        assert result.slug == "ketikoti-sub"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subdomain_of_localhost_resolves(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Localhost Subdomain", slug="local-sub", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        result = await resolve_tenant_by_host(
            "local-sub.localhost:8000",
            db_session,
            root_domains=("localhost",),
        )
        assert result.id == tenant.id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_custom_domain_resolves(self, db_session: AsyncSession) -> None:
        tenant = Tenant(
            name="Custom Domain Foundation",
            slug="custom-sub",
            domain="ketikotivlaardingen.nl",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        result = await resolve_tenant_by_host(
            "ketikotivlaardingen.nl",
            db_session,
            root_domains=("levend-monument.nl",),
        )
        assert result.id == tenant.id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reserved_subdomain_raises_reserved_error(self, db_session: AsyncSession) -> None:
        with pytest.raises(ReservedSlugError):
            await resolve_tenant_by_host(
                "api.levend-monument.nl",
                db_session,
                root_domains=("levend-monument.nl",),
            )

        with pytest.raises(ReservedSlugError):
            await resolve_tenant_by_host(
                "admin.levend-monument.nl",
                db_session,
                root_domains=("levend-monument.nl",),
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_exact_root_domain_raises_not_found(self, db_session: AsyncSession) -> None:
        with pytest.raises(FoundationTenantDomainNotFoundError):
            await resolve_tenant_by_host(
                "levend-monument.nl",
                db_session,
                root_domains=("levend-monument.nl",),
            )


class TestPublicTenantScopeByHost:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scope_cleanup_on_normal_exit(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Host Scope Tenant", slug="host-scope", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        async with public_tenant_scope_by_host(
            "host-scope.levend-monument.nl",
            db_session,
            root_domains=("levend-monument.nl",),
        ) as t:
            assert t.id == tenant.id
            assert get_tenant_id() == tenant.id

        assert get_tenant_id() is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scope_cleanup_on_exception(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Host Scope Tenant 2", slug="host-scope-2", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        with pytest.raises(RuntimeError, match="scope crash"):
            async with public_tenant_scope_by_host(
                "host-scope-2.levend-monument.nl",
                db_session,
                root_domains=("levend-monument.nl",),
            ):
                assert get_tenant_id() == tenant.id
                raise RuntimeError("scope crash")

        assert get_tenant_id() is None


class TestTenantHostRedisCache:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self) -> None:
        cache: dict[str, str] = {}

        class MockRedis:
            async def get(self, key: str) -> str | None:
                return cache.get(key)

            async def setex(self, key: str, time: int, value: str) -> None:
                cache[key] = value

            async def delete(self, key: str) -> None:
                cache.pop(key, None)

        mock_redis = MockRedis()
        host = "ketikoti.levend-monument.nl"

        # Cache miss
        assert await get_cached_tenant_by_host(host, mock_redis) is None

        # Set cache
        await set_cached_tenant_by_host(
            host,
            {"id": 42, "slug": "ketikoti", "name": "Ketikoti", "domain": None},
            mock_redis,
            ttl=3600,
        )

        # Cache hit
        cached = await get_cached_tenant_by_host(host, mock_redis)
        assert cached is not None
        assert cached["id"] == 42
        assert cached["slug"] == "ketikoti"

        # Invalidate
        await invalidate_tenant_host_cache(host, mock_redis)
        assert await get_cached_tenant_by_host(host, mock_redis) is None

