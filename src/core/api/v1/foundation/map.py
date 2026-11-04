"""Foundation Portal public map endpoint (BE-EP-037, ADR-029 gap P0-4).

GET /{tenantSlug}/foundation/map/bbox returns a GeoJSON FeatureCollection
with approved, public content inside a bounding box. Public (no login):
this is the portal showcase endpoint. See
docs/backend/features/BE-EP-037-map-bbox-endpoint.md for decisions O1..O9.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    ContentStatus,
    FoundationContent,
    Privacy,
    Visibility,
)

from src.core.api.v1.foundation.dependencies import (
    get_db,
    portal_public_read_limit,
    public_tenant_scope,
)
from src.core.api.v1.foundation.schemas import apply_anonymity_mask

router = APIRouter(tags=["foundation-map"])

# Anti-scrape (O2/O3): without a span cap a client could dump all public
# content in one call; 2 degrees (~220 km) is generous for a city/region map.
MAX_SPAN_DEG = 2.0
MAX_RESULTS = 500


def validate_bbox(*, sw_lat: float, sw_lng: float, ne_lat: float, ne_lng: float) -> str | None:
    """Validate a bounding box; return an error message or None when valid.

    Pure function (no framework, no DB) so it is unit-testable offline.
    Checks ranges, axis ordering (sw < ne per axis; antimeridian boxes are
    rejected, out of scope per spec) and the 2.0 degree span cap (O2/O7).
    """
    if not (-90.0 <= sw_lat <= 90.0) or not (-90.0 <= ne_lat <= 90.0):
        return "latitude out of range [-90, 90]"
    if not (-180.0 <= sw_lng <= 180.0) or not (-180.0 <= ne_lng <= 180.0):
        return "longitude out of range [-180, 180]"
    if sw_lat >= ne_lat:
        return "sw_lat must be smaller than ne_lat"
    if sw_lng >= ne_lng:
        return "sw_lng must be smaller than ne_lng (antimeridian not supported)"
    if (ne_lat - sw_lat) > MAX_SPAN_DEG or (ne_lng - sw_lng) > MAX_SPAN_DEG:
        return "bbox too large, max 2 degrees per axis"
    return None


def content_to_feature(content: FoundationContent) -> dict[str, object]:
    """Map a content row to a GeoJSON Feature.

    Coordinates are [lng, lat] in that order (O5, RFC 7946). Properties are
    exactly the O8 set: enough for map popups, no excess data.
    """
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [content.lng, content.lat],
        },
        "properties": {
            "id": content.id,
            "title_nl": content.title_nl,
            "type": content.type.value,
            # Respect the uploader's anonymity choice (Gate-2 HIGH-1,
            # 2026-09-09): is_anonymous=True must never leak creator_name on
            # this public, unauthenticated, bulk-scrapeable endpoint.
            # Shared with the content schemas via apply_anonymity_mask
            # (BE-EP-038), so the masking rule cannot drift per serializer.
            "creator_name": apply_anonymity_mask(content.is_anonymous, content.creator_name),
            "category": content.category,
        },
    }


@router.get(
    "/map/bbox",
    summary="Public map content within a bounding box",
)
@portal_public_read_limit
async def map_bbox(
    tenantSlug: str,
    request: Request,
    sw_lat: float | None = Query(None, ge=-90.0, le=90.0),
    sw_lng: float | None = Query(None, ge=-180.0, le=180.0),
    ne_lat: float | None = Query(None, ge=-90.0, le=90.0),
    ne_lng: float | None = Query(None, ge=-180.0, le=180.0),
    min_lat: float | None = Query(None, ge=-90.0, le=90.0),
    min_lng: float | None = Query(None, ge=-180.0, le=180.0),
    max_lat: float | None = Query(None, ge=-90.0, le=90.0),
    max_lng: float | None = Query(None, ge=-180.0, le=180.0),
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Public GeoJSON FeatureCollection of approved public content in a bbox.

    - No authentication (O1); only status=APPROVED and privacy=PUBLIC
    - Rate limit: 60/min per IP (portal_public_read_limit, O6)
    - Span cap 2.0 degrees per axis and result cap 500 (O2/O3, anti-scrape)
    - No audit log per request: public read (O9)
    - Accepts both (sw_lat, sw_lng, ne_lat, ne_lng) and (min_lat, min_lng, max_lat, max_lng)
    """
    eff_sw_lat = sw_lat if sw_lat is not None else min_lat
    eff_sw_lng = sw_lng if sw_lng is not None else min_lng
    eff_ne_lat = ne_lat if ne_lat is not None else max_lat
    eff_ne_lng = ne_lng if ne_lng is not None else max_lng

    if None in (eff_sw_lat, eff_sw_lng, eff_ne_lat, eff_ne_lng):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required bounding box coordinates. Provide either (sw_lat, sw_lng, ne_lat, ne_lng) or (min_lat, min_lng, max_lat, max_lng).",
        )

    c_sw_lat = float(eff_sw_lat)
    c_sw_lng = float(eff_sw_lng)
    c_ne_lat = float(eff_ne_lat)
    c_ne_lng = float(eff_ne_lng)

    bbox_error = validate_bbox(sw_lat=c_sw_lat, sw_lng=c_sw_lng, ne_lat=c_ne_lat, ne_lng=c_ne_lng)
    if bbox_error is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=bbox_error,
        )

    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Explicit tenant_id WHERE: double isolation on top of the ORM hook.
        stmt = (
            select(FoundationContent)
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.APPROVED,
                FoundationContent.privacy == Privacy.PUBLIC,
                FoundationContent.visibility == Visibility.PUBLIC,
                FoundationContent.lat.is_not(None),
                FoundationContent.lng.is_not(None),
                FoundationContent.lat >= c_sw_lat,
                FoundationContent.lat <= c_ne_lat,
                FoundationContent.lng >= c_sw_lng,
                FoundationContent.lng <= c_ne_lng,
            )
            .order_by(FoundationContent.created_at.desc())
            .limit(MAX_RESULTS + 1)  # +1 row to compute has_more
        )
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        # Fetch one extra row to distinguish "exactly at the cap" from "more
        # available" (Gate-2 LOW total-semantiek, 2026-09-09): the frontend
        # can only warn reliably when has_more is explicit.
        has_more = len(items) > MAX_RESULTS
        features = [content_to_feature(item) for item in items[:MAX_RESULTS]]
        return {
            "type": "FeatureCollection",
            "features": features,
            "total": len(features),
            "has_more": has_more,
        }
