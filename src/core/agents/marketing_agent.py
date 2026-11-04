#!/usr/bin/env python3
"""
Marketing Agent - M-MDP Compliant Implementation
Specialized agent for GTM strategy, pricing models, and marketing campaign optimization
Based on content-marketer agent definition from agenten directory
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.agents.llm_types import TaskCharacteristics, TaskComplexity, agent_model_matcher
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel
from src.core.types import AgentType

logger = logging.getLogger(__name__)


class MarketingChannel(Enum):
    """Marketing channel types"""

    DIGITAL_ADS = "digital_ads"
    CONTENT_MARKETING = "content_marketing"
    SOCIAL_MEDIA = "social_media"
    EMAIL_MARKETING = "email_marketing"
    SEO_ORGANIC = "seo_organic"
    INFLUENCER = "influencer"
    EVENTS = "events"
    DIRECT_SALES = "direct_sales"
    PARTNERSHIPS = "partnerships"


class PricingModel(Enum):
    """Pricing strategy models"""

    FREEMIUM = "freemium"
    SUBSCRIPTION = "subscription"
    USAGE_BASED = "usage_based"
    TIERED = "tiered"
    VALUE_BASED = "value_based"
    COMPETITIVE = "competitive"
    PENETRATION = "penetration"
    PREMIUM = "premium"


class CustomerSegment(Enum):
    """Customer segment categories"""

    SMB = "small_medium_business"
    ENTERPRISE = "enterprise"
    STARTUP = "startup"
    INDIVIDUAL = "individual"
    GOVERNMENT = "government"
    NONPROFIT = "nonprofit"


@dataclass
class MarketingCampaign:
    """Marketing campaign definition"""

    campaign_id: str
    name: str
    objective: str
    target_segments: list[CustomerSegment]
    channels: list[MarketingChannel]
    budget: float
    duration_days: int
    expected_reach: int
    expected_conversion_rate: float
    roi_target: float


@dataclass
class PricingStrategy:
    """Pricing strategy structure"""

    strategy_id: str
    model: PricingModel
    base_price: float
    tiers: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    competitive_position: str  # "premium", "competitive", "value"
    value_proposition: str
    elasticity_estimate: float
    revenue_projection: float


@dataclass
class GTMPlan:
    """Go-to-market plan structure"""

    plan_id: str
    product_name: str
    target_market: str
    positioning: str
    pricing_strategy: PricingStrategy
    marketing_mix: list[MarketingCampaign]
    sales_enablement: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    success_metrics: dict[str, float]
    timeline_months: int
    confidence_score: float


class MarketingAgent(CriticMixin, EnhancedBaseAgent):
    """
    Marketing Agent - Strategic marketing planning and campaign optimization
    M-MDP Compliant: Sync for marketing logic, async for I/O
    """

    def __init__(
        self,
        agent_id: str = "marketing_agent_001",
        agent_type: AgentType = AgentType.CREATIVE,
        tenant_id: int = 1,  # Default tenant for backwards compatibility
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=agent_type, tenant_id=tenant_id)
        self.__init_critic__(mode=CriticMode.ADVISORY)
        self.llm_client: ChatTaalmodel | None = None

        # Marketing strategy methods (SYNCHRONOUS - M-MDP Compliant)
        self.marketing_methods = {
            "gtm_planning": self._plan_go_to_market,
            "pricing_strategy": self._develop_pricing_strategy,
            "campaign_optimization": self._optimize_marketing_campaigns,
            "customer_segmentation": self._analyze_customer_segments,
            "competitive_positioning": self._develop_competitive_positioning,
            "channel_mix_optimization": self._optimize_channel_mix,
            "content_strategy": self._develop_content_strategy,
            "conversion_optimization": self._optimize_conversion_funnel,
        }

        # Register agent profile for intelligent model matching
        self._register_agent_profile()

    def _register_agent_profile(self) -> None:
        """Register agent profile for optimal model selection"""
        from src.core.agents.llm_types import AgentCategory, AgentProfile, TaskComplexity

        profile = AgentProfile(
            agent_type="marketing_agent",
            category=AgentCategory.CREATIVE,
            typical_complexity=TaskComplexity.COMPLEX,
            reasoning_required=0.75,  # Strategic + creative reasoning
            speed_priority=0.8,  # Fast iteration for marketing
            cost_sensitivity=0.9,  # Very cost sensitive (high volume)
            context_needs=3000,  # Large context for market analysis
            special_requirements=[
                "creative_writing",
                "marketing_knowledge",
                "data_analysis",
            ],
        )
        agent_model_matcher.register_agent_profile(profile)

    async def initialize(self) -> bool:
        """Initialize Marketing Agent with optimal LLM model"""
        try:
            # Get optimal model for this agent type
            optimal_model = agent_model_matcher.select_optimal_model("marketing_agent")

            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14); hier stond Google.
            self.llm_client = TenantTaalmodel(self.tenant_id)

            logger.info(
                f"Marketing Agent {self.agent_id} initialized with optimal model: {optimal_model}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Marketing Agent: {e}")
            raise

    async def get_capabilities(self) -> list[AgentCapability]:
        """Return agent capabilities"""
        return [
            AgentCapability(
                name="gtm_planning",
                description="Create comprehensive go-to-market strategies",
                input_types=[
                    "product_info",
                    "target_market",
                    "competitive_landscape",
                    "budget",
                ],
                output_types=["gtm_plan"],
            ),
            AgentCapability(
                name="pricing_strategy",
                description="Develop optimal pricing models and strategies",
                input_types=["product_value", "market_analysis", "competitive_pricing"],
                output_types=["pricing_strategy"],
            ),
            AgentCapability(
                name="campaign_optimization",
                description="Optimize marketing campaigns for ROI and conversion",
                input_types=[
                    "current_campaigns",
                    "performance_data",
                    "budget_constraints",
                ],
                output_types=["optimized_campaigns"],
            ),
            AgentCapability(
                name="customer_segmentation",
                description="Analyze and segment target customers",
                input_types=["customer_data", "behavioral_data", "market_research"],
                output_types=["customer_segments"],
            ),
            AgentCapability(
                name="competitive_positioning",
                description="Develop competitive positioning and differentiation",
                input_types=["competitors", "unique_value_props", "market_positioning"],
                output_types=["positioning_strategy"],
            ),
        ]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Process marketing strategy task
        M-MDP: Async wrapper for sync business logic
        """
        start_time = datetime.now(timezone.utc)
        task_id = task.id

        try:
            marketing_type = task.parameters.get("marketing_type", "gtm_planning")

            if marketing_type not in self.marketing_methods:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    error_message=f"Unknown marketing type: {marketing_type}",
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                )

            # Determine task complexity for model selection
            task_chars = self._analyze_task_characteristics(task.parameters)

            # SYNC marketing logic (M-MDP compliant)
            marketing_method = self.marketing_methods[marketing_type]
            marketing_result = marketing_method(task.parameters)

            # ASYNC LLM enhancement (M-MDP compliant)
            enhanced_result = await self._enhance_with_llm_insights(
                marketing_type, marketing_result, task.parameters, task_chars
            )

            return ExecutionResult(
                task_id=task_id,
                success=True,
                result_data=enhanced_result,
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                agent_id=self.agent_id,
            )

        except Exception as e:
            logger.error(f"Marketing strategy failed: {e}")
            return ExecutionResult(
                task_id=task_id,
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
        market_segments = len(params.get("target_segments", []))
        channels = len(params.get("channels", []))
        competitors = len(params.get("competitors", []))
        campaign_count = len(params.get("campaigns", []))

        if market_segments > 5 or channels > 6 or competitors > 8 or campaign_count > 10:
            complexity = TaskComplexity.EXPERT
        elif market_segments > 3 or channels > 4 or competitors > 5 or campaign_count > 5:
            complexity = TaskComplexity.COMPLEX

        return TaskCharacteristics(
            complexity=complexity,
            estimated_tokens=1500 + (market_segments * 200) + (campaign_count * 150),
            requires_reasoning=True,
            speed_critical=params.get("urgent", False),
            cost_sensitive=params.get(
                "cost_sensitive", True
            ),  # Marketing is typically cost-sensitive
            special_features=["creative_writing", "marketing_analysis"],
        )

    def _plan_go_to_market(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Plan comprehensive go-to-market strategy - SYNCHRONOUS M-MDP
        """
        product_name = params.get("product_name", "Product")
        target_market = params.get("target_market", "General Market")
        budget = params.get("budget", 100000)
        timeline_months = params.get("timeline_months", 6)

        # Develop pricing strategy
        pricing_strategy = self._create_pricing_strategy(params)

        # Create marketing campaigns
        marketing_campaigns = self._create_marketing_campaigns(
            params, budget * 0.7
        )  # 70% for campaigns

        # Sales enablement
        sales_enablement = {
            "sales_materials": [
                "Product demo scripts",
                "Competitive battle cards",
                "Customer success stories",
                "ROI calculators",
            ],
            "training_program": {
                "product_training_hours": 8,
                "sales_methodology": "SPIN Selling",
                "objection_handling": "Common objections and responses",
            },
            "lead_qualification": {
                "framework": "BANT (Budget, Authority, Need, Timeline)",
                "scoring_criteria": "Company size, industry fit, engagement level",
            },
        }

        # Success metrics
        success_metrics = {
            "awareness_target": 1000000,  # Brand awareness reach
            "lead_generation_target": 2500,
            "conversion_rate_target": 0.05,  # 5% lead to customer
            "customer_acquisition_target": 125,
            "revenue_target": budget * 2.5,  # 2.5x ROI target
            "market_share_target": 0.02,  # 2% market share
        }

        # Calculate confidence score
        confidence_score = self._calculate_gtm_confidence(
            params, pricing_strategy, marketing_campaigns
        )

        gtm_plan = GTMPlan(
            plan_id=f"gtm_{product_name.lower().replace(' ', '_')}",
            product_name=product_name,
            target_market=target_market,
            positioning=self._generate_market_positioning(params),
            pricing_strategy=pricing_strategy,
            marketing_mix=marketing_campaigns,
            sales_enablement=sales_enablement,
            success_metrics=success_metrics,
            timeline_months=timeline_months,
            confidence_score=confidence_score,
        )

        return self._format_gtm_result(gtm_plan, params)

    def _develop_pricing_strategy(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Develop optimal pricing strategy - SYNCHRONOUS M-MDP
        """
        product_value = params.get("product_value", 100)
        competitors = params.get("competitors", [])
        target_segments = params.get("target_segments", ["SMB"])

        # Analyze competitive pricing
        competitor_prices: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for comp in competitors:
            if isinstance(comp, dict) and "pricing" in comp:
                competitor_prices.append(comp["pricing"])

        avg_competitor_price = (
            sum(competitor_prices) / len(competitor_prices) if competitor_prices else product_value
        )

        # Determine pricing model based on product characteristics
        pricing_model = self._select_optimal_pricing_model(params)

        # Calculate base price
        if pricing_model == PricingModel.COMPETITIVE:
            base_price = avg_competitor_price * 0.95  # Slightly undercut
        elif pricing_model == PricingModel.PREMIUM:
            base_price = avg_competitor_price * 1.25  # Premium positioning
        elif pricing_model == PricingModel.VALUE_BASED:
            base_price = product_value * 0.7  # 70% of delivered value
        else:
            base_price = product_value  # Default to product value

        # Create pricing tiers
        pricing_tiers = self._create_pricing_tiers(base_price, pricing_model, target_segments)

        # Calculate revenue projections
        revenue_projection = self._calculate_pricing_revenue_projection(pricing_tiers, params)

        pricing_strategy = PricingStrategy(
            strategy_id=f"pricing_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            model=pricing_model,
            base_price=base_price,
            tiers=pricing_tiers,
            competitive_position=self._determine_competitive_position(
                base_price, avg_competitor_price
            ),
            value_proposition=params.get("value_proposition", "Superior value and performance"),
            elasticity_estimate=self._estimate_price_elasticity(params),
            revenue_projection=revenue_projection,
        )

        return self._format_pricing_result(pricing_strategy, params)

    def _optimize_marketing_campaigns(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Optimize marketing campaigns for performance - SYNCHRONOUS M-MDP
        """
        current_campaigns = params.get("campaigns", [])
        budget = params.get("budget", 50000)
        params.get("objectives", ["lead_generation"])

        optimized_campaigns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        total_budget_allocation = 0.0

        for i, campaign_data in enumerate(current_campaigns):
            if isinstance(campaign_data, dict):
                # Analyze campaign performance
                performance_score = self._calculate_campaign_performance_score(campaign_data)

                # Optimize budget allocation based on performance
                if performance_score > 0.8:
                    budget_multiplier = 1.3  # Increase high-performing campaigns
                elif performance_score > 0.6:
                    budget_multiplier = 1.0  # Maintain moderate performers
                else:
                    budget_multiplier = 0.7  # Reduce poor performers

                optimized_budget = campaign_data.get("budget", 5000) * budget_multiplier
                total_budget_allocation += optimized_budget

                optimized_campaign = {
                    "campaign_name": campaign_data.get("name", f"Campaign {i + 1}"),
                    "channel": campaign_data.get("channel", "digital_ads"),
                    "original_budget": campaign_data.get("budget", 5000),
                    "optimized_budget": round(optimized_budget, 2),
                    "performance_score": performance_score,
                    "optimization_reasoning": self._generate_optimization_reasoning(
                        performance_score, budget_multiplier
                    ),
                    "recommended_actions": self._generate_campaign_recommendations(
                        campaign_data, performance_score
                    ),
                }
                optimized_campaigns.append(optimized_campaign)

        # Normalize budgets to fit total budget
        if total_budget_allocation > budget:
            scaling_factor = budget / total_budget_allocation
            for campaign in optimized_campaigns:
                campaign["optimized_budget"] = round(
                    campaign["optimized_budget"] * scaling_factor, 2
                )

        return {
            "optimization_type": "campaign_performance",
            "total_campaigns": len(optimized_campaigns),
            "total_budget": budget,
            "budget_reallocation": sum(
                abs(c["optimized_budget"] - c["original_budget"]) for c in optimized_campaigns
            ),
            "optimized_campaigns": optimized_campaigns,
            "expected_performance_improvement": self._calculate_expected_improvement(
                optimized_campaigns
            ),
            "recommendations": self._generate_overall_optimization_recommendations(
                optimized_campaigns
            ),
            "confidence_score": 0.85,
        }

    def _analyze_customer_segments(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze and segment target customers - SYNCHRONOUS M-MDP
        """
        customer_data = params.get("customer_data", [])
        segmentation_criteria = params.get("criteria", ["company_size", "industry", "use_case"])

        segments: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        # Default segments if no customer data
        if not customer_data:
            segments = {
                "enterprise": {
                    "description": "Large companies (500+ employees)",
                    "characteristics": [
                        "High budget",
                        "Complex needs",
                        "Long sales cycle",
                    ],
                    "size_estimate": 1000,
                    "revenue_potential": "High",
                    "acquisition_difficulty": "Hard",
                },
                "smb": {
                    "description": "Small-medium businesses (10-500 employees)",
                    "characteristics": [
                        "Moderate budget",
                        "Standard needs",
                        "Medium sales cycle",
                    ],
                    "size_estimate": 10000,
                    "revenue_potential": "Medium",
                    "acquisition_difficulty": "Medium",
                },
                "startup": {
                    "description": "Early-stage companies (1-50 employees)",
                    "characteristics": [
                        "Limited budget",
                        "Growth-focused",
                        "Quick decisions",
                    ],
                    "size_estimate": 5000,
                    "revenue_potential": "Low-Medium",
                    "acquisition_difficulty": "Easy",
                },
            }
        else:
            # Analyze provided customer data
            for customer in customer_data:
                segment_key = self._classify_customer_segment(customer, segmentation_criteria)
                if segment_key not in segments:
                    segments[segment_key] = {
                        "customers": [],
                        "characteristics": set(),
                        "revenue_potential": 0,
                    }
                segments[segment_key]["customers"].append(customer)

        # Calculate segment metrics
        for segment_name, segment_data in segments.items():
            if "customers" in segment_data:
                segment_data["size"] = len(segment_data["customers"])
                customers = segment_data["customers"]
                if customers:
                    segment_data["avg_revenue"] = sum(c.get("revenue", 0) for c in customers) / len(
                        customers
                    )

        return {
            "segmentation_type": "behavioral_demographic",
            "criteria_used": segmentation_criteria,
            "total_segments": len(segments),
            "segments": segments,
            "segment_priorities": self._prioritize_segments(segments),
            "targeting_recommendations": self._generate_segment_targeting_recommendations(segments),
            "confidence_score": 0.8,
        }

    # Stub methods for missing implementations
    def _develop_competitive_positioning(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Develop competitive positioning - STUB implementation"""
        return {
            "positioning_type": "competitive",
            "differentiation": params.get("unique_value_props", []),
            "market_position": "differentiated",
            "confidence_score": 0.75,
        }

    def _optimize_channel_mix(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Optimize channel mix - STUB implementation"""
        return {
            "channel_mix": params.get("channels", []),
            "optimization": "balanced",
            "confidence_score": 0.75,
        }

    def _develop_content_strategy(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Develop content strategy - STUB implementation"""
        return {
            "content_pillars": ["education", "thought_leadership", "product"],
            "content_types": ["blog", "video", "social"],
            "confidence_score": 0.75,
        }

    def _optimize_conversion_funnel(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Optimize conversion funnel - STUB implementation"""
        return {
            "funnel_stage": params.get("funnel_stage", "full"),
            "optimization_focus": "conversion_rate",
            "confidence_score": 0.75,
        }

    # Helper methods for marketing strategy calculations

    def _create_pricing_strategy(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> PricingStrategy:  # TODO(TYPE): replace Any with concrete type
        """Create pricing strategy based on parameters"""
        base_price = params.get("base_price", 100)

        return PricingStrategy(
            strategy_id="pricing_001",
            model=PricingModel.TIERED,
            base_price=base_price,
            tiers=[
                {
                    "name": "Starter",
                    "price": base_price * 0.7,
                    "features": ["Basic features"],
                },
                {
                    "name": "Professional",
                    "price": base_price,
                    "features": ["All features"],
                },
                {
                    "name": "Enterprise",
                    "price": base_price * 1.5,
                    "features": ["All features + support"],
                },
            ],
            competitive_position="competitive",
            value_proposition="Best value for features",
            elasticity_estimate=-1.5,
            revenue_projection=base_price * 1000,  # Estimate
        )

    def _create_marketing_campaigns(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        budget: float,  # TODO(TYPE): replace Any with concrete type
    ) -> list[MarketingCampaign]:
        """Create marketing campaigns based on parameters"""
        campaigns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Digital ads campaign
        campaigns.append(
            MarketingCampaign(
                campaign_id="campaign_digital_001",
                name="Digital Acquisition Campaign",
                objective="Lead Generation",
                target_segments=[CustomerSegment.SMB, CustomerSegment.STARTUP],
                channels=[MarketingChannel.DIGITAL_ADS, MarketingChannel.SOCIAL_MEDIA],
                budget=budget * 0.4,
                duration_days=90,
                expected_reach=100000,
                expected_conversion_rate=0.03,
                roi_target=3.0,
            )
        )

        # Content marketing campaign
        campaigns.append(
            MarketingCampaign(
                campaign_id="campaign_content_001",
                name="Content Marketing Campaign",
                objective="Brand Awareness",
                target_segments=[CustomerSegment.ENTERPRISE],
                channels=[
                    MarketingChannel.CONTENT_MARKETING,
                    MarketingChannel.SEO_ORGANIC,
                ],
                budget=budget * 0.3,
                duration_days=180,
                expected_reach=500000,
                expected_conversion_rate=0.015,
                roi_target=2.5,
            )
        )

        return campaigns

    def _generate_market_positioning(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate market positioning statement"""
        product_name = params.get("product_name", "Our Product")
        target_market = params.get("target_market", "businesses")
        value_prop = params.get("value_proposition", "superior solution")

        return f"{product_name} is the {value_prop} for {target_market} who need reliable and efficient solutions."

    def _select_optimal_pricing_model(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> PricingModel:  # TODO(TYPE): replace Any with concrete type
        """Select optimal pricing model based on parameters"""
        product_type = params.get("product_type", "saas")
        target_segments = params.get("target_segments", ["SMB"])

        if product_type.lower() == "saas" and "enterprise" in target_segments:
            return PricingModel.TIERED
        elif "startup" in target_segments:
            return PricingModel.FREEMIUM
        else:
            return PricingModel.VALUE_BASED

    def _create_pricing_tiers(
        self, base_price: float, model: PricingModel, segments: list[str]
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Create pricing tiers based on model and segments"""
        if model == PricingModel.TIERED:
            return [
                {
                    "tier": "Basic",
                    "price": base_price * 0.6,
                    "target": "Small businesses",
                },
                {
                    "tier": "Professional",
                    "price": base_price,
                    "target": "Growing companies",
                },
                {
                    "tier": "Enterprise",
                    "price": base_price * 1.8,
                    "target": "Large organizations",
                },
            ]
        else:
            return [{"tier": "Standard", "price": base_price, "target": "All segments"}]

    def _calculate_campaign_performance_score(
        self,
        campaign: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate campaign performance score"""
        # Mock performance calculation based on campaign attributes
        base_score = 0.6

        if campaign.get("channel") == "digital_ads":
            base_score += 0.1
        if campaign.get("budget", 0) > 10000:
            base_score += 0.1
        if campaign.get("conversion_rate", 0) > 0.02:
            base_score += 0.2

        return min(1.0, base_score)

    def _generate_optimization_reasoning(self, score: float, multiplier: float) -> str:
        """Generate reasoning for campaign optimization"""
        if multiplier > 1.2:
            return f"High performance (score: {score:.2f}) warrants increased investment"
        elif multiplier < 0.8:
            return f"Poor performance (score: {score:.2f}) requires budget reduction"
        else:
            return f"Moderate performance (score: {score:.2f}) maintains current allocation"

    async def _enhance_with_llm_insights(
        self,
        marketing_type: str,
        marketing_result: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        task_chars: TaskCharacteristics,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Enhance marketing planning with LLM strategic insights
        M-MDP: ASYNC for I/O operations
        """
        llm_client = self.llm_client
        if llm_client is None:
            logger.warning("LLM client not available, returning raw results")
            return marketing_result

        try:
            # Select optimal model for this specific task
            optimal_model = agent_model_matcher.select_optimal_model("marketing_agent", task_chars)
            logger.info(f"Using model {optimal_model} for {marketing_type}")

            context_prompt = f"""As a senior marketing strategist, analyze this marketing planning output and provide strategic insights:

Marketing Type: {marketing_type}
Product Context: {params.get("product_name", "Product")}
Target Market: {params.get("target_market", "General market")}
Budget: ${params.get("budget", "Not specified")}

Marketing Results:
{json.dumps(marketing_result, indent=2, default=str)}

Provide:
1. Strategic marketing insights and market opportunities
2. Risk assessment and mitigation for marketing approach
3. Competitive positioning and differentiation recommendations
4. Channel optimization and budget allocation suggestions
5. Performance measurement and optimization recommendations

Keep response concise and actionable for marketing team.
Focus on practical implementation and measurable results.
"""

            # ASYNC LLM call (M-MDP compliant)
            response = await llm_client.text_completion(context_prompt)

            enhanced_result = marketing_result.copy()
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
            return marketing_result

    def _calculate_gtm_confidence(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        pricing: PricingStrategy,
        campaigns: list[MarketingCampaign],
    ) -> float:
        """Calculate confidence score for GTM plan"""
        base_confidence = 0.7

        # Increase confidence for clear target market
        if params.get("target_market") and len(params.get("target_segments", [])) > 0:
            base_confidence += 0.1

        # Increase confidence for diversified campaigns
        if len(campaigns) >= 2:
            base_confidence += 0.1

        return min(1.0, base_confidence)

    def _format_gtm_result(
        self,
        gtm_plan: GTMPlan,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Format GTM plan results for output"""
        return {
            "gtm_plan_id": gtm_plan.plan_id,
            "product_name": gtm_plan.product_name,
            "target_market": gtm_plan.target_market,
            "market_positioning": gtm_plan.positioning,
            "pricing_strategy": {
                "model": gtm_plan.pricing_strategy.model.value,
                "base_price": gtm_plan.pricing_strategy.base_price,
                "competitive_position": gtm_plan.pricing_strategy.competitive_position,
                "revenue_projection": gtm_plan.pricing_strategy.revenue_projection,
            },
            "marketing_campaigns": len(gtm_plan.marketing_mix),
            "total_marketing_budget": sum(c.budget for c in gtm_plan.marketing_mix),
            "success_metrics": gtm_plan.success_metrics,
            "timeline_months": gtm_plan.timeline_months,
            "confidence_score": gtm_plan.confidence_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }

    def _format_pricing_result(
        self,
        pricing_strategy: PricingStrategy,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Format pricing strategy results for output"""
        return {
            "pricing_strategy_id": pricing_strategy.strategy_id,
            "pricing_model": pricing_strategy.model.value,
            "base_price": pricing_strategy.base_price,
            "pricing_tiers": pricing_strategy.tiers,
            "competitive_position": pricing_strategy.competitive_position,
            "value_proposition": pricing_strategy.value_proposition,
            "price_elasticity": pricing_strategy.elasticity_estimate,
            "revenue_projection": pricing_strategy.revenue_projection,
            "confidence_score": 0.8,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }

    def _calculate_pricing_revenue_projection(
        self,
        tiers: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate revenue projection from pricing tiers"""
        base_customers = cast(float, params.get("expected_customers", 1000))
        avg_price = sum(cast(float, tier["price"]) for tier in tiers) / len(tiers)
        return base_customers * avg_price

    def _determine_competitive_position(self, our_price: float, competitor_avg: float) -> str:
        """Determine competitive position based on pricing"""
        ratio = our_price / competitor_avg if competitor_avg > 0 else 1.0

        if ratio > 1.2:
            return "premium"
        elif ratio < 0.8:
            return "value"
        else:
            return "competitive"

    def _estimate_price_elasticity(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Estimate price elasticity of demand"""
        product_type = params.get("product_type", "saas")
        market_maturity = params.get("market_maturity", "mature")

        if product_type == "luxury":
            return -0.8  # Less elastic
        elif market_maturity == "emerging":
            return -2.0  # More elastic
        else:
            return -1.5  # Default elasticity

    def _generate_campaign_recommendations(
        self,
        campaign: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        score: float,  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate recommendations for campaign optimization"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if score < 0.6:
            recommendations.append("Consider changing target audience or messaging")
            recommendations.append("Test different creative formats")

        if campaign.get("budget", 0) < 5000:
            recommendations.append("Increase budget for better reach and frequency")

        return recommendations

    def _calculate_expected_improvement(
        self,
        campaigns: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate expected performance improvement from optimization"""
        improvements: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for campaign in campaigns:
            if campaign["optimized_budget"] > campaign["original_budget"]:
                improvements.append(0.2)  # 20% improvement for increased budget
            elif campaign["optimized_budget"] < campaign["original_budget"]:
                improvements.append(-0.1)  # 10% decrease for reduced budget

        return sum(improvements) / len(improvements) if improvements else 0.0

    def _generate_overall_optimization_recommendations(
        self,
        campaigns: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate overall optimization recommendations"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        high_performers = [c for c in campaigns if c["performance_score"] > 0.8]
        if len(high_performers) > 0:
            recommendations.append(
                f"Scale successful campaigns: {', '.join(c['campaign_name'] for c in high_performers)}"
            )

        poor_performers = [c for c in campaigns if c["performance_score"] < 0.5]
        if len(poor_performers) > 0:
            recommendations.append("Redesign or pause underperforming campaigns")

        return recommendations

    def _classify_customer_segment(
        self,
        # TODO(TYPE): replace Any with concrete type
        customer: dict[str, Any],
        criteria: list[str],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Classify customer into segment based on criteria"""
        # Simple classification logic
        company_size = customer.get("company_size", 100)

        if company_size > 1000:
            return "enterprise"
        elif company_size > 50:
            return "smb"
        else:
            return "startup"

    def _prioritize_segments(
        self,
        segments: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Prioritize customer segments by attractiveness"""
        prioritized: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for name, segment in segments.items():
            score = 0.5  # Base score

            if segment.get("revenue_potential") == "High":
                score += 0.3
            if segment.get("size_estimate", 0) > 5000:
                score += 0.2

            prioritized.append(
                {
                    "segment": name,
                    "priority_score": score,
                    "rationale": "Score based on revenue potential and market size",
                }
            )

        return sorted(prioritized, key=lambda x: x["priority_score"], reverse=True)

    def _generate_segment_targeting_recommendations(
        self,
        segments: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Generate recommendations for segment targeting"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "enterprise" in segments:
            recommendations.append(
                "Enterprise segment requires longer sales cycles and premium positioning"
            )

        if "startup" in segments:
            recommendations.append(
                "Startup segment responds well to freemium models and growth messaging"
            )

        return recommendations
