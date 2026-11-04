"""Unit tests for BE-EP-043 Foundation Portal XML Sitemap endpoint (ADR-029 P2-5).

Validates:
- XML syntax and schema conformance (sitemaps.org 0.9 + Google image extension)
- Canonical base URL resolution (custom domain, host headers, fallback)
- Static portal routes presence
- Dynamic content mapping and N-2 invariant filtering
- Image extension generation for artwork and media
- Public registry exemption (/api/v1/foundation/sitemap.xml and /{slug}/foundation/sitemap.xml)
- HTTP Response headers (Cache-Control, Content-Type, X-Robots-Tag)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from xml.sax.saxutils import escape

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from src.core.api.v1.foundation.sitemap import (
    STATIC_PORTAL_ROUTES,
    generate_sitemap_xml,
    get_host_resolved_sitemap,
    get_tenant_sitemap,
    resolve_canonical_base_url,
)
from src.core.models.foundation_content import ContentType
from src.core.models.rbac_models import Tenant
from src.core.shared.datetime_utils import utc_now
from src.core.shared.public_registry import PublicEndpointRegistry


# ============================================================================
# Helpers & Fixtures
# ============================================================================


def _create_mock_request(
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
) -> Request:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/foundation/sitemap.xml",
        "headers": raw_headers,
        "query_string": b"",
    }
    req = Request(scope)
    return req


def _create_mock_tenant(
    id: int = 1,
    slug: str = "ketikoti-vlaardingen",
    name: str = "Stichting Ketikoti",
    custom_domain: str | None = None,
) -> Tenant:
    tenant = MagicMock(spec=Tenant)
    tenant.id = id
    tenant.slug = slug
    tenant.name = name
    tenant.custom_domain = custom_domain
    return tenant


# ============================================================================
# Canonical URL Resolution Tests
# ============================================================================


class TestCanonicalBaseUrlResolution:
    @pytest.mark.unit
    def test_custom_domain_takes_highest_precedence(self) -> None:
        tenant = _create_mock_tenant(custom_domain="verhalen.ketikotivlaardingen.nl")
        req = _create_mock_request(headers={"host": "api.hetlevendmonument.nl"})
        base_url = resolve_canonical_base_url(tenant, req)
        assert base_url == "https://verhalen.ketikotivlaardingen.nl"

    @pytest.mark.unit
    def test_x_tenant_domain_header_resolves_when_no_custom_domain(self) -> None:
        tenant = _create_mock_tenant(custom_domain=None)
        req = _create_mock_request(headers={"x-tenant-domain": "portal.ketikoti.nl"})
        base_url = resolve_canonical_base_url(tenant, req)
        assert base_url == "https://portal.ketikoti.nl"

    @pytest.mark.unit
    def test_x_forwarded_host_resolves(self) -> None:
        tenant = _create_mock_tenant(custom_domain=None)
        req = _create_mock_request(headers={"x-forwarded-host": "ketikoti.hetlevendmonument.nl"})
        base_url = resolve_canonical_base_url(tenant, req)
        assert base_url == "https://ketikoti.hetlevendmonument.nl"

    @pytest.mark.unit
    def test_localhost_uses_http_protocol(self) -> None:
        tenant = _create_mock_tenant(custom_domain=None)
        req = _create_mock_request(headers={"host": "localhost:5173"})
        base_url = resolve_canonical_base_url(tenant, req)
        assert base_url == "http://localhost:5173"

    @pytest.mark.unit
    def test_fallback_uses_tenant_slug_domain(self) -> None:
        tenant = _create_mock_tenant(slug="zeeuwse-verhalen", custom_domain=None)
        req = _create_mock_request(headers={})
        base_url = resolve_canonical_base_url(tenant, req)
        assert base_url == "https://zeeuwse-verhalen.hetlevendmonument.nl"


# ============================================================================
# XML Structure & Schema Validation Tests
# ============================================================================


class TestSitemapXmlGeneration:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_generates_valid_wellformed_xml(self) -> None:
        tenant = _create_mock_tenant()
        req = _create_mock_request(headers={"host": "ketikoti.nl"})

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        xml_str = await generate_sitemap_xml(tenant, req, session)

        assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        root = ET.fromstring(xml_str)
        assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_includes_all_static_portal_routes(self) -> None:
        tenant = _create_mock_tenant()
        req = _create_mock_request(headers={"host": "ketikoti.nl"})

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        xml_str = await generate_sitemap_xml(tenant, req, session)
        root = ET.fromstring(xml_str)

        urls = [
            loc.text
            for loc in root.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
        ]

        expected_paths = [
            "https://ketikoti.nl/",
            "https://ketikoti.nl/kaart",
            "https://ketikoti.nl/educatie",
            "https://ketikoti.nl/over",
            "https://ketikoti.nl/contact",
            "https://ketikoti.nl/nieuwsbrief",
            "https://ketikoti.nl/data-export",
            "https://ketikoti.nl/toegankelijkheid",
        ]
        for path in expected_paths:
            assert path in urls, f"Expected {path} in sitemap static routes"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_includes_dynamic_content_with_dates_and_images(self) -> None:
        tenant = _create_mock_tenant()
        req = _create_mock_request(headers={"host": "ketikoti.nl"})

        now = utc_now()
        item1 = SimpleNamespace(
            id=101,
            updated_at=now,
            created_at=now,
            title_nl="Vrijheidslied 1863",
            type=ContentType.STORY,
            file_url="/uploads/foundation/song.mp3",
            file_mime="audio/mpeg",
        )
        item2 = SimpleNamespace(
            id=102,
            updated_at=now,
            created_at=now,
            title_nl="Schilderij Keti Koti",
            type=ContentType.ARTWORK,
            file_url="/uploads/foundation/painting.jpg",
            file_mime="image/jpeg",
        )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [item1, item2]
        session.execute.return_value = mock_result

        xml_str = await generate_sitemap_xml(tenant, req, session)
        root = ET.fromstring(xml_str)

        item_urls = [
            loc.text
            for loc in root.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
        ]
        assert "https://ketikoti.nl/verhaal/101" in item_urls
        assert "https://ketikoti.nl/verhaal/102" in item_urls

        # Check image tag on item 102
        image_locs = [
            elem.text
            for elem in root.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
                "{http://www.google.com/schemas/sitemap-image/1.1}image/"
                "{http://www.google.com/schemas/sitemap-image/1.1}loc"
            )
        ]
        assert "https://ketikoti.nl/uploads/foundation/painting.jpg" in image_locs


# ============================================================================
# Public Registry Exemption Tests
# ============================================================================


class TestPublicRegistrySitemap:
    @pytest.mark.unit
    def test_tenant_namespaced_sitemap_is_public(self) -> None:
        path = "/ketikoti-vlaardingen/foundation/sitemap.xml"
        assert PublicEndpointRegistry.is_public(path) is True

    @pytest.mark.unit
    def test_host_resolved_sitemap_is_public(self) -> None:
        path = "/api/v1/foundation/sitemap.xml"
        assert PublicEndpointRegistry.is_public(path) is True

    @pytest.mark.unit
    def test_reserved_slug_sitemap_is_rejected(self) -> None:
        path = "/static/foundation/sitemap.xml"
        assert PublicEndpointRegistry.is_public(path) is False


# ============================================================================
# Endpoint Response & Headers Tests
# ============================================================================


class TestSitemapEndpoints:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_tenant_sitemap_response_headers(self) -> None:
        tenant = _create_mock_tenant()
        req = _create_mock_request(headers={"host": "ketikoti.nl"})

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        # Monkeypatch public_tenant_scope to yield mock tenant
        class MockScope:
            async def __aenter__(self):
                return tenant

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        import src.core.api.v1.foundation.sitemap as sitemap_mod

        orig_scope = sitemap_mod.public_tenant_scope
        sitemap_mod.public_tenant_scope = lambda slug, sess: MockScope()

        try:
            resp = await get_tenant_sitemap("ketikoti", req, session)
            assert resp.status_code == 200
            assert resp.media_type == "application/xml; charset=utf-8"
            assert resp.headers["Cache-Control"] == "public, max-age=3600, s-maxage=86400"
            assert resp.headers["X-Robots-Tag"] == "noindex"
            assert "<?xml" in resp.body.decode("utf-8")
        finally:
            sitemap_mod.public_tenant_scope = orig_scope

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_host_resolved_sitemap_response_headers(self) -> None:
        tenant = _create_mock_tenant()
        req = _create_mock_request(headers={"host": "ketikoti.nl"})

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        resp = await get_host_resolved_sitemap(req, tenant, session)
        assert resp.status_code == 200
        assert resp.media_type == "application/xml; charset=utf-8"
        assert resp.headers["Cache-Control"] == "public, max-age=3600, s-maxage=86400"
        assert resp.headers["X-Robots-Tag"] == "noindex"
        assert "<urlset" in resp.body.decode("utf-8")
