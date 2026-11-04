"""
Explainability Module
Captures and persists reasoning chains for AI agent decisions.
Required for User Story #11 (Compliance and User Trust).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ReasoningStepType(Enum):
    """Types of reasoning steps in a decision chain"""

    INPUT_RECEIVED = "input_received"
    COMPLEXITY_ANALYSIS = "complexity_analysis"
    MODEL_SELECTION = "model_selection"
    TOOL_INVOCATION = "tool_invocation"
    LLM_CALL = "llm_call"
    CONFIDENCE_SCORE = "confidence_score"
    OUTPUT_GENERATED = "output_generated"
    ERROR_OCCURRED = "error_occurred"


class ReasoningTrace:
    """
    Container for a sequence of reasoning steps.
    Can be serialized to JSON for audit log storage.
    """

    def __init__(self, agent_name: str, task_id: str | None = None) -> None:
        self.agent_name = agent_name
        self.task_id = task_id
        self.steps: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.start_time = datetime.now(timezone.utc)
        self.end_time: datetime | None = None

    def add_step(
        self,
        step_type: ReasoningStepType,
        description: str,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Add a reasoning step to the trace.

        Args:
            step_type: The type of step
            description: Human-readable description
            metadata: Additional context (e.g., confidence scores, model names)
        """
        step = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": step_type.value,
            "description": description,
            "metadata": metadata or {},
        }
        self.steps.append(step)

    def finalize(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Finalize the trace and return serializable dict.

        Returns: Dict[str, Any] suitable for JSON serialization  # TODO(TYPE): replace Any with concrete type
        """
        self.end_time = datetime.now(timezone.utc)
        duration = (self.end_time - self.start_time).total_seconds()

        return {
            "agent_name": self.agent_name,
            "task_id": self.task_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": duration,
            "steps": self.steps,
        }
