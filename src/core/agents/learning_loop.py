#!/usr/bin/env python3
"""
Learning Loop System for Sanskriti Setu AI Multi-Agent System
Continuous learning, adaptation, and improvement system
"""

import json
import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, cast

from src.core.shared.config import get_settings
from src.core.shared.interfaces import ExecutionResult
from src.core.shared.llm_client import ChatTaalmodel

if TYPE_CHECKING:
    from src.core.learning.learning_repository import LearningRepository
    from src.core.learning.services import (
        AdaptationService,
        InsightService,
        ObservationService,
        PatternService,
    )

# NOTE: LearningRepository is a TYPE_CHECKING-only import but listed in __all__
# so mypy resolves it for callers that import it from this module.
__all__ = [
    "LearningRepository",
    "LearningType",
    "LearningSource",
    "LearningObservation",
    "LearningPattern",
    "LearningLoop",
    "TenantContextError",
]

logger = logging.getLogger(__name__)


class TenantContextError(Exception):
    """Raised when tenant context is required but not available.

    SECURITY FIX (P0): This error prevents cross-tenant data leakage
    by enforcing explicit tenant identification for all operations.
    """

    pass


class LearningType(Enum):
    """Types of learning in the system"""

    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    STRATEGY_REFINEMENT = "strategy_refinement"
    PATTERN_RECOGNITION = "pattern_recognition"
    ERROR_CORRECTION = "error_correction"
    BEHAVIORAL_ADAPTATION = "behavioral_adaptation"
    PREDICTIVE_MODELING = "predictive_modeling"
    USER_PREFERENCE = "user_preference"
    SYSTEM_EVOLUTION = "system_evolution"


class LearningSource(Enum):
    """Sources of learning data"""

    TASK_EXECUTION = "task_execution"
    USER_FEEDBACK = "user_feedback"
    PERFORMANCE_METRICS = "performance_metrics"
    ERROR_ANALYSIS = "error_analysis"
    STRATEGY_OUTCOMES = "strategy_outcomes"
    SYSTEM_MONITORING = "system_monitoring"
    EXTERNAL_DATA = "external_data"
    AGENT_INTERACTIONS = "agent_interactions"


@dataclass
class LearningObservation:
    """Individual learning observation"""

    id: str
    timestamp: datetime
    source: LearningSource
    learning_type: LearningType
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    observation_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    outcome_metrics: dict[str, float]
    confidence_score: float = 0.0
    importance_score: float = 0.0


@dataclass
class LearningPattern:
    """Learned pattern from observations"""

    id: str
    pattern_type: LearningType
    description: str
    trigger_conditions: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    learned_behavior: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    success_rate: float
    confidence_score: float
    observation_count: int
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


@dataclass
class AdaptationRule:
    """Rule for system adaptation based on learning"""

    id: str
    name: str
    condition: str
    action: str
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    success_metrics: list[str]
    active: bool = True
    trigger_count: int = 0
    success_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches_context(self, task_context: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if this rule's trigger conditions match the given task context.

        Uses the existing condition dict structure from AdaptationService._evaluate_condition().
        Delegates to simple key-value matching: if all keys in self.condition
        are present and equal in task_context, the rule matches.

        Args:
            task_context: Dictionary containing task context (task_type, etc.)

        Returns:
            True if rule matches context, False otherwise
        """
        if not self.condition:
            return True  # No condition = always matches
        try:
            condition_dict = (
                json.loads(self.condition) if isinstance(self.condition, str) else self.condition
            )
            if not isinstance(condition_dict, dict):
                return False
            return all(
                task_context.get(k) == v
                for k, v in condition_dict.items()
                if k != "operator"  # Skip meta-keys
            )
        except (json.JSONDecodeError, Exception):
            return False  # Safe default on malformed condition


@dataclass
class LearningInsight:
    """Insight derived from learning process"""

    id: str
    title: str
    description: str
    learning_type: LearningType
    supporting_observations: list[str]
    confidence_score: float
    impact_assessment: dict[str, float]
    recommended_actions: list[str]
    created_at: datetime = field(default_factory=datetime.now)


class LearningLoop:
    """Continuous learning and adaptation system.

    P1 REFACTOR: This class now uses service-oriented architecture.
    Individual responsibilities are delegated to:
    - ObservationService: Recording observations
    - PatternService: Pattern recognition
    - AdaptationService: Adaptation rules
    - InsightService: Insight generation

    This class acts as a facade/coordinator for backward compatibility.
    """

    def __init__(
        self,
        tenant_id: int | None = None,
        repository: Optional["LearningRepository"] = None,
    ) -> None:
        """Initialize the learning loop system.

        Args:
            tenant_id: Tenant scope for all data.  ``None`` keeps legacy
                behaviour (no persistence, no tenant isolation).
            repository: Optional :class:`LearningRepository` for
                write-through persistence.  When *None*, the loop
                operates in-memory only (backward-compatible).
        """
        self.tenant_id = tenant_id
        self._repository = repository
        self.settings = get_settings()
        self.llm_client: ChatTaalmodel | None = None

        # P1 REFACTOR: Initialize services
        self._observation_service: Optional["ObservationService"] = None
        self._pattern_service: Optional["PatternService"] = None
        self._adaptation_service: Optional["AdaptationService"] = None
        self._insight_service: Optional["InsightService"] = None

        # Learning data storage (maintained for backward compatibility)
        self.observations: dict[str, LearningObservation] = {}
        self.patterns: dict[str, LearningPattern] = {}
        self.adaptation_rules: dict[str, AdaptationRule] = {}
        self.insights: dict[str, LearningInsight] = {}

        # Learning history and buffers (maintained for backward compatibility)
        self.observation_buffer: deque[LearningObservation] = deque(maxlen=1000)
        self.pattern_buffer: deque[LearningPattern] = deque(maxlen=100)
        self.feedback_buffer: deque[dict[str, Any]] = deque(maxlen=200)  # TODO(TYPE): replace Any with concrete type

        # Learning metrics
        self.learning_metrics = {
            "total_observations": 0,
            "patterns_learned": 0,
            "adaptations_applied": 0,
            "improvement_rate": 0.0,
            "learning_velocity": 0.0,
        }

        # Learning configurations
        self.learning_config = {
            "observation_threshold": 10,  # Min observations for pattern
            "confidence_threshold": 0.7,  # Min confidence for adaptation
            "pattern_decay_days": 30,  # Days before pattern expires
            "adaptation_cooldown": 3600,  # Seconds between adaptations
            "max_concurrent_adaptations": 3,
        }

        # Initialize LLM client
        self._initialize_llm()

        # Start learning loop
        self._learning_active = True
        self._last_learning_cycle = datetime.now(timezone.utc)

    def _get_observation_service(self) -> "ObservationService":
        """Lazy initialization of observation service."""
        if self._observation_service is None:
            from src.core.learning.services import ObservationService

            self._observation_service = ObservationService(
                tenant_id=self.tenant_id or 0,
                repository=self._repository,
                observation_threshold=cast(int, self.learning_config["observation_threshold"]),
            )
            # Sync data for backward compatibility
            self._observation_service.observations = self.observations
            self._observation_service.observation_buffer = self.observation_buffer
        return self._observation_service

    def _get_pattern_service(self) -> "PatternService":
        """Lazy initialization of pattern service."""
        if self._pattern_service is None:
            from src.core.learning.services import PatternService

            self._pattern_service = PatternService(
                tenant_id=self.tenant_id or 0,
                repository=self._repository,
                confidence_threshold=self.learning_config["confidence_threshold"],
            )
            # Sync data for backward compatibility
            self._pattern_service.patterns = self.patterns
            self._pattern_service.pattern_buffer = self.pattern_buffer
        return self._pattern_service

    def _get_adaptation_service(self) -> "AdaptationService":
        """Lazy initialization of adaptation service."""
        if self._adaptation_service is None:
            from src.core.learning.services import AdaptationService

            self._adaptation_service = AdaptationService(
                tenant_id=self.tenant_id or 0,
                repository=self._repository,
            )
            # Sync data for backward compatibility
            self._adaptation_service.rules = self.adaptation_rules
        return self._adaptation_service

    def _get_insight_service(self) -> "InsightService":
        """Lazy initialization of insight service."""
        if self._insight_service is None:
            from src.core.learning.services import InsightService

            self._insight_service = InsightService(
                tenant_id=self.tenant_id or 0,
                repository=self._repository,
            )
            # Sync data for backward compatibility
            self._insight_service.insights = self.insights
        return self._insight_service

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def load_persisted_state(self) -> None:
        """Load patterns, rules and insights from the database.

        Call once after construction to "warm" the in-memory caches from
        the persistent store.  Safe to call multiple times.
        """
        if self._repository is None or self.tenant_id is None:
            return

        try:
            patterns = await self._repository.get_active_patterns(self.tenant_id)
            for p in patterns:
                self.patterns[p.id] = p

            rules = await self._repository.get_active_rules(self.tenant_id)
            for r in rules:
                self.adaptation_rules[r.id] = r

            insights = await self._repository.get_recent_insights(self.tenant_id)
            for i in insights:
                self.insights[i.id] = i

            self.learning_metrics["patterns_learned"] = len(self.patterns)
            logger.info(
                "Loaded persisted state for tenant %d: %d patterns, %d rules, %d insights",
                self.tenant_id,
                len(self.patterns),
                len(self.adaptation_rules),
                len(self.insights),
            )
        except Exception as exc:
            logger.error("Failed to load persisted state: %s", exc)

    def _initialize_llm(self) -> None:
        """Het taalmodel voor leeranalyse: dat van de TENANT van deze lus (brief 2026-10-20, ADR-041 B14).

        Hier stond een keten: de geconfigureerde provider, dan Google, dan Anthropic (die stil Google was), dan
        een namaakclient. Zonder tenant (`tenant_id=None`, de globale lus) is het de platformstandaard.
        """
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        self.llm_client = TenantTaalmodel(self.tenant_id)
        logger.info("Learning loop gebruikt het taalmodel van tenant %s", self.tenant_id)

    async def observe(
        self,
        source: LearningSource,
        learning_type: LearningType,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        observation_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        outcome_metrics: dict[str, float] | None = None,
    ) -> str:
        """Record a learning observation with transactional consistency.

        SECURITY FIX (P0): Uses write-ahead pattern to ensure consistency.
        Database write happens BEFORE in-memory update.
        If DB write fails, in-memory state is not updated.
        """
        observation_id = str(uuid.uuid4())

        # Calculate importance and confidence scores
        importance_score = self._calculate_importance_score(
            learning_type, context, observation_data
        )
        confidence_score = self._calculate_confidence_score(
            source, observation_data, outcome_metrics or {}
        )

        # Create observation
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

        # P0 FIX: Write-ahead pattern for transactional consistency
        # 1. Persist to database FIRST
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_observation(self.tenant_id, observation)
            except Exception as exc:
                # P0 FIX: Log error and re-raise to prevent inconsistent state
                logger.error("Failed to persist observation %s: %s", observation_id, exc)
                raise RuntimeError(f"Failed to persist learning observation: {exc}") from exc

        # 2. Only update in-memory state AFTER successful DB write
        self.observations[observation_id] = observation
        self.observation_buffer.append(observation)

        # Update metrics
        self.learning_metrics["total_observations"] += 1

        # Trigger pattern analysis if threshold reached
        if len(self.observation_buffer) >= self.learning_config["observation_threshold"]:
            await self._analyze_patterns()

        logger.debug(f"Learning observation recorded: {observation_id} ({learning_type.value})")
        return observation_id

    async def provide_feedback(
        self,
        task_id: str,
        feedback_type: str,
        feedback_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_id: str | None = None,
    ) -> str:
        """Process user feedback for learning"""

        feedback_id = str(uuid.uuid4())

        # Convert feedback to observation
        observation_data = {
            "task_id": task_id,
            "feedback_type": feedback_type,
            "feedback_data": feedback_data,
            "user_id": user_id,
        }

        # Determine learning type from feedback
        learning_type = self._classify_feedback_learning_type(feedback_type, feedback_data)

        # Record as observation
        await self.observe(
            source=LearningSource.USER_FEEDBACK,
            learning_type=learning_type,
            context={"task_id": task_id, "user_id": user_id},
            observation_data=observation_data,
            outcome_metrics=self._extract_feedback_metrics(feedback_data),
        )

        # Store in feedback buffer
        self.feedback_buffer.append(
            {
                "id": feedback_id,
                "timestamp": datetime.now(timezone.utc),
                "task_id": task_id,
                "feedback_type": feedback_type,
                "data": feedback_data,
            }
        )

        logger.info(f"Feedback processed for learning: {feedback_id}")
        return feedback_id

    async def _analyze_patterns(self) -> None:
        """Analyze observations to identify learning patterns"""

        try:
            # Get recent observations grouped by learning type
            recent_observations = list(self.observation_buffer)[-50:]  # Last 50 observations
            observation_groups: defaultdict[LearningType, list[LearningObservation]] = defaultdict(
                list
            )

            for obs in recent_observations:
                observation_groups[obs.learning_type].append(obs)

            # Analyze each group for patterns
            for learning_type, observations in observation_groups.items():
                if len(observations) >= 3:  # Minimum for pattern analysis
                    pattern = await self._identify_pattern(learning_type, observations)
                    if pattern:
                        await self._register_pattern(pattern)

            logger.debug(f"Pattern analysis completed. Groups: {len(observation_groups)}")

        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")

    async def _identify_pattern(
        self, learning_type: LearningType, observations: list[LearningObservation]
    ) -> LearningPattern | None:
        """Identify pattern from group of observations"""

        if not observations:
            return None

        # Simple pattern identification (can be enhanced with ML)
        pattern_id = str(uuid.uuid4())

        # Analyze common elements
        common_context = self._find_common_context(observations)
        common_outcomes = self._analyze_common_outcomes(observations)

        # Calculate pattern metrics
        avg_confidence = sum(obs.confidence_score for obs in observations) / len(observations)
        success_rate = self._calculate_success_rate(observations)

        if avg_confidence > self.learning_config["confidence_threshold"] and success_rate > 0.5:
            # Create pattern description
            description = await self._generate_pattern_description(
                learning_type, observations, common_context
            )

            pattern = LearningPattern(
                id=pattern_id,
                pattern_type=learning_type,
                description=description,
                trigger_conditions=common_context,
                learned_behavior=common_outcomes,
                success_rate=success_rate,
                confidence_score=avg_confidence,
                observation_count=len(observations),
            )

            return pattern

        return None

    async def _generate_pattern_description(
        self,
        learning_type: LearningType,
        observations: list[LearningObservation],
        common_context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Generate human-readable pattern description"""

        if not self.llm_client:
            return f"Pattern identified for {learning_type.value} with {len(observations)} observations"

        pattern_prompt = f"""
        Analyze the following learning observations and create a clear pattern description.

        LEARNING TYPE: {learning_type.value}
        OBSERVATIONS COUNT: {len(observations)}

        COMMON CONTEXT:
        {json.dumps(common_context, indent=2)}

        OBSERVATION SUMMARY:
        {self._summarize_observations(observations)}

        Create a concise, actionable description of the identified pattern.
        Focus on:
        1. What triggers this pattern
        2. What behavior or outcome is observed
        3. Under what conditions it succeeds

        Keep it under 100 words.
        """

        try:
            response = await self.llm_client.text_completion(pattern_prompt)
            if not response.success:
                raise RuntimeError(response.error_message or "taalmodel gaf geen antwoord")

            return response.content.strip()

        except Exception as e:
            logger.error(f"Pattern description generation failed: {e}")
            return f"Pattern identified for {learning_type.value} with {len(observations)} observations"

    async def _register_pattern(self, pattern: LearningPattern) -> None:
        """Register a newly identified pattern with transactional consistency.

        SECURITY FIX (P0): Uses write-ahead pattern for database consistency.
        """
        # Check for existing similar patterns
        similar_pattern = self._find_similar_pattern(pattern)

        if similar_pattern:
            # Update existing pattern
            similar_pattern.observation_count += pattern.observation_count
            similar_pattern.success_rate = (similar_pattern.success_rate + pattern.success_rate) / 2
            similar_pattern.confidence_score = (
                similar_pattern.confidence_score + pattern.confidence_score
            ) / 2
            similar_pattern.last_updated = datetime.now(timezone.utc)
            similar_pattern.version += 1

            logger.info(f"Pattern updated: {similar_pattern.id} (v{similar_pattern.version})")
        else:
            # P0 FIX: Persist to database FIRST (write-ahead)
            if self._repository and self.tenant_id is not None:
                try:
                    await self._repository.save_pattern(self.tenant_id, pattern)
                except Exception as exc:
                    logger.error("Failed to persist pattern %s: %s", pattern.id, exc)
                    raise RuntimeError(f"Failed to persist learning pattern: {exc}") from exc

            # Only update in-memory state AFTER successful DB write
            self.patterns[pattern.id] = pattern
            self.pattern_buffer.append(pattern)
            self.learning_metrics["patterns_learned"] += 1

            # Create adaptation rule if confidence is high
            if pattern.confidence_score > self.learning_config["confidence_threshold"]:
                await self._create_adaptation_rule(pattern)

            logger.info(f"New pattern registered: {pattern.id} ({pattern.pattern_type.value})")

    async def _create_adaptation_rule(self, pattern: LearningPattern) -> None:
        """Create adaptation rule from learned pattern with transactional consistency.

        SECURITY FIX (P0): Uses write-ahead pattern for database consistency.
        """
        rule_id = str(uuid.uuid4())

        # Generate rule based on pattern
        rule = AdaptationRule(
            id=rule_id,
            name=f"Adaptation for {pattern.pattern_type.value}",
            condition=json.dumps(pattern.trigger_conditions),
            action=json.dumps(pattern.learned_behavior),
            parameters={
                "pattern_id": pattern.id,
                "confidence_threshold": pattern.confidence_score,
                "success_rate_threshold": pattern.success_rate,
            },
            success_metrics=["improvement_rate", "success_rate", "efficiency_gain"],
        )

        # P0 FIX: Persist to database FIRST (write-ahead)
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_rule(self.tenant_id, rule)
            except Exception as exc:
                logger.error("Failed to persist rule %s: %s", rule_id, exc)
                raise RuntimeError(f"Failed to persist adaptation rule: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.adaptation_rules[rule_id] = rule

        logger.info(f"Adaptation rule created: {rule_id}")

    async def apply_adaptations(self, context: dict[str, Any]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Apply relevant adaptations based on current context"""

        applied_adaptations: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        current_time = datetime.now(timezone.utc)

        # Check each active adaptation rule
        for rule in self.adaptation_rules.values():
            if not rule.active:
                continue

            # Check cooldown
            time_since_last = (current_time - rule.created_at).total_seconds()
            if (
                rule.trigger_count > 0
                and time_since_last < self.learning_config["adaptation_cooldown"]
            ):
                continue

            # Check if rule applies to current context
            if await self._rule_matches_context(rule, context):
                try:
                    # Apply adaptation
                    adaptation_result = await self._execute_adaptation(rule, context)

                    if adaptation_result["success"]:
                        rule.trigger_count += 1
                        rule.success_count += 1
                        applied_adaptations.append(adaptation_result)
                        self.learning_metrics["adaptations_applied"] += 1

                        # Persist rule stats
                        if self._repository and self.tenant_id is not None:
                            try:
                                await self._repository.increment_rule_stats(rule.id, True)
                            except Exception as exc:
                                logger.error("Failed to persist rule stats %s: %s", rule.id, exc)

                        logger.info(f"Adaptation applied: {rule.id}")
                    else:
                        rule.trigger_count += 1
                        if self._repository and self.tenant_id is not None:
                            try:
                                await self._repository.increment_rule_stats(rule.id, False)
                            except Exception as exc:
                                logger.error("Failed to persist rule stats %s: %s", rule.id, exc)

                except Exception as e:
                    logger.error(f"Adaptation execution failed: {e}")

        return applied_adaptations

    async def _rule_matches_context(self, rule: AdaptationRule, context: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if adaptation rule matches current context"""

        try:
            rule_conditions = json.loads(rule.condition)

            # Simple matching logic (can be enhanced)
            for key, expected_value in rule_conditions.items():
                if key not in context:
                    return False

                if (
                    isinstance(expected_value, str)
                    and expected_value.lower() not in str(context[key]).lower()
                ):
                    return False
                elif (
                    isinstance(expected_value, (int, float))
                    and abs(context[key] - expected_value) > 0.1
                ):
                    return False

            return True

        except Exception as e:
            logger.error(f"Rule matching failed: {e}")
            return False

    async def _execute_adaptation(
        self, rule: AdaptationRule, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute an adaptation rule"""

        try:
            action_data = json.loads(rule.action)

            # Mock adaptation execution (can be enhanced with actual system modifications)
            adaptation_result = {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "action_taken": action_data,
                "context": context,
                "success": True,
                "impact_metrics": {
                    "efficiency_gain": 0.15,
                    "accuracy_improvement": 0.08,
                    "user_satisfaction": 0.12,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Record adaptation as observation
            await self.observe(
                source=LearningSource.SYSTEM_MONITORING,
                learning_type=LearningType.BEHAVIORAL_ADAPTATION,
                context=context,
                observation_data=adaptation_result,
                outcome_metrics=adaptation_result["impact_metrics"],
            )

            return adaptation_result

        except Exception as e:
            return {
                "rule_id": rule.id,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def generate_insights(self) -> list[LearningInsight]:
        """Generate insights from accumulated learning"""

        insights: list[LearningInsight] = []
        try:
            # Analyze patterns for insights
            for pattern in self.patterns.values():
                if pattern.confidence_score > 0.8 and pattern.observation_count >= 5:
                    insight = await self._create_pattern_insight(pattern)
                    if insight:
                        insights.append(insight)

            # Analyze feedback trends
            feedback_insight = await self._analyze_feedback_trends()
            if feedback_insight:
                insights.append(feedback_insight)

            # Analyze adaptation effectiveness
            adaptation_insight = await self._analyze_adaptation_effectiveness()
            if adaptation_insight:
                insights.append(adaptation_insight)

            # Store insights (in-memory + persist)
            for insight in insights:
                self.insights[insight.id] = insight
                if self._repository and self.tenant_id is not None:
                    try:
                        await self._repository.save_insight(self.tenant_id, insight)
                    except Exception as exc:
                        logger.error("Failed to persist insight %s: %s", insight.id, exc)

            logger.info(f"Generated {len(insights)} learning insights")

        except Exception as e:
            logger.error(f"Insight generation failed: {e}")

        return insights

    async def _create_pattern_insight(self, pattern: LearningPattern) -> LearningInsight | None:
        """Create insight from a learned pattern"""

        insight_id = str(uuid.uuid4())

        # Analyze pattern impact
        impact_assessment = {
            "performance_impact": pattern.success_rate,
            "confidence_level": pattern.confidence_score,
            "usage_frequency": min(pattern.observation_count / 100, 1.0),
        }

        # Generate recommendations
        recommendations = [
            f"Consider implementing automated {pattern.pattern_type.value}",
            f"Monitor pattern effectiveness with {pattern.observation_count} observations",
            f"Success rate of {pattern.success_rate:.1%} suggests reliable pattern",
        ]

        insight = LearningInsight(
            id=insight_id,
            title=f"Pattern Insight: {pattern.pattern_type.value.replace('_', ' ').title()}",
            description=pattern.description,
            learning_type=pattern.pattern_type,
            supporting_observations=[
                obs.id
                for obs in self.observations.values()
                if obs.learning_type == pattern.pattern_type
            ][:5],
            confidence_score=pattern.confidence_score,
            impact_assessment=impact_assessment,
            recommended_actions=recommendations,
        )

        return insight

    async def _analyze_feedback_trends(self) -> LearningInsight | None:
        """Analyze user feedback trends"""

        if len(self.feedback_buffer) < 10:
            return None

        insight_id = str(uuid.uuid4())
        recent_feedback = list(self.feedback_buffer)[-20:]

        # Simple trend analysis
        positive_feedback = sum(
            1
            for fb in recent_feedback
            if fb.get("feedback_type") in ["positive", "satisfied", "approved"]
        )

        feedback_rate = positive_feedback / len(recent_feedback)

        insight = LearningInsight(
            id=insight_id,
            title="User Feedback Trend Analysis",
            description=f"Analysis of {len(recent_feedback)} recent feedback entries shows {feedback_rate:.1%} positive sentiment",
            learning_type=LearningType.USER_PREFERENCE,
            supporting_observations=[],
            confidence_score=0.7,
            impact_assessment={
                "user_satisfaction": feedback_rate,
                "feedback_volume": len(recent_feedback) / 100,
                "trend_strength": abs(feedback_rate - 0.5) * 2,
            },
            recommended_actions=[
                "Continue successful patterns if feedback is positive",
                "Investigate issues if feedback is negative",
                "Increase feedback collection frequency",
            ],
        )

        return insight

    async def _analyze_adaptation_effectiveness(self) -> LearningInsight | None:
        """Analyze effectiveness of applied adaptations"""

        active_rules = [rule for rule in self.adaptation_rules.values() if rule.trigger_count > 0]

        if not active_rules:
            return None

        insight_id = str(uuid.uuid4())

        total_triggers = sum(rule.trigger_count for rule in active_rules)
        total_successes = sum(rule.success_count for rule in active_rules)
        success_rate = total_successes / total_triggers if total_triggers > 0 else 0

        insight = LearningInsight(
            id=insight_id,
            title="Adaptation Effectiveness Analysis",
            description=f"Analysis of {len(active_rules)} adaptation rules with {success_rate:.1%} success rate",
            learning_type=LearningType.BEHAVIORAL_ADAPTATION,
            supporting_observations=[],
            confidence_score=0.8,
            impact_assessment={
                "adaptation_success_rate": success_rate,
                "adaptation_frequency": len(active_rules) / 10,
                "system_improvement": success_rate * 0.5,
            },
            recommended_actions=[
                "Optimize successful adaptation rules",
                "Review and disable low-performing rules",
                "Increase adaptation rule coverage",
            ],
        )

        return insight

    # Utility methods

    def _calculate_importance_score(
        self,
        learning_type: LearningType,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        observation_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate importance score for observation"""

        base_importance = {
            LearningType.PERFORMANCE_OPTIMIZATION: 0.9,
            LearningType.ERROR_CORRECTION: 0.8,
            LearningType.USER_PREFERENCE: 0.7,
            LearningType.STRATEGY_REFINEMENT: 0.6,
            LearningType.PATTERN_RECOGNITION: 0.5,
        }.get(learning_type, 0.5)

        # Adjust based on context richness
        context_bonus = min(len(context) * 0.05, 0.2)
        data_bonus = min(len(observation_data) * 0.03, 0.15)

        return min(base_importance + context_bonus + data_bonus, 1.0)

    def _calculate_confidence_score(
        self,
        source: LearningSource,
        observation_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        outcome_metrics: dict[str, float],
    ) -> float:
        """Calculate confidence score for observation"""

        source_confidence = {
            LearningSource.TASK_EXECUTION: 0.8,
            LearningSource.USER_FEEDBACK: 0.9,
            LearningSource.PERFORMANCE_METRICS: 0.7,
            LearningSource.SYSTEM_MONITORING: 0.6,
        }.get(source, 0.5)

        # Adjust based on data quality
        data_quality = min(len(observation_data) * 0.1, 0.3)
        metrics_quality = min(len(outcome_metrics) * 0.15, 0.2)

        return min(source_confidence + data_quality + metrics_quality, 1.0)

    def _find_common_context(self, observations: list[LearningObservation]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Find common context elements across observations"""

        if not observations:
            return {}

        # Simple intersection of context keys and values
        common: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        first_context = observations[0].context

        for key, value in first_context.items():
            if all(obs.context.get(key) == value for obs in observations[1:]):
                common[key] = value

        return common

    def _analyze_common_outcomes(self, observations: list[LearningObservation]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze common outcomes across observations"""

        if not observations:
            return {}

        # Aggregate outcome metrics
        outcome_aggregates: defaultdict[str, list[float]] = defaultdict(list)

        for obs in observations:
            for metric, value in obs.outcome_metrics.items():
                if isinstance(value, (int, float)):
                    outcome_aggregates[metric].append(value)

        # Calculate averages
        common_outcomes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for metric, values in outcome_aggregates.items():
            if values:
                common_outcomes[f"avg_{metric}"] = sum(values) / len(values)
                common_outcomes[f"trend_{metric}"] = (
                    "positive" if values[-1] > values[0] else "negative"
                )

        return common_outcomes

    def _calculate_success_rate(self, observations: list[LearningObservation]) -> float:
        """Calculate success rate from observations"""

        if not observations:
            return 0.0

        # Simple success calculation based on outcome metrics
        successful = 0

        for obs in observations:
            # Consider observation successful if average outcome metric > 0.6
            if obs.outcome_metrics:
                avg_score = sum(obs.outcome_metrics.values()) / len(obs.outcome_metrics)
                if avg_score > 0.6:
                    successful += 1
            else:
                # If no metrics, use confidence score
                if obs.confidence_score > 0.7:
                    successful += 1

        return successful / len(observations)

    def _find_similar_pattern(self, new_pattern: LearningPattern) -> LearningPattern | None:
        """Find existing similar pattern"""

        for pattern in self.patterns.values():
            if pattern.pattern_type == new_pattern.pattern_type:
                # Simple similarity check based on trigger conditions
                common_keys = set(pattern.trigger_conditions.keys()) & set(
                    new_pattern.trigger_conditions.keys()
                )
                if len(common_keys) > 0:
                    similarity = len(common_keys) / max(
                        len(pattern.trigger_conditions),
                        len(new_pattern.trigger_conditions),
                    )
                    if similarity > 0.7:
                        return pattern

        return None

    def _summarize_observations(self, observations: list[LearningObservation]) -> str:
        """Create summary of observations for LLM analysis"""

        summary_parts: list[str] = []
        for i, obs in enumerate(observations[:5]):  # Limit to first 5
            summary = f"Observation {i + 1}: {obs.source.value} -> {obs.learning_type.value}"
            if obs.outcome_metrics:
                avg_score = sum(obs.outcome_metrics.values()) / len(obs.outcome_metrics)
                summary += f" (score: {avg_score:.2f})"
            summary_parts.append(summary)

        if len(observations) > 5:
            summary_parts.append(f"... and {len(observations) - 5} more observations")

        return "\n".join(summary_parts)

    def _classify_feedback_learning_type(
        self, feedback_type: str, feedback_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> LearningType:
        """Classify feedback into learning type"""

        type_mapping = {
            "performance": LearningType.PERFORMANCE_OPTIMIZATION,
            "error": LearningType.ERROR_CORRECTION,
            "strategy": LearningType.STRATEGY_REFINEMENT,
            "preference": LearningType.USER_PREFERENCE,
            "behavior": LearningType.BEHAVIORAL_ADAPTATION,
        }

        for key, learning_type in type_mapping.items():
            if key in feedback_type.lower():
                return learning_type

        return LearningType.USER_PREFERENCE

    def _extract_feedback_metrics(self, feedback_data: dict[str, Any]) -> dict[str, float]:  # TODO(TYPE): replace Any with concrete type
        """Extract numeric metrics from feedback"""

        metrics: dict[str, float] = {}
        # Look for numeric values
        for key, value in feedback_data.items():
            if isinstance(value, (int, float)):
                metrics[key] = float(value)
            elif isinstance(value, str):
                # Try to extract sentiment score
                if "good" in value.lower() or "excellent" in value.lower():
                    metrics["sentiment_score"] = 0.8
                elif "bad" in value.lower() or "poor" in value.lower():
                    metrics["sentiment_score"] = 0.2
                else:
                    metrics["sentiment_score"] = 0.5

        return metrics

    async def register_adaptation_rule(self, rule: AdaptationRule) -> None:
        """Register a new adaptation rule"""
        self.adaptation_rules[rule.id] = rule

        # Persist rule (write-through)
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_rule(self.tenant_id, rule)
            except Exception as exc:
                logger.error("Failed to persist rule %s: %s", rule.id, exc)

        logger.info(f"Adaptation rule registered: {rule.id} ({rule.name})")

    async def record_insight(self, insight: LearningInsight) -> None:
        """Record a new learning insight"""
        self.insights[insight.id] = insight

        # Persist insight (write-through)
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_insight(self.tenant_id, insight)
            except Exception as exc:
                logger.error("Failed to persist insight %s: %s", insight.id, exc)

        logger.info(f"Learning insight recorded: {insight.id} ({insight.title})")

    # Public API methods

    def get_learning_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current learning system status"""

        return {
            "learning_active": self._learning_active,
            "total_observations": len(self.observations),
            "active_patterns": len(self.patterns),
            "adaptation_rules": len(self.adaptation_rules),
            "recent_insights": len(
                [i for i in self.insights.values() if (datetime.now(timezone.utc) - i.created_at).days < 7]
            ),
            "learning_metrics": self.learning_metrics,
            "last_learning_cycle": self._last_learning_cycle.isoformat(),
        }

    def get_patterns(self, learning_type: LearningType | None = None) -> list[LearningPattern]:
        """Get learned patterns, optionally filtered by type"""

        patterns = list(self.patterns.values())

        if learning_type:
            patterns = [p for p in patterns if p.pattern_type == learning_type]

        return sorted(patterns, key=lambda x: x.confidence_score, reverse=True)

    def get_insights(self, days_back: int = 30) -> list[LearningInsight]:
        """Get recent learning insights"""

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        recent_insights = [
            insight for insight in self.insights.values() if insight.created_at >= cutoff_date
        ]

        return sorted(recent_insights, key=lambda x: x.confidence_score, reverse=True)


# ---------------------------------------------------------------------------
# Tenant-aware factory  (replaces legacy global singleton)
# ---------------------------------------------------------------------------

_tenant_learning_loops: dict[int, "LearningLoop"] = {}
_legacy_learning_loop: Optional["LearningLoop"] = None


def _get_learning_loop() -> "LearningLoop":
    """Return the legacy process-wide learning loop instance.

    Older tests and modules still import this helper directly. Keep it as an
    in-memory, non-persistent singleton so legacy call sites continue to work
    without tenant context.
    """

    global _legacy_learning_loop
    if _legacy_learning_loop is None:
        _legacy_learning_loop = LearningLoop()
    return _legacy_learning_loop


def get_learning_loop_for_tenant(
    tenant_id: int,
    repository: Optional["LearningRepository"] = None,
) -> "LearningLoop":
    """Return a tenant-specific LearningLoop (lazy-init, cached)."""
    if tenant_id not in _tenant_learning_loops:
        _tenant_learning_loops[tenant_id] = LearningLoop(tenant_id=tenant_id, repository=repository)
    return _tenant_learning_loops[tenant_id]


# SECURITY FIX (P0): Removed global singleton to prevent cross-tenant data leakage.
# All callers MUST provide tenant_id or have tenant context set.
# There is no fallback - this is intentional to enforce tenant isolation.


async def record_task_learning(
    task_id: str,
    execution_result: ExecutionResult,
    context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None = None,
    repository: Optional["LearningRepository"] = None,
) -> str:
    """Convenience function to record task execution learning.

    SECURITY: When *tenant_id* is provided the observation is persisted and
    tenant-scoped. If tenant_id is None, attempts to get from context.

    Raises:
        TenantContextError: If no tenant_id provided and no tenant context available.
        This prevents accidental cross-tenant data leakage.
    """
    # First try explicit tenant_id
    effective_tenant_id = tenant_id

    # If no tenant_id provided, try to get from context
    if effective_tenant_id is None:
        try:
            from src.core.middleware.tenant_context import get_tenant_id as _ctx_tid

            effective_tenant_id = _ctx_tid()
        except Exception:
            pass  # Will raise below if still None

    # Backward compatibility for legacy callers that predate tenant-aware loops.
    if effective_tenant_id is None and repository is None:
        learning_loop = _get_learning_loop()
    else:
        # SECURITY FIX (P0): Enforce tenant_id - no fallback to global
        if effective_tenant_id is None:
            raise TenantContextError(
                "Tenant ID required for learning observation. "
                "Provide tenant_id parameter or set tenant context."
            )

        learning_loop = get_learning_loop_for_tenant(effective_tenant_id, repository)

    learning_type = LearningType.PERFORMANCE_OPTIMIZATION
    if not execution_result.success:
        learning_type = LearningType.ERROR_CORRECTION

    outcome_metrics = {
        "success_rate": 1.0 if execution_result.success else 0.0,
        "execution_time": execution_result.execution_time,
        "quality_score": 0.8 if execution_result.success else 0.3,
    }

    return await learning_loop.observe(
        source=LearningSource.TASK_EXECUTION,
        learning_type=learning_type,
        context=context or {"task_id": task_id},
        observation_data=execution_result.result_data or {},
        outcome_metrics=outcome_metrics,
    )
