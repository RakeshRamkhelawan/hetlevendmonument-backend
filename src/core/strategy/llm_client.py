"""LLM Client for Strategy Engine."""

import json
import logging
from typing import Any, Optional, cast

from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.strategy.types import StrategicContext, StrategyType

logger = logging.getLogger(__name__)


class LLMMessage:
    """LLM Message format."""

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class LLMResponse:
    """LLM Response format."""

    def __init__(self, content: str, metadata: dict[str, Any] | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        self.content = content
        self.metadata = metadata or {}


class StrategyLLMClient:
    """LLM client wrapper for strategy operations."""

    def __init__(self, client: Any | None = None, provider: str = "mock") -> None:  # TODO(TYPE): replace Any with concrete type
        self._client = client
        self._provider = provider

    @bewaakt_model_aanroep
    async def generate_response(self, messages: list[LLMMessage]) -> LLMResponse:
        """Generate response from LLM."""
        if self._client:
            try:
                response = await self._client.generate(messages)
                return LLMResponse(content=response)
            except Exception as e:
                logger.error("LLM generation failed: %s", e)
        return self._mock_response(messages)

    def _mock_response(self, messages: list[LLMMessage]) -> LLMResponse:
        """Generate mock response for testing."""
        content = messages[-1].content if messages else ""
        return LLMResponse(
            content=json.dumps(
                {
                    "analysis": "Mock analysis",
                    "recommendations": [
                        {
                            "title": "Mock Recommendation 1",
                            "action_statement": "Implement mock strategic action 1",
                            "impact": "High strategic impact",
                            "resources": ["Team A", "Budget $100k"],
                            "timeline_weeks": 4,
                            "success_metrics": ["metric_1", "metric_2"],
                        },
                        {
                            "title": "Mock Recommendation 2",
                            "action_statement": "Execute mock strategic action 2",
                            "impact": "Medium strategic impact",
                            "resources": ["Team B", "Budget $75k"],
                            "timeline_weeks": 6,
                            "success_metrics": ["metric_3", "metric_4"],
                        },
                    ],
                }
            )
        )

    async def analyze_context(
        self,
        strategy_type: StrategyType,
        context: StrategicContext,
        template: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze strategic context."""
        import asyncio

        if not self._client:
            await asyncio.sleep(0.1)
            return self._mock_analysis(strategy_type, context)

        # Create analysis prompt
        analysis_prompt = f"""
        As a senior strategic consultant, conduct a comprehensive {strategy_type.value} analysis.

        CONTEXT:
        - Organization Goals: {context.organization_goals}
        - Market Conditions: {json.dumps(context.market_conditions, indent=2)}
        - Competitive Landscape: {json.dumps(context.competitive_landscape, indent=2)}
        - Internal Capabilities: {json.dumps(context.internal_capabilities, indent=2)}
        - Constraints: {json.dumps(context.constraints, indent=2)}
        - Time Horizon: {context.time_horizon}
        - Success Criteria: {context.success_criteria}

        ANALYSIS FRAMEWORK:
        {template.get("analysis_framework", [])}

        KEY METRICS TO ASSESS:
        {template.get("key_metrics", [])}

        Please provide a detailed analysis covering:
        1. Current Situation Assessment
        2. Key Opportunities and Threats
        3. Strategic Options Analysis
        4. Risk Assessment
        5. Resource Requirements

        Format as JSON with clear sections and actionable insights.
        """

        try:
            response = await self.generate_response(
                [LLMMessage(role="user", content=analysis_prompt)]
            )
            return self._parse_analysis_response(response.content, strategy_type)
        except Exception as e:
            logger.error("Strategic analysis failed: %s", e)
            return self._mock_analysis(strategy_type, context)

    async def generate_recommendations(
        self,
        analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: StrategicContext,
        template: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Generate strategic recommendations."""
        if not self._client:
            return self._mock_recommendations(analysis, context)

        recommendations_prompt = f"""
        Based on the strategic analysis provided, generate specific, actionable recommendations.

        ANALYSIS SUMMARY:
        {json.dumps(analysis, indent=2)}

        CONTEXT:
        - Time Horizon: {context.time_horizon}
        - Success Criteria: {context.success_criteria}
        - Constraints: {json.dumps(context.constraints, indent=2)}

        For each recommendation, provide:
        1. Clear action statement
        2. Expected impact and benefits
        3. Resource requirements
        4. Timeline and milestones
        5. Success metrics
        6. Risk mitigation strategies

        Prioritize recommendations by impact and feasibility.
        Format as JSON array of recommendation objects.
        """

        try:
            response = await self.generate_response(
                [LLMMessage(role="user", content=recommendations_prompt)]
            )
            return self._parse_recommendations_response(response.content)
        except Exception as e:
            logger.error("Recommendation generation failed: %s", e)
            return self._mock_recommendations(analysis, context)

    def _parse_analysis_response(self, text: str, strategy_type: StrategyType) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Parse analysis from LLM response."""
        try:
            if "{" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                return cast(dict[str, Any], json.loads(text[json_start:json_end]))  # TODO(TYPE): replace Any with concrete type
        except json.JSONDecodeError:
            pass
        return self._mock_analysis(
            strategy_type,
            StrategicContext(
                organization_goals=[],
                market_conditions={},
                competitive_landscape={},
                internal_capabilities={},
                constraints={},
                time_horizon="",
                success_criteria=[],
            ),
        )

    def _parse_recommendations_response(self, text: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Parse recommendations from LLM response."""
        try:
            if "[" in text:
                json_start = text.find("[")
                json_end = text.rfind("]") + 1
                return cast(list[dict[str, Any]], json.loads(text[json_start:json_end]))  # TODO(TYPE): replace Any with concrete type
        except json.JSONDecodeError:
            pass
        return self._mock_recommendations({}, None)

    def _mock_analysis(
        self, strategy_type: StrategyType, context: StrategicContext
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "strategy_type": strategy_type.value,
            "current_situation": f"Mock analysis for {strategy_type.value}",
            "opportunities": ["Opportunity 1", "Opportunity 2"],
            "threats": ["Threat 1", "Threat 2"],
            "strategic_options": ["Option A", "Option B", "Option C"],
            "risk_assessment": "Moderate risk level",
            "resource_requirements": [
                "Human resources",
                "Financial resources",
                "Technology resources",
            ],
        }

    def _mock_recommendations(
        self, analysis: dict[str, Any], context: StrategicContext | None  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        return [
            {
                "title": "Recommendation 1",
                "action_statement": "Implement strategic action 1",
                "impact": "High strategic impact",
                "resources": ["Team A", "Budget $100k"],
                "timeline_weeks": 4,
                "success_metrics": ["metric_1", "metric_2"],
            },
            {
                "title": "Recommendation 2",
                "action_statement": "Execute strategic action 2",
                "impact": "Medium strategic impact",
                "resources": ["Team B", "Budget $75k"],
                "timeline_weeks": 6,
                "success_metrics": ["metric_3", "metric_4"],
            },
        ]


def create_strategy_llm_client(provider: str = "mock") -> StrategyLLMClient:
    """Factory function to create LLM client."""
    # Try to get actual client from settings
    try:
        from src.core.shared.llm_client import create_llm_client as _create_client

        client = _create_client(provider)
        if client:
            return StrategyLLMClient(client, provider)
    except Exception as e:
        logger.debug("Could not create LLM client: %s", e)

    return StrategyLLMClient(None, "mock")
