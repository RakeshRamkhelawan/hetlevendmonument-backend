"""
Unit tests for Prometheus middleware path normalization.

Covers:
- Dynamic path segments (IDs, UUIDs) are normalized to {id}
- Static paths remain unchanged
- Mixed paths with multiple dynamic segments
"""

import pytest

from src.core.observability.metrics import _normalize_path


class TestNormalizePath:
    """Tests for the _normalize_path helper."""

    def test_static_path_unchanged(self):
        """Static paths should not be modified."""
        assert _normalize_path("/api/v1/health") == "/api/v1/health"
        assert _normalize_path("/api/v1/auth/login") == "/api/v1/auth/login"

    def test_integer_id_normalized(self):
        """Integer IDs should be replaced with {id}."""
        assert _normalize_path("/api/v1/users/123") == "/api/v1/users/{id}"
        assert _normalize_path("/api/v1/users/42/profile") == "/api/v1/users/{id}/profile"

    def test_uuid_normalized(self):
        """UUIDs should be replaced with {id}."""
        assert (
            _normalize_path("/api/v1/agents/550e8400-e29b-41d4-a716-446655440000")
            == "/api/v1/agents/{id}"
        )

    def test_multiple_ids_normalized(self):
        """Paths with multiple ID segments should all be normalized."""
        assert (
            _normalize_path("/api/v1/tenants/1/users/42/orders/99")
            == "/api/v1/tenants/{id}/users/{id}/orders/{id}"
        )

    def test_root_path_unchanged(self):
        """Root path should remain unchanged."""
        assert _normalize_path("/") == "/"

    def test_empty_string_unchanged(self):
        """Empty string should remain unchanged."""
        assert _normalize_path("") == ""

    def test_hex_id_normalized(self):
        """Hex IDs should be replaced with {id}."""
        assert _normalize_path("/api/v1/blocks/abc12345") == "/api/v1/blocks/{id}"
        assert _normalize_path("/api/v1/blocks/ABC123DEF456") == "/api/v1/blocks/{id}"

    def test_slug_not_normalized(self):
        """URL slugs should not be replaced to avoid over-normalization."""
        assert _normalize_path("/api/v1/items/item-123") == "/api/v1/items/item-123"
        assert _normalize_path("/api/v1/items/item_123") == "/api/v1/items/item_123"
        assert _normalize_path("/api/v1/docs/getting-started") == "/api/v1/docs/getting-started"
