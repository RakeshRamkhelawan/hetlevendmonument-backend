"""Test postgres_engine fixture only"""

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest.mark.asyncio
async def test_engine(postgres_engine):
    """Test that postgres_engine fixture works."""
    from sqlalchemy import text

    async with postgres_engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        assert row[0] == 1
