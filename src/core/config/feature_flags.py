"""Feature flags for rollout and canary deployments.

This module provides the dependencies and configuration for progressively
rolling out new features, such as the AI Copilot Council.
"""

import os
from typing import Any

from fastapi import Depends, HTTPException, status

from src.core.middleware.tenant_context import get_tenant_id

# The rollout percentage is set to 100 to enable the feature for all users,
# but the code structure is retained as an example for future rollouts.
COPILOT_COUNCIL_V1_ROLLOUT_PCT = int(os.getenv("COPILOT_COUNCIL_V1_ROLLOUT_PCT", "100"))

class RequireFeatureRollout:
    """FastAPI dependency to enforce percentage-based rollout."""

    def __init__(self, feature_name: str, rollout_pct: int) -> None:
        self.feature_name = feature_name
        self.rollout_pct = rollout_pct

    async def __call__(self) -> None:
        tenant_id = get_tenant_id()
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No active tenant context found.",
            )

        # Simple deterministic hashing (modulo) for canary rollout
        if (tenant_id % 100) >= self.rollout_pct:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_not_enabled",
                    "feature": self.feature_name,
                    "message": "This feature is not yet enabled for your workspace.",
                },
            )

def check_copilot_rollout() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Check if the Copilot Council feature is rolled out to the current tenant."""
    return Depends(RequireFeatureRollout("COPILOT_COUNCIL_V1", COPILOT_COUNCIL_V1_ROLLOUT_PCT))
