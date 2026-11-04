# orphan:exempt reason: management endpoints exceed 200r due to 4 routes with full validation
"""Security management router -- GET /rate-limits, GET /blocks, POST /block-ip, /unblock-ip, /cleanup (ADR-033 Laag 1)."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.shared.production_logging import SafeLogger

from .dependencies import (
    OAuth2Scope,
    UserResponse,
    ThreatLevel,
    get_current_user,
    get_ip_reputation,
    get_security_manager,
    require_admin,
    require_scopes,
)

logger = SafeLogger(__name__)

management_router = APIRouter()


class RateLimitStatus(BaseModel):
    """Rate limit status model."""

    endpoint: str
    current_requests_per_minute: int
    limit_per_minute: int
    current_requests_per_hour: int
    limit_per_hour: int
    status: str


class BlockIPRequest(BaseModel):
    """Block IP request."""

    ip_address: str = Field(..., description="IP address to block")
    reason: str = Field(default="Manual block", description="Reason for blocking")


class UnblockIPRequest(BaseModel):
    """Unblock IP request -- body to prevent IP from appearing in access logs."""

    ip_address: str = Field(..., description="IP address to unblock")


@management_router.get("/rate-limits", response_model=list[RateLimitStatus])
async def get_rate_limit_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> list[RateLimitStatus]:
    """
    Get current rate limit status.
    Requires: ADMIN permission
    """
    try:
        logger.info("User %s requesting rate limit status", current_user.id)

        security_manager = get_security_manager()
        status_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for rule in security_manager.rate_limit_rules:
            datetime.now(timezone.utc)

            # TODO(SP-VOLGENDE): hardcoded mock-waarden vervangen door echte metrics
            # uit de rate-limiter service (Redis counters per endpoint per IP)
            minute_count = 45
            hour_count = 320

            if minute_count >= rule.requests_per_minute or hour_count >= rule.requests_per_hour:
                status_str = "exceeded"
            elif minute_count >= rule.requests_per_minute * 0.8:
                status_str = "warning"
            else:
                status_str = "ok"

            status_list.append(
                RateLimitStatus(
                    endpoint=rule.endpoint_pattern,
                    current_requests_per_minute=minute_count,
                    limit_per_minute=rule.requests_per_minute,
                    current_requests_per_hour=hour_count,
                    limit_per_hour=rule.requests_per_hour,
                    status=status_str,
                )
            )

        return status_list

    except Exception as e:
        logger.error("Failed to get rate limit status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rate limit status",
        )


#: Blokkeren en deblokkeren vraagt de beheerdersrol als dependency (plan nazorg, punt d), naast
#: de bestaande scope. De scope alleen is geen rol (zie
#: tests/architecture/test_admin_routes_hebben_een_rolcontrole.py).
_ALLEEN_BEHEERDER = [Depends(require_admin)]


class IpBlockEntry(BaseModel):
    """Een actieve blokkade."""

    ip_address: str
    reason: str
    seconds_left: int


def _geldig_ip(waarde: str) -> str:
    import ipaddress

    try:
        return str(ipaddress.ip_address(waarde.strip()))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid IP address")


@management_router.get(
    "/blocks", response_model=list[IpBlockEntry], dependencies=_ALLEEN_BEHEERDER
)
async def list_ip_blocks(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> list[IpBlockEntry]:
    """Actieve IP-blokkades met de resterende tijd (IP-reputatie in Redis)."""
    try:
        blokkades = await get_ip_reputation().list_blocks()
    except Exception as e:
        logger.error("Failed to list IP blocks: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Block store unavailable"
        )
    return [
        IpBlockEntry(ip_address=b.ip, reason=b.reason, seconds_left=b.seconds_left)
        for b in blokkades
    ]


@management_router.post("/block-ip", response_model=dict[str, str], dependencies=_ALLEEN_BEHEERDER)
async def block_ip(
    request: BlockIPRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, str]:
    """Blokkeer een IP-adres tijdelijk (de basisduur van de IP-reputatie)."""
    ip_address = _geldig_ip(request.ip_address)
    try:
        duur = await get_ip_reputation().block(ip_address, "manual: %s" % request.reason)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="IP address is on the exempt list"
        )
    except Exception as e:
        logger.error("Failed to block IP: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Block store unavailable"
        )

    get_security_manager()._log_security_event(
        "ip_blocked_manual",
        ThreatLevel.HIGH,
        "admin_action",
        str(current_user.id),
        "/security/block-ip",
        "IP %s blocked for %s s: %s" % (ip_address, duur, request.reason),
    )
    return {
        "message": "IP address %s has been blocked" % ip_address,
        "reason": request.reason,
        "seconds": str(duur),
    }


@management_router.post(
    "/unblock-ip", response_model=dict[str, str], dependencies=_ALLEEN_BEHEERDER
)
async def unblock_ip(
    request: UnblockIPRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, str]:
    """Hef de blokkade van een IP-adres op, voor elke worker en replica tegelijk."""
    ip_address = _geldig_ip(request.ip_address)
    try:
        was_geblokkeerd = await get_ip_reputation().unblock(ip_address)
    except Exception as e:
        logger.error("Failed to unblock IP: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Block store unavailable"
        )
    if not was_geblokkeerd:
        return {"message": "IP address %s was not blocked" % ip_address}

    get_security_manager()._log_security_event(
        "ip_unblocked",
        ThreatLevel.LOW,
        "admin_action",
        str(current_user.id),
        "/security/unblock-ip",
        "IP %s unblocked" % ip_address,
    )
    return {"message": "IP address %s has been unblocked" % ip_address}


@management_router.post("/cleanup", response_model=dict[str, str])
async def cleanup_security_data(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, str]:
    """
    Cleanup old security data (events older than 30 days).
    Requires: ADMIN permission
    """
    from datetime import timedelta

    try:
        logger.info("User %s initiating security data cleanup", current_user.id)

        security_manager = get_security_manager()

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        original_count = len(security_manager.security_events)

        security_manager.security_events = [
            e for e in security_manager.security_events if e.timestamp > cutoff
        ]

        removed_count = original_count - len(security_manager.security_events)

        logger.info(
            "Security cleanup completed by user %s: removed %s events",
            current_user.id,
            removed_count,
        )

        return {
            "message": "Security data cleanup completed successfully",
            "events_removed": str(removed_count),
        }

    except Exception as e:
        logger.error("Security cleanup failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security cleanup failed",
        )
