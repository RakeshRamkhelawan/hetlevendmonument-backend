"""
Integration tests for Notification Budget Tracker against real Redis.
"""

from datetime import datetime, timezone
import pytest
from src.core.copilot.notification.budget import BudgetVerdict, NotificationBudgetTracker
from src.core.copilot.notification.models import NotificationPreferences
from src.core.database.redis import get_redis_client

@pytest.fixture
async def real_redis_client():
    client = await get_redis_client()
    yield client

@pytest.mark.integration
@pytest.mark.requires_redis
async def test_budget_against_real_redis(real_redis_client):
    tracker = NotificationBudgetTracker(real_redis_client)
    prefs = NotificationPreferences(user_id=999, tenant_id=999, daily_limit=3)

    now = datetime.now(timezone.utc)
    date_key = now.strftime("%Y-%m-%d")
    key = tracker.KEY_TEMPLATE.format(tenant_id=999, user_id=999, date_key=date_key)
    await real_redis_client.delete(key)

    for _ in range(3):
        r = await tracker.consume(tenant_id=999, user_id=999, prefs=prefs, severity="normal")
        assert r.verdict == BudgetVerdict.APPROVED

    r = await tracker.consume(tenant_id=999, user_id=999, prefs=prefs, severity="normal")
    assert r.verdict == BudgetVerdict.DEFERRED

    ttl = await real_redis_client.ttl(key)
    assert 0 < ttl <= 25 * 3600

    await real_redis_client.delete(key)
