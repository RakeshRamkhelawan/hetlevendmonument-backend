"""Unit tests for scripts/seed_hr_acceptance_data.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_SPEC = importlib.util.spec_from_file_location(
    "_seed_hr_acceptance_data_under_test",
    Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "seed_hr_acceptance_data.py",
)
assert _SPEC and _SPEC.loader
_seed_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_seed_module)
seed_hr_acceptance_data = _seed_module.seed_hr_acceptance_data

from src.core.database.database import Base


@pytest.mark.unit
@pytest.mark.asyncio
async def test_seed_hr_acceptance_data_creates_records_and_is_idempotent() -> None:
    """Verify that seed_hr_acceptance_data creates all necessary records and can be re-run safely."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # First run
    async with session_factory() as session:
        result1 = await seed_hr_acceptance_data(session, tenant_id=1)
        assert result1["tenant_id"] == 1
        assert result1["role_id"] is not None
        assert result1["user_id"] is not None
        assert result1["skill_id"] is not None
        assert result1["required_level"] == 4
        assert result1["employee_level"] == 2
        assert result1["training_id"] is not None

    # Second run (idempotent verification)
    async with session_factory() as session:
        result2 = await seed_hr_acceptance_data(session, tenant_id=1)
        assert result2 == result1

    await engine.dispose()
