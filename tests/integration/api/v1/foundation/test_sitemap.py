"""Integration tests for Foundation Portal XML Sitemap endpoint (BE-EP-043 / ADR-029 P2-5)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    Privacy,
    Visibility,
)

NAMESPACES = {
    "ns": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestSitemapXmlSyntaxAndStructure:
    """Tests for XML protocol conformance and static portal routes."""

    async def test_sitemap_xml_protocol_conformance(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Sitemap endpoint returns valid sitemaps.org 0.9 XML document."""
        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK
        assert "application/xml" in res.headers["Content-Type"]

        root = ET.fromstring(res.content)
        assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
        urls = root.findall("ns:url", NAMESPACES)
        assert len(urls) >= 8  # At least the 8 static portal routes

    async def test_static_portal_routes_present_with_priorities(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """All 8 static routes are present with their expected changefreq and priority."""
        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        loc_map: dict[str, tuple[str, str]] = {}
        for u in root.findall("ns:url", NAMESPACES):
            loc_el = u.find("ns:loc", NAMESPACES)
            freq_el = u.find("ns:changefreq", NAMESPACES)
            prio_el = u.find("ns:priority", NAMESPACES)
            if loc_el is not None and loc_el.text:
                path = loc_el.text.split("/")[-1]
                freq = freq_el.text if freq_el is not None and freq_el.text else ""
                prio = prio_el.text if prio_el is not None and prio_el.text else ""
                loc_map[path] = (freq, prio)

        # Verify static routes exist
        expected_routes = [
            ("kaart", "weekly", "0.8"),
            ("educatie", "monthly", "0.8"),
            ("over", "monthly", "0.6"),
            ("contact", "monthly", "0.5"),
            ("nieuwsbrief", "monthly", "0.5"),
            ("data-export", "monthly", "0.6"),
            ("toegankelijkheid", "yearly", "0.4"),
        ]
        for route_path, exp_freq, exp_prio in expected_routes:
            assert route_path in loc_map, f"Static route '{route_path}' missing from sitemap"
            assert loc_map[route_path][0] == exp_freq
            assert loc_map[route_path][1] == exp_prio


@pytest.mark.asyncio
@pytest.mark.integration
class TestSitemapDynamicContentAndN2Invariant:
    """Tests for N-2 Invariant: only APPROVED + PUBLIC content with Visibility.PUBLIC."""

    async def test_approved_public_content_included(
        self,
        integration_client: AsyncClient,
        approved_public_content: FoundationContent,
    ) -> None:
        """Approved public content is indexed in the sitemap with story route."""
        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        all_locs = [
            el.text
            for el in root.findall("ns:url/ns:loc", NAMESPACES)
            if el.text is not None
        ]
        expected_story_url = f"/verhaal/{approved_public_content.id}"
        assert any(expected_story_url in loc for loc in all_locs), (
            f"Approved public content {approved_public_content.id} must be in sitemap"
        )

    async def test_n2_invariant_non_public_content_strictly_excluded(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Non-public and non-approved content must NEVER appear in the sitemap (Audit N-2)."""
        # Seed various non-qualifying content items
        pending_item = FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="In Behandeling Verhaal",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.PENDING,
            rights_confirmed=True,
        )
        community_item = FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Gemeenschap Alleen Verhaal",
            privacy=Privacy.COMMUNITY,
            visibility=Visibility.COMMUNITY,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
        )
        rejected_item = FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Afgewezen Verhaal",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.REJECTED,
            rights_confirmed=True,
        )
        removed_item = FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Verwijderd Verhaal",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.REMOVED,
            rights_confirmed=True,
        )
        edu_item = FoundationContent(
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Educatie Kanaal Verhaal",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.EDU,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
        )

        postgres_session.add_all([pending_item, community_item, rejected_item, removed_item, edu_item])
        await postgres_session.commit()
        await postgres_session.refresh(pending_item)
        await postgres_session.refresh(community_item)
        await postgres_session.refresh(rejected_item)
        await postgres_session.refresh(removed_item)
        await postgres_session.refresh(edu_item)

        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        all_locs = [
            el.text
            for el in root.findall("ns:url/ns:loc", NAMESPACES)
            if el.text is not None
        ]

        forbidden_ids = [
            pending_item.id,
            community_item.id,
            rejected_item.id,
            removed_item.id,
            edu_item.id,
        ]
        for f_id in forbidden_ids:
            assert not any(f"/verhaal/{f_id}" in loc for loc in all_locs), (
                f"N-2 VIOLATION: Non-public content {f_id} was leaked in sitemap XML!"
            )


@pytest.mark.asyncio
@pytest.mark.integration
class TestSitemapGoogleImageExtension:
    """Tests for Google Image Sitemap 1.1 extension metadata."""

    async def test_artwork_or_image_media_generates_image_tags(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Content with image media generates <image:image> child with loc and title."""
        artwork = FoundationContent(
            tenant_id=1,
            type=ContentType.ARTWORK,
            title_nl="Herdenkingsmonument Schilderij",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url="https://storage.hetlevendmonument.nl/media/artwork_vlaardingen.jpg",
            file_mime="image/jpeg",
        )
        postgres_session.add(artwork)
        await postgres_session.commit()
        await postgres_session.refresh(artwork)

        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        found_image = False
        for u in root.findall("ns:url", NAMESPACES):
            loc_el = u.find("ns:loc", NAMESPACES)
            if loc_el is not None and loc_el.text and f"/verhaal/{artwork.id}" in loc_el.text:
                img_el = u.find("image:image", NAMESPACES)
                assert img_el is not None, "Artwork url should contain <image:image>"
                img_loc = img_el.find("image:loc", NAMESPACES)
                img_title = img_el.find("image:title", NAMESPACES)
                assert img_loc is not None and img_loc.text == artwork.file_url
                assert img_title is not None and img_title.text == artwork.title_nl
                found_image = True
                break

        assert found_image, "Artwork entry with image extension was not found in sitemap"

    async def test_text_only_story_without_image_has_no_image_tag(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Textual story without image media has no <image:image> element."""
        poetry = FoundationContent(
            tenant_id=1,
            type=ContentType.POETRY,
            title_nl="Historisch Gedicht",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=None,
            file_mime=None,
        )
        postgres_session.add(poetry)
        await postgres_session.commit()
        await postgres_session.refresh(poetry)

        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        for u in root.findall("ns:url", NAMESPACES):
            loc_el = u.find("ns:loc", NAMESPACES)
            if loc_el is not None and loc_el.text and f"/verhaal/{poetry.id}" in loc_el.text:
                img_el = u.find("image:image", NAMESPACES)
                assert img_el is None, "Pure text content must not contain <image:image>"
                break


@pytest.mark.asyncio
@pytest.mark.integration
class TestSitemapCanonicalUrlAndHostResolution:
    """Tests for canonical URL resolution and host-based sitemap."""

    async def test_forwarded_host_header_sets_canonical_base(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Header x-forwarded-host determines canonical base in <loc> elements."""
        custom_host = "verhalen.ketikotivlaardingen.nl"
        res = await integration_client.get(
            _url("default", "/sitemap.xml"),
            headers={"x-forwarded-host": custom_host},
        )
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        locs = [
            el.text
            for el in root.findall("ns:url/ns:loc", NAMESPACES)
            if el.text is not None
        ]
        assert len(locs) > 0
        for loc in locs:
            assert loc.startswith(f"https://{custom_host}"), f"Expected loc to start with https://{custom_host}, got {loc}"

    async def test_host_resolved_sitemap_endpoint(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Direct GET /api/v1/foundation/sitemap.xml resolves tenant via host."""
        res = await integration_client.get(
            "/api/v1/foundation/sitemap.xml",
            headers={"x-forwarded-host": "default.levendmonument.nl"},
        )
        assert res.status_code == status.HTTP_200_OK
        assert "application/xml" in res.headers["Content-Type"]
        root = ET.fromstring(res.content)
        assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"


@pytest.mark.asyncio
@pytest.mark.integration
class TestSitemapHeadersAndMultiTenantIsolation:
    """Tests for caching headers, robots tags and cross-tenant separation."""

    async def test_cache_control_and_x_robots_tag_headers(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Sitemap response contains public cache headers and noindex robots tag."""
        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK
        assert "public" in res.headers["Cache-Control"]
        assert "max-age=3600" in res.headers["Cache-Control"]
        assert res.headers["X-Robots-Tag"] == "noindex"

    async def test_cross_tenant_isolation(
        self,
        integration_client: AsyncClient,
        other_tenant_content: FoundationContent,
    ) -> None:
        """Content belonging to tenant 2 must not appear in tenant 1's sitemap."""
        res = await integration_client.get(_url("default", "/sitemap.xml"))
        assert res.status_code == status.HTTP_200_OK

        root = ET.fromstring(res.content)
        all_locs = [
            el.text
            for el in root.findall("ns:url/ns:loc", NAMESPACES)
            if el.text is not None
        ]
        assert not any(f"/verhaal/{other_tenant_content.id}" in loc for loc in all_locs)

    async def test_unknown_tenant_slug_returns_404(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Non-existent tenant returns 404."""
        res = await integration_client.get(
            _url("onbekende-stichting-sitemap", "/sitemap.xml")
        )
        assert res.status_code == status.HTTP_404_NOT_FOUND
        data = res.json()
        err_code = data.get("error_code") or data.get("error", {}).get("error_code")
        assert err_code == "TENANT_NOT_FOUND"
