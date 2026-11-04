"""ADR-036 OP-12 (blinde eindreview, 2026-08-26): CVAAutonomousTrigger() zonder
oversight_gate moet fail-closed blokkeren, niet stilzwijgend fail-open doorvallen.

Gevonden door de verplichte onafhankelijke blinde eindreview op commit 556d1cd2: het
governance-blok in `_execute_breakthrough_session()` was alleen ACTIEF als
`oversight_gate is not None` -- was hij None (de class-default, niet gehardened door de
OP-12-fixes die alleen de module-singleton-constructieplek raakten), dan viel de methode
stilzwijgend door naar directe uitvoering, in tegenspraak met haar eigen docstring
("Fail-closed: Blocks on policy violations or approval requirements"). Geen van de 23
eerder toegevoegde OP-12-tests dekte dit pad (de enige test die de klasse zonder gate
bouwt gebruikte priority=3, waardoor `_execute_breakthrough_session()` nooit werd
bereikt).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger, TriggerEvent
from src.core.types import TriggerType


def test_execution_is_blocked_when_no_oversight_gate_is_configured() -> None:
    agent = CVAAutonomousTrigger()  # geen oversight_gate -- de class-default
    agent._log_to_sandbox = MagicMock()  # type: ignore[method-assign]
    agent._run_cva_breakthrough = MagicMock()  # type: ignore[method-assign]

    from datetime import datetime, timezone

    trigger = TriggerEvent(
        trigger_type=TriggerType.MANUAL,
        priority=1,
        trigger_data={},
        timestamp=datetime.now(timezone.utc),
    )
    agent._execute_breakthrough_session(trigger)

    agent._run_cva_breakthrough.assert_not_called()  # type: ignore[attr-defined]
