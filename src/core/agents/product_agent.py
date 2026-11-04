#!/usr/bin/env python3
"""
Product Agent - M-MDP Compliant Implementation
Specialized agent for product roadmap planning, feature prioritization, and product strategy
Based on business-analyst agent definition from agenten directory
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, cast
from collections.abc import Callable

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.agents.llm_types import TaskCharacteristics, TaskComplexity, agent_model_matcher
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel
from src.core.types import AgentType

logger = logging.getLogger(__name__)


class FeaturePriority(Enum):
    """Feature priority levels"""

    CRITICAL = "critical"  # P0 - Must have for MVP
    HIGH = "high"  # P1 - Important for success
    MEDIUM = "medium"  # P2 - Nice to have
    LOW = "low"  # P3 - Future consideration


class ProductPhase(Enum):
    """Product development phases"""

    DISCOVERY = "discovery"
    MVP = "mvp"
    GROWTH = "growth"
    SCALE = "scale"
    MATURE = "mature"


@dataclass
class ProductFeature:
    """Product feature definition"""

    feature_id: str
    name: str
    description: str
    priority: FeaturePriority
    effort_estimate: int  # Story points or days
    business_value: float  # 0.0-1.0 score
    dependencies: list[str]  # Other feature IDs
    release_target: str | None  # Target release version
    compliance_requirements: list[str] | None = None


@dataclass
class ProductRoadmap:
    """Product roadmap structure"""

    roadmap_id: str
    product_name: str
    current_phase: ProductPhase
    features: list[ProductFeature]
    milestones: dict[str, datetime]
    success_metrics: dict[str, float]
    risk_factors: list[str]
    confidence_score: float


@dataclass
class CompetitiveAnalysis:
    """Competitive landscape analysis"""

    competitor_name: str
    strengths: list[str]
    weaknesses: list[str]
    market_share: float
    pricing_model: str
    key_features: list[str]
    threat_level: str  # "low", "medium", "high", "critical"


class ProductAgent(CriticMixin, EnhancedBaseAgent):
    """
    Product Agent - Strategic product planning and feature prioritization
    M-MDP Compliant: Sync for planning logic, async for I/O
    """

    def __init__(
        self,
        agent_id: str = "product_agent_001",
        tenant_id: int = 1,
        llm_client: ChatTaalmodel | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_id,
            llm_client=llm_client,
        )
        self.__init_critic__(mode=CriticMode.SILENT)
        self.llm_client: ChatTaalmodel | None = llm_client

        # Register agent profile for intelligent model matching
        self._register_agent_profile()

    def _get_planning_method(
        self, planning_type: str
    ) -> Callable[..., Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get planning method by type - lazy lookup to avoid forward reference issues"""
        method_map: dict[str, str] = {
            "roadmap_planning": "_plan_product_roadmap",
            "feature_prioritization": "_prioritize_features",
            "competitive_analysis": "_analyze_competition",
            "compliance_assessment": "_assess_compliance_requirements",
            "user_story_generation": "_generate_user_stories",
            "technical_feasibility": "_assess_technical_feasibility",
            "release_planning": "_plan_release_schedule",
            "mvp_definition": "_define_mvp_scope",
        }
        method_name = method_map.get(planning_type)
        if method_name:
            method = getattr(self, method_name, None)
            if method:
                return cast(
                    Callable[..., Any], method
                )  # TODO(TYPE): replace Any with concrete type
        return None

    def _register_agent_profile(self) -> None:
        """Register agent profile for optimal model selection"""
        from src.core.agents.llm_types import AgentCategory, AgentProfile, TaskComplexity

        profile = AgentProfile(
            agent_type="product_agent",
            category=AgentCategory.STRATEGIC,
            typical_complexity=TaskComplexity.COMPLEX,
            reasoning_required=0.85,  # High strategic reasoning
            speed_priority=0.5,  # Quality over speed for product decisions
            cost_sensitivity=0.6,  # Balanced cost consideration
            context_needs=4000,  # Large context for roadmap planning
            special_requirements=[
                "strategic_planning",
                "prioritization",
                "market_analysis",
            ],
        )
        agent_model_matcher.register_agent_profile(profile)

    async def initialize(self) -> bool:
        """Initialize Product Agent with optimal LLM model"""
        try:
            # Get optimal model for this agent type
            optimal_model = agent_model_matcher.select_optimal_model("product_agent")

            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14); hier stond Google.
            self.llm_client = TenantTaalmodel(self.tenant_id)

            logger.info(
                f"Product Agent {self.agent_id} initialized with optimal model: {optimal_model}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Product Agent: {e}")
            return False

    async def get_capabilities(self) -> list[AgentCapability]:
        """Return agent capabilities"""
        return [
            AgentCapability(
                name="roadmap_planning",
                description="Create comprehensive product roadmaps with prioritized features",
                input_types=[
                    "product_vision",
                    "market_context",
                    "timeline",
                    "resources",
                ],
            ),
            AgentCapability(
                name="feature_prioritization",
                description="Prioritize features using business value and effort analysis",
                input_types=["feature_list", "business_goals", "constraints"],
            ),
            AgentCapability(
                name="competitive_analysis",
                description="Analyze competitive landscape and positioning",
                input_types=[
                    "competitors",
                    "market_segment",
                    "differentiation_factors",
                ],
            ),
            AgentCapability(
                name="compliance_assessment",
                description="Assess regulatory and compliance requirements",
                input_types=["regulations", "market_region", "product_type"],
            ),
            AgentCapability(
                name="mvp_definition",
                description="Define minimum viable product scope and features",
                input_types=["user_segments", "core_value_prop", "constraints"],
            ),
        ]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Process product planning task
        M-MDP: Async wrapper for sync business logic
        """
        start_time = datetime.now(timezone.utc)

        try:
            planning_type = task.parameters.get("planning_type", "roadmap_planning")

            planning_method = self._get_planning_method(planning_type)
            if planning_method is None:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Unknown planning type: {planning_type}",
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    agent_id=self.agent_id,
                )

            # Determine task complexity for model selection
            task_chars = self._analyze_task_characteristics(task.parameters)

            # SYNC planning logic (M-MDP compliant)
            product_result = planning_method(task.parameters)

            # ASYNC LLM enhancement (M-MDP compliant)
            enhanced_result = await self._enhance_with_llm_insights(
                planning_type, product_result, task.parameters, task_chars
            )

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data=enhanced_result,
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                agent_id=self.agent_id,
                confidence_score=product_result.get("confidence_score", 0.8),
            )

        except Exception as e:
            logger.error(f"Product planning failed: {e}")
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=str(e),
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                agent_id=self.agent_id,
            )

    def _analyze_task_characteristics(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> TaskCharacteristics:  # TODO(TYPE): replace Any with concrete type
        """Analyze task to determine optimal model characteristics"""
        complexity = TaskComplexity.MODERATE

        # Determine complexity based on task parameters
        feature_count = len(params.get("features", []))
        competitor_count = len(params.get("competitors", []))
        timeline_months = params.get("timeline_months", 6)

        if feature_count > 20 or competitor_count > 5 or timeline_months > 18:
            complexity = TaskComplexity.EXPERT
        elif feature_count > 10 or competitor_count > 3 or timeline_months > 12:
            complexity = TaskComplexity.COMPLEX

        return TaskCharacteristics(
            complexity=complexity,
            estimated_tokens=2000 + (feature_count * 100),
            requires_reasoning=True,
            speed_critical=params.get("urgent", False),
            cost_sensitive=params.get("cost_sensitive", False),
            special_features=["strategic_planning", "prioritization"],
        )

    def _plan_product_roadmap(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Plan comprehensive product roadmap - SYNCHRONOUS M-MDP
        """
        product_name = params.get("product_name", "Unknown Product")
        params.get("timeline_months", 12)
        features = params.get("features", [])
        params.get("business_goals", [])

        # Create feature objects
        product_features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, feature_data in enumerate(features):
            if isinstance(feature_data, dict):
                feature = ProductFeature(
                    feature_id=f"feat_{i:03d}",
                    name=feature_data.get("name", f"Feature {i + 1}"),
                    description=feature_data.get("description", ""),
                    priority=FeaturePriority(feature_data.get("priority", "medium")),
                    effort_estimate=feature_data.get("effort_estimate", 5),
                    business_value=feature_data.get("business_value", 0.5),
                    dependencies=feature_data.get("dependencies", []),
                    release_target=feature_data.get("release_target"),
                )
            else:
                # Simple string feature
                feature = ProductFeature(
                    feature_id=f"feat_{i:03d}",
                    name=str(feature_data),
                    description="",
                    priority=FeaturePriority.MEDIUM,
                    effort_estimate=5,
                    business_value=0.5,
                    dependencies=[],
                    release_target=None,
                )
            product_features.append(feature)

        # Determine current phase
        total_features = len(product_features)
        if total_features <= 5:
            current_phase = ProductPhase.DISCOVERY
        elif total_features <= 15:
            current_phase = ProductPhase.MVP
        else:
            current_phase = ProductPhase.GROWTH

        # Create milestones
        milestones = {
            "MVP Release": datetime.now(timezone.utc) + timedelta(days=90),
            "Beta Launch": datetime.now(timezone.utc) + timedelta(days=180),
            "GA Release": datetime.now(timezone.utc) + timedelta(days=270),
        }

        # Calculate success metrics
        success_metrics = {
            "feature_completion_rate": 0.85,
            "user_adoption_target": 1000,
            "customer_satisfaction_target": 4.2,
            "revenue_target": params.get("revenue_target", 100000),
        }

        # Identify risk factors
        risk_factors = self._identify_risk_factors(params, product_features)

        # Calculate confidence score
        confidence_score = self._calculate_roadmap_confidence(product_features, params)

        roadmap = ProductRoadmap(
            roadmap_id=f"roadmap_{product_name.lower().replace(' ', '_')}",
            product_name=product_name,
            current_phase=current_phase,
            features=product_features,
            milestones=milestones,
            success_metrics=success_metrics,
            risk_factors=risk_factors,
            confidence_score=confidence_score,
        )

        return self._format_roadmap_result(roadmap, params)

    def _prioritize_features(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Prioritize features using business value analysis - SYNCHRONOUS M-MDP
        """
        features = params.get("features", [])
        params.get("business_goals", [])
        params.get("constraints", {})

        prioritized_features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, feature_data in enumerate(features):
            if isinstance(feature_data, dict):
                name = feature_data.get("name", f"Feature {i + 1}")
                business_value = feature_data.get("business_value", 0.5)
                effort = feature_data.get("effort_estimate", 5)

                # Calculate priority score (business value / effort)
                priority_score = business_value / max(effort, 1) * 100

                # Determine priority level
                if priority_score > 15:
                    priority = FeaturePriority.CRITICAL
                elif priority_score > 10:
                    priority = FeaturePriority.HIGH
                elif priority_score > 5:
                    priority = FeaturePriority.MEDIUM
                else:
                    priority = FeaturePriority.LOW

                prioritized_features.append(
                    {
                        "name": name,
                        "priority": priority.value,
                        "priority_score": round(priority_score, 2),
                        "business_value": business_value,
                        "effort_estimate": effort,
                        "rationale": self._generate_priority_rationale(
                            priority_score, business_value, effort
                        ),
                    }
                )

        # Sort by priority score
        prioritized_features.sort(key=lambda x: x["priority_score"], reverse=True)

        return {
            "prioritization_type": "value_effort_matrix",
            "prioritized_features": prioritized_features,
            "total_features": len(prioritized_features),
            "critical_features": len(
                [f for f in prioritized_features if f["priority"] == "critical"]
            ),
            "recommendations": self._generate_prioritization_recommendations(prioritized_features),
            "confidence_score": 0.85,
        }

    def _analyze_competition(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze competitive landscape - SYNCHRONOUS M-MDP
        """
        competitors = params.get("competitors", [])
        market_segment = params.get("market_segment", "General")
        our_features = params.get("our_features", [])

        competitive_analysis: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for competitor_data in competitors:
            if isinstance(competitor_data, dict):
                analysis = CompetitiveAnalysis(
                    competitor_name=competitor_data.get("name", "Unknown"),
                    strengths=competitor_data.get("strengths", []),
                    weaknesses=competitor_data.get("weaknesses", []),
                    market_share=competitor_data.get("market_share", 0.1),
                    pricing_model=competitor_data.get("pricing_model", "Unknown"),
                    key_features=competitor_data.get("key_features", []),
                    threat_level=competitor_data.get("threat_level", "medium"),
                )
                competitive_analysis.append(analysis)

        # Analyze feature gaps
        feature_gaps = self._identify_feature_gaps(our_features, competitive_analysis)

        # Calculate competitive positioning
        positioning = self._calculate_competitive_position(competitive_analysis, our_features)

        return {
            "analysis_type": "competitive_landscape",
            "market_segment": market_segment,
            "competitors_analyzed": len(competitive_analysis),
            "competitive_analysis": [
                {
                    "name": comp.competitor_name,
                    "threat_level": comp.threat_level,
                    "market_share": comp.market_share,
                    "key_strengths": comp.strengths[:3],  # Top 3
                    "key_weaknesses": comp.weaknesses[:3],  # Top 3
                }
                for comp in competitive_analysis
            ],
            "feature_gaps": feature_gaps,
            "competitive_positioning": positioning,
            "recommendations": self._generate_competitive_recommendations(
                competitive_analysis, feature_gaps
            ),
            "confidence_score": 0.8,
        }

    def _assess_compliance_requirements(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Assess regulatory and compliance requirements - SYNCHRONOUS M-MDP
        """
        regulations = params.get("regulations", ["GDPR", "CCPA"])
        market_regions = params.get("market_regions", ["EU", "US"])
        product_type = params.get("product_type", "SaaS")

        compliance_requirements: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for regulation in regulations:
            requirement = {
                "regulation": regulation,
                "applicable_regions": [],
                "key_requirements": [],
                "implementation_effort": "medium",
                "compliance_deadline": None,
                "penalty_risk": "medium",
            }

            if regulation.upper() == "GDPR":
                requirement.update(
                    {
                        "applicable_regions": ["EU"],
                        "key_requirements": [
                            "Data consent management",
                            "Right to erasure (right to be forgotten)",
                            "Data portability",
                            "Privacy by design",
                            "Data breach notification",
                        ],
                        "implementation_effort": "high",
                        "penalty_risk": "high",
                    }
                )
            elif regulation.upper() == "CCPA":
                requirement.update(
                    {
                        "applicable_regions": ["California, US"],
                        "key_requirements": [
                            "Consumer right to know",
                            "Consumer right to delete",
                            "Consumer right to opt-out",
                            "Non-discrimination",
                            "Data inventory and mapping",
                        ],
                        "implementation_effort": "medium",
                        "penalty_risk": "medium",
                    }
                )
            elif regulation.upper() == "EU AI ACT":
                requirement.update(
                    {
                        "applicable_regions": ["EU"],
                        "key_requirements": [
                            "Risk assessment and classification",
                            "Transparency and explainability",
                            "Human oversight requirements",
                            "Audit trails and logging",
                            "Bias monitoring and mitigation",
                        ],
                        "implementation_effort": "high",
                        "penalty_risk": "high",
                    }
                )

            compliance_requirements.append(requirement)

        # Calculate overall compliance complexity
        total_requirements = sum(len(req["key_requirements"]) for req in compliance_requirements)
        high_effort_count = len(
            [req for req in compliance_requirements if req["implementation_effort"] == "high"]
        )

        complexity_score = min((total_requirements / 10) + (high_effort_count * 0.3), 1.0)

        return {
            "assessment_type": "compliance_requirements",
            "product_type": product_type,
            "target_regions": market_regions,
            "compliance_requirements": compliance_requirements,
            "total_requirements": total_requirements,
            "complexity_score": round(complexity_score, 2),
            "estimated_implementation_months": max(3, int(complexity_score * 12)),
            "priority_recommendations": self._generate_compliance_recommendations(
                compliance_requirements
            ),
            "confidence_score": 0.9,
        }

    def _define_mvp_scope(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Define minimum viable product scope - SYNCHRONOUS M-MDP
        """
        user_segments = params.get("user_segments", ["General Users"])
        core_value_prop = params.get("core_value_proposition", "")
        all_features = params.get("features", [])
        params.get("constraints", {})

        # Score features for MVP inclusion
        mvp_features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        nice_to_have_features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for feature in all_features:
            if isinstance(feature, dict):
                mvp_score = self._calculate_mvp_score(feature, user_segments, core_value_prop)

                feature_with_score = feature.copy()
                feature_with_score["mvp_score"] = mvp_score

                if mvp_score >= 0.7:
                    mvp_features.append(feature_with_score)
                else:
                    nice_to_have_features.append(feature_with_score)

        # Sort by MVP score
        mvp_features.sort(key=lambda x: x["mvp_score"], reverse=True)
        nice_to_have_features.sort(key=lambda x: x["mvp_score"], reverse=True)

        # Calculate MVP metrics
        total_effort = sum(f.get("effort_estimate", 5) for f in mvp_features)
        estimated_timeline = max(4, total_effort // 2)  # Assuming 2 story points per week

        return {
            "mvp_definition": {
                "core_value_proposition": core_value_prop,
                "target_user_segments": user_segments,
                "mvp_features": mvp_features,
                "deferred_features": nice_to_have_features,
                "total_mvp_features": len(mvp_features),
                "estimated_effort": total_effort,
                "estimated_timeline_weeks": estimated_timeline,
                "success_criteria": self._generate_mvp_success_criteria(
                    user_segments, core_value_prop
                ),
            },
            "validation_plan": {
                "user_testing_approach": "Prototype testing with key user segments",
                "success_metrics": [
                    "User activation rate",
                    "Feature usage",
                    "User feedback scores",
                ],
                "iteration_plan": "2-week sprints with user feedback integration",
            },
            "confidence_score": 0.85,
        }

    def _identify_risk_factors(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        features: list[ProductFeature],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Identify potential risk factors for the roadmap"""
        risks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Feature complexity risks
        high_effort_features = [f for f in features if f.effort_estimate > 10]
        if len(high_effort_features) > len(features) * 0.3:
            risks.append("High proportion of complex features may cause timeline delays")

        # Dependency risks
        features_with_deps = [f for f in features if f.dependencies]
        if len(features_with_deps) > len(features) * 0.5:
            risks.append("High feature interdependency may create bottlenecks")

        # Market risks
        competitors = params.get("competitors", [])
        if len(competitors) > 5:
            risks.append("Highly competitive market may require feature differentiation")

        # Resource risks
        team_size = params.get("team_size", 5)
        if len(features) / team_size > 3:
            risks.append("Feature-to-team ratio may indicate resource constraints")

        return risks

    def _calculate_roadmap_confidence(
        self,
        features: list[ProductFeature],
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate confidence score for roadmap"""
        base_confidence = 0.8

        # Reduce confidence for high complexity
        complex_features = len([f for f in features if f.effort_estimate > 8])
        if complex_features > len(features) * 0.4:
            base_confidence -= 0.1

        # Reduce confidence for high dependencies
        dependent_features = len([f for f in features if f.dependencies])
        if dependent_features > len(features) * 0.6:
            base_confidence -= 0.1

        # Increase confidence for clear priorities
        critical_features = len([f for f in features if f.priority == FeaturePriority.CRITICAL])
        if critical_features > 0 and critical_features <= len(features) * 0.3:
            base_confidence += 0.1

        return max(0.3, min(1.0, base_confidence))

    # ... (Additional helper methods continue with similar M-MDP compliant patterns)

    def _generate_priority_rationale(self, score: float, business_value: float, effort: int) -> str:
        """Generate rationale for feature prioritization"""
        if score > 15:
            return f"Critical: High business value ({business_value}) with manageable effort ({effort})"
        elif score > 10:
            return f"High priority: Good value-to-effort ratio ({score:.1f})"
        elif score > 5:
            return "Medium priority: Balanced value and effort"
        else:
            return "Low priority: Consider deferring due to low value-to-effort ratio"

    def _calculate_mvp_score(
        self,
        feature: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_segments: list[str],
        value_prop: str,  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate MVP inclusion score for feature"""
        base_score = 0.5

        # Core value alignment
        if any(
            segment.lower() in feature.get("description", "").lower() for segment in user_segments
        ):
            base_score += 0.2

        # Business value
        business_value = feature.get("business_value", 0.5)
        base_score += business_value * 0.3

        # Implementation complexity (inverse relationship)
        effort = feature.get("effort_estimate", 5)
        complexity_penalty = min(effort / 20, 0.3)
        base_score -= complexity_penalty

        return cast(float, max(0.0, min(1.0, base_score)))

    async def _enhance_with_llm_insights(
        self,
        planning_type: str,
        product_result: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        task_chars: TaskCharacteristics,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Enhance product planning with LLM strategic insights
        M-MDP: ASYNC for I/O operations
        """
        if not self.llm_client:
            logger.warning("LLM client not available, returning raw results")
            return product_result

        try:
            # Select optimal model for this specific task
            optimal_model = agent_model_matcher.select_optimal_model("product_agent", task_chars)
            logger.info(f"Using model {optimal_model} for {planning_type}")

            context_prompt = f"""
            As a senior product strategist, analyze this product planning output and provide strategic insights:

            Planning Type: {planning_type}
            Product Context: {params.get("product_name", "Product")}
            Market Context: {params.get("market_segment", "General market")}

            Planning Results:
            {json.dumps(product_result, indent=2, default=str)}

            Provide:
            1. Strategic insights and market implications
            2. Risk assessment and mitigation strategies
            3. Competitive positioning recommendations
            4. Implementation priorities and next steps

            Keep response concise and actionable for product team.
            Focus on strategic value and practical implementation.
            """

            # ASYNC LLM call (M-MDP compliant)
            response = await self.llm_client.text_completion(context_prompt)

            enhanced_result = product_result.copy()
            enhanced_result["llm_insights"] = {
                "strategic_analysis": (
                    response.content if hasattr(response, "content") else str(response)
                ),
                "model_used": optimal_model,
                "provider": "google_gemini",
            }

            return enhanced_result

        except Exception as e:
            logger.error(f"LLM enhancement failed: {e}")
            return product_result

    def _format_roadmap_result(
        self,
        roadmap: ProductRoadmap,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Format roadmap results for output"""
        return {
            "roadmap_id": roadmap.roadmap_id,
            "product_name": roadmap.product_name,
            "current_phase": roadmap.current_phase.value,
            "total_features": len(roadmap.features),
            "features_by_priority": {
                "critical": len(
                    [f for f in roadmap.features if f.priority == FeaturePriority.CRITICAL]
                ),
                "high": len([f for f in roadmap.features if f.priority == FeaturePriority.HIGH]),
                "medium": len(
                    [f for f in roadmap.features if f.priority == FeaturePriority.MEDIUM]
                ),
                "low": len([f for f in roadmap.features if f.priority == FeaturePriority.LOW]),
            },
            "key_milestones": {k: v.isoformat() for k, v in roadmap.milestones.items()},
            "success_metrics": roadmap.success_metrics,
            "identified_risks": roadmap.risk_factors,
            "confidence_score": roadmap.confidence_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }

    def _generate_prioritization_recommendations(
        self,
        features: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Generate recommendations based on feature prioritization"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        critical_count = len([f for f in features if f["priority"] == "critical"])
        if critical_count > 5:
            recommendations.append("Consider breaking down critical features to manage MVP scope")

        low_value_features = [f for f in features if f["priority_score"] < 3]
        if len(low_value_features) > len(features) * 0.3:
            recommendations.append("Consider removing or deferring low-value features")

        return recommendations

    def _identify_feature_gaps(
        self,
        our_features: list[Any],  # TODO(TYPE): replace Any with concrete type
        competitive_analysis: list[
            CompetitiveAnalysis
        ],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Identify missing features compared to competition"""
        our_feature_names = {
            f.get("name", "").lower() if isinstance(f, dict) else str(f).lower()
            for f in our_features
        }

        competitor_features = set()
        for comp in competitive_analysis:
            for feature in comp.key_features:
                competitor_features.add(feature.lower())

        gaps = competitor_features - our_feature_names
        return list(gaps)[:10]  # Top 10 gaps

    def _calculate_competitive_position(
        self,
        competitive_analysis: list[CompetitiveAnalysis],
        our_features: list[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Calculate our competitive position"""
        total_market_share = sum(comp.market_share for comp in competitive_analysis)
        avg_competitor_features = sum(
            len(comp.key_features) for comp in competitive_analysis
        ) / max(len(competitive_analysis), 1)

        return {
            "market_concentration": (
                "high"
                if total_market_share > 0.7
                else "medium"
                if total_market_share > 0.4
                else "low"
            ),
            "feature_competitiveness": (
                "strong"
                if len(our_features) > avg_competitor_features
                else "competitive"
                if len(our_features) > avg_competitor_features * 0.8
                else "weak"
            ),
            "differentiation_opportunity": len(our_features) < avg_competitor_features * 1.2,
        }

    def _generate_competitive_recommendations(
        self, competitive_analysis: list[CompetitiveAnalysis], feature_gaps: list[str]
    ) -> list[str]:
        """Generate recommendations based on competitive analysis"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        high_threat_competitors = [
            comp for comp in competitive_analysis if comp.threat_level == "high"
        ]
        if high_threat_competitors:
            recommendations.append(
                f"Monitor {len(high_threat_competitors)} high-threat competitors closely"
            )

        if len(feature_gaps) > 5:
            recommendations.append("Address key feature gaps to maintain competitive parity")

        return recommendations

    def _generate_compliance_recommendations(
        self,
        requirements: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Generate compliance implementation recommendations"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        high_effort_reqs = [req for req in requirements if req["implementation_effort"] == "high"]
        if high_effort_reqs:
            recommendations.append(
                "Start with high-effort compliance requirements early in development"
            )

        high_risk_reqs = [req for req in requirements if req["penalty_risk"] == "high"]
        if high_risk_reqs:
            recommendations.append("Prioritize high-penalty-risk compliance features")

        return recommendations

    def _generate_mvp_success_criteria(
        self, user_segments: list[str], value_prop: str
    ) -> list[str]:
        """Generate success criteria for MVP"""
        return [
            "User activation rate >20% within first week",
            f"Core feature adoption >60% among {user_segments[0] if user_segments else 'primary users'}",
            "User satisfaction score >3.5/5 for core value proposition",
            "Technical performance meets baseline requirements",
        ]


# Global instance for import
product_agent = ProductAgent()
