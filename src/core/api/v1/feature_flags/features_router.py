"""
Feature Flags -- public features listing sub-router (ADR-033 Laag 1).

Routes:
  GET /features -- list all available features grouped by tier
"""

import logging
from typing import Any, cast

from fastapi import APIRouter

from src.core.feature_flags import (
    Feature,
    Tier,
    get_tier_features,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared constants (re-exported for other sub-routers)
# ---------------------------------------------------------------------------

FEATURE_DESCRIPTIONS: dict[Feature, str] = {
    Feature.CORE_AGENTS: "Access to built-in AI agents (10 agents)",
    Feature.BASIC_ANALYTICS: "Usage statistics and basic metrics",
    Feature.API_ACCESS: "REST API access with rate limiting",
    Feature.MEMORY_MCP: "Semantic memory integration via MCP protocol",
    Feature.ADVANCED_ANALYTICS: "Detailed insights and custom reports",
    Feature.CUSTOM_BRANDING: "White-label UI customization",
    Feature.PRIORITY_SUPPORT: "24-hour response time support",
    Feature.INCREASED_RATE_LIMITS: "10x higher API rate limits",
    Feature.OLLAMA_MCP: "Local LLM integration for privacy",
    Feature.CUSTOM_AGENTS: "Deploy and run custom agent code",
    Feature.SSO: "Single sign-on (SAML/OAuth)",
    Feature.AUDIT_LOGS: "Compliance audit trail",
    Feature.SLA_GUARANTEE: "99.9% uptime SLA",
    Feature.DEDICATED_SUPPORT: "Dedicated support engineer",
    Feature.ON_PREMISE_DEPLOYMENT: "Self-hosted deployment option",
    Feature.CUSTOM_INTEGRATIONS: "Custom API integrations",
}

TIER_PRICING: dict[Tier, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
    Tier.FREE: {
        "display_name": "Free",
        "price": 0.0,
        "workflows_per_month": 50,
        "agents": 5,
    },
    Tier.STARTER: {"display_name": "Starter", "price": 0.0},
    Tier.PRO: {"display_name": "Professional", "price": 49.0},
    Tier.ENTERPRISE: {"display_name": "Enterprise", "price": 499.0},
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class TierInfo(BaseModel):
    """Information about a subscription tier."""

    name: str
    display_name: str
    price_monthly: float
    features: list[str]
    feature_count: int


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/features", response_model=dict[str, list[TierInfo]])
async def list_all_features() -> dict[str, list[TierInfo]]:
    """List all available features grouped by tier."""
    tiers_info: list[TierInfo] = []
    for tier in [Tier.FREE, Tier.STARTER, Tier.PRO, Tier.ENTERPRISE]:
        features = get_tier_features(tier)
        pricing = TIER_PRICING[tier]
        tier_info = TierInfo(
            name=tier.value,
            display_name=cast(str, pricing["display_name"]),
            price_monthly=cast(float, pricing["price"]),
            features=[f.value for f in features],
            feature_count=len(features),
        )
        tiers_info.append(tier_info)

    return {"tiers": tiers_info}
