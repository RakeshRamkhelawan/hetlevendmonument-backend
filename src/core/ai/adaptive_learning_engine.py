"""
Adaptive Learning Engine - Dynamic learning and adaptation system
Implements continuous learning from user interactions and system performance
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import ModuleType
from typing import Any, Optional, TypeVar
from collections.abc import Awaitable, Callable

_T = TypeVar("_T")

# Optional ML dependency
np: ModuleType | None = None
try:
    import numpy as np

    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session import get_db_session
from src.core.knowledge.knowledge_base import KnowledgeType
from src.core.learning.models import LearningExperience  # Phase 6 Task 6: Migrated to domain module
from src.core.learning.reward_calculator import RewardCalculator
from src.core.learning.state_builder import StateBuilder
from src.core.shared.production_logging import SafeLogger

# Import cache system conditionally
try:
    from src.core.caching.cache_layer import cached
except ImportError:
    # Fallback decorator if caching not available -- matches real cached signature
    def cached(
        ttl: int = 300, key_prefix: str = "default"
    ) -> Callable[[Callable[..., Awaitable[_T]]], Callable[..., Awaitable[_T]]]:
        def decorator(
            func: Callable[..., Awaitable[_T]],
        ) -> Callable[..., Awaitable[_T]]:
            return func

        return decorator


try:
    from src.core.knowledge.knowledge_manager import knowledge_manager

    _knowledge_manager_available = True
except ImportError:
    knowledge_manager = None  # type: ignore[assignment]  # fallback sentinel when module unavailable
    _knowledge_manager_available = False

logger = SafeLogger(__name__)


class LearningEventType(Enum):
    """Types of learning events"""

    USER_INTERACTION = "user_interaction"
    SYSTEM_PERFORMANCE = "system_performance"
    ERROR_OCCURRENCE = "error_occurrence"
    SUCCESS_PATTERN = "success_pattern"
    FEEDBACK_RECEIVED = "feedback_received"
    PREFERENCE_CHANGE = "preference_change"
    WORKFLOW_COMPLETION = "workflow_completion"


class LearningType(Enum):
    """Types of learning experiences"""

    TASK_EXECUTION = "task_execution"
    AGENT_INTERACTION = "agent_interaction"
    USER_FEEDBACK = "user_feedback"
    SYSTEM_OBSERVATION = "system_observation"
    MODEL_UPDATE = "model_update"


class LearningOutcome(Enum):
    """Outcomes of learning experiences"""

    SUCCESS = "success"
    FAILURE = "failure"
    IMPROVEMENT = "improvement"
    DEGRADATION = "degradation"
    NEUTRAL = "neutral"


class AdaptationStrategy(Enum):
    """Adaptation strategies"""

    IMMEDIATE = "immediate"
    GRADUAL = "gradual"
    SCHEDULED = "scheduled"
    THRESHOLD_BASED = "threshold_based"


@dataclass
class LearningEvent:
    """Individual learning event with context"""

    event_id: str
    event_type: LearningEventType
    timestamp: datetime
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    metrics: dict[str, float]
    user_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for storage"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "metrics": self.metrics,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "confidence": self.confidence,
        }


@dataclass
class AdaptationInsight:
    """Insight derived from learning events"""

    insight_id: str
    pattern_type: str
    description: str
    confidence: float
    impact_score: float
    recommended_actions: list[str]
    supporting_events: list[str]
    created_at: datetime
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for storage"""
        return {
            "insight_id": self.insight_id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "confidence": self.confidence,
            "impact_score": self.impact_score,
            "recommended_actions": self.recommended_actions,
            "supporting_events": self.supporting_events,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class PatternDetector:
    """Detects patterns in learning events"""

    def __init__(self) -> None:
        self.detection_algorithms = {
            "frequency_pattern": self._detect_frequency_patterns,
            "correlation_pattern": self._detect_correlation_patterns,
            "temporal_pattern": self._detect_temporal_patterns,
            "performance_pattern": self._detect_performance_patterns,
            "user_behavior_pattern": self._detect_user_behavior_patterns,
        }

    async def detect_patterns(self, events: list[LearningEvent]) -> list[AdaptationInsight]:
        """Detect patterns in learning events"""
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pattern_type, algorithm in self.detection_algorithms.items():
            try:
                pattern_insights = await algorithm(events)
                insights.extend(pattern_insights)
            except Exception as e:
                logger.error(f"Pattern detection failed for {pattern_type}: {e}")

        return insights

    async def _detect_frequency_patterns(
        self, events: list[LearningEvent]
    ) -> list[AdaptationInsight]:
        """Detect frequently occurring patterns"""
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Group events by type and context
        event_groups: dict[tuple[str, str], list[LearningEvent]] = {}
        for event in events:
            key = (event.event_type.value, str(sorted(event.context.items())))
            if key not in event_groups:
                event_groups[key] = []
            event_groups[key].append(event)

        # Find high-frequency patterns
        for (event_type, context_str), group_events in event_groups.items():
            if len(group_events) >= 5:  # Threshold for frequency
                frequency = len(group_events) / len(events)
                if frequency > 0.1:  # At least 10% of events
                    insight = AdaptationInsight(
                        insight_id=f"freq_{hash((event_type, context_str)) % 10000}",
                        pattern_type="frequency_pattern",
                        description=f"High frequency pattern detected: {event_type} occurs {frequency:.1%} of the time",
                        confidence=min(0.9, frequency * 2),
                        impact_score=frequency,
                        recommended_actions=[f"Optimize handling of {event_type} events"],
                        supporting_events=[e.event_id for e in group_events[:10]],
                        created_at=datetime.now(timezone.utc),
                    )
                    insights.append(insight)

        return insights

    async def _detect_correlation_patterns(
        self, events: list[LearningEvent]
    ) -> list[AdaptationInsight]:
        """Detect correlated events"""
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Simple correlation detection based on temporal proximity
        for i, event1 in enumerate(events[:-1]):
            for event2 in events[i + 1 : i + 10]:  # Check next 10 events
                time_diff = (event2.timestamp - event1.timestamp).total_seconds()
                if 0 < time_diff <= 300:  # Within 5 minutes
                    correlation_strength = 1.0 - (time_diff / 300)
                    if correlation_strength > 0.7:
                        insight = AdaptationInsight(
                            insight_id=f"corr_{hash((event1.event_id, event2.event_id)) % 10000}",
                            pattern_type="correlation_pattern",
                            description=f"Strong correlation detected between {event1.event_type.value} and {event2.event_type.value}",
                            confidence=correlation_strength,
                            impact_score=correlation_strength * 0.8,
                            recommended_actions=[
                                "Investigate causal relationship",
                                "Optimize event sequence",
                            ],
                            supporting_events=[event1.event_id, event2.event_id],
                            created_at=datetime.now(timezone.utc),
                        )
                        insights.append(insight)
                        break

        return insights

    async def _detect_temporal_patterns(
        self, events: list[LearningEvent]
    ) -> list[AdaptationInsight]:
        """Detect time-based patterns"""
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Group events by hour of day
        hourly_counts: dict[int, int] = {}
        for event in events:
            hour = event.timestamp.hour
            hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

        # Find peak hours
        if hourly_counts:
            max_count = max(hourly_counts.values())
            avg_count = sum(hourly_counts.values()) / len(hourly_counts)

            for hour, count in hourly_counts.items():
                if count > avg_count * 1.5:  # 50% above average
                    insight = AdaptationInsight(
                        insight_id=f"temporal_{hour}",
                        pattern_type="temporal_pattern",
                        description=f"Peak activity detected at hour {hour}:00 ({count} events)",
                        confidence=min(0.9, count / max_count),
                        impact_score=count / len(events),
                        recommended_actions=[
                            f"Scale resources for hour {hour}:00",
                            "Optimize for peak load",
                        ],
                        supporting_events=[],
                        created_at=datetime.now(timezone.utc),
                    )
                    insights.append(insight)

        return insights

    async def _detect_performance_patterns(
        self, events: list[LearningEvent]
    ) -> list[AdaptationInsight]:
        """Detect performance-related patterns"""
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Analyze performance metrics
        performance_events = [
            e for e in events if e.event_type == LearningEventType.SYSTEM_PERFORMANCE
        ]

        if len(performance_events) >= 3:
            response_times: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            error_rates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for event in performance_events:
                if "response_time" in event.metrics:
                    response_times.append(event.metrics["response_time"])
                if "error_rate" in event.metrics:
                    error_rates.append(event.metrics["error_rate"])

            # Detect performance degradation
            if response_times and len(response_times) >= 3 and np is not None:
                recent_avg = np.mean(response_times[-3:])
                overall_avg = np.mean(response_times)

                if recent_avg > overall_avg * 1.3:  # 30% degradation
                    insight = AdaptationInsight(
                        insight_id="perf_degradation",
                        pattern_type="performance_pattern",
                        description=f"Performance degradation detected: recent response time {recent_avg:.2f}s vs average {overall_avg:.2f}s",
                        confidence=0.8,
                        impact_score=0.9,
                        recommended_actions=[
                            "Investigate performance bottlenecks",
                            "Scale resources",
                            "Optimize queries",
                        ],
                        supporting_events=[e.event_id for e in performance_events[-3:]],
                        created_at=datetime.now(timezone.utc),
                    )
                    insights.append(insight)

        return insights

    async def _detect_user_behavior_patterns(
        self, events: list[LearningEvent]
    ) -> list[AdaptationInsight]:
        """Detect user behavior patterns"""
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Group events by user
        user_events: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for event in events:
            if event.user_id:
                if event.user_id not in user_events:
                    user_events[event.user_id] = []
                user_events[event.user_id].append(event)

        # Analyze user interaction patterns
        for user_id, user_event_list in user_events.items():
            if len(user_event_list) >= 5:
                interaction_events = [
                    e for e in user_event_list if e.event_type == LearningEventType.USER_INTERACTION
                ]

                if interaction_events:
                    # Calculate session duration
                    session_durations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                    current_session: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                    for event in sorted(interaction_events, key=lambda x: x.timestamp):
                        if not current_session:
                            current_session = [event]
                        else:
                            time_gap = (
                                event.timestamp - current_session[-1].timestamp
                            ).total_seconds()
                            if time_gap > 1800:  # 30 minutes gap = new session
                                if len(current_session) > 1:
                                    duration = (
                                        current_session[-1].timestamp - current_session[0].timestamp
                                    ).total_seconds()
                                    session_durations.append(duration)
                                current_session = [event]
                            else:
                                current_session.append(event)

                    if session_durations and np is not None:
                        avg_duration = np.mean(session_durations)
                        if avg_duration > 600:  # Long sessions (>10 minutes)
                            insight = AdaptationInsight(
                                insight_id=f"user_engagement_{user_id}",
                                pattern_type="user_behavior_pattern",
                                description=f"High user engagement detected: average session {avg_duration / 60:.1f} minutes",
                                confidence=0.7,
                                impact_score=0.6,
                                recommended_actions=[
                                    "Personalize experience",
                                    "Provide advanced features",
                                ],
                                supporting_events=[e.event_id for e in interaction_events[:5]],
                                created_at=datetime.now(timezone.utc),
                            )
                            insights.append(insight)

        return insights


class AdaptiveLearningEngine:
    """
    Main adaptive learning engine that processes events and generates insights
    Implements continuous learning and system adaptation
    FASE 6: Enhanced with database persistence
    """

    def __init__(self, db_session: AsyncSession | None = None) -> None:
        self.pattern_detector = PatternDetector()
        self.learning_events: list[LearningEvent] = []  # In-memory cache for recent events
        self.insights: list[AdaptationInsight] = []
        self.adaptation_strategies: dict[str, AdaptationStrategy] = {}
        self._initialized = False
        self._stats = {
            "events_processed": 0,
            "insights_generated": 0,
            "adaptations_applied": 0,
            "learning_rate": 0.0,
        }
        # Database session for dependency injection (testing)
        self._db_session = db_session

    async def initialize(self) -> bool:
        """Initialize adaptive learning engine"""
        try:
            # Load existing events and insights from knowledge base
            await self._load_learning_history()

            # Initialize default adaptation strategies
            self._setup_default_strategies()

            self._initialized = True
            logger.info("Adaptive Learning Engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize adaptive learning engine: {e}")
            return False

    async def record_event(self, event: LearningEvent) -> bool:
        """Record a learning event"""
        if not self._initialized:
            await self.initialize()

        try:
            # Validate event
            if not self._validate_event(event):
                return False

            # Store event
            self.learning_events.append(event)
            self._stats["events_processed"] += 1

            # Store in knowledge base for persistence
            await self._persist_event(event)

            # Trigger pattern detection if we have enough events
            if len(self.learning_events) % 10 == 0:  # Every 10 events
                await self._trigger_pattern_analysis()

            logger.debug(f"Recorded learning event: {event.event_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to record learning event: {e}")
            return False

    async def record_experience(
        self,
        agent_id: str,
        task_type: str,
        success: bool,
        duration: float,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        metrics: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        FASE 6: Record a learning experience directly to database
        This method is called by TaskDistributor for automatic feedback loop

        Args:
            agent_id: ID of the agent that performed the task
            task_type: Type of task that was performed
            success: Whether the task was successful
            duration: Time taken to complete the task
            context: Additional context information
            metrics: Performance metrics

        Returns:
            bool: True if experience was recorded successfully
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Generate unique event ID
            event_id = f"exp_{agent_id}_{task_type}_{int(time.time() * 1000)}"

            # --- FASE 5.4: Generate state_vector and calculate reward ---
            state_builder = StateBuilder()
            reward_calculator = RewardCalculator()

            # For state_vector, we need tool_name and payload.
            # Assuming task_type can serve as tool_name for now, and context as payload.
            # In a real scenario, these would be passed more explicitly.
            current_time = datetime.now(timezone.utc)
            state_vector = state_builder.build_state_vector(
                tool_name=task_type, payload=context or {}, current_time=current_time
            )

            # For reward, we need task_result (status, duration)
            task_result = {
                "status": "success" if success else "error",
                "duration": duration,
            }
            reward = reward_calculator.calculate_reward(task_result)
            # --- END FASE 5.4 ---

            # Prepare data for database insertion (FASE 9.6 FIX: Match SQLAlchemy model fields)
            experience_data = {
                "event_id": event_id,
                "event_type": "task_execution",
                "agent_id": agent_id,
                "task_type": task_type,
                "success": success,
                "duration": duration,  # Store in seconds as Float
                "context": context or {},
                "metrics": metrics or {},
                "confidence": 1.0 if success else 0.5,  # Map to confidence field
                "state_vector": state_vector,  # FASE 5.4: Add state_vector
                "reward": reward,  # FASE 5.4: Add reward
            }

            # Insert directly into database (FASE 9.6 FIX: Handle async session properly)
            if self._db_session:
                # Use provided session - Direct ORM approach
                learning_entry = LearningExperience(**experience_data)
                self._db_session.add(learning_entry)
                await self._db_session.commit()
                await self._db_session.refresh(learning_entry)
            else:
                # Use async session context manager - Fixed pattern (SYSTEM STABILITY FIX)
                async with get_db_session() as session:
                    learning_entry = LearningExperience(**experience_data)
                    session.add(learning_entry)
                    await session.commit()
                    await session.refresh(learning_entry)

            self._stats["events_processed"] += 1
            logger.debug(f"Recorded learning experience: {event_id} for agent {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to record learning experience: {e}")
            return False

    async def analyze_patterns(
        self, time_window: timedelta | None = None
    ) -> list[AdaptationInsight]:
        """Analyze patterns in recent learning events"""
        try:
            # Filter events by time window
            if time_window:
                cutoff_time = datetime.now(timezone.utc) - time_window
                relevant_events = [e for e in self.learning_events if e.timestamp >= cutoff_time]
            else:
                relevant_events = self.learning_events[-100:]  # Last 100 events

            if not relevant_events:
                return []

            # Detect patterns
            new_insights = await self.pattern_detector.detect_patterns(relevant_events)

            # Filter out duplicate insights
            unique_insights = self._filter_duplicate_insights(new_insights)

            # Store insights
            self.insights.extend(unique_insights)
            self._stats["insights_generated"] += len(unique_insights)

            # Persist insights
            for insight in unique_insights:
                await self._persist_insight(insight)

            logger.info(
                f"Generated {len(unique_insights)} new insights from {len(relevant_events)} events"
            )
            return unique_insights

        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")
            return []

    async def get_adaptation_recommendations(
        self,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get adaptation recommendations based on current context"""
        try:
            recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Get relevant insights
            relevant_insights = self._get_relevant_insights(context)

            for insight in relevant_insights:
                if insight.confidence > 0.6 and insight.impact_score > 0.5:
                    recommendation = {
                        "insight_id": insight.insight_id,
                        "description": insight.description,
                        "actions": insight.recommended_actions,
                        "confidence": insight.confidence,
                        "impact": insight.impact_score,
                        "urgency": self._calculate_urgency(insight),
                        "strategy": self._get_adaptation_strategy(insight.pattern_type),
                    }
                    recommendations.append(recommendation)

            # Sort by impact and confidence
            recommendations.sort(key=lambda x: x["confidence"] * x["impact"], reverse=True)

            return recommendations[:10]  # Top 10 recommendations

        except Exception as e:
            logger.error(f"Failed to get adaptation recommendations: {e}")
            return []

    async def apply_adaptation(
        self,
        recommendation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply an adaptation based on recommendation"""
        try:
            insight_id = recommendation["insight_id"]
            strategy = recommendation.get("strategy", AdaptationStrategy.GRADUAL)

            # Apply adaptation based on strategy
            success = await self._execute_adaptation(recommendation, strategy)

            if success:
                self._stats["adaptations_applied"] += 1

                # Record adaptation as a learning event
                adaptation_event = LearningEvent(
                    event_id=f"adaptation_{insight_id}_{int(time.time())}",
                    event_type=LearningEventType.SYSTEM_PERFORMANCE,
                    timestamp=datetime.now(timezone.utc),
                    context={"adaptation_applied": True, "insight_id": insight_id},
                    metrics={"success": 1.0, "impact": recommendation["impact"]},
                )
                await self.record_event(adaptation_event)

                logger.info(f"Applied adaptation for insight {insight_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to apply adaptation: {e}")
            return False

    @cached(ttl=300, key_prefix="learning_stats")
    async def get_agent_performance_for_task(self, task_type: str) -> dict[str, float]:
        """
        FASE 5: Get agent performance data for specific task type
        Calculates success rates per agent ID for the given task type

        Args:
            task_type: Type of task to analyze performance for

        Returns:
            dict[str, float]: Mapping[str, Any] of agent_id to success_rate (0.0 to 1.0)  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # Filter learning events for the specific task type
            # Look for events with agent_id and task performance metrics
            task_events: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for event in self.learning_events:
                # Check if event is related to task performance
                if (
                    event.event_type
                    in [
                        LearningEventType.SYSTEM_PERFORMANCE,
                        LearningEventType.SUCCESS_PATTERN,
                        LearningEventType.ERROR_OCCURRENCE,
                    ]
                    and event.agent_id
                    and event.context.get("task_type") == task_type
                ):
                    task_events.append(event)

            # Group events by agent_id and calculate success rates
            agent_performance: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            agent_event_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for event in task_events:
                agent_id = event.agent_id

                if agent_id not in agent_performance:
                    agent_performance[agent_id] = 0.0
                    agent_event_counts[agent_id] = 0

                # Determine if event represents success or failure
                is_success = False
                if "success" in event.metrics:
                    is_success = event.metrics["success"] > 0.5
                elif "error_rate" in event.metrics:
                    is_success = event.metrics["error_rate"] < 0.1
                elif event.event_type == LearningEventType.SUCCESS_PATTERN:
                    is_success = True
                elif event.event_type == LearningEventType.ERROR_OCCURRENCE:
                    is_success = False
                else:
                    # Default to success if performance event with reasonable response time
                    is_success = event.metrics.get("response_time", 0) < 5.0

                # Update running success rate
                current_count = agent_event_counts[agent_id]
                current_rate = agent_performance[agent_id]

                # Calculate new success rate using incremental average
                new_rate = (current_rate * current_count + (1.0 if is_success else 0.0)) / (
                    current_count + 1
                )

                agent_performance[agent_id] = new_rate
                agent_event_counts[agent_id] = current_count + 1

            # Filter out agents with insufficient data (less than 3 events)
            filtered_performance = {
                agent_id: success_rate
                for agent_id, success_rate in agent_performance.items()
                if agent_event_counts[agent_id] >= 3
            }

            logger.debug(f"Agent performance for task '{task_type}': {filtered_performance}")
            return filtered_performance

        except Exception as e:
            logger.error(f"Failed to get agent performance for task {task_type}: {e}")
            return {}

    @cached(ttl=300, key_prefix="learning_stats")
    async def get_insights(
        self,
        category: str | None = None,
        min_confidence: float = 0.7,
        limit: int = 10,
    ) -> list[AdaptationInsight]:
        """
        Get learning insights filtered by category and confidence

        Args:
            category: Optional category filter (pattern_type)
            min_confidence: Minimum confidence threshold
            limit: Maximum number of insights to return

        Returns: list[Any] of AdaptationInsight objects  # TODO(TYPE): replace Any with concrete type
        """
        # Filter insights by confidence
        filtered_insights = [
            insight for insight in self.insights if insight.confidence >= min_confidence
        ]

        # Filter by category if provided
        if category:
            filtered_insights = [
                insight for insight in filtered_insights if insight.pattern_type == category
            ]

        # Sort by confidence and impact score
        filtered_insights.sort(key=lambda x: (x.confidence, x.impact_score), reverse=True)

        # Limit results
        return filtered_insights[:limit]

    async def get_event_count(self) -> int:
        """Get total number of processed events"""
        return int(self._stats.get("events_processed", 0))

    async def get_learning_stats(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get learning engine statistics"""
        try:
            # Calculate learning rate
            recent_events = [
                e
                for e in self.learning_events
                if e.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24)
            ]
            self._stats["learning_rate"] = len(recent_events) / 24.0  # Events per hour

            # Get insight distribution
            insight_types: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for insight in self.insights:
                insight_types[insight.pattern_type] = insight_types.get(insight.pattern_type, 0) + 1

            return {
                "total_events": len(self.learning_events),
                "total_insights": len(self.insights),
                "events_processed": self._stats["events_processed"],
                "insights_generated": self._stats["insights_generated"],
                "adaptations_applied": self._stats["adaptations_applied"],
                "learning_rate_per_hour": round(self._stats["learning_rate"], 2),
                "insight_distribution": insight_types,
                "active_insights": len([i for i in self.insights if self._is_insight_active(i)]),
                "last_analysis": self._get_last_analysis_time(),
            }

        except Exception as e:
            logger.error(f"Failed to get learning stats: {e}")
            return {}

    def _validate_event(self, event: LearningEvent) -> bool:
        """Validate learning event"""
        if not event.event_id or not event.event_type:
            return False

        if not isinstance(event.context, dict) or not isinstance(event.metrics, dict):
            return False

        return True

    async def _persist_event(self, event: LearningEvent) -> None:
        """Persist event to knowledge base"""
        if knowledge_manager is None:
            logger.debug("Knowledge manager not available, skipping event persistence")
            return

        try:
            await knowledge_manager.add_knowledge(
                knowledge_base="system",
                content=json.dumps(event.to_dict(), ensure_ascii=True),
                knowledge_type=KnowledgeType.EXPERIENTIAL,
                metadata={"event_type": event.event_type.value, "learning_event": True},
                tags=["learning_event", event.event_type.value],
            )
        except Exception as e:
            logger.warning(f"Failed to persist learning event: {e}")

    async def _persist_insight(self, insight: AdaptationInsight) -> None:
        """Persist insight to knowledge base"""
        if knowledge_manager is None:
            logger.debug("Knowledge manager not available, skipping insight persistence")
            return

        try:
            await knowledge_manager.add_knowledge(
                knowledge_base="system",
                content=json.dumps(insight.to_dict(), ensure_ascii=True),
                knowledge_type=KnowledgeType.CONCEPTUAL,
                metadata={
                    "insight_type": insight.pattern_type,
                    "adaptation_insight": True,
                },
                tags=["adaptation_insight", insight.pattern_type],
            )
        except Exception as e:
            logger.warning(f"Failed to persist insight: {e}")

    async def _load_learning_history(self) -> None:
        """Load learning events and insights from storage"""
        if knowledge_manager is None:
            logger.debug("Knowledge manager not available, skipping history load")
            return

        try:
            # Enhanced error handling for knowledge manager search
            # Load events with proper type checking
            event_results = await knowledge_manager.search_knowledge(
                query="learning_event", knowledge_bases=["system"], limit=1000
            )

            # Ensure event_results is iterable and handle different return types
            if event_results and hasattr(event_results, "__iter__"):
                for result in event_results:
                    try:
                        # Handle different result object structures
                        if hasattr(result, "entry") and hasattr(result.entry, "content"):
                            event_data = json.loads(result.entry.content)
                        elif hasattr(result, "content"):
                            event_data = json.loads(result.content)  # pyright: ignore[reportAttributeAccessIssue]
                        else:
                            logger.debug(f"Unknown result structure: {type(result)}")
                            continue

                        # Convert back to LearningEvent (simplified)
                        logger.debug(f"Loaded learning event: {event_data.get('event_id')}")
                    except json.JSONDecodeError as e:
                        logger.warning("Failed to parse learning event: %s", e, exc_info=True)
                    except (TypeError, AttributeError) as e:
                        logger.debug("Failed to access learning event attributes: %s", e)
                    except Exception as e:
                        logger.warning(
                            "Unexpected error parsing learning event: %s", e, exc_info=True
                        )

            # Load insights with similar protection
            insight_results = await knowledge_manager.search_knowledge(
                query="adaptation_insight", knowledge_bases=["system"], limit=500
            )

            if insight_results and hasattr(insight_results, "__iter__"):
                for result in insight_results:
                    try:
                        # Handle different result object structures
                        if hasattr(result, "entry") and hasattr(result.entry, "content"):
                            insight_data = json.loads(result.entry.content)
                        elif hasattr(result, "content"):
                            insight_data = json.loads(result.content)  # pyright: ignore[reportAttributeAccessIssue]
                        else:
                            logger.debug(f"Unknown insight result structure: {type(result)}")
                            continue

                        # Convert back to AdaptationInsight (simplified)
                        logger.debug(f"Loaded insight: {insight_data.get('insight_id')}")
                    except json.JSONDecodeError as e:
                        logger.warning("Failed to parse insight: %s", e, exc_info=True)
                    except (TypeError, AttributeError) as e:
                        logger.debug("Failed to access insight attributes: %s", e)
                    except Exception as e:
                        logger.warning("Unexpected error parsing insight: %s", e, exc_info=True)

        except TypeError as e:
            # Specific handling for "unhashable type" errors
            logger.debug(f"Knowledge manager search returned incompatible type: {e}")
        except Exception as e:
            logger.debug(f"Knowledge manager not fully functional, skipping history load: {e}")

    def _setup_default_strategies(self) -> None:
        """Setup default adaptation strategies"""
        self.adaptation_strategies = {
            "frequency_pattern": AdaptationStrategy.GRADUAL,
            "correlation_pattern": AdaptationStrategy.THRESHOLD_BASED,
            "temporal_pattern": AdaptationStrategy.SCHEDULED,
            "performance_pattern": AdaptationStrategy.IMMEDIATE,
            "user_behavior_pattern": AdaptationStrategy.GRADUAL,
        }

    async def _trigger_pattern_analysis(self) -> None:
        """Trigger pattern analysis in background"""
        try:
            asyncio.create_task(self.analyze_patterns(timedelta(hours=1)))
        except Exception as e:
            logger.warning(f"Failed to trigger pattern analysis: {e}")

    def _filter_duplicate_insights(
        self, new_insights: list[AdaptationInsight]
    ) -> list[AdaptationInsight]:
        """Filter out duplicate insights"""
        unique_insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        existing_patterns = {i.pattern_type for i in self.insights if self._is_insight_active(i)}

        for insight in new_insights:
            # Simple duplicate detection based on pattern type and description
            if insight.pattern_type not in existing_patterns:
                unique_insights.append(insight)

        return unique_insights

    def _get_relevant_insights(
        self,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[AdaptationInsight]:  # TODO(TYPE): replace Any with concrete type
        """Get insights relevant to current context"""
        relevant_insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for insight in self.insights:
            if self._is_insight_active(insight):
                # Simple relevance check (in full implementation, use more sophisticated matching)
                if insight.confidence > 0.5:
                    relevant_insights.append(insight)

        return relevant_insights

    def _calculate_urgency(self, insight: AdaptationInsight) -> str:
        """Calculate urgency level for insight"""
        urgency_score = insight.confidence * insight.impact_score

        if urgency_score > 0.8:
            return "high"
        elif urgency_score > 0.6:
            return "medium"
        else:
            return "low"

    def _get_adaptation_strategy(self, pattern_type: str) -> AdaptationStrategy:
        """Get adaptation strategy for pattern type"""
        return self.adaptation_strategies.get(pattern_type, AdaptationStrategy.GRADUAL)

    async def _execute_adaptation(
        self,
        recommendation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        strategy: AdaptationStrategy,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Execute adaptation based on strategy"""
        try:
            # Placeholder implementation - in real system, this would integrate with system components
            logger.info(
                f"Executing adaptation with strategy {strategy.value}: {recommendation['description']}"
            )

            # Simulate adaptation execution
            await asyncio.sleep(0.1)

            return True

        except Exception as e:
            logger.error(f"Adaptation execution failed: {e}")
            return False

    def _is_insight_active(self, insight: AdaptationInsight) -> bool:
        """Check if insight is still active"""
        if insight.expires_at and insight.expires_at < datetime.now(timezone.utc):
            return False

        # Insights are active for 24 hours by default
        age = datetime.now(timezone.utc) - insight.created_at
        return age < timedelta(hours=24)

    def _get_last_analysis_time(self) -> str | None:
        """Get timestamp of last pattern analysis"""
        if self.insights:
            latest_insight = max(self.insights, key=lambda x: x.created_at)
            return latest_insight.created_at.isoformat()
        return None


# Factory function for creating adaptive learning engine
async def create_adaptive_learning_engine(
    db_session: AsyncSession | None = None,
) -> AdaptiveLearningEngine:
    """Create and initialize adaptive learning engine"""
    try:
        engine = AdaptiveLearningEngine(db_session)
        initialization_success = await engine.initialize()

        if not initialization_success:
            logger.warning("AdaptiveLearningEngine initialization returned False")

        return engine
    except Exception as e:
        logger.error(f"Failed to create AdaptiveLearningEngine: {e}")
        # Return a minimal engine that won't crash
        engine = AdaptiveLearningEngine(db_session)
        engine._initialized = False
        return engine


# Global adaptive learning engine instance
_global_learning_engine: AdaptiveLearningEngine | None = None


async def get_adaptive_learning_engine(
    db_session: AsyncSession | None = None,
) -> AdaptiveLearningEngine:
    """Get global adaptive learning engine instance"""
    global _global_learning_engine

    if _global_learning_engine is None:
        _global_learning_engine = await create_adaptive_learning_engine(db_session)

    return _global_learning_engine
