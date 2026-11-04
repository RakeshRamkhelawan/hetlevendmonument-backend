# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Privacy consent endpoints: get + update consent (ADR-033 Laag 1, GDPR Art. 7)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.privacy.dependencies import (
    CookieConsentManager,
    LawfulBasisMissingError,
    LawfulBasisRegistry,
    consent_read_limit,
    consent_update_limit,
    get_current_user,
    get_db,
    get_lawful_basis_registry,
)
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

consent_router = APIRouter()


class ConsentUpdateRequest(BaseModel):
    preferences: dict[str, bool]
    policy_version: str = "1.0"


@consent_router.get("/consent-status")
@consent_read_limit
async def get_consent_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    registry: LawfulBasisRegistry = Depends(get_lawful_basis_registry),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current consent status for the user (GDPR Art. 7)."""
    try:
        await registry.validate_endpoint_access("/api/v1/privacy/consent-status")
    except LawfulBasisMissingError as e:
        logger.error(
            "LawfulBasis hard-blocked (GDPR Art. 6): %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=451,
            detail="Data processing is not authorized for this endpoint",
        ) from e

    manager = CookieConsentManager(db)
    consent = await manager.get_consent(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )

    return {
        "user_id": current_user.id,
        "has_consent": consent.essential,
        "consents": {
            "essential": consent.essential,
            "analytics": consent.analytics,
            "marketing": consent.marketing,
            "personalization": consent.personalization,
            "timestamp": consent.timestamp.isoformat(),
            "policy_version": consent.policy_version,
        },
    }


@consent_router.post("/consent")
@consent_update_limit
async def update_consent(
    request: Request,
    consent_request: ConsentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    registry: LawfulBasisRegistry = Depends(get_lawful_basis_registry),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Update consent preferences (GDPR Art. 7)."""
    try:
        await registry.validate_endpoint_access("/api/v1/privacy/consent")
    except LawfulBasisMissingError as e:
        logger.error(
            "LawfulBasis hard-blocked (GDPR Art. 6): %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=451,
            detail="Data processing is not authorized for this endpoint",
        ) from e

    manager = CookieConsentManager(db)

    try:
        consent = await manager.update_consent(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            preferences=consent_request.preferences,
            policy_version=consent_request.policy_version,
        )

        return {
            "status": "success",
            "message": "Consent preferences updated",
            "essential": consent.essential,
            "analytics": consent.analytics,
            "marketing": consent.marketing,
            "personalization": consent.personalization,
            "timestamp": consent.timestamp.isoformat(),
            "policy_version": consent.policy_version,
        }
    except Exception as e:
        logger.error("Failed to update consent: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to update consent preferences",
        )


@consent_router.post("/consent/withdraw")
@consent_update_limit
async def withdraw_consent(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    registry: LawfulBasisRegistry = Depends(get_lawful_basis_registry),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Withdraw all non-essential consent (GDPR Art. 7(3)).

    ADR-036 OP-73: dit pad stond al in de frontend-clientlaag maar had nooit een
    backend-route (404). Essential kan sowieso niet worden ingetrokken --
    `CookieConsentManager.update_consent` forceert `essential=True` altijd, ongeacht
    wat er in `preferences` staat -- dus die sleutel hoeft hier niet meegegeven te worden.
    """
    try:
        await registry.validate_endpoint_access("/api/v1/privacy/consent/withdraw")
    except LawfulBasisMissingError as e:
        logger.error(
            "LawfulBasis hard-blocked (GDPR Art. 6): %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=451,
            detail="Data processing is not authorized for this endpoint",
        ) from e

    manager = CookieConsentManager(db)

    try:
        consent = await manager.update_consent(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            preferences={"analytics": False, "marketing": False, "personalization": False},
            policy_version="1.0",
        )

        return {
            "status": "success",
            "message": "Non-essential consent withdrawn",
            "essential": consent.essential,
            "analytics": consent.analytics,
            "marketing": consent.marketing,
            "personalization": consent.personalization,
            "timestamp": consent.timestamp.isoformat(),
            "policy_version": consent.policy_version,
        }
    except Exception as e:
        logger.error("Failed to withdraw consent: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to withdraw consent",
        ) from e
