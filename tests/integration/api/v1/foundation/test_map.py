"""Integration tests for the Foundation Portal map endpoint (BE-EP-037).

Follows the test_content.py / test_upload.py pattern. Runs against Postgres
5435 + Redis like the other foundation integration tests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
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


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# Bbox around Vlaardingen, NL (span well under the 2.0 degree cap).
BBOX = "sw_lat=51.8&sw_lng=4.2&ne_lat=52.0&ne_lng=4.5"


def _geo_content(
    *,
    tenant_id: int = 1,
    title: str,
    lat: float | None,
    lng: float | None,
    privacy: Privacy = Privacy.PUBLIC,
    status_: ContentStatus = ContentStatus.APPROVED,
) -> FoundationContent:
    return FoundationContent(
        tenant_id=tenant_id,
        type=ContentType.ARTWORK,
        title_nl=title,
        creator_name="Map Tester",
        privacy=privacy,
        status=status_,
        rights_confirmed=True,
        category="kunst",
        lat=lat,
        lng=lng,
    )


# ============================================================================
# Seeded content fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def content_inside_bbox(postgres_session: AsyncSession) -> FoundationContent:
    """Approved public content inside the test bbox (tenant 1)."""
    content = _geo_content(title="Binnen bbox", lat=51.9125, lng=4.3417)
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def geo_exclusion_content(postgres_session: AsyncSession) -> list[FoundationContent]:
    """Content that must NOT appear in the bbox response (tenant 1 + 2)."""
    items = [
        # Outside the bbox
        _geo_content(title="Buiten bbox", lat=52.5, lng=5.5),
        # COMMUNITY privacy is never public-map content (O1)
        _geo_content(title="Community", lat=51.92, lng=4.35, privacy=Privacy.COMMUNITY),
        # PENDING is not approved (O1)
        _geo_content(title="Pending", lat=51.93, lng=4.36, status_=ContentStatus.PENDING),
        # REJECTED is not approved either
        _geo_content(title="Rejected", lat=51.94, lng=4.37, status_=ContentStatus.REJECTED),
        # Other tenant (cross-tenant isolation)
        _geo_content(title="Andere tenant", lat=51.95, lng=4.38, tenant_id=2),
        # No coordinates at all
        _geo_content(title="Zonder geo", lat=None, lng=None),
    ]
    postgres_session.add_all(items)
    await postgres_session.flush()
    for item in items:
        await postgres_session.refresh(item)
    return items


# ============================================================================
# GET /{tenantSlug}/foundation/map/bbox
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestMapBbox:
    """Tests for the public map bbox endpoint."""

    async def test_happy_path_returns_feature_inside_bbox(
        self,
        integration_client: AsyncClient,
        content_inside_bbox: FoundationContent,
        geo_exclusion_content: list[FoundationContent],
    ) -> None:
        """Only the approved public in-bbox item is returned."""
        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["type"] == "FeatureCollection"
        ids = [f["properties"]["id"] for f in data["features"]]
        assert content_inside_bbox.id in ids
        excluded_ids = {item.id for item in geo_exclusion_content}
        assert excluded_ids.isdisjoint(ids)
        assert data["total"] == len(data["features"])
        assert data["has_more"] is False

    async def test_anonymous_content_hides_creator_name(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Gate-2 HIGH-1: APPROVED+PUBLIC content with is_anonymous=True must
        appear in the bbox response with creator_name null."""
        content = _geo_content(title="Anoniem werk", lat=51.9125, lng=4.3417)
        content.is_anonymous = True
        content.creator_name = "Geheime Persoon"
        postgres_session.add(content)
        await postgres_session.flush()
        await postgres_session.refresh(content)

        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK
        feature = next(
            f for f in response.json()["features"] if f["properties"]["id"] == content.id
        )
        assert feature["properties"]["creator_name"] is None

    async def test_geojson_structure_and_coordinate_order(
        self,
        integration_client: AsyncClient,
        content_inside_bbox: FoundationContent,
    ) -> None:
        """GeoJSON: coordinates are [lng, lat]; properties are the O8 set."""
        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK
        feature = next(
            f
            for f in response.json()["features"]
            if f["properties"]["id"] == content_inside_bbox.id
        )
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [
            content_inside_bbox.lng,
            content_inside_bbox.lat,
        ]
        assert feature["properties"] == {
            "id": content_inside_bbox.id,
            "title_nl": "Binnen bbox",
            "type": "artwork",
            "creator_name": "Map Tester",
            "category": "kunst",
        }

    async def test_empty_bbox_returns_empty_collection(
        self, integration_client: AsyncClient
    ) -> None:
        """A valid bbox without content returns an empty FeatureCollection."""
        response = await integration_client.get(
            _url("default", "/map/bbox?sw_lat=50.0&sw_lng=3.0&ne_lat=50.5&ne_lng=3.5")
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []
        assert data["total"] == 0

    async def test_result_cap_500(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """501 matching items -> exactly 500 features + has_more=true (O3)."""
        items = [
            _geo_content(
                title=f"Cap {i}",
                lat=51.9 + (i % 10) * 0.001,
                lng=4.3 + (i // 10) * 0.001,
            )
            for i in range(501)
        ]
        postgres_session.add_all(items)
        await postgres_session.flush()

        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["features"]) == 500
        assert data["total"] == 500
        assert data["has_more"] is True

    async def test_below_cap_has_more_false(
        self,
        integration_client: AsyncClient,
        content_inside_bbox: FoundationContent,
    ) -> None:
        """Fewer matches than the cap -> has_more=false (no phantom cap)."""
        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["has_more"] is False

    async def test_span_cap_rejected(self, integration_client: AsyncClient) -> None:
        """Span above 2.0 degrees -> 400 (O2 anti-scrape)."""
        response = await integration_client.get(
            _url("default", "/map/bbox?sw_lat=50.0&sw_lng=3.0&ne_lat=52.1&ne_lng=5.0")
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_inverted_lat_rejected(self, integration_client: AsyncClient) -> None:
        response = await integration_client.get(
            _url("default", "/map/bbox?sw_lat=52.0&sw_lng=4.2&ne_lat=51.8&ne_lng=4.5")
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_inverted_lng_antimeridian_rejected(
        self, integration_client: AsyncClient
    ) -> None:
        response = await integration_client.get(
            _url("default", "/map/bbox?sw_lat=51.0&sw_lng=179.0&ne_lat=52.0&ne_lng=-179.0")
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_out_of_range_lat_rejected(self, integration_client: AsyncClient) -> None:
        """Query ge/le validation rejects out-of-range coordinates."""
        response = await integration_client.get(
            _url("default", "/map/bbox?sw_lat=-91.0&sw_lng=4.2&ne_lat=51.8&ne_lng=4.5")
        )
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    async def test_unknown_tenant_slug_404(self, integration_client: AsyncClient) -> None:
        response = await integration_client.get(_url("nonexistent", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_no_auth_required(
        self,
        integration_client: AsyncClient,
        content_inside_bbox: FoundationContent,
    ) -> None:
        """The endpoint is public: no Authorization header needed (O1)."""
        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK

    async def test_edu_visibility_excluded_from_public_map(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Educational content inside bbox must NOT be returned on public map (N-2 invariant)."""
        edu_item = FoundationContent(
            tenant_id=1,
            type=ContentType.EDUCATIONAL_WORKBOOK,
            title_nl="Geheim Schoolmateriaal BBox",
            creator_name="Docent Jan",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.EDU,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            category="educatie",
            lat=51.91,
            lng=4.35,
        )
        postgres_session.add(edu_item)
        await postgres_session.commit()

        response = await integration_client.get(_url("default", f"/map/bbox?{BBOX}"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        titles = [f["properties"]["title_nl"] for f in data["features"]]
        assert "Geheim Schoolmateriaal BBox" not in titles
