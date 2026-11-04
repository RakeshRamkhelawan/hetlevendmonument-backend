"""
Scheduling Orchestrator Agent.

Orchestrates the scheduling workflow via OODA loop pattern.
Inherits from EnhancedBaseAgent for tenant isolation and learning.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.ai.explainability import ReasoningStepType
from src.core.shared.interfaces import ExecutionResult
from src.core.scheduling.schemas import SchedulingRequest as ScheduleRequest
from src.core.scheduling.services.scheduling_service import SchedulingService
from src.core.types import AgentType


class SchedulingOrchestratorAgent(EnhancedBaseAgent):
    """Orchestrates scheduling workflow for a single tenant.

    Implements full OODA loop:
    - Observe: Parse incoming scheduling requests and extract parameters
    - Orient: Analyze constraints, preferences, and availability context
    - Decide: Select optimal scheduling strategy and options
    - Act: Execute booking and return structured result

    Integrates with learning system via @auto_learn decorator.
    """

    def __init__(
        self,
        agent_id: str,
        tenant_id: int,
        scheduling_service: SchedulingService,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.ORCHESTRATOR,
            tenant_id=tenant_id,
        )
        self.scheduling_service = scheduling_service

    @classmethod
    async def create(
        cls,
        tenant_id: int,
        db_session: AsyncSession,
    ) -> "SchedulingOrchestratorAgent":
        """Factory method for dependency injection.

        Args:
            tenant_id: The tenant ID for isolation
            db_session: Database session for scheduling service

        Returns:
            Configured SchedulingOrchestratorAgent instance
        """
        return cls(
            agent_id=f"scheduling_orchestrator_{tenant_id}",
            tenant_id=tenant_id,
            scheduling_service=SchedulingService(db_session),
        )

    # =========================================================================
    # OODA Loop Implementation
    # =========================================================================

    async def observe(self, request_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Observe: Parse scheduling request and extract parameters.

        Args:
            request_data: Raw scheduling request data

        Returns:
            Structured observation with extracted parameters
        """
        observation: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": {
                "title": request_data.get("title", "Untitled Meeting"),
                "duration_minutes": request_data.get("duration_minutes", 30),
                "participants": request_data.get("participants", []),
                "preferred_dates": request_data.get("preferred_dates", []),
                "time_range": request_data.get("time_range", {}),
                "priority": request_data.get("priority", 3),
                "constraints": request_data.get("constraints", []),
            },
            "context": {
                "participant_count": len(request_data.get("participants", [])),
                "has_time_preference": bool(request_data.get("time_range")),
                "has_date_preference": bool(request_data.get("preferred_dates")),
            },
        }

        # Emit observation event for monitoring
        await self.emit_event(
            "scheduling_observation",
            {
                "tenant_id": self.tenant_id,
                "participant_count": observation["context"]["participant_count"],
                "has_constraints": len(observation["request"]["constraints"]) > 0,
            },
        )

        return observation

    async def orient(self, observation: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Orient: Analyze context, constraints, and availability.

        Args:
            observation: Structured observation from observe phase

        Returns:
            Orientation with context analysis and strategy hints
        """
        request = observation["request"]

        # Build orientation context
        orientation = {
            "observation": observation,
            "analysis": {
                "complexity_score": self._calculate_complexity(request),
                "urgency_level": self._assess_urgency(request),
                "flexibility_score": self._assess_flexibility(request),
            },
            "strategy_hints": {
                "use_smart_scheduling": len(request["participants"]) > 2,
                "check_all_participants": len(request["participants"]) > 1,
                "enforce_hard_constraints": any(
                    c.get("type") == "hard" for c in request["constraints"]
                ),
            },
            "constraints_summary": {
                "hard_constraints": [c for c in request["constraints"] if c.get("type") == "hard"],
                "soft_constraints": [c for c in request["constraints"] if c.get("type") == "soft"],
            },
        }

        # Add reasoning trace for explainability
        if self.reasoning_trace:
            self.reasoning_trace.add_step(
                ReasoningStepType.COMPLEXITY_ANALYSIS,
                f"Complexity: {orientation['analysis']['complexity_score']}, "
                f"Urgency: {orientation['analysis']['urgency_level']}",
                orientation["strategy_hints"],
            )

        return orientation

    async def decide(self, orientation: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Decide: Select optimal scheduling strategy.

        Args:
            orientation: Context analysis from orient phase

        Returns:
            Decision string representing chosen strategy
        """
        analysis = orientation["analysis"]
        hints = orientation["strategy_hints"]

        # Decision logic based on context analysis
        if analysis["urgency_level"] == "high":
            decision = "schedule_immediate"
        elif hints["use_smart_scheduling"]:
            decision = "schedule_smart"
        elif analysis["flexibility_score"] < 0.3:
            decision = "schedule_with_compromises"
        else:
            decision = "schedule_standard"

        # Record decision in reasoning trace
        if self.reasoning_trace:
            self.reasoning_trace.add_step(
                ReasoningStepType.MODEL_SELECTION,
                f"Selected strategy: {decision}",
                {"strategy": decision, "reasoning": analysis},
            )

        await self.emit_event(
            "scheduling_decision",
            {
                "tenant_id": self.tenant_id,
                "strategy": decision,
                "complexity": analysis["complexity_score"],
            },
        )

        return decision

    async def act(self, decision: str, orientation: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Act: Execute scheduling based on decision.

        Args:
            decision: Selected strategy from decide phase
            orientation: Full orientation context

        Returns:
            ExecutionResult with scheduling outcome
        """
        request_data = orientation["observation"]["request"]

        try:
            # Derive time window from time_range dict or use a 7-day default
            time_range: dict[str, Any] = request_data.get("time_range") or {}  # TODO(TYPE): replace Any with concrete type
            now = datetime.now(timezone.utc)
            earliest_start = (
                datetime.fromisoformat(time_range["start"]) if time_range.get("start") else now
            )
            latest_end = (
                datetime.fromisoformat(time_range["end"])
                if time_range.get("end")
                else now + timedelta(days=7)
            )

            # Build ScheduleRequest from orientation data
            schedule_request = ScheduleRequest(
                title=request_data["title"],
                duration_minutes=request_data["duration_minutes"],
                participants=request_data["participants"],
                earliest_start=earliest_start,
                latest_end=latest_end,
                priority=request_data["priority"],
            )

            organizer_id: str = str(request_data.get("organizer_id") or self.tenant_id)

            # Execute scheduling via service
            result = await self.scheduling_service.schedule_meeting(
                tenant_id=self.tenant_id,
                request=schedule_request,
                organizer_id=organizer_id,
            )

            # Format and return result
            message = self._format_response(result)

            return ExecutionResult(
                task_id=f"scheduling_{datetime.now(timezone.utc).timestamp()}",
                success=result.success if hasattr(result, "success") else True,
                result_data=result.model_dump(),
                error_message=(
                    None if (result.success if hasattr(result, "success") else True) else message
                ),
            )

        except Exception as exc:
            error_msg = f"Scheduling failed: {str(exc)}"
            await self.emit_event(
                "scheduling_error",
                {
                    "tenant_id": self.tenant_id,
                    "error": error_msg,
                    "decision": decision,
                },
            )
            return ExecutionResult(
                task_id=f"scheduling_{datetime.now(timezone.utc).timestamp()}",
                success=False,
                error_message=error_msg,
            )

    # =========================================================================
    # Main Execution Entry Point
    # =========================================================================

    async def process_scheduling_request(self, request_data: dict[str, Any]) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Process a scheduling request through full OODA loop.

        This is the main entry point for scheduling operations.

        Args:
            request_data: Raw scheduling request

        Returns:
            ExecutionResult with scheduling outcome
        """
        # OODA Loop execution
        observation = await self.observe(request_data)
        orientation = await self.orient(observation)
        decision = await self.decide(orientation)
        result = await self.act(decision, orientation)

        return result

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _calculate_complexity(self, request: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate scheduling complexity score (0-1).

        Args:
            request: Scheduling request data

        Returns:
            Complexity score between 0.0 and 1.0
        """
        score = 0.0
        participant_count = len(request.get("participants", []))
        constraint_count = len(request.get("constraints", []))

        # More participants = more complex
        if participant_count > 5:
            score += 0.4
        elif participant_count > 2:
            score += 0.2

        # More constraints = more complex
        if constraint_count > 3:
            score += 0.3
        elif constraint_count > 0:
            score += 0.1

        # Date/time restrictions add complexity
        if request.get("preferred_dates"):
            score += 0.2
        if request.get("time_range"):
            score += 0.1

        return min(score, 1.0)

    def _assess_urgency(self, request: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Assess urgency level based on priority and constraints.

        Args:
            request: Scheduling request data

        Returns:
            Urgency level as "high", "medium", or "low"
        """
        priority = request.get("priority", 3)

        if priority >= 8:
            return "high"
        elif priority >= 5:
            return "medium"
        return "low"

    def _assess_flexibility(self, request: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Assess scheduling flexibility (0-1, higher = more flexible).

        Args:
            request: Scheduling request data

        Returns:
            Flexibility score between 0.0 and 1.0
        """
        score = 1.0

        # Preferred dates reduce flexibility
        if request.get("preferred_dates"):
            score -= 0.2

        # Time range restrictions reduce flexibility
        if request.get("time_range"):
            score -= 0.15

        # Constraints reduce flexibility
        constraint_count = len(request.get("constraints", []))
        score -= min(constraint_count * 0.1, 0.3)

        return max(score, 0.0)

    def _format_response(self, result: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format a SchedulingResult into a human-readable message.

        Args:
            result: SchedulingResult object with success, event_id, or error info

        Returns:
            Human-readable message describing the scheduling outcome
        """
        if hasattr(result, "success") and result.success:
            event_id = getattr(result, "event_id", None) or getattr(
                result, "scheduled_event_id", "unknown"
            )
            return f"Meeting scheduled successfully (event: {event_id})"
        message = getattr(result, "message", None) or ", ".join(
            getattr(result, "conflicts", []) or ["No slots available"]
        )
        return f"Could not schedule meeting: {message}"
