"""Unit tests for LearningBudgetService.

All tests use AsyncMock for AsyncSession -- no PostgreSQL required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError

from src.core.learning.budget_service import LearningBudgetService


def _make_mock_budget(
    tenant_id: int = 1,
    month: str = "2026-06",
    budget_eur_soft: float = 10.0,
    budget_eur_hard: float = 50.0,
    spent_eur: float = 5.0,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> MagicMock:
    budget = MagicMock()
    budget.tenant_id = tenant_id
    budget.month = month
    budget.budget_eur_soft = budget_eur_soft
    budget.budget_eur_hard = budget_eur_hard
    budget.spent_eur = spent_eur
    budget.created_at = None
    budget.updated_at = None
    return budget


@pytest.mark.asyncio
async def test_get_budget_returns_existing_record() -> None:
    """Service returns values from an existing DB record."""
    db = AsyncMock()
    mock_budget = _make_mock_budget(spent_eur=5.0)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_budget
    db.execute.return_value = result_mock

    with patch("src.core.learning.budget_service.set_twin_llm_budget_hard") as mock_gauge:
        service = LearningBudgetService(db)
        data = await service.get_budget(tenant_id=1)

    assert data["tenant_id"] == 1
    assert data["budget_eur_soft"] == 10.0
    assert data["budget_eur_hard"] == 50.0
    assert data["spent_eur"] == 5.0
    assert data["remaining_soft"] == 5.0
    assert data["remaining_hard"] == 45.0
    mock_gauge.assert_called_once_with(1, 50.0)


@pytest.mark.asyncio
async def test_get_budget_returns_defaults_when_no_record_exists() -> None:
    """Service returns default values when no DB record exists; Prometheus gauge NOT set."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    with patch("src.core.learning.budget_service.set_twin_llm_budget_hard") as mock_gauge:
        service = LearningBudgetService(db)
        data = await service.get_budget(tenant_id=2)

    assert data["tenant_id"] == 2
    assert data["budget_eur_soft"] == LearningBudgetService.DEFAULT_SOFT
    assert data["budget_eur_hard"] == LearningBudgetService.DEFAULT_HARD
    assert data["spent_eur"] == 0.0
    mock_gauge.assert_not_called()


@pytest.mark.asyncio
async def test_update_budget_creates_new_record() -> None:
    """Service creates a new record when none exists."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    db.refresh = AsyncMock(side_effect=lambda b: None)

    added_objects: list[object] = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    with (
        patch("src.core.learning.budget_service.set_twin_llm_budget_hard"),
        patch("src.core.learning.budget_service.log_learning_audit_event", new_callable=AsyncMock),
    ):
        service = LearningBudgetService(db)
        service._db.refresh = AsyncMock(
            side_effect=lambda b: setattr(b, "budget_eur_hard", 80.0) or None
        )

        data = await service.update_budget(tenant_id=1, budget_eur_soft=20.0, budget_eur_hard=80.0)

    assert len(added_objects) == 1
    db.commit.assert_called()
    assert data["tenant_id"] == 1
    assert data["budget_eur_soft"] == 20.0
    assert data["budget_eur_hard"] == 80.0
    assert data["spent_eur"] == 0.0


@pytest.mark.asyncio
async def test_update_budget_updates_existing_record() -> None:
    """Service updates an existing record in-place."""
    db = AsyncMock()
    mock_budget = _make_mock_budget(budget_eur_soft=10.0, budget_eur_hard=50.0, spent_eur=3.0)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_budget
    db.execute.return_value = result_mock
    db.refresh = AsyncMock()

    with (
        patch("src.core.learning.budget_service.set_twin_llm_budget_hard"),
        patch("src.core.learning.budget_service.log_learning_audit_event", new_callable=AsyncMock),
    ):
        service = LearningBudgetService(db)
        await service.update_budget(tenant_id=1, budget_eur_soft=25.0, budget_eur_hard=100.0)

    assert mock_budget.budget_eur_soft == 25.0
    assert mock_budget.budget_eur_hard == 100.0
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_update_budget_triggers_prometheus_metric_update() -> None:
    """Service calls set_twin_llm_budget_hard with the persisted hard cap value."""
    db = AsyncMock()
    mock_budget = _make_mock_budget(budget_eur_hard=75.0, spent_eur=0.0)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_budget
    db.execute.return_value = result_mock
    db.refresh = AsyncMock()

    with (
        patch("src.core.learning.budget_service.set_twin_llm_budget_hard") as mock_gauge,
        patch("src.core.learning.budget_service.log_learning_audit_event", new_callable=AsyncMock),
    ):
        service = LearningBudgetService(db)
        await service.update_budget(tenant_id=1, budget_eur_soft=25.0, budget_eur_hard=75.0)

    mock_gauge.assert_called_once()


@pytest.mark.asyncio
async def test_update_budget_handles_integrity_error_with_reread() -> None:
    """Service recovers from concurrent INSERT race via re-read."""
    db = AsyncMock()
    result_mock_none = MagicMock()
    result_mock_none.scalar_one_or_none.return_value = None

    mock_budget = _make_mock_budget(budget_eur_soft=20.0, budget_eur_hard=80.0, spent_eur=0.0)
    result_mock_existing = MagicMock()
    result_mock_existing.scalar_one.return_value = mock_budget

    db.execute.side_effect = [result_mock_none, result_mock_existing]

    db.commit = AsyncMock(side_effect=[IntegrityError("uq", {}, None), None, None])
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    with (
        patch("src.core.learning.budget_service.set_twin_llm_budget_hard"),
        patch("src.core.learning.budget_service.log_learning_audit_event", new_callable=AsyncMock),
    ):
        service = LearningBudgetService(db)
        data = await service.update_budget(tenant_id=1, budget_eur_soft=20.0, budget_eur_hard=80.0)

    db.rollback.assert_called_once()
    assert data["tenant_id"] == 1
