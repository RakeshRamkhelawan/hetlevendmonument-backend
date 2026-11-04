"""
Registration Service - Refactored User Creation Logic

Provides isolated registration logic using the BaseService pattern.

Part of SC-1.3 implementation.
"""

from typing import Optional

from sqlalchemy.future import select

from src.core.auth.jwt_handler import get_password_hash
from src.core.auth.password_policy import validate_password_detailed
from src.core.base.service import BaseService
from src.core.models.rbac_models import User


class RegistrationService(BaseService):
    """
    Service for user registration.

    Inherits from BaseService to use dependency injection
    for database session access.
    """

    async def create_user(
        self, email: str, password: str, tenant_id: int = 1, is_active: bool = True
    ) -> User | None:
        """
        Create a new user with hashed password.

        Args:
            email: User's email address
            password: Plain text password (will be hashed)
            tenant_id: Tenant ID for multi-tenant support
            is_active: Whether user is active (default: True)

        Returns:
            User object if created successfully, None if email exists
        """
        # Check if user already exists
        existing = await self._get_user_by_email(email)
        if existing:
            return None

        # Validate password against policy (SA-3.1)
        is_valid, errors = validate_password_detailed(password)
        if not is_valid:
            raise ValueError(f"Password policy violation: {'; '.join(errors)}")

        # Create new user with hashed password
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            tenant_id=tenant_id,
            is_active=is_active,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def _get_user_by_email(self, email: str) -> User | None:
        """Check if user with email exists."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
