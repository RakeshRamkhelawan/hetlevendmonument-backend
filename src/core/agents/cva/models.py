from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.core.agents.cva_state_machine import CVAMode

__all__ = ["CVAMode", "OrchestrationCommand", "CVAState"]


@dataclass
class OrchestrationCommand:
    """Command structure for orchestrator communication with memory context"""

    command: str
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    priority: int
    masterprompt: str | None = None
    expected_agents: list[str] | None = None


@dataclass
class CVAState:
    """CVA operational state tracking for strategic memory"""

    mode: CVAMode
    active_orchestrations: list[str]
    learning_context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    performance_metrics: dict[str, float]
    last_optimization: datetime
    autonomous_triggers_active: bool
