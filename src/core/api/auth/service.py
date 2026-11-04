"""
Unified Auth Service.
Acts as a facade/wrapper around existing auth_service and oauth2_service
to provide a cleaner interface for the unified router.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import AuthService, UserCreate, UserResponse
from src.core.auth.oauth2_service import OAuth2Service


class UnifiedAuthService:
    def __init__(self) -> None:
        # We reuse the existing implementation for now to minimize risk
        # In Phase 2, we can refactor the implementations into this class
        self.auth_service = AuthService()
        self.oauth2_service = OAuth2Service()

    async def register_user(
        self, db: AsyncSession, user_data: UserCreate, client_ip: str, tenant_id: int
    ) -> UserResponse | None:
        """Facade zonder levende aanroeper (gemeten 2026-09-11 met git grep).

        Het type is hier bewust GEEN `Any` meer: met `Any` kon een toekomstige aanroeper
        een willekeurig object met een `role_name` uit een request-body doorgeven en
        daarmee ADR-036 OP-184 opnieuw openzetten, zonder dat mypy iets zei. Nu is het
        expliciet het INTERNE model, dat je alleen server-side hoort te bouwen.
        """
        return await self.auth_service.create_user(
            db,
            user_data,
            client_ip,
            tenant_id=tenant_id,
            # Deze facade IS het registratiepad -- de naam zegt het. De herkomst hoort
            # daarom hier vast te staan en niet in `create_user` (ADR-036 OP-235a).
            request_path="/api/v1/auth/register",
            event_type="REGISTRATION_FAILED",
        )

    async def login_user(self, db: AsyncSession, email: str, password: str, client_ip: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        return await self.auth_service.authenticate_user(db, email, password, client_ip)

    async def create_tokens(self, user: Any, scopes: list[str]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return await self.oauth2_service.create_tokens(
            user_id=user.id,
            email=user.email,
            role_ids=[r.id for r in user.roles] if user.roles else [],
            scopes=scopes,
            tenant_id=user.tenant_id,
        )


# Singleton instance
unified_auth_service = UnifiedAuthService()
