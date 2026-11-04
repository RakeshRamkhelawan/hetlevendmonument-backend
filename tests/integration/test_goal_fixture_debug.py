"""Debug test for integration fixtures"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


async def test_simple_in_integration(postgres_session: AsyncSession) -> None:
    """Test that we can run a simple test in the integration folder."""
    result = await postgres_session.execute(text("SELECT 1 as test"))
    row = result.fetchone()
    assert row is not None
    assert row[0] == 1
