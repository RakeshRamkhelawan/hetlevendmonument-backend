"""
Observation Service - Handles learning observation recording and management.

This service is responsible for:
- Recording new observations
- Managing observation buffers
- Persisting observations to database
- Triggering pattern analysis when thresholds are reached
"""

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from src.core.shared.learning_audit import log_learning_audit_event
from src.core.learning.metrics import record_learning_observation

if TYPE_CHECKING:
    from src.core.agents.learning_loop import (
        LearningObservation,
        LearningRepository,
        LearningSource,
        LearningType,
    )
    from src.core.learning.services.adaptation_service import AdaptationService
    from src.core.learning.services.insight_service import InsightService
    from src.core.learning.services.pattern_service import PatternService

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter for observation recording.

    P2 FIX: Prevents DoS attacks by limiting observation rate.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: deque[datetime] = deque()

    def is_allowed(self) -> bool:
        """Check if request is within rate limit."""
        now = datetime.now(timezone.utc)

        # Remove old requests outside window
        while self._requests and (now - self._requests[0]).seconds > self.window_seconds:
            self._requests.popleft()

        # Check if under limit
        if len(self._requests) < self.max_requests:
            self._requests.append(now)
            return True

        return False

    def get_wait_time(self) -> float:
        """Get seconds to wait before next allowed request."""
        if not self._requests:
            return 0.0

        oldest = self._requests[0]
        elapsed = (datetime.now(timezone.utc) - oldest).total_seconds()
        return max(0.0, self.window_seconds - elapsed)


class ObservationService:
    """Service for managing learning observations."""

    def __init__(
        self,
        tenant_id: int,
        repository: Optional["LearningRepository"] = None,
        observation_threshold: int = 50,
        rate_limit_max: int = 100,  # P2: Max observations per minute
    ) -> None:
        self.tenant_id = tenant_id
        self._repository = repository
        self.observation_threshold = observation_threshold

        # P2 FIX: Rate limiter to prevent DoS
        self._rate_limiter = RateLimiter(max_requests=rate_limit_max, window_seconds=60)

        # In-memory storage
        self.observations: dict[str, "LearningObservation"] = {}
        self.observation_buffer: deque["LearningObservation"] = deque(maxlen=1000)

        # Metrics
        self.total_observations = 0
        self._pattern_service: Optional["PatternService"] = None
        self._adaptation_service: Optional["AdaptationService"] = None
        self._insight_service: Optional["InsightService"] = None

    @property
    def pattern_service(self) -> "PatternService":
        """Lazily construct the pattern service for observation analysis."""
        if self._pattern_service is None:
            from src.core.learning.services.pattern_service import PatternService

            self._pattern_service = PatternService(
                tenant_id=self.tenant_id,
                repository=self._repository,
            )
        return self._pattern_service

    @property
    def adaptation_service(self) -> "AdaptationService":
        """Lazily construct the adaptation service for learned patterns."""
        if self._adaptation_service is None:
            from src.core.learning.services.adaptation_service import AdaptationService

            self._adaptation_service = AdaptationService(
                tenant_id=self.tenant_id,
                repository=self._repository,
            )
        return self._adaptation_service

    @property
    def insight_service(self) -> "InsightService":
        """Lazily construct the insight service for generated insights."""
        if self._insight_service is None:
            from src.core.learning.services.insight_service import InsightService

            self._insight_service = InsightService(
                tenant_id=self.tenant_id,
                repository=self._repository,
            )
        return self._insight_service

    async def record(
        self,
        source: "LearningSource",
        learning_type: "LearningType",
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        observation_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        outcome_metrics: dict[str, float] | None = None,
        importance_score: float = 0.5,
        confidence_score: float = 0.8,
    ) -> str:
        """Record a learning observation with transactional consistency.

        P1 FIX: Uses write-ahead pattern - database write happens BEFORE
        in-memory update to ensure consistency.

        P2 FIX: Rate limiting prevents DoS attacks.

        Args:
            source: Source of the learning data
            learning_type: Type of learning
            context: Contextual information
            observation_data: The actual observation data
            outcome_metrics: Metrics about the outcome
            importance_score: Importance of this observation (0-1)
            confidence_score: Confidence in this observation (0-1)

        Returns:
            observation_id: Unique ID of the recorded observation

        Raises:
            RuntimeError: If database persistence fails
            RateLimitExceeded: If rate limit is exceeded
        """
        # P2 FIX: Check rate limit
        if not self._rate_limiter.is_allowed():
            wait_time = self._rate_limiter.get_wait_time()
            raise RuntimeError(f"Rate limit exceeded. Please wait {wait_time:.1f} seconds.")

        from src.core.agents.learning_loop import LearningObservation

        observation_id = str(uuid.uuid4())

        observation = LearningObservation(
            id=observation_id,
            timestamp=datetime.now(timezone.utc),
            source=source,
            learning_type=learning_type,
            context=context,
            observation_data=observation_data,
            outcome_metrics=outcome_metrics or {},
            confidence_score=confidence_score,
            importance_score=importance_score,
        )

        # P1 FIX: Write-ahead pattern - persist to database FIRST
        if self._repository:
            try:
                await self._repository.save_observation(self.tenant_id, observation)
            except Exception as exc:
                logger.error("Failed to persist observation %s: %s", observation_id, exc)
                raise RuntimeError(f"Failed to persist observation: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.observations[observation_id] = observation
        self.observation_buffer.append(observation)
        self.total_observations += 1
        record_learning_observation(self.tenant_id, learning_type.value)
        await log_learning_audit_event(
            action="learning.observation_created",
            tenant_id=self.tenant_id,
            resource=f"observation:{observation_id}",
            details={
                "learning_type": learning_type.value,
                "agent_id": context.get("agent_id"),
                "task_type": context.get("task_type"),
            },
        )

        if self.should_trigger_analysis():
            await self.analyze_recent_observations()

        logger.debug("Observation recorded: %s (%s)", observation_id, learning_type.value)
        return observation_id

    async def analyze_recent_observations(
        self,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Analyze the current observation buffer and create learning artifacts."""
        if len(self.observation_buffer) < self.observation_threshold:
            return None

        observations = list(self.observation_buffer)
        if not observations:
            return None

        latest = observations[-1]
        success_values = [obs.outcome_metrics.get("success", 0.0) for obs in observations]
        confidence_values = [obs.confidence_score for obs in observations]
        success_rate = sum(success_values) / len(success_values) if success_values else 0.0
        confidence_score = (
            sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        )

        trigger_conditions = {
            "agent_id": latest.context.get("agent_id"),
            "agent_type": latest.context.get("agent_type"),
            "task_type": latest.context.get("task_type"),
            "source": latest.source.value,
        }
        learned_behavior = {
            "recommended_action": "prioritize_successful_execution_path",
            "source": latest.source.value,
            "learning_type": latest.learning_type.value,
            "average_execution_time": sum(
                obs.outcome_metrics.get("execution_time", 0.0) for obs in observations
            )
            / len(observations),
        }
        user_id = latest.context.get("user_id") or latest.observation_data.get("user_id")
        if user_id is not None:
            normalized_user_id = str(user_id)
            trigger_conditions["user_id"] = normalized_user_id
            learned_behavior["user_id"] = normalized_user_id

        try:
            pattern = await self.pattern_service.register(
                pattern_type=latest.learning_type,
                trigger_conditions=trigger_conditions,
                learned_behavior=learned_behavior,
                observation_count=len(observations),
                success_rate=success_rate,
                confidence_score=confidence_score,
            )
        except Exception as exc:
            logger.warning("Pattern analysis failed for tenant %s: %s", self.tenant_id, exc)
            return None

        result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "pattern": pattern,
            "rule": None,
            "insight": None,
        }  # TODO(TYPE): replace Any with concrete type

        if latest.context.get("task_type") == "tool_execution":
            try:
                result["tool_patterns"] = await self.pattern_service.analyze_tool_patterns(
                    observations
                )
            except Exception as exc:
                logger.warning(
                    "Tool pattern analysis failed for tenant %s: %s",
                    self.tenant_id,
                    exc,
                )

        if confidence_score >= self.pattern_service.confidence_threshold:
            try:
                from src.core.learning.cross_agent_service import CrossAgentLearningService

                cross_agent_service = CrossAgentLearningService(
                    tenant_id=self.tenant_id,
                    pattern_service=self.pattern_service,
                )
                result["shared_patterns"] = await cross_agent_service.share_pattern(
                    pattern,
                    trigger_conditions.get("agent_type"),
                )
            except Exception as exc:
                logger.warning(
                    "Cross-agent sharing failed for tenant %s: %s",
                    self.tenant_id,
                    exc,
                )

        if confidence_score >= self.pattern_service.confidence_threshold:
            try:
                rule = await self.adaptation_service.create_from_pattern(pattern)
                result["rule"] = rule
            except Exception as exc:
                logger.warning(
                    "Adaptation rule creation failed for tenant %s: %s",
                    self.tenant_id,
                    exc,
                )

            try:
                insight = await self.insight_service.generate(
                    title="Execution pattern detected",
                    description=(
                        "Observed a repeated execution pattern for "
                        f"{trigger_conditions.get('agent_type') or 'unknown_agent'}"
                    ),
                    insight_type=latest.learning_type,
                    supporting_observations=[obs.id for obs in observations],
                    confidence_score=confidence_score,
                    impact_assessment={
                        "success_rate": success_rate,
                        "observation_count": float(len(observations)),
                        "user_id": str(user_id) if user_id is not None else None,
                    },
                    recommended_actions=[
                        "Promote the successful execution path in future planning"
                    ],
                )
                result["insight"] = insight
            except Exception as exc:
                logger.warning(
                    "Insight generation failed for tenant %s: %s",
                    self.tenant_id,
                    exc,
                )

        return result

    def get_recent(self, limit: int = 100) -> list["LearningObservation"]:
        """Get recent observations from buffer."""
        return list(self.observation_buffer)[-limit:]

    def get_by_id(self, observation_id: str) -> Optional["LearningObservation"]:
        """Get a specific observation by ID."""
        return self.observations.get(observation_id)

    def should_trigger_analysis(self) -> bool:
        """Check if pattern analysis should be triggered."""
        return len(self.observation_buffer) >= self.observation_threshold

    def clear_buffer(self) -> None:
        """Clear the observation buffer."""
        self.observation_buffer.clear()

    async def load_from_db(self) -> None:
        """Load recent observations from database."""
        if not self._repository:
            return

        try:
            observations = await self._repository.get_recent_observations(self.tenant_id, limit=100)
            for obs in observations:
                self.observations[obs.id] = obs
            logger.info(
                "Loaded %d observations from database for tenant %s",
                len(observations),
                self.tenant_id,
            )
        except Exception as exc:
            logger.error("Failed to load observations from database: %s", exc)
            raise
