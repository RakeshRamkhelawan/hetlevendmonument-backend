"""Foundation Portal XML Sitemap endpoint (BE-EP-043, ADR-029 P2-5).

Implements standard Sitemaps XML protocol (sitemaps.org/schemas/sitemap/0.9)
with Google Image Sitemap extension (sitemap-image/1.1):
- URL 1: /{tenantSlug}/foundation/sitemap.xml
- URL 2: /api/v1/foundation/sitemap.xml (via host-based resolution)
- Content-Type: application/xml; charset=utf-8
- Invariant N-2: Only APPROVED + PUBLIC content with Visibility.PUBLIC
- Static portal routes included: /, /kaart, /educatie, /over, /contact, /nieuwsbrief, /data-export, /toegankelijkheid
- Dynamic routes included: /verhaal/{id}
- Image tags included for artwork and image media
- HTTP Cache headers: public, max-age=3600, s-maxage=86400
- Protected by rate limiter: @portal_public_read_limit
"""

from __future__ import annotations

import logging
from typing import Sequence
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    get_db,
    get_public_tenant,
    portal_public_read_limit,
    public_tenant_scope,
)
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    Privacy,
    Visibility,
)
from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.models.rbac_models import Tenant
from src.core.api.v1.foundation.dependencies import zet_tenant_in_lopende_transactie
from src.core.shared.datetime_utils import to_utc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["foundation-sitemap"])

# List of static portal routes: (relative_path, priority, changefreq)
STATIC_PORTAL_ROUTES: list[tuple[str, str, str]] = [
    ("", "1.0", "weekly"),
    ("kaart", "0.8", "weekly"),
    ("educatie", "0.8", "monthly"),
    ("over", "0.6", "monthly"),
    ("contact", "0.5", "monthly"),
    ("nieuwsbrief", "0.5", "monthly"),
    ("data-export", "0.6", "monthly"),
    ("toegankelijkheid", "0.4", "yearly"),
]


def resolve_canonical_base_url(tenant: Tenant, request: Request) -> str:
    """Resolve canonical base URL for a tenant's public portal."""
    custom_domain = getattr(tenant, "custom_domain", None)
    if custom_domain:
        return f"https://{custom_domain}".rstrip("/")

    # Check incoming request host headers
    host = (
        request.headers.get("x-tenant-domain")
        or request.headers.get("x-forwarded-host")
        or request.headers.get("host")
    )
    if host:
        proto = request.headers.get("x-forwarded-proto") or (
            "http" if "localhost" in host or "127.0.0.1" in host else "https"
        )
        return f"{proto}://{host}".rstrip("/")

    slug = getattr(tenant, "slug", "default")
    return f"https://{slug}.hetlevendmonument.nl"


def _is_image_media(
    content_type: ContentType | None, file_mime: str | None, file_url: str | None
) -> bool:
    """Determine if a content item has associated image media."""
    if file_mime and file_mime.lower().startswith("image/"):
        return True
    if content_type == ContentType.ARTWORK:
        return True
    if file_url:
        low = file_url.lower()
        if any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")):
            return True
    return False


async def generate_sitemap_xml(
    tenant: Tenant,
    request: Request,
    session: AsyncSession,
) -> str:
    """Generate valid sitemaps.org XML with static and public dynamic routes."""
    base_url = resolve_canonical_base_url(tenant, request)

    # N-2 Invariant query: only APPROVED + PUBLIC privacy + PUBLIC visibility
    stmt = (
        select(
            FoundationContent.id,
            FoundationContent.updated_at,
            FoundationContent.created_at,
            FoundationContent.title_nl,
            FoundationContent.type,
            FoundationContent.file_url,
            FoundationContent.file_mime,
        )
        .where(
            FoundationContent.tenant_id == tenant.id,
            FoundationContent.status == ContentStatus.APPROVED,
            FoundationContent.privacy == Privacy.PUBLIC,
            FoundationContent.visibility == Visibility.PUBLIC,
        )
        .order_by(FoundationContent.updated_at.desc())
        .limit(50000)
    )

    result = await session.execute(stmt)
    items = result.all()

    xml_lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]

    # 1. Static portal routes
    for path, priority, changefreq in STATIC_PORTAL_ROUTES:
        loc = f"{base_url}/{path}" if path else f"{base_url}/"
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{escape(loc)}</loc>")
        xml_lines.append(f"    <changefreq>{changefreq}</changefreq>")
        xml_lines.append(f"    <priority>{priority}</priority>")
        xml_lines.append("  </url>")

    # 2. Dynamic content routes
    for row in items:
        content_id = row.id
        updated_at = row.updated_at or row.created_at
        title_nl = row.title_nl or "Verhaal"
        c_type = row.type
        file_url = row.file_url
        file_mime = row.file_mime

        item_loc = f"{base_url}/verhaal/{content_id}"
        dt = to_utc(updated_at)
        lastmod = dt.strftime("%Y-%m-%d") if dt else ""

        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{escape(item_loc)}</loc>")
        if lastmod:
            xml_lines.append(f"    <lastmod>{lastmod}</lastmod>")
        xml_lines.append("    <changefreq>monthly</changefreq>")
        xml_lines.append("    <priority>0.7</priority>")

        if file_url and _is_image_media(c_type, file_mime, file_url):
            img_loc = (
                file_url
                if file_url.startswith(("http://", "https://"))
                else f"{base_url}{file_url}"
            )
            xml_lines.append("    <image:image>")
            xml_lines.append(f"      <image:loc>{escape(img_loc)}</image:loc>")
            xml_lines.append(f"      <image:title>{escape(title_nl)}</image:title>")
            xml_lines.append("    </image:image>")

        xml_lines.append("  </url>")

    xml_lines.append("</urlset>")
    return "\n".join(xml_lines)


@router.get(
    "/sitemap.xml",
    response_class=Response,
    summary="Get XML Sitemap for tenant foundation portal",
    description=(
        "Public discovery sitemap conform sitemaps.org protocol for search engines "
        "and NDE crawlers. Includes static pages and approved public stories."
    ),
)
@portal_public_read_limit
async def get_tenant_sitemap(
    tenantSlug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Generate and return public XML Sitemap for tenant."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        xml_content = await generate_sitemap_xml(tenant, request, session)
        return Response(
            content=xml_content,
            media_type="application/xml; charset=utf-8",
            headers={
                "Cache-Control": "public, max-age=3600, s-maxage=86400",
                "X-Robots-Tag": "noindex",
            },
        )


@router.get(
    "/robots.txt",
    response_class=Response,
    summary="Get robots.txt for tenant",
)
async def get_tenant_robots_txt(tenantSlug: str) -> Response:
    """Return robots.txt referencing the tenant sitemap."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /docenten\n"
        "Disallow: /magic-link\n"
        "\n"
        f"Sitemap: /{tenantSlug}/foundation/sitemap.xml\n"
    )
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )


host_sitemap_router = APIRouter(prefix="/api/v1/foundation", tags=["foundation-sitemap"])


@host_sitemap_router.get(
    "/sitemap.xml",
    response_class=Response,
    summary="Get XML Sitemap via host-based tenant resolution",
    description=(
        "Public discovery sitemap conform sitemaps.org protocol for search engines "
        "and NDE crawlers. Resolves tenant via host headers or query params."
    ),
)
@portal_public_read_limit
async def get_host_resolved_sitemap(
    request: Request,
    tenant: Tenant = Depends(get_public_tenant),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Generate and return public XML Sitemap for tenant resolved from host."""
    # `get_public_tenant` zet geen tenantcontext; zonder context gaf de sitemap onder de
    # applicatierol (RLS) nul items (gemeten 2026-11-02). Zelfde drie stappen als
    # `public_tenant_scope`, maar met de al opgezochte tenant (geen tweede opzoekquery).
    set_tenant_id(tenant.id)
    try:
        await zet_tenant_in_lopende_transactie(session, tenant.id)
        xml_content = await generate_sitemap_xml(tenant, request, session)
    finally:
        clear_tenant_context()
    return Response(
        content=xml_content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "noindex",
        },
    )


@host_sitemap_router.get(
    "/robots.txt",
    response_class=Response,
    summary="Get robots.txt for search engines and crawlers",
)
async def get_robots_txt() -> Response:
    """Public robots.txt discovery directive referencing the foundation sitemap."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /docenten\n"
        "Disallow: /magic-link\n"
        "\n"
        "Sitemap: /api/v1/foundation/sitemap.xml\n"
    )
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )
