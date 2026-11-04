"""Strategy Engine Facade - maintains backward compatible API."""

import logging
from typing import Any, Optional

from src.core.strategy.llm_client import create_strategy_llm_client
from src.core.strategy.services import (
    AnalysisService,
    InsightService,
    ObjectiveService,
    StrategyDevelopmentService,
)
from src.core.strategy.types import (
    STRATEGY_TEMPLATES,
    StrategicContext,
    StrategicInsight,
    StrategicObjective,
    StrategyType,
)

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    Advanced strategic planning and analysis engine.

    This is a facade class that delegates to specialized services:
    - StrategyDevelopmentService: Creating comprehensive strategies
    - ObjectiveService: Managing strategic objectives
    - InsightService: Recording and analyzing insights
    - AnalysisService: Parsing analysis results
    """

    def __init__(
        self,
        tenant_id: int | None = None,
        repository: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Initialize the strategy engine.

        Args:
            tenant_id: Tenant scope. None keeps legacy behaviour.
            repository: Optional persistence back-end.
        """
        self.tenant_id = tenant_id
        self._repository = repository

        # Initialize LLM client
        self.llm_client = create_strategy_llm_client()

        # Initialize services
        self._strategy_service = StrategyDevelopmentService(
            tenant_id=tenant_id,
            repository=repository,
            llm_client=self.llm_client,
        )
        self._objective_service = ObjectiveService(
            tenant_id=tenant_id,
            repository=repository,
        )
        self._insight_service = InsightService(
            tenant_id=tenant_id,
            repository=repository,
        )
        self._analysis_service = AnalysisService()

        # Storage (for backward compatibility)
        self.objectives = self._objective_service.objectives
        self.insights = self._insight_service.insights
        self.strategies: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.context_history: list[StrategicContext] = []

        # Strategy templates (for backward compatibility)
        self.strategy_templates = STRATEGY_TEMPLATES

        # Initialize settings
        self.settings: Any = None
        try:
            from src.core.shared.config import get_settings

            self.settings = get_settings()
        except Exception:
            pass

    async def load_persisted_state(self) -> None:
        """Load objectives, insights and strategies from the database."""
        await self._objective_service.load_from_repository()
        await self._insight_service.load_from_repository()

        # Sync local references
        self.objectives = self._objective_service.objectives
        self.insights = self._insight_service.insights

        # Load strategies if repository available
        if self._repository and self.tenant_id is not None:
            try:
                strategies = await self._repository.get_strategies(self.tenant_id)
                for s in strategies:
                    self.strategies[s["id"]] = s
                logger.info(
                    "Loaded %d strategies for tenant %s",
                    len(self.strategies),
                    self.tenant_id,
                )
            except Exception as exc:
                logger.error("Failed to load strategies: %s", exc)

    async def develop_strategy(
        self,
        strategy_type: StrategyType,
        context: StrategicContext,
        requirements: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Develop a comprehensive strategy."""
        result = await self._strategy_service.develop_strategy(strategy_type, context, requirements)

        # Convert to dict for backward compatibility
        strategy_dict = {
            "id": result.id,
            "type": result.type.value,
            "context": result.context,
            "analysis": result.analysis,
            "recommendations": result.recommendations,
            "implementation_plan": result.implementation_plan,
            "success_metrics": result.success_metrics,
            "created_at": result.created_at,
            "status": result.status,
            "confidence_score": result.confidence_score,
        }

        # Update local storage
        self.strategies[result.id] = strategy_dict

        return strategy_dict

    async def add_objective(self, objective: StrategicObjective) -> None:
        """Add a new strategic objective."""
        await self._objective_service.add(objective)

    async def record_insight(self, insight: StrategicInsight) -> None:
        """Record a strategic insight."""
        await self._insight_service.record(insight)

    async def analyze_strategic_opportunity(
        self, opportunity_description: str, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> StrategicInsight:
        """Analyze a specific strategic opportunity."""
        return await self._insight_service.analyze_opportunity(opportunity_description, context)

    def get_strategy_status(self, strategy_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get status of a specific strategy."""
        return self.strategies.get(strategy_id)

    def list_active_strategies(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """List all active strategies."""
        return [
            strategy
            for strategy in self.strategies.values()
            if strategy.get("status") not in ["completed", "cancelled"]
        ]

    def get_strategic_insights(
        self, strategy_type: StrategyType | None = None
    ) -> list[StrategicInsight]:
        """Get strategic insights, optionally filtered by type."""
        return self._insight_service.list_all(strategy_type)

    # Internal methods (for backward compatibility)
    async def _analyze_strategic_context(
        self,
        strategy_type: StrategyType,
        context: StrategicContext,
        template: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze strategic context using LLM."""
        return await self._strategy_service._analyze_strategic_context(
            strategy_type, context, template
        )

    async def _generate_recommendations(
        self,
        analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: StrategicContext,
        template: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Generate strategic recommendations."""
        return await self._strategy_service._generate_recommendations(analysis, context, template)

    async def _create_implementation_plan(
        self, recommendations: list[dict[str, Any]], context: StrategicContext  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create detailed implementation plan."""
        return await self._strategy_service._create_implementation_plan(recommendations, context)

    async def _define_success_metrics(
        self,
        strategy_type: StrategyType,
        recommendations: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        context: StrategicContext,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Define comprehensive success metrics."""
        return await self._strategy_service._define_success_metrics(
            strategy_type, recommendations, context
        )

    def _calculate_confidence_score(
        self, analysis: dict[str, Any], recommendations: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate confidence score for strategy."""
        return self._analysis_service.calculate_confidence_score(analysis, recommendations)

    def _parse_strategic_analysis(
        self, analysis_text: str, strategy_type: StrategyType
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Parse strategic analysis from LLM response."""
        return self._analysis_service.parse_strategic_analysis(analysis_text, strategy_type)

    def _parse_recommendations(self, recommendations_text: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Parse recommendations from LLM response."""
        return self._analysis_service.parse_recommendations(recommendations_text)

    async def _create_custom_strategy(
        self,
        strategy_type: StrategyType,
        context: StrategicContext,
        requirements: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create custom strategy for types without templates."""
        result = await self._strategy_service._create_custom_strategy(
            strategy_type, context, requirements
        )
        return {
            "id": result.id,
            "type": result.type.value,
            "status": result.status,
            "analysis": result.analysis,
            "recommendations": result.recommendations,
            "implementation_plan": result.implementation_plan,
            "confidence_score": result.confidence_score,
        }

    async def _mock_strategic_analysis(
        self, strategy_type: StrategyType, context: StrategicContext
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Mock strategic analysis for testing."""
        return await self._strategy_service._mock_strategic_analysis(strategy_type, context)

    def _mock_recommendations(
        self, analysis: dict[str, Any], context: StrategicContext  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Mock recommendations for testing."""
        return self._strategy_service._mock_recommendations(analysis, context)

    def _initialize_llm(self) -> None:
        """Initialize LLM client (for backward compatibility)."""
        self.llm_client = create_strategy_llm_client()
