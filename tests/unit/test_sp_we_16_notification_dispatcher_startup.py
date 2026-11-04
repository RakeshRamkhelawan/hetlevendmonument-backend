"""
TDD tests for SP-WE-16: NotificationDispatcher startup ordering fix (CG-003).

RED tests: prove the bug exists (compliance monitors skip when dispatcher is None).
GREEN tests: prove the fix works (compliance monitors wire when dispatcher is present).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class MockAppState:
    """Minimal app.state stub -- avoids importing the full FastAPI app."""
    pass


@pytest.mark.unit
class TestCG003NotificationDispatcherStartup:
    """CG-003: _init_compliance_monitors must run AFTER _init_proactive_deps."""

    @pytest.mark.asyncio
    async def test_compliance_monitors_skip_when_dispatcher_is_none(self):
        """
        RED test -- proves the bug: when notification_dispatcher is absent from
        app.state, _init_compliance_monitors logs the skip and returns without
        setting app.state.compliance_monitors.
        """
        from src.core.app_lifespan import _init_compliance_monitors

        app = MagicMock()
        app.state = MockAppState()
        # Simulate state BEFORE _init_proactive_deps has run:
        # copilot_service and notification_dispatcher are absent.

        await _init_compliance_monitors(app)

        # Compliance monitors must NOT be set when dispatcher is absent
        assert not hasattr(app.state, "compliance_monitors"), (
            "compliance_monitors must not be set when notification_dispatcher is None"
        )

    @pytest.mark.asyncio
    async def test_compliance_monitors_wire_when_dispatcher_is_present(self):
        """
        GREEN test -- proves the fix: when notification_dispatcher is already set
        on app.state (as it is after _init_proactive_deps runs), _init_compliance_monitors
        successfully wires DSARExportMonitor and PolicyChangeMonitor.
        """
        from src.core.app_lifespan import _init_compliance_monitors

        app = MagicMock()
        app.state = MockAppState()

        # Simulate state AFTER _init_proactive_deps has run:
        mock_dispatcher = MagicMock()
        mock_copilot_service = MagicMock()
        mock_tenant_repo = MagicMock()
        mock_redis = MagicMock()

        app.state.notification_dispatcher = mock_dispatcher
        app.state.copilot_service = mock_copilot_service
        app.state.tenant_repo = mock_tenant_repo
        app.state.redis_client = mock_redis

        with patch(
            "src.core.copilot.council.cache_invalidator.get_cache_invalidation_event_bus"
        ) as mock_bus_factory, patch(
            "src.core.copilot.proactive.monitors.DSARExportMonitor"
        ) as MockDSAR, patch(
            "src.core.copilot.proactive.monitors.PolicyChangeMonitor"
        ) as MockPolicy:
            mock_bus = MagicMock()
            mock_bus._subscribers = {"dsar_export": [], "policy_change": []}
            mock_bus_factory.return_value = mock_bus

            MockDSAR.return_value = MagicMock()
            MockPolicy.return_value = MagicMock()

            await _init_compliance_monitors(app)

        # After fix: compliance_monitors must be set with both monitors
        assert hasattr(app.state, "compliance_monitors"), (
            "compliance_monitors must be set when dispatcher is available"
        )
        assert "dsar_export" in app.state.compliance_monitors
        assert "policy_change" in app.state.compliance_monitors

    @pytest.mark.asyncio
    async def test_proactive_deps_sets_notification_dispatcher(self):
        """
        GREEN test -- proves _init_proactive_deps sets app.state.notification_dispatcher.
        This is the attribute that _init_compliance_monitors depends on.
        """
        from src.core.app_lifespan import _init_proactive_deps

        app = MagicMock()
        app.state = MockAppState()

        with patch("src.core.database.redis.get_redis_client", new_callable=AsyncMock) as mock_redis, \
             patch("src.core.copilot.notification.ws_pusher.WSPusher") as MockWSPusher, \
             patch("src.core.copilot.notification.digest.DigestQueue") as MockDigestQueue, \
             patch("src.core.copilot.notification.budget.NotificationBudgetTracker") as MockBudget, \
             patch("src.core.copilot.notification.dispatcher.NotificationDispatcher") as MockDispatcher, \
             patch("src.core.copilot.proactive.deps._DBTenantRepo") as MockTenantRepo, \
             patch("src.core.copilot.proactive.deps._ProactiveServiceProxy") as MockProxy, \
             patch("src.core.copilot.notification.preferences_repo.UserNotificationPreferencesRepo"), \
             patch("src.core.database.database.get_async_session"):
            mock_redis.return_value = MagicMock()
            MockDispatcher.return_value = MagicMock(spec=["dispatch"])

            await _init_proactive_deps(app)

        assert hasattr(app.state, "notification_dispatcher"), (
            "_init_proactive_deps must set app.state.notification_dispatcher"
        )
        assert app.state.notification_dispatcher is not None

    @pytest.mark.asyncio
    async def test_startup_order_deps_before_compliance_monitors(self):
        """
        GREEN test -- proves the correct startup order: _init_proactive_deps
        must be called before _init_compliance_monitors in app_lifespan().
        Verifies by inspecting the source order, not by running the full lifespan.
        """
        import inspect
        from src.core import app_lifespan as _module

        source = inspect.getsource(_module.app_lifespan)
        idx_deps = source.index("_init_proactive_deps")
        idx_compliance = source.index("_init_compliance_monitors")

        assert idx_deps < idx_compliance, (
            "CG-003 fix: _init_proactive_deps() must appear BEFORE "
            "_init_compliance_monitors() in app_lifespan(). "
            f"Found: deps at char {idx_deps}, compliance at char {idx_compliance}."
        )

    @pytest.mark.asyncio
    async def test_proactive_scheduler_still_after_proactive_deps(self):
        """
        Regression test -- proves the scheduler order is unchanged after fix.
        _init_proactive_scheduler must remain AFTER _init_proactive_deps.
        """
        import inspect
        from src.core import app_lifespan as _module

        source = inspect.getsource(_module.app_lifespan)
        idx_deps = source.index("_init_proactive_deps")
        idx_scheduler = source.index("_init_proactive_scheduler")

        assert idx_deps < idx_scheduler, (
            "Regression: _init_proactive_deps() must remain BEFORE "
            "_init_proactive_scheduler() in app_lifespan()."
        )

    @pytest.mark.asyncio
    async def test_compliance_monitors_graceful_degradation_when_redis_absent(self):
        """
        Regression test -- proves graceful degradation is intact when Redis is
        unavailable. If _init_proactive_deps fails (Redis down), neither
        dispatcher nor compliance_monitors should be set -- but no exception
        should propagate to the caller.
        """
        from src.core.app_lifespan import _init_proactive_deps, _init_compliance_monitors

        app = MagicMock()
        app.state = MockAppState()

        with patch(
            "src.core.database.redis.get_redis_client",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis unavailable"),
        ):
            # Must not raise -- graceful degradation
            await _init_proactive_deps(app)

        # dispatcher not set because Redis failed
        assert not hasattr(app.state, "notification_dispatcher")

        # compliance monitors must also not raise -- they check for None and skip
        await _init_compliance_monitors(app)
        assert not hasattr(app.state, "compliance_monitors")
