"""Missions domain dependencies (re-exports for router isolation, ADR-033)."""

from src.core.api.dependencies import get_db as get_db
from src.core.auth.api_deps import get_current_user as get_current_user, require_scopes as require_scopes, OAuth2Scope as OAuth2Scope
from src.core.copilot.council.models import CouncilDecisionRow as CouncilDecisionRow
from src.core.middleware.tenant_context import get_current_tenant_id as get_current_tenant_id

__all__ = [
    "CouncilDecisionRow",
    "get_db",
    "get_current_user",
    "require_scopes",
    "OAuth2Scope",
    "get_current_tenant_id",
]
