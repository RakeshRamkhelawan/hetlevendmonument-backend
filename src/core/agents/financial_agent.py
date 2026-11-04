#!/usr/bin/env python3
"""
Financial Agent - M-MDP Compliant Implementation
Specialized agent for financial analysis, ROI calculations, and business modeling
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel
from src.core.types import AgentType

logger = logging.getLogger(__name__)


@dataclass
class FinancialMetrics:
    """Financial calculation results"""

    revenue_projection: Decimal
    break_even_month: int
    roi_percentage: Decimal
    ltv_cac_ratio: Decimal
    cash_flow: list[Decimal]
    funding_required: Decimal
    confidence_score: float


class FinancialAgent(CriticMixin, EnhancedBaseAgent):
    """
    Financial Agent - Strategic financial analysis and business modeling
    M-MDP Compliant: Sync for calculations, async for I/O
    """

    def __init__(
        self,
        agent_id: str = "financial_agent_001",
        agent_type: AgentType = AgentType.SPECIALIST,
        tenant_id: int = 1,
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=agent_type, tenant_id=tenant_id)
        self.llm_client: ChatTaalmodel | None = None

        # CriticMixin: BLOCKING mode -- financial outputs must score >= 0.50
        # before being returned to the caller. Up to 2 automatic retries.
        self.__init_critic__(mode=CriticMode.BLOCKING, score_threshold=0.50, max_retries=2)

        # Financial calculation methods (SYNCHRONOUS - M-MDP Compliant)
        self.calculation_methods = {
            "revenue_projection": self._calculate_revenue_projection,
            "break_even_analysis": self._calculate_break_even,
            "roi_analysis": self._calculate_roi,
            "ltv_cac_optimization": self._calculate_ltv_cac,
            "cash_flow_modeling": self._calculate_cash_flow,
            "funding_requirements": self._calculate_funding_needs,
            "competitive_pricing": self._analyze_competitive_pricing,
            "unit_economics": self._analyze_unit_economics,
        }

    async def initialize(self) -> bool:
        """Initialize Financial Agent with LLM client"""
        try:
            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14); hier stond het platformmodel.
            self.llm_client = TenantTaalmodel(self.tenant_id)

            logger.info(f"Financial Agent {self.agent_id} initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Financial Agent: {e}")
            return False

    async def get_capabilities(self) -> list[AgentCapability]:
        """Return agent capabilities"""
        return [
            AgentCapability(
                name="revenue_projection",
                description="Calculate revenue projections with market scenarios",
                input_types=["timeline", "growth_rate", "market_size"],
                output_types=["revenue_projection", "cash_flow"],
            ),
            AgentCapability(
                name="break_even_analysis",
                description="Determine break-even point and timeline",
                input_types=["fixed_costs", "variable_costs", "price_point"],
                output_types=["break_even_month", "break_even_units"],
            ),
            AgentCapability(
                name="roi_analysis",
                description="Calculate ROI for investments and initiatives",
                input_types=["investment", "returns", "timeline"],
                output_types=["roi_percentage", "annualized_roi"],
            ),
            AgentCapability(
                name="ltv_cac_optimization",
                description="Optimize LTV/CAC ratio for sustainable growth",
                input_types=["customer_data", "acquisition_costs", "retention_rates"],
                output_types=["ltv_cac_ratio", "ltv", "cac"],
            ),
        ]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Process financial analysis task
        M-MDP: Async wrapper for sync business logic
        """
        start_time = datetime.now(timezone.utc)

        try:
            analysis_type = task.metadata.get("analysis_type", "revenue_projection")

            if analysis_type not in self.calculation_methods:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Unknown analysis type: {analysis_type}",
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    agent_id=self.agent_id,
                )

            # SYNC calculation (M-MDP compliant)
            calculation_method = self.calculation_methods[analysis_type]
            financial_result = calculation_method(task.metadata)

            # ASYNC LLM enhancement (M-MDP compliant)
            enhanced_result = await self._enhance_with_llm_insights(
                analysis_type, financial_result, task.metadata
            )

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data=enhanced_result,
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                agent_id=self.agent_id,
                confidence_score=1.0,
            )

        except Exception as e:
            logger.error(f"Financial analysis failed: {e}")
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=str(e),
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                agent_id=self.agent_id,
                confidence_score=0.0,
            )

    def _calculate_revenue_projection(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate revenue projection - SYNCHRONOUS M-MDP
        """
        timeline_months = params.get("timeline_months", 12)
        initial_revenue = Decimal(str(params.get("initial_revenue", 0)))
        growth_rate = Decimal(str(params.get("growth_rate", 0.15)))
        market_size = Decimal(str(params.get("market_size", 1000000)))

        cash_flow: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        current_revenue = initial_revenue

        for month in range(timeline_months):
            monthly_growth = current_revenue * growth_rate / 12
            current_revenue += monthly_growth

            # Market penetration cap
            market_cap = market_size * Decimal("0.05")  # 5% market share cap
            if current_revenue > market_cap:
                current_revenue = market_cap

            cash_flow.append(current_revenue.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        final_revenue = cash_flow[-1] if cash_flow else Decimal("0")
        confidence = min(0.95, 0.7 + (float(growth_rate) * 0.1))

        return FinancialMetrics(
            revenue_projection=final_revenue,
            break_even_month=0,  # Will be calculated separately
            roi_percentage=Decimal("0"),
            ltv_cac_ratio=Decimal("0"),
            cash_flow=cash_flow,
            funding_required=Decimal("0"),
            confidence_score=confidence,
        )

    def _calculate_break_even(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate break-even analysis - SYNCHRONOUS M-MDP
        """
        fixed_costs = Decimal(str(params.get("fixed_costs", 50000)))
        variable_cost_per_unit = Decimal(str(params.get("variable_cost_per_unit", 20)))
        price_per_unit = Decimal(str(params.get("price_per_unit", 100)))

        # Break-even calculation
        contribution_margin = price_per_unit - variable_cost_per_unit

        if contribution_margin <= 0:
            break_even_units = Decimal("inf")
            break_even_month = 999
        else:
            break_even_units = fixed_costs / contribution_margin
            # Assume linear growth to break-even
            units_per_month = Decimal(params.get("units_per_month", 100))
            break_even_month = int(break_even_units / units_per_month) + 1

        confidence = 0.8 if contribution_margin > 0 else 0.3

        return FinancialMetrics(
            revenue_projection=break_even_units * price_per_unit,
            break_even_month=break_even_month,
            roi_percentage=Decimal("0"),
            ltv_cac_ratio=Decimal("0"),
            cash_flow=[],
            funding_required=fixed_costs,
            confidence_score=confidence,
        )

    def _calculate_roi(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate ROI analysis - SYNCHRONOUS M-MDP
        """
        investment = Decimal(str(params.get("investment", 100000)))
        expected_returns = Decimal(str(params.get("expected_returns", 150000)))
        timeline_months = params.get("timeline_months", 12)

        if investment == 0:
            roi_percentage = Decimal("0")
        else:
            roi = (expected_returns - investment) / investment * 100
            roi_percentage = roi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Annualize ROI if timeline is not 12 months
        if timeline_months != 12:
            annualized_roi = roi_percentage * (Decimal(12) / Decimal(timeline_months))
            roi_percentage = annualized_roi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        confidence = 0.75 if roi_percentage > 0 else 0.4

        return FinancialMetrics(
            revenue_projection=expected_returns,
            break_even_month=0,
            roi_percentage=roi_percentage,
            ltv_cac_ratio=Decimal("0"),
            cash_flow=[],
            funding_required=investment,
            confidence_score=confidence,
        )

    def _calculate_ltv_cac(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate LTV/CAC optimization - SYNCHRONOUS M-MDP
        """
        avg_order_value = Decimal(str(params.get("avg_order_value", 100)))
        purchase_frequency = Decimal(str(params.get("purchase_frequency", 2)))
        customer_lifespan_months = Decimal(str(params.get("customer_lifespan_months", 24)))
        gross_margin = Decimal(str(params.get("gross_margin", 0.5)))
        cac = Decimal(str(params.get("customer_acquisition_cost", 50)))

        # LTV Calculation
        ltv = (
            avg_order_value
            * purchase_frequency
            * (customer_lifespan_months / Decimal(12))
            * gross_margin
        )

        # LTV/CAC Ratio
        if cac > 0:
            ltv_cac_ratio = (ltv / cac).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            ltv_cac_ratio = Decimal("0")

        # Confidence based on ratio quality
        if ltv_cac_ratio >= 3:
            confidence = 0.9
        elif ltv_cac_ratio >= 2:
            confidence = 0.7
        else:
            confidence = 0.4

        return FinancialMetrics(
            revenue_projection=ltv,
            break_even_month=0,
            roi_percentage=Decimal("0"),
            ltv_cac_ratio=ltv_cac_ratio,
            cash_flow=[],
            funding_required=cac,
            confidence_score=confidence,
        )

    def _calculate_cash_flow(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate cash flow modeling - SYNCHRONOUS M-MDP
        """
        months = params.get("months", 12)
        initial_cash = Decimal(str(params.get("initial_cash", 100000)))
        monthly_revenue = Decimal(str(params.get("monthly_revenue", 10000)))
        monthly_expenses = Decimal(str(params.get("monthly_expenses", 8000)))
        revenue_growth_rate = Decimal(str(params.get("revenue_growth_rate", 0.05)))

        cash_flow: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        current_cash = initial_cash
        current_monthly_revenue = monthly_revenue

        for month in range(months):
            # Revenue grows monthly
            current_monthly_revenue *= Decimal(1) + revenue_growth_rate / Decimal(12)
            monthly_net = current_monthly_revenue - monthly_expenses
            current_cash += monthly_net
            cash_flow.append(current_cash.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        final_cash = cash_flow[-1] if cash_flow else Decimal("0")
        funding_needed = Decimal("0")

        # Check if funding is needed
        min_cash = min(cash_flow) if cash_flow else Decimal("0")
        if min_cash < 0:
            funding_needed = abs(min_cash)

        confidence = 0.8 if final_cash > initial_cash else 0.5

        return FinancialMetrics(
            revenue_projection=final_cash,
            break_even_month=0,
            roi_percentage=Decimal("0"),
            ltv_cac_ratio=Decimal("0"),
            cash_flow=cash_flow,
            funding_required=funding_needed,
            confidence_score=confidence,
        )

    def _calculate_funding_needs(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate funding requirements - SYNCHRONOUS M-MDP
        """
        # Implementation for funding needs calculation
        monthly_burn_rate = Decimal(str(params.get("monthly_burn_rate", 25000)))
        runway_months = params.get("runway_months", 18)
        growth_capital = Decimal(str(params.get("growth_capital", 50000)))

        operating_capital = monthly_burn_rate * Decimal(runway_months)
        total_funding = operating_capital + growth_capital

        confidence = 0.85

        return FinancialMetrics(
            revenue_projection=Decimal("0"),
            break_even_month=runway_months,
            roi_percentage=Decimal("0"),
            ltv_cac_ratio=Decimal("0"),
            cash_flow=[],
            funding_required=total_funding,
            confidence_score=confidence,
        )

    def _analyze_competitive_pricing(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze competitive pricing - SYNCHRONOUS M-MDP
        """
        # Placeholder implementation
        our_price = Decimal(str(params.get("our_price", 100)))
        competitor_prices_raw = params.get("competitor_prices", [90, 110, 95])
        competitor_prices: list[Decimal] = [Decimal(str(p)) for p in competitor_prices_raw]

        avg_competitor_price = (
            sum(competitor_prices) / Decimal(len(competitor_prices))
            if competitor_prices
            else our_price
        )
        price_advantage = Decimal(
            (our_price - avg_competitor_price) / avg_competitor_price * 100
        ).quantize(Decimal("0.01"))

        confidence = 0.7

        return FinancialMetrics(
            revenue_projection=our_price,
            break_even_month=0,
            roi_percentage=price_advantage,
            ltv_cac_ratio=Decimal("0"),
            cash_flow=[],
            funding_required=Decimal("0"),
            confidence_score=confidence,
        )

    def _analyze_unit_economics(self, params: dict[str, Any]) -> FinancialMetrics:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze unit economics - SYNCHRONOUS M-MDP
        """
        # Placeholder implementation
        revenue_per_unit = Decimal(str(params.get("revenue_per_unit", 100)))
        cost_per_unit = Decimal(str(params.get("cost_per_unit", 60)))

        unit_profit = revenue_per_unit - cost_per_unit
        unit_margin = (
            (unit_profit / revenue_per_unit * 100).quantize(Decimal("0.01"))
            if revenue_per_unit > 0
            else Decimal("0")
        )

        confidence = 0.8

        return FinancialMetrics(
            revenue_projection=unit_profit,
            break_even_month=0,
            roi_percentage=unit_margin,
            ltv_cac_ratio=Decimal("0"),
            cash_flow=[],
            funding_required=Decimal("0"),
            confidence_score=confidence,
        )

    async def _enhance_with_llm_insights(
        self, analysis_type: str, metrics: FinancialMetrics, params: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Enhance financial calculations with LLM strategic insights
        M-MDP: ASYNC for I/O operations
        """
        if not self.llm_client:
            logger.warning("LLM client not available, returning raw metrics")
            return self._format_financial_result(metrics, analysis_type)

        # Cast to non-optional type for type checker
        llm_client = self.llm_client

        try:
            context_prompt = f"""
            As a strategic financial advisor, analyze these financial metrics and provide actionable insights:

            Analysis Type: {analysis_type}
            Financial Metrics:
            - Revenue Projection: ${metrics.revenue_projection}
            - Break-even Month: {metrics.break_even_month}
            - ROI: {metrics.roi_percentage}%
            - LTV/CAC Ratio: {metrics.ltv_cac_ratio}
            - Funding Required: ${metrics.funding_required}
            - Confidence Score: {metrics.confidence_score:.2f}

            Provide:
            1. Key insights and interpretation
            2. Risk assessment
            3. Strategic recommendations
            4. Action items

            Keep response concise and business-focused.
            """

            # ASYNC LLM call (M-MDP compliant)
            response = await llm_client.text_completion(context_prompt)

            base_result = self._format_financial_result(metrics, analysis_type)
            base_result["llm_insights"] = {
                "analysis": response.content if hasattr(response, "content") else str(response),
                "provider": "llm",
            }

            return base_result

        except Exception as e:
            logger.error(f"LLM enhancement failed: {e}")
            return self._format_financial_result(metrics, analysis_type)

    def _format_financial_result(
        self, metrics: FinancialMetrics, analysis_type: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Format financial metrics for output"""
        return {
            "analysis_type": analysis_type,
            "revenue_projection": float(metrics.revenue_projection),
            "break_even_month": metrics.break_even_month,
            "roi_percentage": float(metrics.roi_percentage),
            "ltv_cac_ratio": float(metrics.ltv_cac_ratio),
            "cash_flow": [float(cf) for cf in metrics.cash_flow],
            "funding_required": float(metrics.funding_required),
            "confidence_score": metrics.confidence_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }


# Global instance for import - requires tenant_id
# Note: Use with caution - prefer creating instance with explicit tenant_id
financial_agent = FinancialAgent()
