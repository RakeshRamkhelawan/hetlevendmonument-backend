"""
Feature Flag System for Multi-Tenant Monetization
Task 1.3: Feature Flag Manager Implementation

This module provides:
- Feature and Tier enums (features.py)
- FeatureFlagManager for checking/managing flags (manager.py)
- @requires_feature decorator for endpoint protection

Usage:
    # In main.py startup
    from src.core.feature_flags import FeatureFlagManager, Feature, Tier

    ff_manager = FeatureFlagManager(redis_client=redis, db_session=db)
    app.state.ff_manager = ff_manager

    # In endpoint
    from src.core.feature_flags import requires_feature, Feature

    @app.get("/api/memory/search")
    @requires_feature(Feature.MEMORY_MCP)  # Only Pro+ tenants
    async def search_memories(query: str, request: Request):
        ...

    # Check feature programmatically
    if await ff_manager.is_enabled(tenant_id, Feature.CUSTOM_AGENTS):
        # Allow custom agent deployment
        pass
"""

from typing import Any

from src.core.feature_flags.features import (
    TIER_FEATURES,
    Feature,
    Tier,
    feature_included_in_tier,
    get_missing_features,
    get_tier_features,
    get_tier_for_feature,
)
from src.core.feature_flags.manager import FeatureFlagManager, requires_feature

__all__ = [
    # Enums
    "Feature",
    "Tier",
    "TIER_FEATURES",
    # Helper functions
    "get_tier_features",
    "feature_included_in_tier",
    "get_missing_features",
    "get_tier_for_feature",
    # Manager
    "FeatureFlagManager",
    "requires_feature",
]
