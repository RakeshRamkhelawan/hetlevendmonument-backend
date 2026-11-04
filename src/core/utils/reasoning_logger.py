import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

# Fallback logger if not provided
default_logger = logging.getLogger("reasoning_trace")


class ReasoningLogger:
    """
    Specialized logger for Explainable AI (XAI) traces.
    Captures the "Thought Process" of agents for audit and debugging.
    """

    @staticmethod
    def log_trace(
        agent_id: str,
        execution_id: str,
        step_name: str,
        thought_process: str,
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Logs a discrete reasoning step.
        """
        payload = {
            "event_type": "reasoning_trace",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "execution_id": execution_id,
            "step": step_name,
            "thought": thought_process,  # The "Why"
            "outcome": outcome,  # The "What happened"
            "metadata": metadata or {},
        }

        # Log as structured JSON for easy parsing by observability tools (Jaeger/Elastic)
        default_logger.info(json.dumps(payload))

        # In a real implementation, this might also write to a specific DB table
        # for the "Reasoning" tab in the UI.

    @staticmethod
    def log_decision(
        agent_id: str,
        execution_id: str,
        decision: str,
        rationale: str,
        alternatives_considered: list[str] | None = None,
    ) -> None:
        """
        Logs a critical decision point.
        """
        ReasoningLogger.log_trace(
            agent_id=agent_id,
            execution_id=execution_id,
            step_name="Make Decision",
            thought_process=rationale,
            outcome=decision,
            metadata={"alternatives": alternatives_considered},
        )
