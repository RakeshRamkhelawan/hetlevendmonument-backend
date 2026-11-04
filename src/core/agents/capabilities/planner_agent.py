"""
Slice 3: PlannerAgent Implementation (GREEN Phase - Minimal Code)

Orchestrator that converts a scored procedure into an executable plan
with confidence-based routing decisions.

Responsibilities:
- Route decision based on confidence score
- Build execution steps appropriate for the decision
- Create structured execution plan
- Log all operations
- Enforce tenant isolation
"""

import logging

from src.core.agents.capabilities.schemas import (
    ExecutionDecision,
    ExecutionStep,
    PlannerResult,
    PlannerTask,
    ScoredProcedure,
)

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Planning orchestrator that converts a scored procedure into an executable plan.

    High confidence (>0.85) -> AUTO_EXECUTE
    Medium confidence (0.50-0.85) -> USER_CONFIRM
    Low confidence (<0.50) -> NO_MATCH
    """

    # Confidence thresholds for routing decisions
    AUTO_EXECUTE_THRESHOLD = 0.85
    USER_CONFIRM_THRESHOLD = 0.50

    def __init__(self) -> None:
        """Initialize PlannerAgent."""
        logger.info("PlannerAgent initialized")

    async def plan(self, task: PlannerTask) -> PlannerResult:
        """
        Convert a task with a scored procedure into an executable plan.

        Args:
            task: PlannerTask with a pre-selected scored procedure

        Returns:
            PlannerResult with execution plan and routing decision

        Raises:
            ValueError: If task validation fails
        """
        # Validate input
        self._validate_task(task)

        logger.info(
            f"Planning started for task with procedure {task.procedure.procedure_id} (tenant: {task.tenant_id})"
        )

        # Route decision based on confidence
        confidence = task.procedure.confidence_score
        decision = self._route_decision(confidence)

        # Build appropriate execution steps
        steps = self._build_steps(task.procedure, decision)

        # Determine if human approval required
        requires_approval = decision == ExecutionDecision.USER_CONFIRM

        # Create result
        result = PlannerResult(
            execution_plan=steps,
            estimated_duration_minutes=max(1, len(steps) * 5),  # Estimate 5 min per step
            confidence_in_plan=confidence,
            decision=decision,
            reasoning=self._generate_reasoning(task.procedure, decision),
            requires_human_approval=requires_approval,
        )

        logger.info(f"Plan created with decision: {decision.value} (confidence: {confidence:.2%})")

        return result

    def _validate_task(self, task: PlannerTask) -> None:
        """Validate task input."""
        if not task.user_intent:
            raise ValueError("user_intent is required")

        if not task.procedure:
            raise ValueError("procedure is required")

        if not task.tenant_id:
            raise ValueError("tenant_id is required")

        if not task.user_id:
            raise ValueError("user_id is required")

        # Validate confidence score
        if not (0.0 <= task.procedure.confidence_score <= 1.0):
            raise ValueError(
                f"confidence_score must be 0.0-1.0, got {task.procedure.confidence_score}"
            )

        logger.debug("Task validation passed")

    def _route_decision(self, confidence: float) -> ExecutionDecision:
        """
        Route decision based on confidence threshold.

        Args:
            confidence: Confidence score (0.0-1.0)

        Returns:
            ExecutionDecision (AUTO_EXECUTE / USER_CONFIRM / NO_MATCH)
        """
        if confidence > self.AUTO_EXECUTE_THRESHOLD:
            return ExecutionDecision.AUTO_EXECUTE

        elif confidence >= self.USER_CONFIRM_THRESHOLD:
            return ExecutionDecision.USER_CONFIRM

        else:
            return ExecutionDecision.NO_MATCH

    def _build_steps(
        self, procedure: ScoredProcedure, decision: ExecutionDecision
    ) -> list[ExecutionStep]:
        """
        Build execution steps based on decision.

        Args:
            procedure: ScoredProcedure
            decision: Routing decision

        Returns: List[Any] of ExecutionStep objects  # TODO(TYPE): replace Any with concrete type
        """
        if decision == ExecutionDecision.AUTO_EXECUTE:
            return self._build_auto_execute_steps(procedure)

        elif decision == ExecutionDecision.USER_CONFIRM:
            return self._build_user_confirm_steps(procedure)

        else:  # NO_MATCH
            return self._build_no_match_steps()

    def _build_auto_execute_steps(self, procedure: ScoredProcedure) -> list[ExecutionStep]:
        """Build steps for auto-execution."""
        return [
            ExecutionStep(
                step_number=1,
                action="execute",
                description=f"Execute procedure: {procedure.procedure_name}",
                parameters={
                    "procedure_id": str(procedure.procedure_id),
                    "procedure_name": procedure.procedure_name,
                    "domain_pack_id": str(procedure.domain_pack_id),
                },
                compliance_checks=["check_permissions", "check_tenant_scope"],
            )
        ]

    def _build_user_confirm_steps(self, procedure: ScoredProcedure) -> list[ExecutionStep]:
        """Build steps for user confirmation."""
        return [
            ExecutionStep(
                step_number=1,
                action="confirm",
                description=f"Request confirmation for: {procedure.procedure_name}",
                parameters={
                    "procedure_id": str(procedure.procedure_id),
                    "procedure_name": procedure.procedure_name,
                    "message": f"Proceed with {procedure.procedure_name}?",
                    "options": ["Approve", "Modify", "Reject"],
                    "timeout_seconds": 300,
                },
                compliance_checks=["check_user_authorization"],
            ),
            ExecutionStep(
                step_number=2,
                action="execute",
                description="Proceed with execution if approved",
                parameters={
                    "procedure_id": str(procedure.procedure_id),
                    "conditional": True,
                    "depends_on_step": 1,
                },
                compliance_checks=["check_permissions"],
            ),
        ]

    def _build_no_match_steps(self) -> list[ExecutionStep]:
        """Build steps for no-match (guidance)."""
        return [
            ExecutionStep(
                step_number=1,
                action="guidance",
                description="Unable to determine matching procedure",
                parameters={
                    "message": "Could not confidently match your intent to a procedure. Please provide more details.",
                    "suggested_actions": [
                        "Clarify your intent",
                        "Contact support",
                        "Try a different query",
                    ],
                },
                compliance_checks=[],
            )
        ]

    def _generate_reasoning(self, procedure: ScoredProcedure, decision: ExecutionDecision) -> str:
        """Generate reasoning for the decision."""
        if decision == ExecutionDecision.AUTO_EXECUTE:
            return f"High confidence ({procedure.confidence_score:.2%}) in '{procedure.procedure_name}' procedure. Auto-executing."

        elif decision == ExecutionDecision.USER_CONFIRM:
            return f"Medium confidence ({procedure.confidence_score:.2%}) in '{procedure.procedure_name}' procedure. User confirmation requested."

        else:  # NO_MATCH
            return f"Low confidence ({procedure.confidence_score:.2%}) in procedure match. Unable to execute without clarification."


__all__ = ["PlannerAgent"]
