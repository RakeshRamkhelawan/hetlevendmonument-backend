"""
Security Service - Account Lockout Logic

Provides brute-force protection by tracking failed login attempts
and implementing account lockout functionality.

Part of SA-1.3 implementation.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.auth.models.account_lockout import AccountLockout


class SecurityService:
    """Service for security-related operations including account lockout."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def is_account_locked(self, user_id: int) -> bool:
        """
        Checks if the user is currently locked out.
        If the lock has expired, it automatically clears the lock.

        Args:
            user_id: The ID of the user to check

        Returns:
            True if the account is currently locked, False otherwise
        """
        # Order by last_attempt_at DESC to get the most recent lockout record
        # Use first() instead of scalar_one_or_none() to handle duplicate records gracefully
        stmt = (
            select(AccountLockout)
            .where(AccountLockout.user_id == user_id)
            .order_by(AccountLockout.last_attempt_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        lockout = result.scalars().first()

        if not lockout:
            return False

        if lockout.locked_until:
            # Check if lock is still active (handle both naive and aware datetimes)
            lock_time = lockout.locked_until
            if lock_time.tzinfo is None:
                lock_time = lock_time.replace(tzinfo=timezone.utc)
            if lock_time > datetime.now(timezone.utc):
                return True
            else:
                # Lock expired - reset counters
                lockout.locked_until = None
                lockout.failed_attempts = 0
                await self.db.commit()
                return False

        return False

    async def register_failed_attempt(self, user_id: int, ip_address: str | None = None) -> None:
        """
        Increments failed attempts. Locks account if threshold reached.

        Args:
            user_id: The ID of the user
            ip_address: Optional client IP address for audit
        """
        from datetime import timedelta

        from loguru import logger

        # Order by last_attempt_at DESC to get the most recent lockout record
        # Use first() to handle potential duplicates gracefully
        stmt = (
            select(AccountLockout)
            .where(AccountLockout.user_id == user_id)
            .order_by(AccountLockout.last_attempt_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        lockout = result.scalars().first()

        logger.debug(
            f"[LOCKOUT DEBUG] user_id={user_id}, lockout found: {lockout is not None}, lockout_id: {lockout.id if lockout else 'N/A'}"
        )

        if not lockout:
            logger.warning(f"[LOCKOUT CREATE] Creating NEW lockout for user_id={user_id}")
            lockout = AccountLockout(user_id=user_id, ip_address=ip_address, failed_attempts=0)
            self.db.add(lockout)

        lockout.failed_attempts += 1
        lockout.last_attempt_at = datetime.now(timezone.utc)
        lockout.ip_address = ip_address  # Update IP

        # Check Threshold (Hardcoded 5 for now, move to config later)
        if lockout.failed_attempts >= 5:
            lockout.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)

        await self.db.commit()

    async def reset_attempts(self, user_id: int) -> None:
        """
        Clears failed attempts upon successful login.

        Args:
            user_id: The ID of the user
        """
        # Order by last_attempt_at DESC to get the most recent lockout record
        stmt = (
            select(AccountLockout)
            .where(AccountLockout.user_id == user_id)
            .order_by(AccountLockout.last_attempt_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        lockout = result.scalars().first()

        if lockout:
            lockout.failed_attempts = 0
            lockout.locked_until = None
            await self.db.commit()
