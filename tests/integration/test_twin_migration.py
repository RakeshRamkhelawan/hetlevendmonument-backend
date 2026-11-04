"""Integration test: verify digital twin tables exist after migration."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
@pytest.mark.integration
async def test_digital_twin_tables_exist(db_session: AsyncSession) -> None:
    """All 4 digital twin tables must exist in the database."""
    expected_tables = [
        "user_behavior_observations",
        "user_cognitive_profiles",
        "user_twin_consent",
        "focus_builder_accepted_workflows",
    ]

    for table_name in expected_tables:
        result = await db_session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table_name},
        )
        assert result.scalar_one_or_none() is not None, f"Table {table_name} does not exist"
