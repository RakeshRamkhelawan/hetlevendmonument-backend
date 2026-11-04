"""
Authentication Service - Refactored Login Logic

Provides isolated authentication logic using the BaseService pattern.

Part of SC-1.2 implementation.
"""

from typing import Optional

from sqlalchemy.future import select

from src.core.auth.jwt_handler import verify_password
from src.core.base.service import BaseService
from src.core.models.rbac_models import User


class AuthenticationService(BaseService):
    """
    Service for user authentication.

    Inherits from BaseService to use dependency injection
    for database session access.
    """

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """
        Authenticate a user by email and password.

        Args:
            email: User's email address
            password: Plain text password to verify

        Returns:
            User object if authentication successful, None otherwise
        """
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        # Check if user is active
        if hasattr(user, "is_active") and not user.is_active:
            return None

        return user

    async def get_user_by_email(self, email: str) -> User | None:
        """
        Get user by email without password verification.

        Args:
            email: User's email address

        Returns:
            User object if found, None otherwise
        """
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
