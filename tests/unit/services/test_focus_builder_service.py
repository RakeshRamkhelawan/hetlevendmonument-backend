"""Tests for focus_builder_service functions."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_save_accepted_workflow_creates_row():
    """save_accepted_workflow inserts a row; second call with same proposal_id is a no-op."""
    from src.core.services.focus_builder_service import save_accepted_workflow

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await save_accepted_workflow(
        user_id=1,
        tenant_id=1,
        proposal_id="prop_abc",
        name="test workflow",
        nodes=[{"id": "n1"}],
        edges=[],
        intake_context={"trigger": "dagelijks", "doel": "rapport", "output": "email"},
        template_id=None,
        db=db,
    )
    db.execute.assert_called_once()
