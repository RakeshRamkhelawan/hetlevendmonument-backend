"""Offline unit tests for BE-EP-037 bbox validation (no DB, no HTTP).

Covers the pure functions in src/core/api/v1/foundation/map.py:
span-cap (exactly 2.0 allowed, above rejected), sw >= ne rejected per axis,
lat/lng range boundaries, antimeridian rejection, and the GeoJSON feature
builder (coordinate order [lng, lat], O8 properties).
"""

from __future__ import annotations

import pytest

from src.core.api.v1.foundation.map import (
    MAX_RESULTS,
    MAX_SPAN_DEG,
    content_to_feature,
    validate_bbox,
)

# A valid reference bbox around Vlaardingen, NL.
VALID = {"sw_lat": 51.8, "sw_lng": 4.2, "ne_lat": 52.0, "ne_lng": 4.5}


@pytest.mark.unit
class TestValidateBBox:
    def test_valid_bbox_returns_none(self) -> None:
        assert validate_bbox(**VALID) is None

    def test_span_exactly_at_cap_allowed(self) -> None:
        assert (
            validate_bbox(sw_lat=50.0, sw_lng=3.0, ne_lat=52.0, ne_lng=5.0) is None
        )

    def test_span_above_cap_lat_rejected(self) -> None:
        error = validate_bbox(sw_lat=50.0, sw_lng=3.0, ne_lat=52.1, ne_lng=5.0)
        assert error is not None
        assert "too large" in error

    def test_span_above_cap_lng_rejected(self) -> None:
        error = validate_bbox(sw_lat=50.0, sw_lng=3.0, ne_lat=52.0, ne_lng=5.1)
        assert error is not None
        assert "too large" in error

    def test_span_cap_constant_is_2_degrees(self) -> None:
        assert MAX_SPAN_DEG == 2.0

    def test_sw_lat_equal_ne_lat_rejected(self) -> None:
        error = validate_bbox(sw_lat=51.0, sw_lng=4.2, ne_lat=51.0, ne_lng=4.5)
        assert error is not None
        assert "sw_lat" in error

    def test_sw_lat_above_ne_lat_rejected(self) -> None:
        error = validate_bbox(sw_lat=52.0, sw_lng=4.2, ne_lat=51.0, ne_lng=4.5)
        assert error is not None
        assert "sw_lat" in error

    def test_sw_lng_equal_ne_lng_rejected(self) -> None:
        error = validate_bbox(sw_lat=51.8, sw_lng=4.3, ne_lat=52.0, ne_lng=4.3)
        assert error is not None
        assert "sw_lng" in error

    def test_antimeridian_rejected(self) -> None:
        """A box crossing the 180-meridian (sw_lng > ne_lng) is out of scope."""
        error = validate_bbox(sw_lat=51.0, sw_lng=179.0, ne_lat=52.0, ne_lng=-179.0)
        assert error is not None
        assert "sw_lng" in error

    def test_latitude_range_boundaries(self) -> None:
        # Exactly -90 / 90 is in range (still subject to ordering/span rules).
        assert (
            validate_bbox(sw_lat=-90.0, sw_lng=0.0, ne_lat=-88.0, ne_lng=1.0) is None
        )
        error = validate_bbox(sw_lat=-91.0, sw_lng=0.0, ne_lat=-89.0, ne_lng=1.0)
        assert error is not None
        assert "latitude" in error
        error = validate_bbox(sw_lat=89.0, sw_lng=0.0, ne_lat=91.0, ne_lng=1.0)
        assert error is not None
        assert "latitude" in error

    def test_longitude_range_boundaries(self) -> None:
        assert (
            validate_bbox(sw_lat=51.0, sw_lng=-180.0, ne_lat=52.0, ne_lng=-178.0)
            is None
        )
        error = validate_bbox(sw_lat=51.0, sw_lng=-181.0, ne_lat=52.0, ne_lng=-179.0)
        assert error is not None
        assert "longitude" in error
        error = validate_bbox(sw_lat=51.0, sw_lng=179.0, ne_lat=52.0, ne_lng=181.0)
        assert error is not None
        assert "longitude" in error

    def test_whole_planet_rejected(self) -> None:
        error = validate_bbox(sw_lat=-90.0, sw_lng=-180.0, ne_lat=90.0, ne_lng=180.0)
        assert error is not None
        assert "too large" in error


@pytest.mark.unit
class TestContentToFeature:
    def _content(self, *, is_anonymous: bool = False) -> object:
        from types import SimpleNamespace

        from src.core.models.foundation_content import ContentType

        return SimpleNamespace(
            id=42,
            title_nl="Monument Vlaardingen",
            type=ContentType.ARTWORK,
            creator_name="Test Maker",
            is_anonymous=is_anonymous,
            category="kunst",
            lat=51.9125,
            lng=4.3417,
        )

    def test_geojson_structure(self) -> None:
        feature = content_to_feature(self._content())  # type: ignore[arg-type]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"

    def test_coordinates_are_lng_lat_order(self) -> None:
        """GeoJSON (RFC 7946) is longitude-first (O5)."""
        feature = content_to_feature(self._content())  # type: ignore[arg-type]
        assert feature["geometry"]["coordinates"] == [4.3417, 51.9125]

    def test_properties_exactly_o8_set(self) -> None:
        feature = content_to_feature(self._content())  # type: ignore[arg-type]
        assert feature["properties"] == {
            "id": 42,
            "title_nl": "Monument Vlaardingen",
            "type": "artwork",
            "creator_name": "Test Maker",
            "category": "kunst",
        }

    def test_anonymous_content_hides_creator_name(self) -> None:
        """Gate-2 HIGH-1: is_anonymous=True must null out creator_name."""
        feature = content_to_feature(self._content(is_anonymous=True))  # type: ignore[arg-type]
        assert feature["properties"]["creator_name"] is None
        # The rest of the O8 properties stay intact.
        assert feature["properties"]["title_nl"] == "Monument Vlaardingen"
        assert feature["properties"]["type"] == "artwork"

    def test_result_cap_constant(self) -> None:
        assert MAX_RESULTS == 500
