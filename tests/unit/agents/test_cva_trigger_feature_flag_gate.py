"""ADR-036 OP-12 (addendum SS8.2, Taak 5, 2026-08-26): `_add_trigger()` weigert elke
trigger zolang de `autonomous_breakthrough`-feature-flag uit staat (default). Dit is
defense-in-depth naast de architectuurguards die al bewijzen dat niemand dit pad van
buitenaf aanroept (`tests/architecture/test_op12_autonomous_breakthrough_stays_unwired.py`).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger
from src.core.types import TriggerType


def _build_agent() -> CVAAutonomousTrigger:
    agent = CVAAutonomousTrigger()
    agent._log_to_sandbox = MagicMock()  # type: ignore[method-assign]
    return agent


def test_trigger_is_rejected_when_the_flag_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEATURE_AUTONOMOUS_BREAKTHROUGH", raising=False)
    agent = _build_agent()

    agent._add_trigger(TriggerType.MANUAL, 3, {"reason": "test"})

    assert agent.trigger_queue == [], (
        "Met de flag uit (default) mag geen enkele trigger in de wachtrij belanden."
    )


def test_trigger_is_accepted_when_the_flag_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_AUTONOMOUS_BREAKTHROUGH", "true")
    agent = _build_agent()

    agent._add_trigger(TriggerType.MANUAL, 3, {"reason": "test"})

    assert len(agent.trigger_queue) == 1, (
        "Met de flag expliciet aan moet een trigger wel degelijk in de wachtrij komen "
        "(dit bewijst dat de guard niet hol is -- de vlag doet echt iets)."
    )
