"""Tests for HITL Router."""
import pytest
from unittest.mock import MagicMock
from src.core.agents.hitl_router import resolve_hitl_recipient

@pytest.mark.asyncio
async def test_resolve_hitl_uses_department_user_id() -> None:
    config = MagicMock()
    config.department_user_id = 42
    config.tenant_id = 1
    decision = await resolve_hitl_recipient(config)
    assert decision.recipient_user_id == 42
    assert decision.fallback is False

@pytest.mark.asyncio
async def test_resolve_hitl_falls_back_to_tenant_admin() -> None:
    config = MagicMock()
    config.department_user_id = None
    config.tenant_id = 1
    decision = await resolve_hitl_recipient(config)
    assert decision.recipient_user_id == 1  # tenant_id used as fallback admin
    assert decision.fallback is True
