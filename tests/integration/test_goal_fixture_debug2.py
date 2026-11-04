"""Debug test for integration fixtures"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest.mark.asyncio
async def test_with_postgres_engine(postgres_engine):
    """Test that we can use postgres_engine fixture."""
    from sqlalchemy import text

    async with postgres_engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        assert row[0] == 1


@pytest.mark.asyncio
async def test_with_postgres_session(postgres_session: AsyncSession):
    """Test that we can use postgres_session fixture."""
    from sqlalchemy import text

    result = await postgres_session.execute(text("SELECT 1 as test"))
    row = result.fetchone()
    assert row[0] == 1
