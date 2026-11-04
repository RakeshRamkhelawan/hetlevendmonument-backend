"""Fase 3 Session Test - Test postgres_session fixture"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest.mark.asyncio
async def test_postgres_session(postgres_session: AsyncSession):
    """Test that postgres_session fixture works."""
    from sqlalchemy import text

    result = await postgres_session.execute(text("SELECT 1 as test"))
    row = result.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_postgres_session_goals(postgres_session: AsyncSession):
    """Test that we can query goals table with postgres_session."""
    from sqlalchemy import text

    result = await postgres_session.execute(text("SELECT COUNT(*) FROM goals"))
    row = result.fetchone()
    assert row[0] >= 0
