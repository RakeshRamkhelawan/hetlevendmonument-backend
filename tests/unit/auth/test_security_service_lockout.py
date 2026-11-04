"""
Unit tests for SecurityService (security_service.py).

Covers: is_account_locked, register_failed_attempt, reset_attempts.
Uses an in-memory SQLite database for fast, isolated testing.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.auth.models.account_lockout import AccountLockout
from src.core.auth.security_service import SecurityService
from src.core.database.database import Base


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def security_service(async_session):
    return SecurityService(db=async_session)


class TestIsAccountLocked:
    """Tests for is_account_locked()."""

    @pytest.mark.asyncio
    async def test_unlocked_when_no_record(self, security_service):
        result = await security_service.is_account_locked(user_id=999)
        assert result is False

    @pytest.mark.asyncio
    async def test_unlocked_when_locked_until_is_none(self, security_service, async_session):
        lockout = AccountLockout(user_id=42, failed_attempts=3, locked_until=None)
        async_session.add(lockout)
        await async_session.commit()

        result = await security_service.is_account_locked(user_id=42)
        assert result is False

    @pytest.mark.asyncio
    async def test_locked_when_lock_is_active(self, security_service, async_session):
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        lockout = AccountLockout(user_id=42, failed_attempts=5, locked_until=future_time)
        async_session.add(lockout)
        await async_session.commit()

        result = await security_service.is_account_locked(user_id=42)
        assert result is True

    @pytest.mark.asyncio
    async def test_unlocked_when_lock_expired(self, security_service, async_session):
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        lockout = AccountLockout(user_id=42, failed_attempts=5, locked_until=past_time)
        async_session.add(lockout)
        await async_session.commit()

        result = await security_service.is_account_locked(user_id=42)
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_lock_resets_counters(self, security_service, async_session):
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        lockout = AccountLockout(user_id=42, failed_attempts=5, locked_until=past_time)
        async_session.add(lockout)
        await async_session.commit()

        await security_service.is_account_locked(user_id=42)

        # Refresh and check counters were reset
        await async_session.refresh(lockout)
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None

    @pytest.mark.asyncio
    async def test_handles_naive_datetime(self, security_service, async_session):
        """Ensure naive datetimes (without tzinfo) are handled correctly."""
        future_naive = datetime.utcnow() + timedelta(minutes=10)
        lockout = AccountLockout(user_id=42, failed_attempts=5, locked_until=future_naive)
        async_session.add(lockout)
        await async_session.commit()

        result = await security_service.is_account_locked(user_id=42)
        assert result is True


class TestRegisterFailedAttempt:
    """Tests for register_failed_attempt()."""

    @pytest.mark.asyncio
    async def test_creates_new_lockout_record(self, security_service, async_session):
        await security_service.register_failed_attempt(user_id=100, ip_address="1.2.3.4")

        from sqlalchemy import select

        result = await async_session.execute(
            select(AccountLockout).where(AccountLockout.user_id == 100)
        )
        lockout = result.scalars().first()

        assert lockout is not None
        assert lockout.failed_attempts == 1
        assert lockout.ip_address == "1.2.3.4"
        assert lockout.locked_until is None  # Not locked yet

    @pytest.mark.asyncio
    async def test_increments_existing_record(self, security_service, async_session):
        lockout = AccountLockout(user_id=100, failed_attempts=2)
        async_session.add(lockout)
        await async_session.commit()

        await security_service.register_failed_attempt(user_id=100, ip_address="1.2.3.4")

        await async_session.refresh(lockout)
        assert lockout.failed_attempts == 3
        assert lockout.locked_until is None

    @pytest.mark.asyncio
    async def test_locks_account_at_threshold(self, security_service, async_session):
        lockout = AccountLockout(user_id=100, failed_attempts=4)
        async_session.add(lockout)
        await async_session.commit()

        # 5th attempt triggers lockout
        await security_service.register_failed_attempt(user_id=100)

        await async_session.refresh(lockout)
        assert lockout.failed_attempts == 5
        assert lockout.locked_until is not None
        # Lock should be ~15 minutes in the future
        # Handle both naive and aware datetimes from SQLite
        lock_time = lockout.locked_until
        now = datetime.now(timezone.utc)
        if lock_time.tzinfo is None:
            lock_time = lock_time.replace(tzinfo=timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        delta = lock_time - now
        assert timedelta(minutes=14) < delta < timedelta(minutes=16)

    @pytest.mark.asyncio
    async def test_locks_account_beyond_threshold(self, security_service, async_session):
        lockout = AccountLockout(user_id=100, failed_attempts=9)
        async_session.add(lockout)
        await async_session.commit()

        await security_service.register_failed_attempt(user_id=100)

        await async_session.refresh(lockout)
        assert lockout.failed_attempts == 10
        assert lockout.locked_until is not None

    @pytest.mark.asyncio
    async def test_updates_ip_address(self, security_service, async_session):
        lockout = AccountLockout(user_id=100, failed_attempts=1, ip_address="1.1.1.1")
        async_session.add(lockout)
        await async_session.commit()

        await security_service.register_failed_attempt(user_id=100, ip_address="2.2.2.2")

        await async_session.refresh(lockout)
        assert lockout.ip_address == "2.2.2.2"


class TestResetAttempts:
    """Tests for reset_attempts()."""

    @pytest.mark.asyncio
    async def test_resets_counters(self, security_service, async_session):
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        lockout = AccountLockout(user_id=100, failed_attempts=5, locked_until=future_time)
        async_session.add(lockout)
        await async_session.commit()

        await security_service.reset_attempts(user_id=100)

        await async_session.refresh(lockout)
        assert lockout.failed_attempts == 0
        assert lockout.locked_until is None

    @pytest.mark.asyncio
    async def test_noop_when_no_record(self, security_service):
        # Should not raise
        await security_service.reset_attempts(user_id=9999)

    @pytest.mark.asyncio
    async def test_full_lockout_cycle(self, security_service, async_session):
        """Integration: 5 fails -> lockout -> login success -> reset."""
        user_id = 200

        for _ in range(5):
            await security_service.register_failed_attempt(user_id=user_id, ip_address="1.2.3.4")

        assert await security_service.is_account_locked(user_id=user_id) is True

        await security_service.reset_attempts(user_id=user_id)
        assert await security_service.is_account_locked(user_id=user_id) is False
