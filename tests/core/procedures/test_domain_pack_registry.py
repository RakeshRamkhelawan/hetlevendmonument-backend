"""Tests for DomainPackRegistry."""

from unittest.mock import AsyncMock

import pytest

from src.core.procedures.domain_pack_registry import DomainPackRegistry


@pytest.mark.asyncio
async def test_get_active_packs_returns_list():
    """Registry returns a list (may be empty)."""
    mock_db = AsyncMock()
    registry = DomainPackRegistry(db_manager=mock_db)

    packs = await registry.get_active_packs(tenant_id=1)

    assert isinstance(packs, list)
