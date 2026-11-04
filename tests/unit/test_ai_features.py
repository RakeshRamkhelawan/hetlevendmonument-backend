"""Tests for AI Features - Fase 2.4"""

from datetime import datetime, timezone

import pytest

from src.core.ai.adaptive_learning_engine import (
    AdaptationInsight,
    AdaptiveLearningEngine,
    LearningEvent,
    LearningEventType,
)
from src.core.ai.intelligent_routing import (
    IntelligentRouter,
    RequestContext,
    RequestPriority,
    RouteOption,
    RouteStatus,
)
from src.core.ai.predictive_analytics import PredictionType, PredictiveAnalyticsEngine, TimeHorizon


class TestAdaptiveLearningEngine:
    """Test suite for Adaptive Learning Engine"""

    @pytest.fixture
    async def engine(self):
        """Create adaptive learning engine"""
        engine = AdaptiveLearningEngine()
        await engine.initialize()
        return engine

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine):
        """Test engine initializes correctly"""
        assert engine._initialized is True
        assert isinstance(engine.insights, list)
        assert isinstance(engine.learning_events, list)

    @pytest.mark.asyncio
    async def test_get_insights(self, engine):
        """Test get_insights method"""
        insights = await engine.get_insights(min_confidence=0.5, limit=10)

        assert isinstance(insights, list)
        # All insights should meet confidence threshold
        for insight in insights:
            assert isinstance(insight, AdaptationInsight)
            assert insight.confidence >= 0.5

    @pytest.mark.asyncio
    async def test_get_insights_with_category(self, engine):
        """Test get_insights with category filter"""
        # Add some test insights
        test_insight = AdaptationInsight(
            insight_id="test_1",
            pattern_type="frequency_pattern",
            description="Test insight",
            confidence=0.9,
            impact_score=0.8,
            recommended_actions=["action1"],
            supporting_events=["event1"],
            created_at=datetime.now(timezone.utc),
        )
        engine.insights.append(test_insight)

        insights = await engine.get_insights(category="frequency_pattern", min_confidence=0.5)

        assert all(i.pattern_type == "frequency_pattern" for i in insights)

    @pytest.mark.asyncio
    async def test_get_event_count(self, engine):
        """Test get_event_count method"""
        count = await engine.get_event_count()

        assert isinstance(count, int)
        assert count >= 0


class TestIntelligentRouter:
    """Test suite for Intelligent Router"""

    @pytest.fixture
    async def router(self):
        """Create intelligent router"""
        router = IntelligentRouter()
        await router.initialize()
        # Router already has default routes from initialize
        yield router
        # Cleanup background tasks
        await router.cleanup()

    @pytest.mark.asyncio
    async def test_router_initialization(self, router):
        """Test router initializes correctly"""
        assert router._initialized is True
        assert isinstance(router.routes, dict)

    @pytest.mark.asyncio
    async def test_get_available_routes(self, router):
        """Test get_available_routes method"""
        count = await router.get_available_routes()

        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_get_average_decision_time(self, router):
        """Test get_average_decision_time method"""
        time_ms = await router.get_average_decision_time()

        assert isinstance(time_ms, float)
        assert time_ms >= 0.0

    @pytest.mark.asyncio
    async def test_route_alias_method(self, router):
        """Test route() method is alias for route_request()"""
        context = RequestContext(
            request_id="test_123",
            user_id="user_1",
            session_id="session_1",
            request_type="test",
            priority=RequestPriority.NORMAL,
            payload_size=100,
            expected_complexity="low",
        )

        result = await router.route(context)

        # Result can be None if no routes available, or RoutingDecision object
        assert result is None or hasattr(result, "selected_route")


class TestPredictiveAnalyticsEngine:
    """Test suite for Predictive Analytics Engine"""

    @pytest.fixture
    async def engine(self):
        """Create predictive analytics engine"""
        engine = PredictiveAnalyticsEngine()
        await engine.initialize()
        return engine

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine):
        """Test engine initializes correctly"""
        assert engine._initialized is True

    @pytest.mark.asyncio
    async def test_get_active_models_count(self, engine):
        """Test get_active_models_count method"""
        count = await engine.get_active_models_count()

        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_get_average_confidence(self, engine):
        """Test get_average_confidence method"""
        confidence = await engine.get_average_confidence()

        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_predict_alias_method(self, engine):
        """Test predict() method is alias for generate_prediction()"""
        result = await engine.predict(
            prediction_type=PredictionType.LOAD_FORECAST,
            time_horizon=TimeHorizon.SHORT_TERM,
            context={"test": "value"},
            features={"metric1": 0.5, "metric2": 0.8},
        )

        assert hasattr(result, "prediction_id")
        assert hasattr(result, "predicted_value")
        assert hasattr(result, "confidence")
        assert hasattr(result, "uncertainty_bounds")
        assert hasattr(result, "feature_importance")

        assert isinstance(result.confidence, float)
        assert isinstance(result.uncertainty_bounds, list)
        assert isinstance(result.feature_importance, dict)
