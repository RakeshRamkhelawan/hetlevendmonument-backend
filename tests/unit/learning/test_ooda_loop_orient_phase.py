"""Unit tests: OODALoopObserver Orient-fase + CritiqueScoreLow event.

SP-AGT-008 Dag 1 -- Item F
Tests zijn ROOD voor implementatie: CritiqueScoreLow bestaat niet in twin_events.py
en OODALoopObserver heeft geen _orient_publish_critique_event().
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.learning.observers.ooda_loop_observer import OODALoopObserver


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orient_publishes_critique_score_low_event(caplog: pytest.LogCaptureFixture) -> None:
    """Orient-fase publiceert CritiqueScoreLow event op TwinEventBus bij lage score."""
    # ImportError als CritiqueScoreLow niet bestaat -- RED voor implementatie
    from src.core.learning.events.twin_events import CritiqueScoreLow  # noqa: F401

    observer = OODALoopObserver()
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    with patch(
        "src.core.learning.observers.ooda_loop_observer.get_twin_event_bus",
        return_value=mock_bus,
    ):
        await observer.on_intervention_suggested(
            user_id=1,
            tenant_id=1,
            event_data={"agent_name": "TestAgent", "score": 0.20},
        )

    mock_bus.publish.assert_called_once()
    published_event = mock_bus.publish.call_args[0][0]
    assert published_event.event_type == "twin.critique.score_low"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orient_does_not_publish_when_score_above_threshold() -> None:
    """Orient-fase publiceert niets als score >= drempel."""
    observer = OODALoopObserver()
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    with patch(
        "src.core.learning.observers.ooda_loop_observer.get_twin_event_bus",
        return_value=mock_bus,
    ):
        await observer.on_intervention_suggested(
            user_id=1,
            tenant_id=1,
            event_data={"agent_name": "TestAgent", "score": 0.85},
        )

    mock_bus.publish.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orient_tolerates_missing_score_in_event_data() -> None:
    """Orient-fase gooit geen exception als score ontbreekt in event_data."""
    observer = OODALoopObserver()
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    with patch(
        "src.core.learning.observers.ooda_loop_observer.get_twin_event_bus",
        return_value=mock_bus,
    ):
        await observer.on_intervention_suggested(
            user_id=1,
            tenant_id=1,
            event_data={"agent_name": "TestAgent"},
        )

    mock_bus.publish.assert_not_called()


@pytest.mark.unit
def test_critique_score_low_event_has_required_fields() -> None:
    """CritiqueScoreLow heeft event_type, agent_name en score velden."""
    # ImportError als CritiqueScoreLow niet bestaat -- RED voor implementatie
    from src.core.learning.events.twin_events import CritiqueScoreLow

    event = CritiqueScoreLow(
        user_id="1",
        tenant_id=1,
        agent_name="TestAgent",
        score=0.20,
    )
    assert event.event_type == "twin.critique.score_low"
    assert event.agent_name == "TestAgent"
    assert event.score == 0.20


@pytest.mark.unit
@pytest.mark.asyncio
async def test_decide_phase_logs_intervention(caplog: pytest.LogCaptureFixture) -> None:
    """Decide-fase logt ooda_decide_intervention bij lage score."""
    observer = OODALoopObserver()
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    import logging

    with patch(
        "src.core.learning.observers.ooda_loop_observer.get_twin_event_bus",
        return_value=mock_bus,
    ):
        with caplog.at_level(logging.INFO, logger="src.core.learning.observers.ooda_loop_observer"):
            await observer.on_intervention_suggested(
                user_id=1,
                tenant_id=1,
                event_data={"agent_name": "TestAgent", "score": 0.20},
            )

    assert any("ooda_decide_intervention" in r.message for r in caplog.records)
