"""
Unit tests for User Notification Preferences Repository.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.notification.models import NotificationPreferences
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo


@pytest.mark.unit
async def test_get_for_user_returns_defaults_when_no_row():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    repo = UserNotificationPreferencesRepo(mock_db)

    prefs = await repo.get_for_user(user_id=1, tenant_id=1)

    assert prefs.user_id == 1
    assert prefs.tenant_id == 1
    assert prefs.daily_limit == 25
    assert prefs.delivery_mode == "individual"
    assert prefs.critical_always_immediate is True


@pytest.mark.unit
@pytest.mark.security
async def test_get_for_user_filters_by_tenant():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    repo = UserNotificationPreferencesRepo(mock_db)

    await repo.get_for_user(user_id=1, tenant_id=42)

    # Verify the SQL statement generation contains tenant_id == 42
    # Though difficult with pure mocks without inspecting AST, we ensure execute was called
    assert mock_db.execute.called
    call_args = mock_db.execute.call_args[0][0]

    # In string representation of SQLAlchemy statement it should mention tenant_id = :tenant_id
    stmt_str = str(call_args)
    assert "user_notification_preferences.tenant_id = :tenant_id" in stmt_str
