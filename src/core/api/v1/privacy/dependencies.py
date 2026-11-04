# orphan:exempt reason: Laag 1 dependencies, imported by privacy sub-routers (ADR-033)
"""Privacy API shared dependencies (ADR-033 Laag 1)."""

from src.core.auth.api_deps import get_current_user as get_current_user
from src.core.database.database import get_db as get_db
from src.core.governance.ai_transparency_service import (
    AITransparencyService as AITransparencyService,
    ProfilingType as ProfilingType,
)
from src.core.governance.cookie_consent import CookieConsentManager as CookieConsentManager
from src.core.governance.dependencies import (
    LawfulBasisMissingError as LawfulBasisMissingError,
    LawfulBasisRegistry as LawfulBasisRegistry,
    get_lawful_basis_registry as get_lawful_basis_registry,
)
from src.core.governance.models import (
    AIDecision as AIDecision,
    HumanReviewRequest as HumanReviewRequest,
    UserProfilingOptOut as UserProfilingOptOut,
)
from src.core.governance.rate_limiter import (
    ai_transparency_limit as ai_transparency_limit,
    consent_read_limit as consent_read_limit,
    consent_update_limit as consent_update_limit,
    dsar_delete_limit as dsar_delete_limit,
    dsar_export_limit as dsar_export_limit,
    human_review_limit as human_review_limit,
)

__all__ = [
    "AIDecision",
    "AITransparencyService",
    "CookieConsentManager",
    "HumanReviewRequest",
    "LawfulBasisMissingError",
    "LawfulBasisRegistry",
    "ProfilingType",
    "UserProfilingOptOut",
    "ai_transparency_limit",
    "consent_read_limit",
    "consent_update_limit",
    "dsar_delete_limit",
    "dsar_export_limit",
    "get_current_user",
    "get_db",
    "get_lawful_basis_registry",
    "human_review_limit",
]
