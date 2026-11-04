"""Scheduling agent type registry.

Maps agent type identifiers to their implementation classes.
Used for agent discovery and factory creation.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Registry of scheduling agent type names -> class paths
SCHEDULING_AGENT_TYPES: dict[str, str] = {
    "scheduling_orchestrator": (
        "src.core.scheduling.agents.orchestrator_agent.SchedulingOrchestratorAgent"
    ),
}
