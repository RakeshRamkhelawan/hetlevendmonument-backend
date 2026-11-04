"""
Unit tests for ResourceOfficer.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.copilot.council.members.resource_officer import ResourceOfficer
from src.core.copilot.council.types import (
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)
from src.core.copilot.notification.budget import BudgetResult, BudgetVerdict
from src.core.copilot.notification.models import NotificationPreferences


@pytest.fixture
def mock_rate_limiter():
    mock = AsyncMock()
    mock.check.return_value = True
    return mock


@pytest.fixture
def mock_prana_service():
    mock = AsyncMock()
    mock.has_budget.return_value = True
    return mock


@pytest.fixture
def mock_budget_tracker():
    mock = AsyncMock()
    mock.consume.return_value = BudgetResult(
        verdict=BudgetVerdict.APPROVED, remaining=10, daily_limit=25, reason="WITHIN_BUDGET"
    )
    return mock


@pytest.fixture
def mock_prefs_repo():
    mock = AsyncMock()
    mock.get_for_user.return_value = NotificationPreferences(user_id=1, tenant_id=1)
    return mock


def create_proposal(trigger=ProposalTrigger.PROACTIVE_MONITOR, severity="normal"):
    return Proposal(
        tenant_id=1,
        user_id=1,
        trigger=trigger,
        action_type="send_notification",
        action_params={},
        reasoning="Test",
        data_classification="public",
        confidence=0.9,
        model_id="test",
        model_version="1",
        context_snapshot={"severity": severity},
    )


def create_context():
    return DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=1000,
        request_id="test-id",
    )


@pytest.mark.unit
@pytest.mark.als
async def test_approve_when_all_budgets_ok(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    verdict = await officer.deliberate(create_proposal(), create_context())

    assert verdict.verdict == VerdictType.APPROVE
    assert mock_rate_limiter.check.called
    assert mock_prana_service.has_budget.called
    assert mock_budget_tracker.consume.called


@pytest.mark.unit
@pytest.mark.als
async def test_defer_when_rate_limit_exhausted(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    mock_rate_limiter.check.return_value = False

    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    verdict = await officer.deliberate(create_proposal(), create_context())

    assert verdict.verdict == VerdictType.REQUIRE_DEFERRAL
    assert verdict.reason_code == "RATE_LIMIT_EXCEEDED"
    assert not mock_prana_service.has_budget.called


@pytest.mark.unit
@pytest.mark.als
async def test_defer_when_prana_empty(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    mock_prana_service.has_budget.return_value = False

    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    verdict = await officer.deliberate(create_proposal(), create_context())

    assert verdict.verdict == VerdictType.REQUIRE_DEFERRAL
    assert verdict.reason_code == "PRANA_BUDGET_EMPTY"
    assert not mock_budget_tracker.consume.called


@pytest.mark.unit
@pytest.mark.als
async def test_defer_when_notification_budget_full(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    mock_budget_tracker.consume.return_value = BudgetResult(
        verdict=BudgetVerdict.DEFERRED, remaining=0, daily_limit=25, reason="DAILY_LIMIT_REACHED"
    )

    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    verdict = await officer.deliberate(create_proposal(), create_context())

    assert verdict.verdict == VerdictType.REQUIRE_DEFERRAL
    assert verdict.reason_code == "DAILY_LIMIT_REACHED"


@pytest.mark.unit
@pytest.mark.als
async def test_override_on_critical_severity(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    mock_budget_tracker.consume.return_value = BudgetResult(
        verdict=BudgetVerdict.OVERRIDE, remaining=-1, daily_limit=25, reason="CRITICAL_BYPASS"
    )

    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    verdict = await officer.deliberate(create_proposal(severity="critical"), create_context())

    assert verdict.verdict == VerdictType.OVERRIDE_BUDGET
    assert verdict.reason_code == "CRITICAL_BYPASS"


@pytest.mark.unit
@pytest.mark.als
async def test_skip_notification_check_when_trigger_is_user_action(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    verdict = await officer.deliberate(
        create_proposal(trigger=ProposalTrigger.USER_REQUEST), create_context()
    )

    assert verdict.verdict == VerdictType.APPROVE
    assert not mock_budget_tracker.consume.called


@pytest.mark.unit
@pytest.mark.als
def test_resource_officer_never_emits_veto():
    assert ResourceOfficer.can_veto is False


@pytest.mark.unit
@pytest.mark.als
async def test_internal_error_defers_proposal(
    mock_rate_limiter, mock_prana_service, mock_budget_tracker, mock_prefs_repo
):
    mock_rate_limiter.check.side_effect = Exception("Internal DB error")

    officer = ResourceOfficer(
        rate_limiter=mock_rate_limiter,
        prana_service=mock_prana_service,
        budget_tracker=mock_budget_tracker,
        preferences_repo=mock_prefs_repo,
    )

    with patch("src.core.copilot.council.members.resource_officer.logger") as mock_logger:
        verdict = await officer.deliberate(create_proposal(), create_context())

        assert verdict.verdict == VerdictType.REQUIRE_DEFERRAL
        assert verdict.reason_code == "OFFICER_INTERNAL_ERROR"
        assert mock_logger.error.called
