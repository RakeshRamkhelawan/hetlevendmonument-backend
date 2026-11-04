"""MockMonitor for testing - returns fixed signals filtered by tenant_id."""

from __future__ import annotations

from typing import Any

from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.types import Signal


class MockMonitor(ProactiveMonitor):
    """Test monitor that returns pre-configured signals."""

    name = "mock"
    version = "1.0.0"
    interval_seconds = 60

    def __init__(
        self,
        copilot_service: Any,  # TODO(TYPE): replace Any with concrete type
        dispatcher: Any,  # TODO(TYPE): replace Any with concrete type
        signals: list[Signal] | None = None,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._signals = signals or []

    async def detect(self, tenant_id: int) -> list[Signal]:
        return [s for s in self._signals if s.tenant_id == tenant_id]
