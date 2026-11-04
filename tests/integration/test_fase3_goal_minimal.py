"""Fase 3 Minimal Integration Test - Just test the database connection"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


async def test_database_connection(postgres_session: AsyncSession) -> None:
    """Test that we can connect to the database."""
    result = await postgres_session.execute(text("SELECT 1 as test"))
    row = result.fetchone()
    assert row is not None
    assert row[0] == 1


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Schema initialization missing 'goals' table (ADR-026 migration pending)")
async def test_goals_table_exists(postgres_session: AsyncSession) -> None:
    """Test that the goals table exists.

    De fixture-parameter ontbrak tot 2026-08-01, waardoor deze test faalde op een
    NameError in plaats van op de ontbrekende tabel. De xfail dekte dat af, dus de test
    "slaagde" jarenlang om de verkeerde reden. Nu meet hij wat de reden beweert -- en
    slaat hij om naar XPASS zodra de goals-migratie is gedraaid.
    """
    result = await postgres_session.execute(text("SELECT COUNT(*) FROM goals"))
    row = result.fetchone()
    assert row is not None
    assert row[0] >= 0  # Table exists, may be empty
