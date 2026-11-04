"""Debug postgres_engine fixture"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest.mark.asyncio
async def test_simple_engine(postgres_engine: AsyncEngine) -> None:
    """Test simple engine."""
    print("\n[TEST] Starting test...")
    async with postgres_engine.connect() as conn:
        result = await conn.execute(text("SELECT 2 as test"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 2
    print("[TEST] Test complete")
