# tests/unit/test_dynamic_rate_limiting.py
import pytest

from src.core.middleware.rate_limit_middleware import resolve_rate_limit_for_tier


@pytest.mark.unit
def test_resolve_rate_limit_scales_with_tier():
    # Test that we assign the correct rate limits based on subscription tier
    assert resolve_rate_limit_for_tier("free") == 60
    assert resolve_rate_limit_for_tier("starter") == 120
    assert resolve_rate_limit_for_tier("pro") == 360
    assert resolve_rate_limit_for_tier("enterprise") == 5000
    assert resolve_rate_limit_for_tier(None) == 60  # Safe fallback
