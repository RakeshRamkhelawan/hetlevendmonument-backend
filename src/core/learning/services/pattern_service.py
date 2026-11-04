"""
Pattern Service - Handles pattern recognition and management.

This service is responsible for:
- Pattern identification from observations
- Pattern storage and retrieval
- Pattern matching and similarity detection
- Pattern statistics tracking
"""

import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from src.core.shared.learning_audit import log_learning_audit_event
from src.core.learning.metrics import set_learning_patterns_active
from src.core.shared.config import get_feature_flag

if TYPE_CHECKING:
    from src.core.agents.learning_loop import (
        LearningObservation,
        LearningPattern,
        LearningRepository,
        LearningType,
    )

logger = logging.getLogger(__name__)


class PatternService:
    """Service for managing learned patterns."""

    TOOLBROKER_PATTERN_TYPES: tuple[str, str, str, str] = (
        "tool_usage_frequency",
        "tool_failure_correlation",
        "circuit_breaker_trigger",
        "tool_chain_optimization",
    )

    def __init__(
        self,
        tenant_id: int,
        repository: Optional["LearningRepository"] = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.tenant_id = tenant_id
        self._repository = repository
        self.confidence_threshold = confidence_threshold

        # In-memory storage
        self.patterns: dict[str, "LearningPattern"] = {}
        self.pattern_buffer: deque["LearningPattern"] = deque(maxlen=100)

        # Metrics
        self.patterns_learned = 0

    async def register(
        self,
        pattern_type: "LearningType",
        trigger_conditions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        learned_behavior: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        observation_count: int = 1,
        success_rate: float = 0.5,
        confidence_score: float = 0.5,
    ) -> "LearningPattern":
        """Register a new pattern with transactional consistency.

        P1 FIX: Uses write-ahead pattern - database write happens BEFORE
        in-memory update to ensure consistency.

        Args:
            pattern_type: Type of pattern
            trigger_conditions: Conditions that trigger this pattern
            learned_behavior: The behavior learned from this pattern
            observation_count: Number of observations supporting this pattern
            success_rate: Success rate of this pattern (0-1)
            confidence_score: Confidence in this pattern (0-1)

        Returns:
            The registered LearningPattern

        Raises:
            RuntimeError: If database persistence fails
        """
        from src.core.agents.learning_loop import LearningPattern

        pattern_id = str(uuid.uuid4())

        pattern = LearningPattern(
            id=pattern_id,
            pattern_type=pattern_type,
            description=f"Pattern {pattern_id}",
            trigger_conditions=trigger_conditions,
            learned_behavior=learned_behavior,
            observation_count=observation_count,
            success_rate=success_rate,
            confidence_score=confidence_score,
            last_updated=datetime.now(timezone.utc),
        )

        # Check for similar existing patterns
        similar = self._find_similar(pattern)
        if similar:
            # Update existing pattern
            similar.observation_count += observation_count
            similar.success_rate = (similar.success_rate + success_rate) / 2
            similar.confidence_score = (similar.confidence_score + confidence_score) / 2
            similar.last_updated = datetime.now(timezone.utc)

            # Persist update
            if self._repository:
                try:
                    await self._repository.save_pattern(self.tenant_id, similar)
                except Exception as exc:
                    logger.error("Failed to update pattern %s: %s", similar.id, exc)
                    raise RuntimeError(f"Failed to update pattern: {exc}") from exc

            set_learning_patterns_active(self.tenant_id, len(self.get_active()))
            await log_learning_audit_event(
                action="learning.pattern_detected",
                tenant_id=self.tenant_id,
                resource=f"pattern:{similar.id}",
                details={"pattern_type": str(similar.pattern_type), "updated": True},
            )
            logger.info("Pattern updated: %s (v%s)", similar.id, getattr(similar, "version", 1))
            return similar

        # P1 FIX: Write-ahead pattern - persist to database FIRST
        if self._repository:
            try:
                await self._repository.save_pattern(self.tenant_id, pattern)
            except Exception as exc:
                logger.error("Failed to persist pattern %s: %s", pattern_id, exc)
                raise RuntimeError(f"Failed to persist pattern: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.patterns[pattern_id] = pattern
        self.pattern_buffer.append(pattern)
        self.patterns_learned += 1
        set_learning_patterns_active(self.tenant_id, len(self.get_active()))
        await log_learning_audit_event(
            action="learning.pattern_detected",
            tenant_id=self.tenant_id,
            resource=f"pattern:{pattern_id}",
            details={
                "pattern_type": (
                    pattern_type.value if hasattr(pattern_type, "value") else str(pattern_type)
                )
            },
        )

        logger.info(
            "New pattern registered: %s (%s)",
            pattern_id,
            pattern_type.value if hasattr(pattern_type, "value") else pattern_type,
        )
        return pattern

    def _find_similar(self, pattern: "LearningPattern") -> Optional["LearningPattern"]:
        """Find a similar existing pattern."""
        for existing in self.patterns.values():
            if self._is_similar(existing, pattern):
                return existing
        return None

    def _is_similar(self, p1: "LearningPattern", p2: "LearningPattern") -> bool:
        """Check if two patterns are similar."""
        # Compare pattern types
        if p1.pattern_type != p2.pattern_type:
            return False

        # Compare trigger conditions (simplified)
        p1_conditions = json.dumps(p1.trigger_conditions, sort_keys=True)
        p2_conditions = json.dumps(p2.trigger_conditions, sort_keys=True)

        # Consider similar if conditions match significantly
        return p1_conditions == p2_conditions

    def get_active(self) -> list["LearningPattern"]:
        """Get all active patterns with high confidence."""
        return [
            p for p in self.patterns.values() if p.confidence_score >= self.confidence_threshold
        ]

    def get_by_type(self, pattern_type: "LearningType") -> list["LearningPattern"]:
        """Get patterns by type."""
        return [p for p in self.patterns.values() if p.pattern_type == pattern_type]

    def get_by_id(self, pattern_id: str) -> Optional["LearningPattern"]:
        """Get a specific pattern by ID."""
        return self.patterns.get(pattern_id)

    def get_patterns_by_agent_type(self, agent_type: str | None) -> list["LearningPattern"]:
        """Return patterns for a specific agent type, or all patterns when omitted."""
        normalized = (agent_type or "").strip().lower()
        patterns = list(self.patterns.values())
        if not normalized:
            return patterns
        return [
            pattern
            for pattern in patterns
            if str(pattern.trigger_conditions.get("agent_type", "")).strip().lower() == normalized
        ]

    async def analyze_tool_patterns(
        self,
        observations: list["LearningObservation"],
    ) -> list["LearningPattern"]:
        """Detect and register ToolBroker-specific patterns from observations."""
        from src.core.agents.learning_loop import LearningType

        tool_observations = [
            obs
            for obs in observations
            if obs.observation_data.get("tool_name")
            or obs.context.get("task_type") == "tool_execution"
        ]
        if not tool_observations:
            return []

        registered: list["LearningPattern"] = []

        async def _register_tool_pattern(
            subtype: str,
            trigger_conditions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
            learned_behavior: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
            observation_count: int,
            success_rate: float,
            confidence_score: float,
        ) -> None:
            if confidence_score < self.confidence_threshold:
                return
            pattern = await self.register(
                pattern_type=LearningType.PATTERN_RECOGNITION,
                trigger_conditions=trigger_conditions,
                learned_behavior=learned_behavior,
                observation_count=observation_count,
                success_rate=success_rate,
                confidence_score=confidence_score,
            )
            registered.append(pattern)

        by_tool: dict[str, list["LearningObservation"]] = {}
        for observation in tool_observations:
            tool_name = observation.observation_data.get("tool_name")
            if not tool_name:
                continue
            by_tool.setdefault(str(tool_name), []).append(observation)

        for tool_name, tool_group in by_tool.items():
            if len(tool_group) >= 10:
                representative = tool_group[-1]
                avg_success = sum(
                    obs.outcome_metrics.get("success", 0.0) for obs in tool_group
                ) / len(tool_group)
                await _register_tool_pattern(
                    subtype="tool_usage_frequency",
                    trigger_conditions={
                        "agent_id": representative.context.get("agent_id"),
                        "agent_type": representative.context.get("agent_type"),
                        "task_type": "tool_execution",
                        "tool_name": tool_name,
                        "pattern_subtype": "tool_usage_frequency",
                    },
                    learned_behavior={
                        "preferred_tool": tool_name,
                        "pattern_subtype": "tool_usage_frequency",
                        "usage_count": len(tool_group),
                    },
                    observation_count=len(tool_group),
                    success_rate=avg_success,
                    confidence_score=min(0.95, 0.7 + len(tool_group) / 100.0),
                )

        failed_groups: dict[tuple[str, str], list["LearningObservation"]] = {}
        for observation in tool_observations:
            if observation.observation_data.get("success", True):
                continue
            tool_name = str(observation.observation_data.get("tool_name", ""))
            payload = json.dumps(observation.observation_data.get("payload", {}), sort_keys=True)
            failed_groups.setdefault((tool_name, payload), []).append(observation)

        for (tool_name, payload_signature), failed_group in failed_groups.items():
            if len(failed_group) < 3:
                continue
            representative = failed_group[-1]
            await _register_tool_pattern(
                subtype="tool_failure_correlation",
                trigger_conditions={
                    "agent_id": representative.context.get("agent_id"),
                    "agent_type": representative.context.get("agent_type"),
                    "task_type": "tool_execution",
                    "tool_name": tool_name,
                    "payload_signature": payload_signature,
                    "pattern_subtype": "tool_failure_correlation",
                },
                learned_behavior={
                    "pattern_subtype": "tool_failure_correlation",
                    "failure_count": len(failed_group),
                    "recommended_action": "avoid_payload_signature",
                },
                observation_count=len(failed_group),
                success_rate=0.0,
                confidence_score=min(0.95, 0.7 + len(failed_group) / 10.0),
            )

        circuit_breaker_groups: dict[str, list["LearningObservation"]] = {}
        for observation in tool_observations:
            error_text = str(observation.observation_data.get("error", "")).lower()
            if "circuit breaker" not in error_text:
                continue
            tool_name = str(observation.observation_data.get("tool_name", ""))
            circuit_breaker_groups.setdefault(tool_name, []).append(observation)

        for tool_name, breaker_group in circuit_breaker_groups.items():
            if len(breaker_group) < 3:
                continue
            representative = breaker_group[-1]
            await _register_tool_pattern(
                subtype="circuit_breaker_trigger",
                trigger_conditions={
                    "agent_id": representative.context.get("agent_id"),
                    "agent_type": representative.context.get("agent_type"),
                    "task_type": "tool_execution",
                    "tool_name": tool_name,
                    "pattern_subtype": "circuit_breaker_trigger",
                },
                learned_behavior={
                    "pattern_subtype": "circuit_breaker_trigger",
                    "breaker_open_count": len(breaker_group),
                    "recommended_action": "switch_tool_or_backoff",
                },
                observation_count=len(breaker_group),
                success_rate=0.0,
                confidence_score=min(0.95, 0.7 + len(breaker_group) / 10.0),
            )

        chain_groups: dict[tuple[str, str, str, str], int] = {}
        for previous, current in zip(tool_observations, tool_observations[1:]):
            if previous.context.get("agent_id") != current.context.get("agent_id"):
                continue
            first_tool = str(previous.observation_data.get("tool_name", ""))
            second_tool = str(current.observation_data.get("tool_name", ""))
            if not first_tool or not second_tool:
                continue
            key = (
                str(previous.context.get("agent_id", "")),
                str(previous.context.get("agent_type", "")),
                first_tool,
                second_tool,
            )
            chain_groups[key] = chain_groups.get(key, 0) + 1

        for (
            agent_id,
            agent_type,
            first_tool,
            second_tool,
        ), count in chain_groups.items():
            if count < 5:
                continue
            await _register_tool_pattern(
                subtype="tool_chain_optimization",
                trigger_conditions={
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "task_type": "tool_execution",
                    "tool_chain": [first_tool, second_tool],
                    "pattern_subtype": "tool_chain_optimization",
                },
                learned_behavior={
                    "pattern_subtype": "tool_chain_optimization",
                    "optimized_chain": [first_tool, second_tool],
                    "sequence_count": count,
                },
                observation_count=count,
                success_rate=1.0,
                confidence_score=min(0.95, 0.7 + count / 20.0),
            )

        return registered

    async def update_stats(
        self,
        pattern_id: str,
        occurrence_count: int,
        success_rate: float,
    ) -> None:
        """Update pattern statistics."""
        if not get_feature_flag("learning_enabled"):
            return

        pattern = self.patterns.get(pattern_id)
        if pattern:
            pattern.observation_count = occurrence_count
            pattern.success_rate = success_rate
            pattern.last_updated = datetime.now(timezone.utc)

        if self._repository:
            try:
                await self._repository.update_pattern_stats(
                    pattern_id, occurrence_count, success_rate
                )
            except Exception as exc:
                logger.error("Failed to update pattern stats: %s", exc)
                raise

    async def load_from_db(self) -> None:
        """Load patterns from database."""
        if not self._repository:
            return

        try:
            patterns = await self._repository.get_active_patterns(self.tenant_id)
            for pattern in patterns:
                self.patterns[pattern.id] = pattern
            logger.info(
                "Loaded %d patterns from database for tenant %s",
                len(patterns),
                self.tenant_id,
            )
        except Exception as exc:
            logger.error("Failed to load patterns from database: %s", exc)
            raise
