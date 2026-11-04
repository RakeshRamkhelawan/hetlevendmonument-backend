"""
Unit tests for FREE tier (TASK-002)
Tests Freemium tier implementation with limits
"""

import pytest

from src.core.feature_flags.features import (
    TIER_FEATURES,
    Feature,
    Tier,
    feature_included_in_tier,
    get_tier_features,
    get_tier_for_feature,
)


class TestFreeTierEnum:
    """Test FREE tier enum exists and is valid"""

    def test_free_tier_exists(self):
        """FREE tier should exist in Tier enum"""
        assert hasattr(Tier, "FREE")
        assert Tier.FREE.value == "free"

    def test_tier_order(self):
        """Tiers should be in correct order"""
        tiers = list(Tier)
        tier_values = [t.value for t in tiers]
        assert "free" in tier_values
        # FREE should come before or at same position as STARTER
        free_idx = tier_values.index("free")
        starter_idx = tier_values.index("starter")
        assert free_idx <= starter_idx


class TestFreeTierFeatures:
    """Test FREE tier has correct features"""

    def test_free_tier_in_tier_features(self):
        """FREE tier should be in TIER_FEATURES mapping"""
        assert Tier.FREE in TIER_FEATURES

    def test_free_tier_has_core_agents(self):
        """FREE tier should include CORE_AGENTS"""
        free_features = TIER_FEATURES[Tier.FREE]
        assert Feature.CORE_AGENTS in free_features

    def test_free_tier_limited_features(self):
        """FREE tier should have very limited features"""
        free_features = TIER_FEATURES[Tier.FREE]
        # FREE tier should have much fewer features than STARTER
        starter_features = TIER_FEATURES[Tier.STARTER]
        assert len(free_features) < len(starter_features)

    def test_free_tier_no_advanced_features(self):
        """FREE tier should NOT have advanced features"""
        free_features = TIER_FEATURES[Tier.FREE]
        assert Feature.MEMORY_MCP not in free_features
        assert Feature.CUSTOM_AGENTS not in free_features
        assert Feature.SSO not in free_features
        assert Feature.ADVANCED_ANALYTICS not in free_features


class TestGetTierFeatures:
    """Test get_tier_features helper with FREE tier"""

    def test_get_free_tier_features(self):
        """get_tier_features should work for FREE tier"""
        features = get_tier_features(Tier.FREE)
        assert isinstance(features, set)
        assert len(features) >= 1

    def test_free_tier_subset_of_starter(self):
        """FREE features should be subset of STARTER features"""
        free_features = get_tier_features(Tier.FREE)
        starter_features = get_tier_features(Tier.STARTER)
        assert free_features.issubset(starter_features)


class TestFeatureIncludedInTier:
    """Test feature_included_in_tier with FREE tier"""

    def test_core_agents_in_free(self):
        """CORE_AGENTS should be included in FREE tier"""
        assert feature_included_in_tier(Feature.CORE_AGENTS, Tier.FREE)

    def test_api_access_not_in_free(self):
        """API_ACCESS should NOT be in FREE tier"""
        assert not feature_included_in_tier(Feature.API_ACCESS, Tier.FREE)

    def test_basic_analytics_not_in_free(self):
        """BASIC_ANALYTICS should NOT be in FREE tier"""
        assert not feature_included_in_tier(Feature.BASIC_ANALYTICS, Tier.FREE)


class TestGetTierForFeature:
    """Test get_tier_for_feature includes FREE tier"""

    def test_core_agents_minimum_tier_is_free(self):
        """CORE_AGENTS minimum tier should be FREE"""
        min_tier = get_tier_for_feature(Feature.CORE_AGENTS)
        assert min_tier == Tier.FREE

    def test_api_access_minimum_tier_is_starter(self):
        """API_ACCESS minimum tier should be STARTER"""
        min_tier = get_tier_for_feature(Feature.API_ACCESS)
        assert min_tier == Tier.STARTER

    def test_memory_mcp_minimum_tier_is_pro(self):
        """MEMORY_MCP minimum tier should be PRO"""
        min_tier = get_tier_for_feature(Feature.MEMORY_MCP)
        assert min_tier == Tier.PRO


class TestTierPricing:
    """Test TIER_PRICING includes FREE tier"""

    def test_free_tier_pricing_exists(self):
        """FREE tier should be in TIER_PRICING"""
        from src.core.api.v1.feature_flags.features_router import TIER_PRICING

        assert Tier.FREE in TIER_PRICING

    def test_free_tier_price_is_zero(self):
        """FREE tier price should be 0"""
        from src.core.api.v1.feature_flags.features_router import TIER_PRICING

        assert TIER_PRICING[Tier.FREE]["price"] == 0.0

    def test_free_tier_has_workflow_limit(self):
        """FREE tier should have workflows_per_month limit"""
        from src.core.api.v1.feature_flags.features_router import TIER_PRICING

        assert "workflows_per_month" in TIER_PRICING[Tier.FREE]
        assert TIER_PRICING[Tier.FREE]["workflows_per_month"] == 50

    def test_free_tier_has_agent_limit(self):
        """FREE tier should have agents limit"""
        from src.core.api.v1.feature_flags.features_router import TIER_PRICING

        assert "agents" in TIER_PRICING[Tier.FREE]
        assert TIER_PRICING[Tier.FREE]["agents"] == 5
