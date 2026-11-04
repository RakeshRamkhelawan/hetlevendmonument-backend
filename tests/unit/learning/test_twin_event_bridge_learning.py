"""Unit tests for TwinEventBridge agent learning consumer (ADR-025 Task 3.1).

Happy paths:
  - InterventionSuggested with flag on -> LearningExperience persisted
  - Learning handler is always registered in start(); flag checked per-event

Unhappy paths:
  - Feature flag off -> DB never touched
  - ConsentChanged event -> handler returns early (wrong type guard)
  - tenant_id <= 0 -> warning, no DB call
  - No session_factory and db_manager.async_session_maker is None -> warning, no crash
  - session.commit() raises -> best_effort catches, rollback called, no re-raise

User behavioral tests:
  - stop() cleanly unregisters the learning handler alongside all others
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.learning.events.twin_events import ConsentChanged, InterventionSuggested
from src.core.learning.wiring.twin_event_bridge import TwinEventBridge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_bus() -> MagicMock:
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    return bus


def _make_session() -> AsyncMock:
    """AsyncSession mock that supports `async with session` and add/commit/rollback."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_sf(session: AsyncMock) -> MagicMock:
    """async_sessionmaker mock: calling it returns *session* as context manager."""
    sf = MagicMock()
    sf.return_value = session
    return sf


def _make_bridge(
    bus: MagicMock | None = None,
    sf: MagicMock | None = None,
) -> TwinEventBridge:
    return TwinEventBridge(event_bus=bus or _make_bus(), session_factory=sf)


def _intervention(tenant_id: int = 1) -> InterventionSuggested:
    return InterventionSuggested(
        user_id="u1",
        tenant_id=tenant_id,
        intervention_type="struggle",
        message="You seem stuck.",
        confidence=0.80,
        trace_id="trace-001",
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestTwinEventBridgeLearning:
    # ------------------------------------------------------------------
    # Registration / wiring
    # ------------------------------------------------------------------

    async def test_learning_handler_always_registered(self) -> None:
        """Both the Redis-forward and learning-persist handlers are registered for
        twin.intervention.suggested, regardless of feature flag state."""
        bus = _make_bus()
        bridge = _make_bridge(bus=bus)
        await bridge.start()

        registered = [et for et, _ in bridge._handlers]
        assert registered.count("twin.intervention.suggested") == 2

    async def test_stop_unregisters_all_handlers(self) -> None:
        """stop() removes all handlers, including the learning handler."""
        bus = _make_bus()
        bridge = _make_bridge(bus=bus)
        await bridge.start()
        handler_count_before = len(bridge._handlers)
        await bridge.stop()

        assert bus.unsubscribe.call_count == handler_count_before
        assert bridge._handlers == []

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_intervention_event_creates_learning_experience(self, _flag: MagicMock) -> None:
        """Valid InterventionSuggested + flag on -> LearningExperience row inserted."""
        session = _make_session()
        sf = _make_sf(session)
        bridge = _make_bridge(sf=sf)
        event = _intervention(tenant_id=7)

        with patch("src.core.learning.models.LearningExperience") as MockLE:
            mock_record = MagicMock()
            MockLE.return_value = mock_record
            await bridge._on_intervention_suggested_learning(event)

        MockLE.assert_called_once()
        kw = MockLE.call_args.kwargs
        assert kw["tenant_id"] == 7
        assert kw["event_type"] == "twin.intervention.suggested"
        assert kw["agent_id"] == "twin_service"
        assert kw["task_type"] == "struggle"
        assert kw["success"] is True
        assert kw["confidence"] == pytest.approx(0.80)
        # PII guard: message must NOT be stored in context
        assert "message" not in (kw.get("context") or {})
        session.add.assert_called_once_with(mock_record)
        session.commit.assert_awaited_once()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_rls_set_local_injected_before_insert(self, _flag: MagicMock) -> None:
        """SET LOCAL app.current_tenant is executed before the INSERT."""
        session = _make_session()
        bridge = _make_bridge(sf=_make_sf(session))
        event = _intervention(tenant_id=42)

        with patch("src.core.learning.models.LearningExperience"):
            await bridge._on_intervention_suggested_learning(event)

        # Sinds 2026-10-08 set_config met een gebonden parameter i.p.v. een f-string in
        # `text()` (plan nazorg, punt c; tests/architecture/test_geen_sql_met_interpolatie.py).
        execute_calls = [
            (str(c.args[0]), c.args[1] if len(c.args) > 1 else {})
            for c in session.execute.await_args_list
        ]
        assert any(
            "set_config('app.current_tenant'" in sql and params == {"t": "42"}
            for sql, params in execute_calls
        ), "RLS tenant context must be set before INSERT"

    # ------------------------------------------------------------------
    # Unhappy paths
    # ------------------------------------------------------------------

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=False)
    async def test_feature_flag_off_skips_db(self, _flag: MagicMock) -> None:
        """When agent_learning flag is off the session factory is never called."""
        sf = MagicMock()
        bridge = _make_bridge(sf=sf)
        await bridge._on_intervention_suggested_learning(_intervention())
        sf.assert_not_called()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_consent_event_returns_early(self, _flag: MagicMock) -> None:
        """ConsentChanged is the wrong event type — handler exits before any DB work."""
        sf = MagicMock()
        bridge = _make_bridge(sf=sf)
        event = ConsentChanged(user_id="u1", tenant_id=1, new_status="disabled")
        await bridge._on_intervention_suggested_learning(event)
        sf.assert_not_called()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_invalid_tenant_id_zero_skips_persist(self, _flag: MagicMock) -> None:
        """tenant_id == 0 is rejected before opening a DB session."""
        sf = MagicMock()
        bridge = _make_bridge(sf=sf)
        await bridge._on_intervention_suggested_learning(_intervention(tenant_id=0))
        sf.assert_not_called()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_no_session_factory_logs_warning_no_crash(self, _flag: MagicMock) -> None:
        """When session_factory is None and db_manager has none, a warning is logged
        and the handler returns cleanly."""
        bridge = _make_bridge(sf=None)
        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = None
            # Must not raise
            await bridge._on_intervention_suggested_learning(_intervention())

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_commit_failure_caught_by_best_effort(self, _flag: MagicMock) -> None:
        """If session.commit() raises, best_effort swallows it, rollback is called,
        and the handler returns without re-raising."""
        session = _make_session()
        session.commit.side_effect = Exception("DB connection lost")
        bridge = _make_bridge(sf=_make_sf(session))

        with patch("src.core.learning.models.LearningExperience"):
            # Must not raise
            await bridge._on_intervention_suggested_learning(_intervention())

        session.rollback.assert_awaited_once()
