"""
Unit Tests for AccountLockout Model

Verifies:
1. Basic CRUD operations for AccountLockout
2. Cascade delete behavior when user is deleted

Part of SA-1.1 implementation.
"""

from typing import Any, Dict

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.auth.models.account_lockout import AccountLockout
from src.core.models.rbac_models import User


@pytest.mark.asyncio
async def test_create_lockout_entry(db_session: AsyncSession, test_user: Dict[str, Any]):
    """Verify basic CRUD operations for AccountLockout"""
    # 1. Create - test_user is a dict with 'id' key
    lockout = AccountLockout(user_id=test_user["id"], failed_attempts=1, ip_address="127.0.0.1")
    db_session.add(lockout)
    await db_session.commit()

    # 2. Read
    result = await db_session.execute(
        select(AccountLockout).where(AccountLockout.user_id == test_user["id"])
    )
    fetched = result.scalar_one()

    assert fetched.failed_attempts == 1
    assert fetched.locked_until is None
    assert fetched.last_attempt_at is not None


@pytest.mark.asyncio
async def test_cascade_delete(db_session: AsyncSession, test_user: Dict[str, Any]):
    """Verify deleting a user also deletes their lockout records

    NOTE: This test is skipped in SQLite test mode because CASCADE delete
    requires PRAGMA foreign_keys=ON. The model correctly defines ondelete='CASCADE'
    which works in PostgreSQL production.
    """
    from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

    # Skip if using SQLite (CASCADE requires PRAGMA foreign_keys=ON)
    # Check the dialect of the session's bind
    dialect_name = db_session.bind.dialect.name if db_session.bind else ""
    if dialect_name == "sqlite":
        pytest.skip("CASCADE delete requires PostgreSQL - skipping in SQLite mode")

    # Create lockout entry
    lockout = AccountLockout(user_id=test_user["id"])
    db_session.add(lockout)
    await db_session.commit()

    # Store lockout id for verification
    lockout_id = lockout.id

    # Fetch the actual User object for delete
    user_result = await db_session.execute(select(User).where(User.id == test_user["id"]))
    user = user_result.scalar_one()

    # Delete User
    await db_session.delete(user)
    await db_session.commit()

    # Verify Lockout is gone (CASCADE delete)
    result = await db_session.execute(select(AccountLockout).where(AccountLockout.id == lockout_id))
    assert result.scalar_one_or_none() is None
