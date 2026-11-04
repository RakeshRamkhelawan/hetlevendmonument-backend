"""
Security test fixtures for Co-Pilot Council.

Provides postgres_session alias as db_session for security regression tests.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def db_session(postgres_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Alias postgres_session for security tests requiring PostgreSQL."""
    yield postgres_session
