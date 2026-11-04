"""Unit tests for src/core/database/vacuum_manager.py security guards."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.core.database.vacuum_manager import VacuumManager


@pytest.mark.unit
def test_vacuum_table_rejects_invalid_table_name() -> None:
    """Table names outside [schema.]identifier pattern must be rejected without DB access."""
    manager = VacuumManager("postgresql+asyncpg://user:pass@localhost/db")
    result = asyncio.run(manager.vacuum_table("public.users; DROP TABLE users"))
    assert result["status"] == "error"
    assert result["error"] == "invalid table name"


@pytest.mark.unit
async def test_vacuum_all_tables_preserves_schema_prefix() -> None:
    """vacuum_all_tables must pass the full schema.table name to vacuum_table."""

    @dataclass
    class FakeStat:
        table_name: str
        vacuum_needed: bool = True

    manager = VacuumManager("postgresql+asyncpg://user:pass@localhost/db")
    stats = [FakeStat("public.users"), FakeStat("custom.events")]

    with patch.object(manager, "get_table_stats", new=AsyncMock(return_value=stats)):
        with patch.object(manager, "vacuum_table", new=AsyncMock(return_value={"status": "success"})) as mock_vacuum:
            await manager.vacuum_all_tables()

    called_tables = [call.args[0] for call in mock_vacuum.call_args_list]
    assert "public.users" in called_tables
    assert "custom.events" in called_tables
    assert "users" not in called_tables
    assert "events" not in called_tables
