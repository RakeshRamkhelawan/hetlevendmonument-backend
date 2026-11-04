"""
Unit tests: BudgetManager.check_budget() wiring in ExternalAgentService -- LLM-C7-005 (SP-SEC-002)
RED voor de fix (check_budget niet aangeroepen), GREEN na de fix.
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db_manager():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: None))

    @asynccontextmanager
    async def _get_session():
        yield mock_session

    db = MagicMock()
    db.get_session = _get_session
    return db, mock_session


@pytest.fixture
def mock_tenant_context():
    ctx = MagicMock()
    ctx.tenant_id = 1
    return ctx


@pytest.fixture
def mock_budget_manager():
    bm = AsyncMock()
    bm.check_budget = AsyncMock(return_value=MagicMock(allowed=True, reason=None))
    bm.track_usage = AsyncMock(return_value=None)
    return bm


@pytest.mark.asyncio
async def test_get_next_task_calls_check_budget(
    mock_db_manager, mock_tenant_context, mock_budget_manager
):
    """ExternalAgentService.get_next_task() MOET budget_manager.check_budget() aanroepen -- LLM-C7-005.

    Huidig: check_budget wordt nooit aangeroepen (audit bevinding 2026-06-30).
    Fix: aanroepen voor taak-uitgifte; 429 retourneren bij budget-overschrijding.
    """
    from src.core.company.external_agent_service import ExternalAgentService

    db, _ = mock_db_manager

    agent_id = uuid.uuid4()
    mock_agent = MagicMock()
    mock_agent.company_id = 1
    mock_agent.department_id = 1

    with (
        patch.object(
            ExternalAgentService,
            "_get_agent",
            new=AsyncMock(return_value=mock_agent),
        ),
        patch.object(
            ExternalAgentService,
            "_get_pending_tasks",
            new=AsyncMock(return_value=[]),
        ),
    ):
        service = ExternalAgentService(
            db_manager=db,
            tenant_context=mock_tenant_context,
            policy_engine=MagicMock(),
            budget_manager=mock_budget_manager,
        )
        await service.get_next_task(agent_id)

    mock_budget_manager.check_budget.assert_called_once()


@pytest.mark.asyncio
async def test_get_next_task_returns_none_when_budget_exceeded(
    mock_db_manager, mock_tenant_context, mock_budget_manager
):
    """get_next_task() MOET None retourneren wanneer budget overschreden -- LLM-C7-005."""
    from src.core.company.external_agent_service import ExternalAgentService

    db, _ = mock_db_manager

    agent_id = uuid.uuid4()
    mock_agent = MagicMock()
    mock_agent.company_id = 1
    mock_agent.department_id = 1

    # Budget overschreden
    mock_budget_manager.check_budget = AsyncMock(
        return_value=MagicMock(allowed=False, reason="daily limit reached")
    )

    with (
        patch.object(
            ExternalAgentService,
            "_get_agent",
            new=AsyncMock(return_value=mock_agent),
        ),
        patch.object(
            ExternalAgentService,
            "_get_pending_tasks",
            new=AsyncMock(
                return_value=[
                    {
                        "task_id": uuid.uuid4(),
                        "action": "run",
                        "input": {},
                    }
                ]
            ),
        ),
    ):
        service = ExternalAgentService(
            db_manager=db,
            tenant_context=mock_tenant_context,
            policy_engine=MagicMock(),
            budget_manager=mock_budget_manager,
        )
        result = await service.get_next_task(agent_id)

    assert result is None, (
        "LLM-C7-005: get_next_task() geeft een taak terug ondanks budget-overschrijding. "
        "Fix: check_budget() aanroepen en None retourneren bij allowed=False."
    )


@pytest.mark.asyncio
async def test_null_budget_manager_allows_all_requests():
    """_NullBudgetManager MOET altijd allowed=True retourneren (null-object patroon)."""
    from src.core.api.v1.company.external_agent_router import _NullBudgetManager

    bm = _NullBudgetManager()
    result = await bm.check_budget()
    allowed = (
        result.get("allowed") if isinstance(result, dict) else getattr(result, "allowed", True)
    )
    assert allowed is True, (
        "_NullBudgetManager.check_budget() moet allowed=True retourneren als fallback."
    )
