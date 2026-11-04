"""
Dependencies for analytics_ingest domain (ADR-033 thin delivery).

Shared dependency helpers -- keeps router files free of direct
src.core.database / src.core.governance imports.
"""

from fastapi import Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db  # noqa: F401 -- re-export for domain routers
from src.core.auth.api_deps import get_current_user_dependency as get_current_user  # noqa: F401
from src.core.auth.auth_service import UserResponse  # noqa: F401 -- re-export voor domeinrouters
from src.core.governance.cookie_consent import CookieConsentManager
from src.core.middleware.tenant_context import (
    get_current_tenant_id,
    safe_get_tenant_id,
)  # noqa: F401


async def analytics_consent_allowed(
    current_user: UserResponse = Depends(get_current_user),  # noqa: B008 -- FastAPI dependency
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> bool:
    """GDPR-004: is analytics tracking allowed for the authenticated user?

    Reads the stored `analytics` consent with the SAME key as the consent writer
    (`privacy/consent_router.py`): `str(current_user.id)` + `current_user.tenant_id`
    (attribute access on the verified-JWT UserResponse -- never `sub`/email or a body
    field). Fail-closed: any read error means no tracking.
    """
    try:
        prefs = await CookieConsentManager(db).get_consent(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
        )
        return bool(prefs.analytics)
    except Exception as e:  # fail-closed
        logger.warning(
            "analytics consent read failed (fail-closed, no tracking): {}: {}",
            type(e).__name__,
            e,
        )
        return False


__all__ = [
    "UserResponse",
    "get_db",
    "get_current_user",
    "get_current_tenant_id",
    "safe_get_tenant_id",
    "analytics_consent_allowed",
]
