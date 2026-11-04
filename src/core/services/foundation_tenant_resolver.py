"""
Foundation Portal Tenant Resolver

Provides async slug-, domain- and host-to-tenant resolution and context managers
that guarantee ContextVar cleanup on exit (normal, exception,
or asyncio.CancelledError).

Supports multi-tenant custom domains (e.g. stichtingketikotivlaardingen.nl)
and subdomains (e.g. ketikoti.levend-monument.nl).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import json
import re
from typing import cast

from src.core.typing import AsyncRedisClient

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.exceptions.foundation import (
    FoundationTenantDomainNotFoundError,
    FoundationTenantSlugNotFoundError,
    InvalidDomainError,
    InvalidSlugError,
    ReservedSlugError,
)
from src.core.middleware.tenant_context import (
    clear_tenant_context,
    set_tenant_id,
)
from src.core.models.rbac_models import Tenant
from src.core.schemas.validators import (
    FOUNDATION_RESERVED_SLUGS,
    validate_slug,
)

# RFC 1035 compliant domain name pattern (alphanumeric, hyphens, dots)
DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)

DEFAULT_ROOT_DOMAINS: tuple[str, ...] = (
    "levendmonument.nl",
    "levend-monument.nl",
    "sanskritisetu.org",
    "localhost",
)

TENANT_HOST_CACHE_TTL: int = 3600
TENANT_HOST_CACHE_PREFIX: str = "tenant:host:"


def normalize_host(host: str) -> str:
    """Normalize and validate a host or domain string.

    Strips port numbers, handles comma-separated proxy headers,
    lowercases, and validates against RFC 1035 syntax to prevent
    Host Header Injection attacks.

    Args:
        host: Raw host string from Host or X-Forwarded-Host header.

    Returns:
        Normalized lowercase domain string.

    Raises:
        InvalidDomainError: If host is empty or contains forbidden characters.
    """
    if not host or not isinstance(host, str):
        raise InvalidDomainError(str(host))

    # Take first value if multiple forwarded hosts are present
    cleaned = host.split(",")[0].strip()

    # Strip port if present (e.g. ketikoti.levend-monument.nl:5174 -> ketikoti.levend-monument.nl)
    if ":" in cleaned:
        cleaned = cleaned.split(":")[0].strip()

    # Lowercase and remove trailing dot
    cleaned = cleaned.lower().rstrip(".")

    if not cleaned or not DOMAIN_PATTERN.match(cleaned):
        raise InvalidDomainError(cleaned)

    return cleaned


def _cache_key(host: str) -> str:
    """Generate cache key for host lookup."""
    return f"{TENANT_HOST_CACHE_PREFIX}{host}"


async def get_cached_tenant_by_host(
    host: str, redis_client: AsyncRedisClient | None = None
) -> dict[str, object] | None:
    """Retrieve cached tenant metadata by host.

    Best-effort: returns None on cache miss, missing redis client, or error.
    """
    if not redis_client:
        return None

    try:
        norm = normalize_host(host)
        key = _cache_key(norm)
        data = await redis_client.get(key)
        if data:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return cast(dict[str, object], parsed)
    except Exception:
        pass
    return None


async def set_cached_tenant_by_host(
    host: str,
    tenant_data: dict[str, object],
    redis_client: AsyncRedisClient | None = None,
    ttl: int = TENANT_HOST_CACHE_TTL,
) -> None:
    """Cache tenant metadata by host with TTL."""
    if not redis_client:
        return

    try:
        norm = normalize_host(host)
        key = _cache_key(norm)
        await redis_client.setex(key, ttl, json.dumps(tenant_data))
    except Exception:
        pass


async def invalidate_tenant_host_cache(
    host: str, redis_client: AsyncRedisClient | None = None
) -> None:
    """Invalidate cached tenant metadata for a host."""
    if not redis_client:
        return

    try:
        norm = normalize_host(host)
        key = _cache_key(norm)
        await redis_client.delete(key)
    except Exception:
        pass


async def resolve_tenant_by_slug(
    slug: str, db: AsyncSession, redis_client: AsyncRedisClient | None = None
) -> Tenant:
    """Resolve an active tenant by slug.

    Anti-enumeration: identical error message for both unknown
    and inactive tenants.

    Args:
        slug: Tenant slug from URL path.
        db: Database session.
        redis_client: Optional async Redis client for caching.

    Returns:
        The Tenant instance.

    Raises:
        InvalidSlugError: If slug format is invalid.
        FoundationTenantSlugNotFoundError: If tenant is unknown or inactive.
    """
    validate_foundation_slug(slug)

    with TenantFilterBypass():
        result = await db.execute(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
        )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise FoundationTenantSlugNotFoundError(slug)

    return tenant


async def resolve_tenant_by_domain(
    domain: str, db: AsyncSession, redis_client: AsyncRedisClient | None = None
) -> Tenant:
    """Resolve an active tenant by custom domain.

    Anti-enumeration: identical error message for both unknown
    and inactive domains.

    Args:
        domain: Domain name from Host header.
        db: Database session.
        redis_client: Optional async Redis client for caching.

    Returns:
        The Tenant instance.

    Raises:
        InvalidDomainError: If domain format is invalid.
        FoundationTenantDomainNotFoundError: If tenant is unknown or inactive.
    """
    norm_domain = normalize_host(domain)

    # Check cache first
    cached = await get_cached_tenant_by_host(norm_domain, redis_client)
    if cached and isinstance(cached, dict) and "id" in cached:
        with TenantFilterBypass():
            tenant = await db.get(Tenant, cached["id"])
            if tenant is not None and tenant.is_active:
                return tenant

    # Query DB with TenantFilterBypass
    with TenantFilterBypass():
        result = await db.execute(
            select(Tenant).where(Tenant.domain == norm_domain, Tenant.is_active.is_(True))
        )
        tenant = result.scalar_one_or_none()

        # Optional www. fallback
        if tenant is None and norm_domain.startswith("www."):
            fallback_domain = norm_domain[4:]
            result = await db.execute(
                select(Tenant).where(Tenant.domain == fallback_domain, Tenant.is_active.is_(True))
            )
            tenant = result.scalar_one_or_none()

    if tenant is None:
        raise FoundationTenantDomainNotFoundError(norm_domain)

    if redis_client:
        await set_cached_tenant_by_host(
            norm_domain,
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "domain": tenant.domain,
            },
            redis_client,
        )

    return tenant


async def resolve_tenant_by_host(
    host: str,
    db: AsyncSession,
    root_domains: tuple[str, ...] | None = None,
    redis_client: AsyncRedisClient | None = None,
) -> Tenant:
    """Resolve an active tenant by HTTP Host header.

    Checks if the host is a subdomain of a known root domain (e.g. ketikoti.levend-monument.nl),
    and if so, resolves via slug. Otherwise, resolves as a custom domain (e.g. ketikotivlaardingen.nl).

    Args:
        host: Host header value (may include port).
        db: Database session.
        root_domains: Allowed root domains for subdomain extraction.
        redis_client: Optional async Redis client.

    Returns:
        The Tenant instance.

    Raises:
        ReservedSlugError: If subdomain is in the reserved list.
        FoundationTenantSlugNotFoundError: If subdomain tenant is not found.
        FoundationTenantDomainNotFoundError: If custom domain is not found.
    """
    norm_host = normalize_host(host)
    roots = root_domains if root_domains is not None else DEFAULT_ROOT_DOMAINS

    # Exact match on root domain is not a tenant portal
    if norm_host in roots:
        if norm_host in ("localhost", "127.0.0.1"):
            try:
                return await resolve_tenant_by_slug("default", db, redis_client)
            except Exception:
                pass
        raise FoundationTenantDomainNotFoundError(norm_host)

    # Check if host is a subdomain of any root domain
    subdomain: str | None = None
    for root in roots:
        suffix = f".{root}"
        if norm_host.endswith(suffix):
            prefix = norm_host[: -len(suffix)]
            # Take innermost segment for multi-level domains
            subdomain = prefix.split(".")[-1]
            break

    if subdomain:
        # Check against reserved slugs (api, www, portal, admin, etc.)
        if subdomain in FOUNDATION_RESERVED_SLUGS:
            raise ReservedSlugError(subdomain)

        tenant = await resolve_tenant_by_slug(subdomain, db, redis_client)
        if redis_client:
            await set_cached_tenant_by_host(
                norm_host,
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "domain": tenant.domain,
                },
                redis_client,
            )
        return tenant

    # Not a subdomain of root: resolve as custom domain
    return await resolve_tenant_by_domain(norm_host, db, redis_client)


async def zet_tenant_in_lopende_transactie(db: AsyncSession, tenant_id: int) -> None:
    """Geef de net opgezochte tenant ook aan de AL LOPENDE transactie door (ADR-036 OP-151).

    `_zet_tenantcontext` (src/core/database/database.py) zet `app.current_tenant` bij het BEGIN
    van een transactie, vanuit de ContextVar. De scopes hieronder zoeken de tenant eerst op;
    die query opent de transactie terwijl de ContextVar nog leeg is. `set_tenant_id` daarna
    verandert de ContextVar, maar niet meer de instelling van die transactie. Onder de
    applicatierol `sanskritisetu_app` leverde elke publieke foundation-query daardoor nul
    rijen op (gemeten 2026-11-02 op productie: tenant gevonden, /content gaf total=0 met vijf
    goedgekeurde PUBLIC-items in de tabel). Als tabeleigenaar viel het niet op, want RLS geldt
    niet voor de eigenaar.

    Alleen op PostgreSQL en alleen binnen een lopende transactie: een volgende transactie
    krijgt de waarde via het begin-event zelf. De waarde is transactie-lokaal (`true`) en gaat
    als bindparameter mee, net als in `_zet_tenantcontext`.
    """
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    if getattr(dialect, "name", None) != "postgresql":
        return
    if not db.in_transaction():
        return
    await db.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(int(tenant_id))}
    )


@asynccontextmanager
async def public_tenant_scope(
    slug: str, db: AsyncSession
) -> AsyncGenerator[Tenant, None]:
    """Resolve tenant by slug, set ContextVar, guarantee cleanup.

    Uses try/finally so cleanup runs on normal exit, exception,
    and asyncio.CancelledError. Prevents tenant state leakage to
    the next request in the same worker.

    Args:
        slug: Tenant slug from URL path.
        db: Database session.

    Yields:
        The resolved Tenant instance.
    """
    tenant = await resolve_tenant_by_slug(slug, db)
    set_tenant_id(tenant.id)
    await zet_tenant_in_lopende_transactie(db, tenant.id)
    try:
        yield tenant
    finally:
        clear_tenant_context()


@asynccontextmanager
async def public_tenant_scope_by_host(
    host: str,
    db: AsyncSession,
    root_domains: tuple[str, ...] | None = None,
    redis_client: AsyncRedisClient | None = None,
) -> AsyncGenerator[Tenant, None]:
    """Resolve tenant by host, set ContextVar, guarantee cleanup.

    Args:
        host: Host header string.
        db: Database session.
        root_domains: Optional tuple of root domains.
        redis_client: Optional async Redis client.

    Yields:
        The resolved Tenant instance.
    """
    tenant = await resolve_tenant_by_host(host, db, root_domains, redis_client)
    set_tenant_id(tenant.id)
    await zet_tenant_in_lopende_transactie(db, tenant.id)
    try:
        yield tenant
    finally:
        clear_tenant_context()


def validate_foundation_slug(slug: str) -> None:
    """Foundation-specific wrapper that converts ValueError to typed exceptions.

    Args:
        slug: The slug to validate.

    Raises:
        ReservedSlugError: If the slug is in the reserved list.
        InvalidSlugError: If the slug does not match the strict pattern.
    """
    try:
        validate_slug(slug, reserved=FOUNDATION_RESERVED_SLUGS, strict=True)
    except ValueError as exc:
        msg = str(exc)
        if "reserved" in msg:
            raise ReservedSlugError(slug) from exc
        raise InvalidSlugError(slug) from exc

