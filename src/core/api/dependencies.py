"""
FastAPI Dependencies for Sanskriti Setu API
Database connections, authentication, and shared dependencies
"""

from datetime import timedelta
from typing import Any, cast
from collections.abc import AsyncGenerator, Generator, Mapping

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSession
from sqlalchemy.orm import Session

from src.core.api.user_helpers import get_user_id
from src.core.auth.api_deps import (
    controleer_resource_recht,
    get_current_user_dependency as get_current_user,
    is_admin,
    jwt_handler,
    JWTPayload,
    VerifiedJWTPayload,
    UserResponse,
)
from src.core.config.unified_config import config
from src.core.database.database import db_manager as db_manager, get_db as get_async_db_session

from src.core.governance.rate_limiter import consent_read_limit as consent_read_limit
from src.core.learning.services.tenant_admin_stats import get_twin_stats as get_twin_stats

__all__ = [
    "AsyncSession",
    "consent_read_limit",
    "controleer_resource_recht",
    "db_manager",
    "get_current_user",
    "get_db",
    "get_database",
    "get_twin_stats",
    "init_database",
    "security",
]

# Security
security = HTTPBearer(auto_error=False)

# Database setup
engine: Any | None = None  # TODO(TYPE): replace Any with concrete type
SessionLocal: Any | None = None  # TODO(TYPE): replace Any with concrete type


def init_database() -> None:
    """Initialize database connection (Synchronous - Legacy Support)"""
    global engine, SessionLocal

    if engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_config = config.get_database_config()
        db_url = db_config["url"]

        # Convert async URL to sync URL for legacy sync code
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "+psycopg2")

        engine = create_engine(
            db_url,
            pool_size=db_config["pool_size"],
            pool_pre_ping=True,
            echo=db_config["echo"],
        )

        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Direct alias to database.py's get_db -- avoids nested async generators
# that cause '_AsyncGeneratorContextManager' errors in FastAPI DI.
# See: https://github.com/fastapi/fastapi/issues/3205
get_db = get_async_db_session


def get_database() -> Generator[Session, None, None]:
    """DEPRECATED: Use get_db() instead for async sessions"""
    if SessionLocal is None:
        init_database()

    if SessionLocal is None:
        raise RuntimeError("Failed to initialize database session")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    expires_delta: timedelta | None = None,
) -> str:
    """Create JWT access token using production JWT handler."""
    return cast(str, jwt_handler.create_access_token(cast(JWTPayload, data), expires_delta))


async def token_mag_op_een_websocket(payload: Mapping[str, object]) -> bool:
    """Mag dit (geverifieerde) token op een WebSocket? Geen portaaltoken, account ingeschakeld.

    Een dunne doorverwijzing naar `src.core.auth.websocket_auth.token_mag_op_een_websocket` (late
    import: patchbaar in tests, en het DSM-fan-outbudget van core_api telt een rand minder).
    """
    from src.core.auth.websocket_auth import token_mag_op_een_websocket as controle

    return await controle(payload)


def verify_token(
    token: str,
) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
    """Verify JWT token using production JWT handler."""
    return cast(
        dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
        jwt_handler.verify_token(token),
    )


async def require_authenticated_user(
    current_user: UserResponse | None = Depends(get_current_user),
) -> UserResponse:
    """Require authenticated user with production validation.

    OP-11 (2026-07-31): dit deed `current_user.get("user_id")` terwijl
    get_current_user_dependency een UserResponse teruggeeft -- een Pydantic-model zonder
    `.get()`. Dat gooide een AttributeError, maar UITSLUITEND achter
    `config.is_production()`: lokaal en in staging werkte het, in productie niet. De
    vergelijking met "anonymous"/"dev_user" kon met een UserResponse bovendien nooit
    matchen (`id` is een int), dus de productie-check deed effectief niets behalve
    crashen. `get_user_id` is vorm-agnostisch (UserResponse, ORM-object of JWT-dict).
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Production mode: strict validation -- een niet-herleidbare of placeholder-identiteit
    # mag daar nooit door (fail closed).
    if config.is_production():
        resolved_user_id = get_user_id(current_user)
        if resolved_user_id is None or str(resolved_user_id) in {"anonymous", "dev_user"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid authentication required in production",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return current_user


async def require_admin_user(
    current_user: UserResponse = Depends(require_authenticated_user),
) -> UserResponse:
    """Require admin user.

    OP-11 (2026-07-31): dit deed `current_user.get("role") != "admin"` op een
    UserResponse. Dat is dubbel fout: het model heeft geen `.get()` (AttributeError ->
    500) en het heeft ook geen veld `role` -- wel `roles: list[str]`, `role_id` en
    `is_superuser`. De check kon dus nooit slagen. Deze dependency had op dat moment 0
    call-sites, dus er is geen endpoint door geraakt; hij is gerepareerd in plaats van
    verwijderd zodat een volgende aanroeper geen eigen variant hoeft te schrijven.

    Sinds ADR-036 OP-40 delegeert hij naar `is_admin`, de definitie voor beheer BINNEN een
    tenant. Tot dan accepteerde hij als enige van de zeven checks alleen `{admin}`. Let op: die
    zeven zijn niet alles -- checks die de TENANT-GRENS poorten zijn bewust smaller en staan in
    `KNOWN_UNCONSOLIDATED_ADMIN_CHECKS` in
    `tests/architecture/test_admin_checks_use_the_central_definition.py`.
    """
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )

    return current_user


# ---------------------------------------------------------------------------
# App-wide helpers -- moved here from endpoint files per ADR-033 Stap 0C
# ---------------------------------------------------------------------------


async def require_admin_role(
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    db: Any = Depends(get_async_db_session),  # TODO(TYPE): replace Any with concrete type
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Check if user has admin role -- delegeert naar `is_admin` (ADR-036 OP-40).

    Tot 2026-09-01 stond hier een eigen `role in ["admin", "system_admin"]`, exacte case en
    zonder superuser-bypass. Dat was een van de zeven eigen definities.
    """
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def get_current_tenant_id() -> int:
    """App-wide dependency: tenant id from request context (moved from search_endpoints)."""
    from src.core.middleware.tenant_context import require_tenant_id

    return require_tenant_id()
