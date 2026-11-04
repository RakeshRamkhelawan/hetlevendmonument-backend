"""Deprecated compatibility engine for pre-LearningMixin learning flows.

The canonical runtime path for agent learning is now ``LearningMixin`` plus the
observation, pattern, insight, and adaptation services. This engine is retained
only for older endpoint and compatibility scenarios.
"""

import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from src.core.database.session import get_db_session
from src.core.learning.models import LearningExperience  # Phase 6 Task 6: Migrated to domain module

logger = logging.getLogger(__name__)


class LearningEventType(str, Enum):
    """Types of learning events"""

    TASK_COMPLETION = "task_completion"
    AGENT_PERFORMANCE = "agent_performance"
    USER_FEEDBACK = "user_feedback"
    SYSTEM_OPTIMIZATION = "system_optimization"
    ERROR_PATTERN = "error_pattern"
    SUCCESS_PATTERN = "success_pattern"


class AdaptationStrategy(str, Enum):
    """Adaptation strategies for learning"""

    IMMEDIATE = "immediate"
    GRADUAL = "gradual"
    THRESHOLD_BASED = "threshold_based"
    COLLABORATIVE = "collaborative"


@dataclass
class LearningPattern:
    """Identified learning pattern"""

    pattern_id: str
    pattern_type: str
    confidence: float
    occurrences: int
    last_seen: datetime
    metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


@dataclass
class AdaptationRule:
    """Rule for system adaptation"""

    rule_id: str
    condition: str
    action: str
    confidence: float
    priority: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    applied_count: int = 0


class LearningEngine:
    """
    Production adaptive learning engine for multi-agent system
    Implements continuous learning and system optimization
    """

    def __init__(self) -> None:
        # Learning data storage
        self.learning_patterns: dict[str, LearningPattern] = {}
        self.adaptation_rules: dict[str, AdaptationRule] = {}
        self.performance_history: dict[str, deque[dict[str, Any]]] = defaultdict(  # TODO(TYPE): Any
            lambda: deque(maxlen=100)
        )

        # Learning metrics
        self.total_events_processed = 0
        self.patterns_identified = 0
        self.adaptations_applied = 0
        self.learning_accuracy = 0.0

        # Configuration
        self.pattern_confidence_threshold = 0.7
        self.adaptation_threshold = 0.8
        self.learning_window = timedelta(hours=24)
        self.max_patterns = 1000

        logger.info("Adaptive learning engine initialized")

    async def record_learning_event(
        self,
        event_type: LearningEventType,
        agent_id: str | None = None,
        task_type: str | None = None,
        success: bool = True,
        duration: float | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        metrics: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        user_id: str | None = None,
        session_id: str | None = None,
        confidence: float = 1.0,
    ) -> str:
        """
        Record learning event for analysis

        Returns:
            event_id: Unique event identifier
        """
        event_id = f"event_{uuid4().hex[:8]}"

        # Create learning experience for database persistence
        try:
            async with get_db_session() as session:
                learning_experience = LearningExperience(
                    event_id=event_id,
                    event_type=event_type.value,
                    agent_id=agent_id,
                    task_type=task_type,
                    success=success,
                    duration=duration,
                    context=context or {},
                    metrics=metrics or {},
                    user_id=user_id,
                    session_id=session_id,
                    confidence=confidence,
                )

                session.add(learning_experience)
                await session.commit()

        except Exception as e:
            logger.error(f"Failed to persist learning event: {e}")

        # Update in-memory learning data
        await self._process_learning_event(
            event_id=event_id,
            event_type=event_type,
            agent_id=agent_id,
            task_type=task_type,
            success=success,
            duration=duration,
            context=context or {},
            metrics=metrics or {},
        )

        self.total_events_processed += 1

        logger.debug(f"Learning event recorded: {event_id} ({event_type})")
        return event_id

    async def _process_learning_event(
        self,
        event_id: str,
        event_type: LearningEventType,
        agent_id: str | None,
        task_type: str | None,
        success: bool,
        duration: float | None,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Process learning event for pattern identification"""

        # Update performance history
        if agent_id:
            self.performance_history[agent_id].append(
                {
                    "event_id": event_id,
                    "success": success,
                    "duration": duration,
                    "timestamp": datetime.now(timezone.utc),
                    "task_type": task_type,
                }
            )

        # Identify patterns
        await self._identify_patterns(
            event_type, agent_id, task_type, success, duration, context, metrics
        )

        # Check for adaptation opportunities
        await self._check_adaptation_opportunities()

    async def _identify_patterns(
        self,
        event_type: LearningEventType,
        agent_id: str | None,
        task_type: str | None,
        success: bool,
        duration: float | None,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Identify learning patterns from events"""

        # Pattern 1: Agent performance trends
        if agent_id and event_type == LearningEventType.TASK_COMPLETION:
            await self._analyze_agent_performance_pattern(agent_id, task_type, success, duration)

        # Pattern 2: Task type success rates
        if task_type and event_type == LearningEventType.TASK_COMPLETION:
            await self._analyze_task_success_pattern(task_type, success, duration)

        # Pattern 3: Error patterns
        if not success and event_type == LearningEventType.TASK_COMPLETION:
            await self._analyze_error_pattern(agent_id, task_type, context)

        # Pattern 4: Performance optimization opportunities
        if success and duration and event_type == LearningEventType.TASK_COMPLETION:
            await self._analyze_optimization_pattern(agent_id, task_type, duration, metrics)

    async def _analyze_agent_performance_pattern(
        self,
        agent_id: str,
        task_type: str | None,
        success: bool,
        duration: float | None,
    ) -> None:
        """Analyze agent performance patterns"""
        pattern_key = f"agent_performance_{agent_id}_{task_type or 'all'}"

        if pattern_key not in self.learning_patterns:
            self.learning_patterns[pattern_key] = LearningPattern(
                pattern_id=pattern_key,
                pattern_type="agent_performance",
                confidence=0.0,
                occurrences=0,
                last_seen=datetime.now(timezone.utc),
            )

        pattern = self.learning_patterns[pattern_key]
        pattern.occurrences += 1
        pattern.last_seen = datetime.now(timezone.utc)

        # Calculate performance metrics
        agent_history = list(self.performance_history[agent_id])
        if len(agent_history) >= 5:  # Minimum sample size
            success_rate = sum(1 for event in agent_history if event["success"]) / len(
                agent_history
            )
            avg_duration = statistics.mean(
                [event["duration"] for event in agent_history if event["duration"]]
            )

            # Update pattern metadata
            pattern.metadata.update(
                {
                    "success_rate": success_rate,
                    "average_duration": avg_duration,
                    "sample_size": len(agent_history),
                    "trend": self._calculate_trend(agent_history),
                }
            )

            # Update confidence based on data quality
            pattern.confidence = min(0.95, len(agent_history) / 50.0 + success_rate * 0.5)

            # Check if adaptation is needed
            if success_rate < 0.7 and pattern.confidence > self.pattern_confidence_threshold:
                await self._create_adaptation_rule(
                    f"improve_{agent_id}_performance",
                    f"agent_success_rate < 0.7 AND agent_id == '{agent_id}'",
                    "adjust_agent_parameters",
                    confidence=pattern.confidence,
                )

    async def _analyze_task_success_pattern(
        self, task_type: str, success: bool, duration: float | None
    ) -> None:
        """Analyze task type success patterns"""
        pattern_key = f"task_success_{task_type}"

        if pattern_key not in self.learning_patterns:
            self.learning_patterns[pattern_key] = LearningPattern(
                pattern_id=pattern_key,
                pattern_type="task_success",
                confidence=0.0,
                occurrences=0,
                last_seen=datetime.now(timezone.utc),
            )

        pattern = self.learning_patterns[pattern_key]
        pattern.occurrences += 1
        pattern.last_seen = datetime.now(timezone.utc)

        # Analyze success rates across all agents for this task type
        task_events: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_history in self.performance_history.values():
            task_events.extend(
                [event for event in agent_history if event.get("task_type") == task_type]
            )

        if len(task_events) >= 10:  # Minimum sample size
            success_rate = sum(1 for event in task_events if event["success"]) / len(task_events)
            avg_duration = statistics.mean(
                [event["duration"] for event in task_events if event["duration"]]
            )

            pattern.metadata.update(
                {
                    "success_rate": success_rate,
                    "average_duration": avg_duration,
                    "total_attempts": len(task_events),
                }
            )

            pattern.confidence = min(0.95, len(task_events) / 100.0)

            # Create adaptation rule for problematic task types
            if success_rate < 0.6 and pattern.confidence > self.pattern_confidence_threshold:
                await self._create_adaptation_rule(
                    f"optimize_{task_type}_handling",
                    f"task_success_rate < 0.6 AND task_type == '{task_type}'",
                    "enhance_task_processing",
                    confidence=pattern.confidence,
                )

    async def _analyze_error_pattern(
        self,
        agent_id: str | None,
        task_type: str | None,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Analyze error patterns for prevention"""
        pattern_key = f"error_pattern_{agent_id}_{task_type}"

        if pattern_key not in self.learning_patterns:
            self.learning_patterns[pattern_key] = LearningPattern(
                pattern_id=pattern_key,
                pattern_type="error_pattern",
                confidence=0.0,
                occurrences=0,
                last_seen=datetime.now(timezone.utc),
            )

        pattern = self.learning_patterns[pattern_key]
        pattern.occurrences += 1
        pattern.last_seen = datetime.now(timezone.utc)

        # Extract error information
        error_info = context.get("error", "unknown")
        pattern.metadata.setdefault("errors", []).append(
            {
                "error": error_info,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "context": context,
            }
        )

        # Update confidence based on error frequency
        pattern.confidence = min(0.9, pattern.occurrences / 20.0)

        # Create prevention rule if error is frequent
        if pattern.occurrences >= 5 and pattern.confidence > self.pattern_confidence_threshold:
            await self._create_adaptation_rule(
                f"prevent_error_{pattern_key}",
                f"error_frequency > 5 AND agent_id == '{agent_id}' AND task_type == '{task_type}'",
                "implement_error_prevention",
                confidence=pattern.confidence,
            )

    async def _analyze_optimization_pattern(
        self,
        agent_id: str | None,
        task_type: str | None,
        duration: float,
        metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Analyze performance optimization opportunities"""
        pattern_key = f"optimization_{agent_id}_{task_type}"

        if pattern_key not in self.learning_patterns:
            self.learning_patterns[pattern_key] = LearningPattern(
                pattern_id=pattern_key,
                pattern_type="optimization",
                confidence=0.0,
                occurrences=0,
                last_seen=datetime.now(timezone.utc),
            )

        pattern = self.learning_patterns[pattern_key]
        pattern.occurrences += 1
        pattern.last_seen = datetime.now(timezone.utc)

        # Track performance metrics
        pattern.metadata.setdefault("durations", []).append(duration)
        pattern.metadata.setdefault("metrics_history", []).append(metrics)

        # Keep only recent data
        if len(pattern.metadata["durations"]) > 50:
            pattern.metadata["durations"] = pattern.metadata["durations"][-50:]
            pattern.metadata["metrics_history"] = pattern.metadata["metrics_history"][-50:]

        # Calculate optimization opportunities
        if len(pattern.metadata["durations"]) >= 10:
            avg_duration = statistics.mean(pattern.metadata["durations"])
            duration_trend = self._calculate_duration_trend(pattern.metadata["durations"])

            pattern.metadata.update(
                {"average_duration": avg_duration, "duration_trend": duration_trend}
            )

            pattern.confidence = min(0.9, len(pattern.metadata["durations"]) / 30.0)

            # Create optimization rule if performance is declining
            if duration_trend > 1.2 and pattern.confidence > self.pattern_confidence_threshold:
                await self._create_adaptation_rule(
                    f"optimize_performance_{pattern_key}",
                    f"duration_trend > 1.2 AND agent_id == '{agent_id}' AND task_type == '{task_type}'",
                    "optimize_task_processing",
                    confidence=pattern.confidence,
                )

    def _calculate_trend(
        self,
        history: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Calculate performance trend"""
        if len(history) < 5:
            return "insufficient_data"

        recent = history[-5:]
        earlier = history[-10:-5] if len(history) >= 10 else history[:-5]

        if not earlier:
            return "insufficient_data"

        recent_success = sum(1 for event in recent if event["success"]) / len(recent)
        earlier_success = sum(1 for event in earlier if event["success"]) / len(earlier)

        if recent_success > earlier_success + 0.1:
            return "improving"
        elif recent_success < earlier_success - 0.1:
            return "declining"
        else:
            return "stable"

    def _calculate_duration_trend(self, durations: list[float]) -> float:
        """Calculate duration trend (ratio of recent to earlier average)"""
        if len(durations) < 10:
            return 1.0

        mid_point = len(durations) // 2
        recent_avg = statistics.mean(durations[mid_point:])
        earlier_avg = statistics.mean(durations[:mid_point])

        return recent_avg / earlier_avg if earlier_avg > 0 else 1.0

    async def _create_adaptation_rule(
        self,
        rule_id: str,
        condition: str,
        action: str,
        confidence: float,
        priority: int = 5,
    ) -> None:
        """Create new adaptation rule"""
        if rule_id in self.adaptation_rules:
            # Update existing rule
            self.adaptation_rules[rule_id].confidence = max(
                self.adaptation_rules[rule_id].confidence, confidence
            )
            return

        rule = AdaptationRule(
            rule_id=rule_id,
            condition=condition,
            action=action,
            confidence=confidence,
            priority=priority,
        )

        self.adaptation_rules[rule_id] = rule
        logger.info(f"Created adaptation rule: {rule_id} (confidence: {confidence:.2f})")

    async def _check_adaptation_opportunities(self) -> None:
        """Check if any adaptation rules should be applied"""
        for rule in self.adaptation_rules.values():
            if rule.confidence >= self.adaptation_threshold:
                await self._apply_adaptation_rule(rule)

    async def _apply_adaptation_rule(self, rule: AdaptationRule) -> None:
        """Apply adaptation rule to system"""
        try:
            # Log adaptation attempt
            logger.info(f"Applying adaptation rule: {rule.rule_id}")

            # Simulate rule application (in production, this would trigger actual system changes)
            adaptation_result = await self._execute_adaptation_action(rule.action, rule.condition)

            if adaptation_result:
                rule.applied_count += 1
                self.adaptations_applied += 1
                logger.info(f"Successfully applied adaptation: {rule.rule_id}")
            else:
                logger.warning(f"Failed to apply adaptation: {rule.rule_id}")

        except Exception as e:
            logger.error(f"Error applying adaptation rule {rule.rule_id}: {e}")

    async def _execute_adaptation_action(self, action: str, condition: str) -> bool:
        """Execute specific adaptation action"""
        # This would be implemented based on specific system requirements
        # For now, we'll simulate successful adaptation

        adaptation_actions = {
            "adjust_agent_parameters": self._adjust_agent_parameters,
            "enhance_task_processing": self._enhance_task_processing,
            "implement_error_prevention": self._implement_error_prevention,
            "optimize_task_processing": self._optimize_task_processing,
        }

        handler = adaptation_actions.get(action)
        if handler:
            return await handler(condition)
        else:
            logger.warning(f"Unknown adaptation action: {action}")
            return False

    async def _adjust_agent_parameters(self, condition: str) -> bool:
        """Adjust agent parameters based on condition"""
        # Placeholder for agent parameter adjustment
        logger.info(f"Adjusting agent parameters for condition: {condition}")
        return True

    async def _enhance_task_processing(self, condition: str) -> bool:
        """Enhance task processing based on condition"""
        # Placeholder for task processing enhancement
        logger.info(f"Enhancing task processing for condition: {condition}")
        return True

    async def _implement_error_prevention(self, condition: str) -> bool:
        """Implement error prevention measures"""
        # Placeholder for error prevention implementation
        logger.info(f"Implementing error prevention for condition: {condition}")
        return True

    async def _optimize_task_processing(self, condition: str) -> bool:
        """Optimize task processing performance"""
        # Placeholder for task processing optimization
        logger.info(f"Optimizing task processing for condition: {condition}")
        return True

    def get_learning_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get learning engine performance metrics"""
        return {
            "total_events_processed": self.total_events_processed,
            "patterns_identified": len(self.learning_patterns),
            "high_confidence_patterns": len(
                [
                    p
                    for p in self.learning_patterns.values()
                    if p.confidence >= self.pattern_confidence_threshold
                ]
            ),
            "adaptation_rules_created": len(self.adaptation_rules),
            "adaptations_applied": self.adaptations_applied,
            "active_rules": len(
                [
                    r
                    for r in self.adaptation_rules.values()
                    if r.confidence >= self.adaptation_threshold
                ]
            ),
        }

    def get_agent_insights(
        self, agent_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get learning insights for specific agent"""
        if agent_id not in self.performance_history:
            return {"error": "No data available for agent"}

        history = list(self.performance_history[agent_id])
        if not history:
            return {"error": "No performance data available"}

        success_rate = sum(1 for event in history if event["success"]) / len(history)
        avg_duration = statistics.mean(
            [event["duration"] for event in history if event["duration"]]
        )
        trend = self._calculate_trend(history)

        # Find relevant patterns
        agent_patterns = [p for p in self.learning_patterns.values() if agent_id in p.pattern_id]

        return {
            "agent_id": agent_id,
            "success_rate": success_rate,
            "average_duration": avg_duration,
            "performance_trend": trend,
            "total_tasks": len(history),
            "patterns_identified": len(agent_patterns),
            "high_confidence_patterns": len(
                [p for p in agent_patterns if p.confidence >= self.pattern_confidence_threshold]
            ),
        }


# Global learning engine instance
_learning_engine: LearningEngine | None = None


def get_learning_engine() -> LearningEngine:
    """Get global learning engine instance"""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine()
    return _learning_engine
