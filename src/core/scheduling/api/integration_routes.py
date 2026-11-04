"""
REST API endpoints for external calendar integrations (OAuth, sync).

Security: JWT auth via ``get_current_user`` on all endpoints.
Audit:   State-changing operations are logged via ``AuditService``.
Rate Limiting: OAuth endpoints are rate-limited to prevent abuse.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.security.security_manager import ThreatLevel

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
from src.core.scheduling.integrations.base_provider import BaseCalendarProvider
from src.core.scheduling.integrations.exceptions import (
    CalendarIntegrationError,
    OAuthError,
    RateLimitError,
)
from src.core.scheduling.integrations.google_calendar import GoogleCalendarProvider
from src.core.scheduling.integrations.outlook_calendar import OutlookCalendarProvider
from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
from src.core.scheduling.integrations.sync_service import CalendarSyncService
from src.core.scheduling.integrations.token_encryption import TokenEncryptionService
from src.core.scheduling.schemas import (
    CalendarIntegrationResponse,
    OAuthCallbackRequest,
    SyncStatusResponse,
)
from src.core.governance.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scheduling/integrations",
    tags=["Scheduling Integrations"],
)

# -- Provider registry (singleton-ish, stateless) --------------------

_PROVIDERS: dict[str, BaseCalendarProvider] = {
    "google": GoogleCalendarProvider(),
    "outlook": OutlookCalendarProvider(),
}


def _get_encryption() -> TokenEncryptionService:
    return TokenEncryptionService()


def _get_repo(
    db: AsyncSession = Depends(get_db),
    enc: TokenEncryptionService = Depends(_get_encryption),
) -> CalendarIntegrationRepository:
    return CalendarIntegrationRepository(db, enc)


def _get_sync_service(
    db: AsyncSession = Depends(get_db),
    repo: CalendarIntegrationRepository = Depends(_get_repo),
) -> CalendarSyncService:
    return CalendarSyncService(
        db=db,
        providers=_PROVIDERS,
        integration_repo=repo,
    )


# -- Endpoints --------------------------------------------------------


@router.get(
    "",
    response_model=list[CalendarIntegrationResponse],
    summary="List calendar integrations for current user",
)
async def list_integrations(
    current_user: UserResponse = Depends(get_current_user),
    repo: CalendarIntegrationRepository = Depends(_get_repo),
) -> list[CalendarIntegrationResponse]:
    integrations = await repo.list_by_user(
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
    )
    return [CalendarIntegrationResponse.model_validate(i) for i in integrations]


@router.post(
    "/connect/{provider}",
    response_model=CalendarIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Complete OAuth callback and store tokens",
)
@limiter.limit("5/minute")  # Rate limit: 5 connections per minute per IP
async def connect_provider(
    request: Request,  # Required by slowapi
    response: Response,  # Required by slowapi (X-RateLimit-* header injection)
    provider: str,
    body: OAuthCallbackRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    repo: CalendarIntegrationRepository = Depends(_get_repo),
) -> CalendarIntegrationResponse:
    if provider not in _PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {provider}",
        )

    prov = _PROVIDERS[provider]
    try:
        tokens = await prov.exchange_code(code=body.code, redirect_uri=body.redirect_uri)
    except OAuthError as e:
        logger.warning(f"OAuth error for {provider}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )
    except RateLimitError as e:
        logger.warning(f"Rate limit hit for {provider}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )
    except CalendarIntegrationError as e:
        logger.error(f"Integration error for {provider}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider error: {e.message}",
        )

    # Upsert -- if the user already connected this provider, update
    existing = await repo.get_any_by_user_provider(
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
        provider=provider,
    )

    if existing:
        if existing.is_deleted:
            integration = await repo.restore_and_update(
                existing,
                provider_account_id=tokens.account_id or "",
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_expires_at=tokens.expires_at,
                token_scope=tokens.scope,
            )
        else:
            integration = await repo.update_tokens(
                existing,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_expires_at=tokens.expires_at,
            )
    else:
        integration = await repo.create(
            tenant_id=current_user.tenant_id,
            user_id=str(current_user.id),
            provider=provider,
            provider_account_id=tokens.account_id or "",
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_expires_at=tokens.expires_at,
            token_scope=tokens.scope,
        )

    await db.commit()

    await AuditService.log_event(
        db=db,
        event_type="CALENDAR_CONNECTED",
        severity=ThreatLevel.MEDIUM,
        source_ip="internal",
        endpoint=f"/api/v1/scheduling/integrations/connect/{provider}",
        description=f"Calendar connected: {provider}",
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="CREATE",
        resource=f"calendar_integration:{integration.id}",
        metadata={"provider": provider},
    )

    return CalendarIntegrationResponse.model_validate(integration)


@router.delete(
    "/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect a calendar integration",
    response_class=Response,
)
async def disconnect_integration(
    integration_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    repo: CalendarIntegrationRepository = Depends(_get_repo),
) -> None:
    deleted = await repo.soft_delete(integration_id, current_user.tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    await db.commit()

    await AuditService.log_event(
        db=db,
        event_type="CALENDAR_DISCONNECTED",
        severity=ThreatLevel.MEDIUM,
        source_ip="internal",
        endpoint=f"/api/v1/scheduling/integrations/{integration_id}",
        description="Calendar integration disconnected",
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="DELETE",
        resource=f"calendar_integration:{integration_id}",
    )


@router.post(
    "/{integration_id}/sync",
    response_model=SyncStatusResponse,
    summary="Trigger manual sync for an integration",
)
@limiter.limit("10/minute")  # Rate limit: 10 syncs per minute per IP
async def trigger_sync(
    request: Request,  # Required by slowapi
    response: Response,  # Required by slowapi (X-RateLimit-* header injection)
    integration_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    repo: CalendarIntegrationRepository = Depends(_get_repo),
    sync_svc: CalendarSyncService = Depends(_get_sync_service),
) -> SyncStatusResponse:
    integration = await repo.get_by_id(integration_id, current_user.tenant_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    if not integration.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is deactivated",
        )

    result = await sync_svc.sync_integration(integration)
    await db.commit()

    return SyncStatusResponse(
        integration_id=integration.id,
        provider=integration.provider,
        created=result.created,
        updated=result.updated,
        deleted=result.deleted,
        errors=result.errors,
        next_sync_token=result.next_sync_token,
    )
