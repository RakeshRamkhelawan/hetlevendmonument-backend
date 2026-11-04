"""DomainPackOrchestrator -- enforces Golden Rule R1 before each step.

Thin layer over MultiPackAssembler that:
1. Builds AgentExecutionContext for each step
2. Calls GoalAlignmentValidator before execution
3. Raises GoalMisalignmentError for MISALIGNED results (blocks execution)
"""

from __future__ import annotations

from src.core.company.context import AgentExecutionContext
from src.core.company.goal_alignment import GoalAlignmentValidator


class GoalMisalignmentError(RuntimeError):
    """Raised when a proposed action is misaligned with the goal chain."""

    def __init__(self, action: str, reason: str) -> None:
        super().__init__(f"Action '{action}' is MISALIGNED: {reason}")
        self.action = action
        self.reason = reason


class DomainPackOrchestrator:
    """Validates goal alignment (R1) before delegating to execution."""

    def __init__(self) -> None:
        self._validator = GoalAlignmentValidator()

    async def validate_step(
        self,
        proposed_action: str,
        context: AgentExecutionContext,
    ) -> None:
        """Validate proposed_action against context.goal_chain.

        Raises:
            GoalMisalignmentError: if status == "MISALIGNED"
        """
        result = await self._validator.validate(proposed_action, context)
        if result.status == "MISALIGNED":
            raise GoalMisalignmentError(proposed_action, result.reason)
