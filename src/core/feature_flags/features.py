"""
Feature Flag Definitions for Multi-Tenant Monetization
Task 1.3.1: Define Feature Enums

This module defines:
- Feature enum: All gated features in the platform
- Tier enum: Subscription tiers (STARTER, PRO, ENTERPRISE)
- TIER_FEATURES: Mapping[str, Any] of which features are included in each tier  # TODO(TYPE): replace Any with concrete type

Usage:
    from src.core.feature_flags.features import Feature, Tier, TIER_FEATURES

    # Check if tier includes feature
    if Feature.MEMORY_MCP in TIER_FEATURES[Tier.PRO]:
        print("Pro tier includes semantic memory")

    # Get all features for a tier
    pro_features = TIER_FEATURES[Tier.PRO]
"""

from enum import Enum


class Feature(str, Enum):
    """
    Monetized features available per tier

    Feature Categories:
    - Core: Included in all tiers
    - Analytics: Data insights and reporting
    - AI/ML: Advanced AI capabilities
    - Integration: Third-party integrations
    - Enterprise: Advanced security and compliance
    """

    # ========================================================================
    # STARTER TIER (Free/Basic)
    # ========================================================================
    CORE_AGENTS = "core_agents"  # Access to built-in agents
    BASIC_ANALYTICS = "basic_analytics"  # Usage stats, basic metrics
    API_ACCESS = "api_access"  # REST API access (rate-limited)

    # ========================================================================
    # PRO TIER ($49/month)
    # ========================================================================
    MEMORY_MCP = "memory_mcp"  # Semantic memory integration (MCP)
    ADVANCED_ANALYTICS = "advanced_analytics"  # Detailed insights, custom reports
    CUSTOM_BRANDING = "custom_branding"  # White-label UI
    PRIORITY_SUPPORT = "priority_support"  # 24h response time
    INCREASED_RATE_LIMITS = "increased_rate_limits"  # 10x API rate limits

    # ========================================================================
    # ENTERPRISE TIER ($499/month)
    # ========================================================================
    OLLAMA_MCP = "ollama_mcp"  # Local LLM integration (privacy)
    CUSTOM_AGENTS = "custom_agents"  # Deploy custom agent code
    SSO = "sso"  # Single sign-on (SAML/OAuth)
    AUDIT_LOGS = "audit_logs"  # Compliance audit trail
    SLA_GUARANTEE = "sla_guarantee"  # 99.9% uptime SLA
    DEDICATED_SUPPORT = "dedicated_support"  # Dedicated support engineer
    ON_PREMISE_DEPLOYMENT = "on_premise_deployment"  # Self-hosted option
    CUSTOM_INTEGRATIONS = "custom_integrations"  # Custom API integrations


class Tier(str, Enum):
    """
    Subscription tiers with included features

    Pricing:
    - FREE: $0/month (demo/trial tier with strict limits)
    - STARTER: $0/month (free tier with basic features)
    - PRO: $49/month
    - ENTERPRISE: $499/month (custom pricing for >100 users)
    """

    FREE = "free"  # TASK-002: Freemium tier with 50 workflows/month limit
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# ============================================================================
# TIER TO FEATURES MAPPING
# ============================================================================

TIER_FEATURES: dict[Tier, set[Feature]] = {
    # ------------------------------------------------------------------------
    # FREE TIER: Demo/Trial (Very Limited) - TASK-002
    # 50 workflows/month, 5 agents, no custom agents
    # ------------------------------------------------------------------------
    Tier.FREE: {
        Feature.CORE_AGENTS,  # Access to 5 built-in agents only
    },
    # ------------------------------------------------------------------------
    # STARTER TIER: Free (Limited)
    # ------------------------------------------------------------------------
    Tier.STARTER: {
        Feature.CORE_AGENTS,  # Access to 10 built-in agents
        Feature.BASIC_ANALYTICS,  # Basic usage stats
        Feature.API_ACCESS,  # 60 req/min rate limit
    },
    # ------------------------------------------------------------------------
    # PRO TIER: $49/month (Small teams)
    # ------------------------------------------------------------------------
    Tier.PRO: {
        # Includes all STARTER features
        Feature.CORE_AGENTS,
        Feature.BASIC_ANALYTICS,
        Feature.API_ACCESS,
        # PRO-exclusive features
        Feature.MEMORY_MCP,  # Semantic memory
        Feature.ADVANCED_ANALYTICS,  # Custom reports
        Feature.CUSTOM_BRANDING,  # White-label
        Feature.PRIORITY_SUPPORT,  # 24h response
        Feature.INCREASED_RATE_LIMITS,  # 600 req/min
    },
    # ------------------------------------------------------------------------
    # ENTERPRISE TIER: $499/month (Large organizations)
    # ------------------------------------------------------------------------
    Tier.ENTERPRISE: {
        # Includes all PRO features
        Feature.CORE_AGENTS,
        Feature.BASIC_ANALYTICS,
        Feature.API_ACCESS,
        Feature.MEMORY_MCP,
        Feature.ADVANCED_ANALYTICS,
        Feature.CUSTOM_BRANDING,
        Feature.PRIORITY_SUPPORT,
        Feature.INCREASED_RATE_LIMITS,
        # ENTERPRISE-exclusive features
        Feature.OLLAMA_MCP,  # Local LLM (privacy)
        Feature.CUSTOM_AGENTS,  # Custom code deployment
        Feature.SSO,  # SAML/OAuth
        Feature.AUDIT_LOGS,  # Compliance
        Feature.SLA_GUARANTEE,  # 99.9% uptime
        Feature.DEDICATED_SUPPORT,  # Dedicated engineer
        Feature.ON_PREMISE_DEPLOYMENT,  # Self-hosted
        Feature.CUSTOM_INTEGRATIONS,  # Custom APIs
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_tier_features(tier: Tier) -> set[Feature]:
    """
    Get all features included in a tier

    Args:
        tier: Subscription tier

    Returns: Set[Any] of features included in tier  # TODO(TYPE): replace Any with concrete type

    Example:
        >>> features = get_tier_features(Tier.PRO)
        >>> Feature.MEMORY_MCP in features
        True
    """
    return TIER_FEATURES.get(tier, set())


def feature_included_in_tier(feature: Feature, tier: Tier) -> bool:
    """
    Check if feature is included in tier

    Args:
        feature: Feature to check
        tier: Tier to check against

    Returns:
        True if feature is included in tier

    Example:
        >>> feature_included_in_tier(Feature.SSO, Tier.STARTER)
        False
        >>> feature_included_in_tier(Feature.SSO, Tier.ENTERPRISE)
        True
    """
    return feature in TIER_FEATURES.get(tier, set())


def get_missing_features(current_tier: Tier, target_tier: Tier) -> set[Feature]:
    """
    Get features gained by upgrading from current_tier to target_tier

    Args:
        current_tier: Current subscription tier
        target_tier: Target tier to upgrade to

    Returns: Set[Any] of new features gained by upgrading  # TODO(TYPE): replace Any with concrete type

    Example:
        >>> missing = get_missing_features(Tier.STARTER, Tier.PRO)
        >>> Feature.MEMORY_MCP in missing
        True
    """
    current_features = TIER_FEATURES.get(current_tier, set())
    target_features = TIER_FEATURES.get(target_tier, set())
    return target_features - current_features


def get_tier_for_feature(feature: Feature) -> Tier:
    """
    Get minimum tier required for a feature

    Args:
        feature: Feature to check

    Returns:
        Minimum tier that includes this feature

    Example:
        >>> get_tier_for_feature(Feature.MEMORY_MCP)
        <Tier.PRO: 'pro'>
    """
    for tier in [Tier.FREE, Tier.STARTER, Tier.PRO, Tier.ENTERPRISE]:
        if feature in TIER_FEATURES[tier]:
            return tier
    raise ValueError(f"Feature {feature} not found in any tier")
