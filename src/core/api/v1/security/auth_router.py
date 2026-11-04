"""Security auth router -- POST /auth/login (deprecated) (ADR-033 Laag 1)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.production_logging import SafeLogger

from .dependencies import SecurityLevel, ThreatLevel, get_db, get_security_manager

logger = SafeLogger(__name__)

auth_router = APIRouter()


class LoginRequest(BaseModel):
    """Login request model."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    security_level: str


# DEPRECATED: This login endpoint is deprecated.
# Use /api/v1/auth/login (auth/router.py) instead.
# That endpoint is OAuth2 compliant (form-urlencoded with 'username' field).
# This endpoint remains for backward compatibility but should not be used for new code.
@auth_router.post("/auth/login", response_model=TokenResponse, deprecated=True)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    DEPRECATED: Use /api/v1/auth/login instead.

    Authenticate user and return JWT token.
    Public endpoint (no RBAC required for login).
    """
    from passlib.context import CryptContext
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.models.rbac_models import User

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    try:
        if not request.username or not request.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username and password are required",
            )

        client_ip = http_request.client.host if http_request.client else "unknown"
        security_manager = get_security_manager()

        result = await db.execute(
            select(User).options(selectinload(User.roles)).where(User.email == request.username)
        )
        user = result.scalar_one_or_none()

        if not user or not pwd_context.verify(request.password, user.hashed_password):
            security_manager._log_security_event(
                "login_failed",
                ThreatLevel.MEDIUM,
                client_ip,
                request.username,
                "/auth/login",
                "Failed login - invalid credentials for user: %s" % request.username,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        user_id = "user_%s" % user.email
        security_level = SecurityLevel.AUTHORIZED

        primary_role = user.roles[0] if user.roles else None
        if primary_role and primary_role.name == "admin":
            security_level = SecurityLevel.ADMIN

        token = security_manager.generate_token(user_id, security_level)

        security_manager._log_security_event(
            "login_successful",
            ThreatLevel.LOW,
            client_ip,
            user_id,
            "/auth/login",
            "Successful login for user: %s" % user_id,
        )

        logger.info("User %s successfully authenticated from %s", user_id, client_ip)

        return TokenResponse(
            access_token=token,
            expires_in=24 * 3600,
            security_level=security_level.value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error",
        )
