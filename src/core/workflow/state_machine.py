"""
State Machine for Workflow and Task Status Transitions
Enforces valid state transitions and prevents illegal status changes

Design:
- Workflow states: PENDING -> RUNNING -> SUCCEEDED/FAILED/CANCELLED/TIMEOUT
- Task states: PENDING -> RUNNING -> SUCCEEDED/FAILED/RETRYING/TIMEOUT/SKIPPED
- Prevents illegal transitions (e.g., SUCCEEDED -> RUNNING)
- Provides introspection (get_allowed_transitions)
"""


from src.core.workflow.interfaces import IStateMachine


class WorkflowStateMachine(IStateMachine):
    """
    Production state machine with strict transition rules

    State Diagrams:

    Workflow:
    PENDING -> RUNNING -> {SUCCEEDED, FAILED, CANCELLED, TIMEOUT}
    RUNNING -> CANCELLED (user cancellation)

    Task:
    PENDING -> RUNNING -> {SUCCEEDED, FAILED, TIMEOUT, SKIPPED}
    RUNNING -> RETRYING -> RUNNING (retry loop)
    FAILED -> RETRYING -> RUNNING (retry after failure)
    """

    # Define allowed transitions as adjacency list
    WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"running", "cancelled"},  # Can cancel before starting
        "running": {"succeeded", "failed", "cancelled", "timeout"},
        "succeeded": set(),  # Terminal state
        "failed": set(),  # Terminal state
        "cancelled": set(),  # Terminal state
        "timeout": set(),  # Terminal state
    }

    TASK_TRANSITIONS: dict[str, set[str]] = {
        "pending": {
            "running",
            "skipped",
            "cancelled",
        },  # Can skip if dependency failed, or cancel
        "running": {"succeeded", "failed", "timeout", "retrying", "cancelled"},
        "retrying": {
            "running",
            "failed",
            "timeout",
            "cancelled",
        },  # Retry or give up, or cancel
        "succeeded": set(),  # Terminal state
        "failed": {"retrying"},  # Can retry after failure (if retries remaining)
        "timeout": set(),  # Terminal state
        "skipped": set(),  # Terminal state
        "cancelled": set(),  # Terminal state
    }

    def can_transition(
        self, from_status: str, to_status: str, entity_type: str = "workflow"
    ) -> bool:
        """
        Check if state transition is allowed

        Args:
            from_status: Current status (lowercase)
            to_status: Desired status (lowercase)
            entity_type: "workflow" or "task"

        Returns:
            True if transition is allowed, False otherwise
        """
        # Normalize to lowercase
        from_status = from_status.lower()
        to_status = to_status.lower()

        # Get transition map
        transitions = (
            self.WORKFLOW_TRANSITIONS if entity_type == "workflow" else self.TASK_TRANSITIONS
        )

        # Check if from_status exists
        if from_status not in transitions:
            return False

        # Check if to_status is in allowed set
        return to_status in transitions[from_status]

    def get_allowed_transitions(
        self, current_status: str, entity_type: str = "workflow"
    ) -> list[str]:
        """
        Get list of allowed next states

        Args:
            current_status: Current status (lowercase)
            entity_type: "workflow" or "task"

        Returns: List[Any] of allowed next statuses  # TODO(TYPE): replace Any with concrete type
        """
        current_status = current_status.lower()

        transitions = (
            self.WORKFLOW_TRANSITIONS if entity_type == "workflow" else self.TASK_TRANSITIONS
        )

        if current_status not in transitions:
            return []

        return sorted(list(transitions[current_status]))

    def validate_transition(
        self, from_status: str, to_status: str, entity_type: str = "workflow"
    ) -> None:
        """
        Validate transition and raise exception if invalid

        Args:
            from_status: Current status
            to_status: Desired status
            entity_type: "workflow" or "task"

        Raises:
            ValueError: If transition is not allowed
        """
        if not self.can_transition(from_status, to_status, entity_type):
            allowed = self.get_allowed_transitions(from_status, entity_type)
            raise ValueError(
                f"Invalid {entity_type} state transition: {from_status} -> {to_status}. "
                f"Allowed transitions from '{from_status}': {allowed}"
            )

    def is_terminal_state(self, status: str, entity_type: str = "workflow") -> bool:
        """
        Check if status is a terminal state (no further transitions)

        Args:
            status: Status to check
            entity_type: "workflow" or "task"

        Returns:
            True if terminal state (no outgoing transitions)
        """
        allowed = self.get_allowed_transitions(status, entity_type)
        return len(allowed) == 0


# Singleton instance
_state_machine = WorkflowStateMachine()


def get_state_machine() -> IStateMachine:
    """Get global state machine instance"""
    return _state_machine
