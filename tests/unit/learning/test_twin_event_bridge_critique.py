"""Unit tests for TwinEventBridge CritiqueScoreLow learning handler (SP-AGT-009).

Covers ADR-025 gap #2: a feature-flagged downstream consumer that persists
CritiqueScoreLow events as LearningExperience rows.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.learning.events.twin_events import CritiqueScoreLow, InterventionSuggested
from src.core.learning.wiring.twin_event_bridge import TwinEventBridge


def _make_bus() -> MagicMock:
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    return bus


def _make_session() -> AsyncMock:
    """AsyncSession mock supporting async context manager + add/commit/execute."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
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


def _critique_event(tenant_id: int = 1) -> CritiqueScoreLow:
    return CritiqueScoreLow(
        user_id="u1",
        tenant_id=tenant_id,
        agent_name="TestAgent",
        score=0.20,
        trace_id="trace-critique-001",
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTwinEventBridgeCritique:
    def test_critique_score_low_in_redis_event_type_map(self) -> None:
        """TwinEventBridge._REDIS_EVENT_TYPE_MAP must contain 'twin.critique.score_low'."""
        assert "twin.critique.score_low" in TwinEventBridge._REDIS_EVENT_TYPE_MAP

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_on_critique_score_low_persists_learning_experience(
        self, _flag: MagicMock
    ) -> None:
        """Valid CritiqueScoreLow + flag on -> LearningExperience row inserted."""
        session = _make_session()
        sf = _make_sf(session)
        bridge = _make_bridge(sf=sf)
        event = _critique_event(tenant_id=7)

        with patch("src.core.learning.models.LearningExperience") as MockLE:
            mock_record = MagicMock()
            MockLE.return_value = mock_record
            await bridge._on_critique_score_low_learning(event)

        MockLE.assert_called_once()
        kw = MockLE.call_args.kwargs
        assert kw["tenant_id"] == 7
        assert kw["event_type"] == "twin.critique.score_low"
        assert kw["agent_id"] == "TestAgent"
        assert kw["task_type"] == "critique_signal"
        assert kw["success"] is False
        assert kw["confidence"] == pytest.approx(0.20)
        assert kw["context"] == {"agent_name": "TestAgent", "trace_id": "trace-critique-001"}
        assert kw["metrics"] == {"score": 0.20}
        session.add.assert_called_once_with(mock_record)
        session.commit.assert_awaited_once()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=False)
    async def test_on_critique_score_low_skips_when_flag_off(self, _flag: MagicMock) -> None:
        """When agent_learning flag is off the session factory is never called."""
        sf = MagicMock()
        bridge = _make_bridge(sf=sf)
        await bridge._on_critique_score_low_learning(_critique_event())
        sf.assert_not_called()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_on_critique_score_low_skips_wrong_event_type(self, _flag: MagicMock) -> None:
        """InterventionSuggested is the wrong event type -- handler exits early."""
        sf = MagicMock()
        bridge = _make_bridge(sf=sf)
        wrong_event = InterventionSuggested(
            user_id="u1",
            tenant_id=1,
            intervention_type="struggle",
            message="You seem stuck.",
            confidence=0.80,
            trace_id="trace-001",
        )
        await bridge._on_critique_score_low_learning(wrong_event)
        sf.assert_not_called()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_on_critique_score_low_skips_invalid_tenant_id(
        self, _flag: MagicMock
    ) -> None:
        """tenant_id <= 0 is rejected before opening a DB session."""
        sf = MagicMock()
        bridge = _make_bridge(sf=sf)
        await bridge._on_critique_score_low_learning(_critique_event(tenant_id=0))
        sf.assert_not_called()

    @patch("src.core.learning.wiring.twin_event_bridge.get_feature_flag", return_value=True)
    async def test_on_critique_score_low_skips_when_no_session_factory(
        self, _flag: MagicMock
    ) -> None:
        """When session_factory is None and db_manager has none, handler returns cleanly."""
        bridge = _make_bridge(sf=None)
        with patch("src.core.database.database.db_manager") as mock_dm:
            mock_dm.async_session_maker = None
            # Must not raise
            await bridge._on_critique_score_low_learning(_critique_event())
