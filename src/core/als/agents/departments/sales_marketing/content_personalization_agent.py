"""
Content Personalization Agent - Sales & Marketing

Technology: ML
Function: Content personalization, recommendation engine, audience segmentation
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from src.core.als.agents.departments.base_department_agent import DepartmentType, MLAgent
from src.core.als.agents.symbiotic_agent import ExecutionResult

logger = logging.getLogger(__name__)


class ContentPersonalizationAgent(MLAgent):
    """
    Content Personalization Agent

    Responsibilities:
    - Personalized content recommendations
    - Audience segmentation
    - Behavioral targeting
    - Content matching
    - Dynamic content optimization
    - Recommendation engine management

    Capabilities:
    - Personalization
    - Segmentation
    - Recommendation
    - Behavioral analysis
    - A/B testing
    """

    department = DepartmentType.SALES_MARKETING
    priority = "high"

    department_capabilities = [
        "personalization",
        "segmentation",
        "recommendation",
        "behavioral_analysis",
        "dynamic_content",
        "audience_clustering",
        "preference_learning",
        "content_matching",
    ]

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(agent_id, tenant_id, **kwargs)

        self.recommendation_types = [
            "content",
            "product",
            "next_best_action",
            "channel",
            "timing",
        ]

        self.segmentation_methods = [
            "demographic",
            "behavioral",
            "psychographic",
            "rfm",  # Recency, Frequency, Monetary
            "predictive",
        ]

        self.model_accuracy = 0.89
        self.personalization_threshold = 0.7

        logger.info(f"ContentPersonalizationAgent {agent_id} initialized")

    async def orient(
        self,
        observation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze user behavior and content context."""
        payload = observation.get("payload", {})

        user_data = payload.get("user", {})
        content_pool = payload.get("content_pool", [])
        interaction_history = payload.get("interactions", [])

        analysis = {
            **observation,
            "user_profile": self._build_user_profile(user_data, interaction_history),
            "behavioral_segments": self._identify_segments(user_data, interaction_history),
            "content_preferences": self._extract_preferences(interaction_history),
            "engagement_patterns": self._analyze_engagement_patterns(interaction_history),
            "content_inventory": self._analyze_content_pool(content_pool),
            "personalization_opportunities": self._find_personalization_opps(
                user_data, content_pool
            ),
        }

        return analysis

    async def decide(
        self,
        orientation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Decide personalization action."""
        user_profile = orientation.get("user_profile", {})
        opps = orientation.get("personalization_opportunities", [])
        segments = orientation.get("behavioral_segments", [])

        if len(opps) > 10:
            return "generate_personalized_content_feed"
        elif user_profile.get("engagement_level") == "high":
            return "recommend_next_best_action"
        elif len(segments) > 1:
            return "refine_audience_segmentation"
        elif user_profile.get("new_user", False):
            return "create_onboarding_personalization"
        else:
            return "optimize_content_matching"

    async def act(self, decision: str) -> ExecutionResult:
        """Execute personalization action."""
        logger.info(f"ContentPersonalizationAgent acting: {decision}")

        result_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "action": decision
        }  # TODO(TYPE): replace Any with concrete type

        if decision == "generate_personalized_content_feed":
            result_data["personalized_feed"] = await self._generate_content_feed()
        elif decision == "recommend_next_best_action":
            result_data["next_best_action"] = await self._get_next_best_action()
        elif decision == "refine_audience_segmentation":
            result_data["segments"] = await self._refine_segments()
        elif decision == "create_onboarding_personalization":
            result_data["onboarding_flow"] = self._create_onboarding_flow()
        else:
            result_data["content_matches"] = await self._optimize_matches()

        return ExecutionResult(
            task_id=f"personalize_{self.agent_id}_{id(decision)}",
            success=True,
            result_data=result_data,
        )

    def _build_user_profile(
        self,
        user_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build comprehensive user profile."""
        # Calculate engagement level
        recent_interactions = len(
            [i for i in interactions if self._is_recent_interaction(i, days=30)]
        )

        engagement_level = (
            "high" if recent_interactions > 10 else "medium" if recent_interactions > 3 else "low"
        )

        return {
            "user_id": user_data.get("id"),
            "engagement_level": engagement_level,
            "content_affinity": self._calculate_content_affinity(interactions),
            "channel_preference": self._detect_channel_preference(interactions),
            "topic_interests": self._extract_topic_interests(interactions),
            "purchase_stage": self._determine_purchase_stage(interactions),
            "new_user": len(interactions) < 3,
        }

    def _is_recent_interaction(
        self,
        interaction: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        days: int = 30,
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if an interaction is within the specified days."""
        ts: str | None = interaction.get("timestamp")
        if ts is None:
            return False
        try:
            interaction_time = datetime.fromisoformat(ts)
            return (datetime.now(timezone.utc) - interaction_time).days < days
        except (ValueError, TypeError):
            return False

    def _identify_segments(
        self,
        user_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Identify behavioral segments for user."""
        segments: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # RFM Analysis mock
        if len(interactions) > 10:
            segments.append(
                {
                    "type": "rfm",
                    "segment": "champions",
                    "score": 95,
                }
            )
        elif len(interactions) > 5:
            segments.append(
                {
                    "type": "rfm",
                    "segment": "loyal_customers",
                    "score": 75,
                }
            )
        else:
            segments.append(
                {
                    "type": "rfm",
                    "segment": "new_customers",
                    "score": 40,
                }
            )

        # Behavioral segments
        topics = self._extract_topic_interests(interactions)
        if "pricing" in topics or "roi" in topics:
            segments.append(
                {
                    "type": "behavioral",
                    "segment": "price_conscious",
                    "confidence": 0.8,
                }
            )

        if "technical" in topics or "integration" in topics:
            segments.append(
                {
                    "type": "behavioral",
                    "segment": "technical_buyer",
                    "confidence": 0.75,
                }
            )

        return segments

    def _extract_preferences(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract user content preferences."""
        content_types: dict[str, int] = {}
        topics: dict[str, int] = {}

        for interaction in interactions:
            content_type: str = interaction.get("content_type", "unknown")
            topic: str = interaction.get("topic", "general")

            content_types[content_type] = content_types.get(content_type, 0) + 1
            topics[topic] = topics.get(topic, 0) + 1

        # Get top preferences
        top_content = sorted(content_types.items(), key=lambda x: x[1], reverse=True)[:3]
        top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "preferred_content_types": [c[0] for c in top_content],
            "preferred_topics": [t[0] for t in top_topics],
            "content_type_weights": dict(top_content),
            "topic_weights": dict(top_topics),
        }

    def _analyze_engagement_patterns(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze user engagement patterns."""
        if not interactions:
            return {"pattern": "insufficient_data"}

        # Time analysis mock
        return {
            "peak_engagement_day": "Tuesday",
            "peak_engagement_time": "10:00 AM",
            "avg_session_duration": 240,  # seconds
            "content_consumption_rate": 0.75,
            "return_frequency": "weekly",
        }

    def _analyze_content_pool(
        self,
        content_pool: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze available content inventory."""
        total_content = len(content_pool)

        content_by_type: dict[str, int] = {}
        for content in content_pool:
            content_type: str = content.get("type", "unknown")
            content_by_type[content_type] = content_by_type.get(content_type, 0) + 1

        return {
            "total_content": total_content,
            "content_by_type": content_by_type,
            "fresh_content": sum(1 for c in content_pool if c.get("is_new", False)),
            "personalized_variants": sum(1 for c in content_pool if c.get("has_variants", False)),
        }

    def _find_personalization_opps(
        self,
        user_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        content_pool: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Find personalization opportunities."""
        opportunities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Mock opportunities based on user attributes
        if not user_data.get("industry"):
            opportunities.append(
                {
                    "type": "industry_content",
                    "priority": "high",
                    "potential_impact": "increase_engagement_25%",
                }
            )

        if len(content_pool) > 100:
            opportunities.append(
                {
                    "type": "content_recommendation",
                    "priority": "high",
                    "potential_impact": "increase_ctr_40%",
                }
            )

        return opportunities

    def _calculate_content_affinity(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:  # TODO(TYPE): replace Any with concrete type
        """Calculate affinity scores for content types."""
        affinity: dict[str, list[float]] = {}

        for interaction in interactions:
            content_type: str = interaction.get("content_type", "unknown")
            score: float = cast(float, interaction.get("engagement_score", 0.5))

            if content_type not in affinity:
                affinity[content_type] = []
            affinity[content_type].append(score)

        # Average scores with None check
        result: dict[str, float] = {}
        for content_type, scores in affinity.items():
            if scores:  # Check if list is not empty
                result[content_type] = sum(scores) / len(scores)
            else:
                result[content_type] = 0.0
        return result

    def _detect_channel_preference(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Detect preferred engagement channel."""
        channels: dict[str, int] = {}

        for interaction in interactions:
            channel: str = interaction.get("channel", "email")
            channels[channel] = channels.get(channel, 0) + 1

        if not channels:
            return "email"
        return max(channels.items(), key=lambda x: x[1])[0]

    def _extract_topic_interests(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Extract topics of interest from interactions."""
        topics: dict[str, int] = {}

        for interaction in interactions:
            topic: str = interaction.get("topic", "general")
            topics[topic] = topics.get(topic, 0) + 1

        # Return top 5 topics
        sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_topics[:5]]

    def _determine_purchase_stage(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Determine user's purchase journey stage."""
        # Simple stage determination based on interaction types
        has_pricing = any(i.get("topic") == "pricing" for i in interactions)
        has_demo = any(i.get("action") == "demo_request" for i in interactions)
        has_case_study = any(i.get("content_type") == "case_study" for i in interactions)

        if has_demo:
            return "decision"
        elif has_pricing and has_case_study:
            return "consideration"
        elif has_case_study:
            return "interest"
        else:
            return "awareness"

    async def _generate_content_feed(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate personalized content feed."""
        return {
            "feed_id": f"feed_{datetime.now(timezone.utc).timestamp()}",
            "items": [
                {
                    "content_id": "c001",
                    "title": "How to Scale Your Marketing with AI",
                    "type": "blog",
                    "personalization_score": 0.92,
                    "match_reasons": ["topic_interest", "reading_history"],
                },
                {
                    "content_id": "c002",
                    "title": "ROI Calculator: AI Marketing Tools",
                    "type": "interactive",
                    "personalization_score": 0.88,
                    "match_reasons": ["purchase_stage", "engagement_pattern"],
                },
                {
                    "content_id": "c003",
                    "title": "Case Study: Enterprise Success Story",
                    "type": "case_study",
                    "personalization_score": 0.85,
                    "match_reasons": ["industry_match", "company_size"],
                },
            ],
            "personalization_coverage": 0.87,
        }

    async def _get_next_best_action(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get next best action recommendation."""
        return {
            "action": "schedule_demo",
            "channel": "email",
            "timing": "Tuesday 10:00 AM",
            "confidence": 0.89,
            "expected_outcome": "demo_booking",
            "personalization_elements": {
                "subject_line": "Quick demo tailored to {{company}}'s needs",
                "cta_text": "See how {{competitor}} achieved 3x ROI",
            },
        }

    async def _refine_segments(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Refine audience segmentation."""
        return [
            {
                "segment_id": "seg_001",
                "name": "High-Intent Enterprise",
                "size": 2500,
                "criteria": ["company_size > 1000", "pricing_page_visits > 2"],
                "predicted_conversion": 0.15,
            },
            {
                "segment_id": "seg_002",
                "name": "Content Engaged Mid-Market",
                "size": 5000,
                "criteria": ["company_size 100-1000", "content_downloads > 3"],
                "predicted_conversion": 0.08,
            },
        ]

    def _create_onboarding_flow(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create personalized onboarding flow."""
        return {
            "flow_name": "Personalized Onboarding",
            "steps": [
                {"step": 1, "content": "Welcome video", "personalized": False},
                {"step": 2, "content": "Industry-specific use cases", "personalized": True},
                {"step": 3, "content": "ROI calculator", "personalized": True},
                {"step": 4, "content": "Schedule success call", "personalized": True},
            ],
            "estimated_completion": "5 minutes",
        }

    async def _optimize_matches(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Optimize content-to-user matching."""
        return [
            {"user_segment": "enterprise", "content_type": "whitepaper", "match_score": 0.91},
            {"user_segment": "smb", "content_type": "video", "match_score": 0.87},
            {"user_segment": "startup", "content_type": "blog", "match_score": 0.85},
        ]

    async def predict(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Predict content engagement probability."""
        user_profile: dict[str, Any] = data.get(
            "user_profile", {}
        )  # TODO(TYPE): replace Any with concrete type
        content: dict[str, Any] = data.get(
            "content", {}
        )  # TODO(TYPE): replace Any with concrete type

        # Base prediction on profile match
        base_score = 0.5

        preferred_types: list[str] = user_profile.get("preferred_content_types", [])
        if content.get("type") in preferred_types:
            base_score += 0.25

        topic_interests: list[str] = user_profile.get("topic_interests", [])
        if content.get("topic") in topic_interests:
            base_score += 0.20

        if user_profile.get("engagement_level") == "high":
            base_score += 0.15

        return {
            "engagement_probability": min(base_score, 1.0),
            "confidence": self.model_accuracy,
            "predicted_action": "click" if base_score > 0.7 else "view",
            "recommended_variant": "A" if base_score > 0.6 else "B",
        }
