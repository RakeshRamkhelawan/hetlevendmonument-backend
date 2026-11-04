"""
tests/fixtures/auth.py - Authentication Fixtures

Provides test users, tokens, and authentication-related fixtures.
Uses factory pattern for creating unique test data per test.

KEY PRINCIPLES:
1. Unique IDs per test (forward-only pattern)
2. No hardcoded user IDs
3. Easy to create users with specific roles
4. JWT tokens for authenticated requests

Created: 2025-12-06
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class FixtureData(dict):
    """Dict-like fixture payload that also supports attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


# ============================================================================
# USER FACTORY
# ============================================================================


class UserFactory:
    """Factory for creating test users with unique IDs."""

    def __init__(self, db_session: AsyncSession):
        self._session = db_session

    async def create_user(
        self,
        tenant_id: int,
        email: Optional[str] = None,
        role_name: str = "user",
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a test user with unique identifiers and proper RBAC roles.

        Args:
            tenant_id: Tenant this user belongs to
            email: User email (auto-generated if not provided)
            role_name: Role to assign (user, admin, etc.)
            is_active: Whether user is active

        Returns:
            Dict with user details including id, email, tenant_id
        """
        from sqlalchemy import insert, select

        from src.core.models.rbac_models import Role, RolePermission, User, user_roles

        unique_id = uuid.uuid4().hex[:8]
        user_email = email or f"test-{unique_id}@example.com"

        # 1. Create User with bcrypt-hashed password for "password"
        # This hash was generated with: passlib.context.CryptContext.hash('password')
        # and will authenticate correctly when user logs in with password="password"
        user = User(
            email=user_email,
            hashed_password="$2b$12$9uHPFyLPJcBD/WCRNXgueetgH6HI69HW3AWR1RtIKfwM7qE1v3B6C",
            tenant_id=tenant_id,
            is_active=is_active,
        )
        self._session.add(user)
        await self._session.flush()  # flush to get user.id

        # 2. Ensure Role exists for this tenant
        role_result = await self._session.execute(
            select(Role).where(Role.name == role_name, Role.tenant_id == tenant_id)
        )
        role = role_result.scalar_one_or_none()

        if not role:
            # Create role if missing
            role = Role(
                tenant_id=tenant_id,
                name=role_name,
                description=f"Test {role_name} role",
                is_active=True,
            )
            self._session.add(role)
            await self._session.flush()

            # Add basic permissions based on role name
            resource = "*" if role_name == "admin" else "dashboard"
            action = "*" if role_name == "admin" else "read"

            perm = RolePermission(
                role_id=role.id,
                tenant_id=tenant_id,
                resource=resource,
                action="*",  # Force wildcard action for simplicity in tests
            )
            self._session.add(perm)

        # 3. Assign Role to User
        # Check if assignment already exists
        existing = await self._session.execute(
            select(user_roles).where(
                user_roles.c.user_id == user.id, user_roles.c.role_id == role.id
            )
        )
        if not existing.scalar_one_or_none():
            await self._session.execute(
                user_roles.insert().values(user_id=user.id, role_id=role.id)
            )

        await self._session.commit()
        # No refresh needed: db_session uses expire_on_commit=False
        # user.id was populated during the earlier flush()

        return FixtureData(
            {
                "id": user.id,
                "email": user.email,
                "tenant_id": tenant_id,
                "is_active": is_active,
                "role": role_name,
            }
        )

    async def create_admin_user(self, tenant_id: int) -> Dict[str, Any]:
        """Create an admin user."""
        return await self.create_user(tenant_id, role_name="admin")


@pytest.fixture
def user_factory(db_session: AsyncSession) -> UserFactory:
    """Provide UserFactory instance for creating test users."""
    return UserFactory(db_session)


# ============================================================================
# TEST USER FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_tenant: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a standard test user.

    Depends on test_tenant fixture to ensure proper tenant association.
    """
    factory = UserFactory(db_session)
    return await factory.create_user(test_tenant["id"])


@pytest_asyncio.fixture
async def test_admin_user(db_session: AsyncSession, test_tenant: Dict[str, Any]) -> Dict[str, Any]:
    """Create an admin test user."""
    factory = UserFactory(db_session)
    return await factory.create_admin_user(test_tenant["id"])


# ============================================================================
# POSTGRESQL USER FIXTURES
# ============================================================================


@pytest.fixture
def postgres_user_factory(postgres_session: AsyncSession) -> UserFactory:
    """Provide UserFactory for PostgreSQL tests."""
    return UserFactory(postgres_session)


@pytest_asyncio.fixture
async def postgres_test_user(
    postgres_session: AsyncSession, postgres_test_tenant: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create a test user in PostgreSQL database.

    For production-like testing with real PostgreSQL.
    Password is 'password' (bcrypt hashed).
    """
    factory = UserFactory(postgres_session)
    return await factory.create_user(postgres_test_tenant["id"])


@pytest_asyncio.fixture
async def test_inactive_user(
    db_session: AsyncSession, test_tenant: Dict[str, Any]
) -> Dict[str, Any]:
    """Create an inactive test user."""
    factory = UserFactory(db_session)
    return await factory.create_user(test_tenant["id"], is_active=False)


# ============================================================================
# TOKEN FIXTURES
# ============================================================================


def create_test_token(
    user_id: int,
    tenant_id: int,
    email: str = "test@example.com",
    roles: list = None,
    scopes: list = None,
    expires_delta: timedelta = None,
) -> str:
    """
    Create a JWT token for testing.

    This creates a real JWT token that can be verified by the application.
    For tests that don't need real verification, use mock_token_data instead.
    """
    from src.core.auth.jwt_handler import jwt_handler

    token_data = {
        "sub": str(user_id),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "roles": roles or ["user"],
        "scopes": scopes or ["agents:write", "agents:read", "workflows:write", "workflows:read"],
    }

    # SecurityMiddleware compatibility: autonomous endpoints require admin level
    if roles and "admin" in roles:
        token_data["security_level"] = "admin"

    return jwt_handler.create_access_token(
        data=token_data,
        expires_delta=expires_delta or timedelta(hours=1),
    )


@pytest.fixture
def test_token(test_user: Dict[str, Any]) -> str:
    """Create a valid JWT token for test_user."""
    return create_test_token(
        user_id=test_user["id"],
        tenant_id=test_user["tenant_id"],
        email=test_user["email"],
    )


@pytest.fixture
def admin_token(test_admin_user: Dict[str, Any]) -> str:
    """Create a valid JWT token for admin user."""
    return create_test_token(
        user_id=test_admin_user["id"],
        tenant_id=test_admin_user["tenant_id"],
        email=test_admin_user["email"],
        roles=["admin"],
    )


@pytest.fixture
def expired_token(test_user: Dict[str, Any]) -> str:
    """Create an expired JWT token."""
    return create_test_token(
        user_id=test_user["id"],
        tenant_id=test_user["tenant_id"],
        expires_delta=timedelta(seconds=-1),  # Already expired
    )


# ============================================================================
# MOCK TOKEN DATA (for tests that don't need real JWT)
# ============================================================================


@pytest.fixture
def mock_token_data() -> Dict[str, Any]:
    """
    Mock token payload for tests that don't need real JWT verification.

    Use this with dependency overrides to bypass JWT validation.
    """
    return {
        "sub": "1",
        "user_id": 1,
        "tenant_id": 1,
        "email": "mock@example.com",
        "roles": ["user"],
        "exp": (datetime.utcnow() + timedelta(hours=1)).timestamp(),
    }


@pytest.fixture
def mock_admin_token_data() -> Dict[str, Any]:
    """Mock admin token payload."""
    return {
        "sub": "1",
        "user_id": 1,
        "tenant_id": 1,
        "email": "admin@example.com",
        "roles": ["admin"],
        "exp": (datetime.utcnow() + timedelta(hours=1)).timestamp(),
    }


# ============================================================================
# AUTH DEPENDENCY OVERRIDES
# ============================================================================


@pytest.fixture
def auth_override(mock_token_data: Dict[str, Any]):
    """
    Create auth dependency override for tests.

    Usage:
        def test_endpoint(app, auth_override):
            app.dependency_overrides[get_current_user] = auth_override
    """

    async def override_get_current_user():
        return mock_token_data

    return override_get_current_user


@pytest.fixture
def admin_auth_override(mock_admin_token_data: Dict[str, Any]):
    """Create admin auth dependency override."""

    async def override_get_current_user():
        return mock_admin_token_data

    return override_get_current_user


@pytest.fixture
def no_auth_override():
    """
    Create override that simulates no authentication.

    Use for testing public endpoints or auth failure scenarios.
    """

    async def override_get_current_user():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    return override_get_current_user


# ============================================================================
# OAUTH2 SCHEME MOCKS
# ============================================================================


@pytest.fixture
def mock_oauth2_scheme():
    """
    Mock OAuth2 scheme for bypassing token extraction.

    Returns a valid-looking token string.
    """

    async def override_oauth2():
        return "mock_bearer_token"

    return override_oauth2


@pytest.fixture
def mock_oauth2_scheme_none():
    """Mock OAuth2 scheme that returns None (no token)."""

    async def override_oauth2():
        return None

    return override_oauth2


def mock_sessie_zonder_intrekking(
    mock_session: AsyncMock, gebruikersresultaat: MagicMock
) -> AsyncMock:
    """Laat de blacklistquery "niet ingetrokken" teruggeven, en de rest het echte resultaat.

    Sinds ADR-036 OP-260 (2026-09-19) raadplegen BEIDE authenticatie-ingangen de blacklist
    via `_weiger_als_ingetrokken`. Een test die `session.execute` onvoorwaardelijk een
    gebruiker laat teruggeven, laat daarmee ook de blacklistquery een rij opleveren -- en
    dan concludeert de code "ingetrokken" en geeft 401. Dat is een 401 die niets met het
    testgeval te maken heeft.

    Deze helper routeert op de tabel in de query in plaats van op de volgorde van aanroepen,
    zodat hij blijft kloppen als er een query bijkomt of er een verdwijnt.

    GRENS, benoemd door de Gate 2-quality-reviewer: hij geeft "niet ingetrokken" terug voor
    ELKE query op die tabel. Komt er ooit een tweede, semantisch andere query op
    `token_blacklist` op dit pad -- een lookup die juist wel een rij MOET vinden -- dan nemen
    de tests die deze helper gebruiken stilzwijgend de verkeerde tak. Vandaag is er maar een.
    """
    from src.core.auth.oauth2_service import TokenBlacklist

    leeg = MagicMock()
    leeg.scalar_one_or_none.return_value = None
    # Uit het model, niet als letterlijke string: hernoemt iemand de tabel, dan verhuist
    # deze router mee in plaats van stil de gebruikersrij op de blacklistvraag te zetten.
    tabel = TokenBlacklist.__tablename__.lower()

    async def _execute(statement: object, *args: object, **kwargs: object) -> MagicMock:
        if tabel in str(statement).lower():
            return leeg
        return gebruikersresultaat

    mock_session.execute.side_effect = _execute
    return mock_session
