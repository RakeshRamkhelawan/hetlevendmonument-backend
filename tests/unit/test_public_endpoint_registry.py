"""
Unit tests for PUBLIC_PREFIXES registry (Task 8).

Verifies /api/v1/public/ is present and /admin/ is NOT present.
"""

import pytest

from src.core.api.public_endpoints import PublicEndpointRegistry


class TestPublicPrefixes:
    @pytest.mark.unit
    def test_api_v1_public_present(self) -> None:
        assert "/api/v1/public/" in PublicEndpointRegistry.PUBLIC_PREFIXES

    @pytest.mark.unit
    def test_admin_not_present(self) -> None:
        for prefix in PublicEndpointRegistry.PUBLIC_PREFIXES:
            assert not prefix.startswith("/admin"), f"Forbidden prefix: {prefix}"

    @pytest.mark.unit
    def test_is_public_matches(self) -> None:
        assert PublicEndpointRegistry.is_public("/api/v1/public/ketikoti/content")
        assert PublicEndpointRegistry.is_public("/api/v1/public/ketikoti/settings")

    @pytest.mark.unit
    def test_admin_is_not_public(self) -> None:
        assert not PublicEndpointRegistry.is_public("/admin/foundation/content")
