"""Tests for Strategy Engine Service Layer."""

from datetime import datetime, timezone

import pytest

from src.core.strategy.facade import StrategyEngine
from src.core.strategy.repository import InMemoryStrategyRepository
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
    StrategicPriority,
    StrategyType,
)


class TestStrategyTypes:
    """Test strategy type definitions."""

    def test_strategy_type_values(self):
        assert StrategyType.MARKET_ANALYSIS.value == "market_analysis"
        assert StrategyType.COMPETITIVE_INTELLIGENCE.value == "competitive_intelligence"
        assert StrategyType.PRODUCT_STRATEGY.value == "product_strategy"

    def test_strategic_priority_values(self):
        assert StrategicPriority.CRITICAL.value == "critical"
        assert StrategicPriority.HIGH.value == "high"
        assert StrategicPriority.MEDIUM.value == "medium"

    def test_strategy_templates_exist(self):
        assert StrategyType.MARKET_ANALYSIS in STRATEGY_TEMPLATES
        assert StrategyType.COMPETITIVE_INTELLIGENCE in STRATEGY_TEMPLATES
        assert StrategyType.PRODUCT_STRATEGY in STRATEGY_TEMPLATES


class TestObjectiveService:
    """Test ObjectiveService."""

    @pytest.fixture
    def service(self):
        return ObjectiveService(tenant_id=1)

    @pytest.fixture
    def sample_objective(self):
        return StrategicObjective(
            id="obj-1",
            title="Test Objective",
            description="Test description",
            priority=StrategicPriority.HIGH,
            target_date=datetime.now(timezone.utc),
            success_metrics=["metric1", "metric2"],
        )

    @pytest.mark.asyncio
    async def test_add_objective(self, service, sample_objective):
        await service.add(sample_objective)
        assert "obj-1" in service.objectives
        assert service.objectives["obj-1"].title == "Test Objective"

    @pytest.mark.asyncio
    async def test_get_objective(self, service, sample_objective):
        await service.add(sample_objective)
        obj = service.get("obj-1")
        assert obj is not None
        assert obj.title == "Test Objective"

    def test_get_nonexistent_objective(self, service):
        obj = service.get("nonexistent")
        assert obj is None

    @pytest.mark.asyncio
    async def test_list_active_objectives(self, service):
        obj1 = StrategicObjective(
            id="obj-1",
            title="Active",
            description="",
            priority=StrategicPriority.HIGH,
            target_date=datetime.now(timezone.utc),
            success_metrics=["m1"],
            status="active",
        )
        obj2 = StrategicObjective(
            id="obj-2",
            title="Completed",
            description="",
            priority=StrategicPriority.LOW,
            target_date=datetime.now(timezone.utc),
            success_metrics=["m2"],
            status="completed",
        )
        await service.add(obj1)
        await service.add(obj2)

        active = service.list_active()
        assert len(active) == 1
        assert active[0].id == "obj-1"

    @pytest.mark.asyncio
    async def test_list_by_priority(self, service):
        obj1 = StrategicObjective(
            id="obj-1",
            title="High",
            description="",
            priority=StrategicPriority.HIGH,
            target_date=datetime.now(timezone.utc),
            success_metrics=[],
        )
        obj2 = StrategicObjective(
            id="obj-2",
            title="Low",
            description="",
            priority=StrategicPriority.LOW,
            target_date=datetime.now(timezone.utc),
            success_metrics=[],
        )
        await service.add(obj1)
        await service.add(obj2)

        high = service.list_by_priority(StrategicPriority.HIGH)
        assert len(high) == 1
        assert high[0].title == "High"

    @pytest.mark.asyncio
    async def test_remove_objective(self, service, sample_objective):
        await service.add(sample_objective)
        result = await service.remove("obj-1")
        assert result is True
        assert "obj-1" not in service.objectives

    @pytest.mark.asyncio
    async def test_update_progress(self, service, sample_objective):
        await service.add(sample_objective)
        updated = service.update_progress("obj-1", 0.5)
        assert updated.progress == 0.5

        # Test auto-completion
        updated = service.update_progress("obj-1", 1.0)
        assert updated.status == "completed"


class TestInsightService:
    """Test InsightService."""

    @pytest.fixture
    def service(self):
        return InsightService(tenant_id=1)

    @pytest.fixture
    def sample_insight(self):
        return StrategicInsight(
            id="insight-1",
            type=StrategyType.MARKET_ANALYSIS,
            title="Test Insight",
            description="Test description",
            confidence=0.85,
            impact_score=8.5,
            urgency_score=7.0,
            supporting_evidence=["evidence1"],
            recommended_actions=["action1"],
            risks=["risk1"],
            opportunities=["opportunity1"],
        )

    @pytest.mark.asyncio
    async def test_record_insight(self, service, sample_insight):
        await service.record(sample_insight)
        assert "insight-1" in service.insights

    @pytest.mark.asyncio
    async def test_list_all_insights(self, service):
        insight1 = StrategicInsight(
            id="i1",
            type=StrategyType.MARKET_ANALYSIS,
            title="Insight 1",
            description="",
            confidence=0.8,
            impact_score=7.0,
            urgency_score=6.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        insight2 = StrategicInsight(
            id="i2",
            type=StrategyType.PRODUCT_STRATEGY,
            title="Insight 2",
            description="",
            confidence=0.7,
            impact_score=8.0,
            urgency_score=5.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        await service.record(insight1)
        await service.record(insight2)

        all_insights = service.list_all()
        assert len(all_insights) == 2

    @pytest.mark.asyncio
    async def test_list_by_type(self, service):
        insight1 = StrategicInsight(
            id="i1",
            type=StrategyType.MARKET_ANALYSIS,
            title="Market",
            description="",
            confidence=0.8,
            impact_score=7.0,
            urgency_score=6.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        insight2 = StrategicInsight(
            id="i2",
            type=StrategyType.PRODUCT_STRATEGY,
            title="Product",
            description="",
            confidence=0.7,
            impact_score=8.0,
            urgency_score=5.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        await service.record(insight1)
        await service.record(insight2)

        market_insights = service.list_all(StrategyType.MARKET_ANALYSIS)
        assert len(market_insights) == 1
        assert market_insights[0].title == "Market"

    @pytest.mark.asyncio
    async def test_list_by_confidence(self, service):
        insight1 = StrategicInsight(
            id="i1",
            type=StrategyType.MARKET_ANALYSIS,
            title="High Conf",
            description="",
            confidence=0.9,
            impact_score=7.0,
            urgency_score=6.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        insight2 = StrategicInsight(
            id="i2",
            type=StrategyType.PRODUCT_STRATEGY,
            title="Low Conf",
            description="",
            confidence=0.4,
            impact_score=8.0,
            urgency_score=5.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        await service.record(insight1)
        await service.record(insight2)

        high_conf = service.list_by_confidence(min_confidence=0.5)
        assert len(high_conf) == 1

    @pytest.mark.asyncio
    async def test_list_high_impact(self, service):
        insight1 = StrategicInsight(
            id="i1",
            type=StrategyType.MARKET_ANALYSIS,
            title="High Impact",
            description="",
            confidence=0.8,
            impact_score=8.5,
            urgency_score=6.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        insight2 = StrategicInsight(
            id="i2",
            type=StrategyType.PRODUCT_STRATEGY,
            title="Low Impact",
            description="",
            confidence=0.7,
            impact_score=5.0,
            urgency_score=5.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        await service.record(insight1)
        await service.record(insight2)

        high_impact = service.list_high_impact(threshold=7.0)
        assert len(high_impact) == 1

    @pytest.mark.asyncio
    async def test_analyze_opportunity(self, service):
        insight = await service.analyze_opportunity(
            opportunity_description="Enter new market segment",
            context={"market_conditions": {"growth": "high"}},
        )
        assert insight.type == StrategyType.OPPORTUNITY_ANALYSIS
        assert "Enter new market" in insight.title
        assert insight.confidence > 0


class TestAnalysisService:
    """Test AnalysisService."""

    @pytest.fixture
    def service(self):
        return AnalysisService()

    def test_parse_strategic_analysis_valid_json(self, service):
        json_text = '{"current_situation": "test", "opportunities": ["opp1"]}'
        result = service.parse_strategic_analysis(json_text, StrategyType.MARKET_ANALYSIS)
        assert result["current_situation"] == "test"
        assert result["opportunities"] == ["opp1"]

    def test_parse_strategic_analysis_invalid_json(self, service):
        text = "This is not JSON"
        result = service.parse_strategic_analysis(text, StrategyType.MARKET_ANALYSIS)
        assert "current_situation" in result  # Fallback structure

    def test_parse_recommendations_valid_json(self, service):
        json_text = '[{"title": "Rec 1", "action_statement": "Do this"}]'
        result = service.parse_recommendations(json_text)
        assert len(result) == 1
        assert result[0]["title"] == "Rec 1"

    def test_parse_recommendations_invalid_json(self, service):
        text = "Not JSON"
        result = service.parse_recommendations(text)
        assert len(result) == 2  # Fallback recommendations

    def test_calculate_confidence_score_with_good_data(self, service):
        analysis = {
            "section1": "data1",
            "section2": "data2",
            "section3": "data3",
            "section4": "data4",
        }
        recommendations = [{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5} for _ in range(3)]
        score = service.calculate_confidence_score(analysis, recommendations)
        assert 0 <= score <= 1

    def test_calculate_confidence_score_with_poor_data(self, service):
        analysis = {"section1": "data1"}  # Only 1 section
        recommendations = [{"a": 1}]  # Only 1 recommendation, minimal data
        score = service.calculate_confidence_score(analysis, recommendations)
        assert 0 <= score <= 1

    def test_extract_key_themes(self, service):
        texts = ["growth market opportunity", "growth strategy expansion"]
        themes = service.extract_key_themes(texts)
        assert "growth" in themes

    def test_analyze_sentiment(self, service):
        text = "This is a great opportunity with positive growth potential"
        sentiment = service.analyze_sentiment(text)
        assert sentiment["positive"] > sentiment["negative"]


class TestStrategyDevelopmentService:
    """Test StrategyDevelopmentService."""

    @pytest.fixture
    def service(self):
        return StrategyDevelopmentService(tenant_id=1)

    @pytest.fixture
    def context(self):
        return StrategicContext(
            organization_goals=["growth", "innovation"],
            market_conditions={"size": "large", "growth": "10%"},
            competitive_landscape={"intensity": "high"},
            internal_capabilities={"resources": "adequate"},
            constraints={"budget": "limited"},
            time_horizon="12 months",
            success_criteria=["revenue_growth", "market_share"],
        )

    @pytest.mark.asyncio
    async def test_develop_strategy_with_template(self, service, context):
        result = await service.develop_strategy(StrategyType.MARKET_ANALYSIS, context)
        assert result.id is not None
        assert result.type == StrategyType.MARKET_ANALYSIS
        assert result.status == "draft"
        assert result.confidence_score > 0

    @pytest.mark.asyncio
    async def test_develop_strategy_without_template(self, service, context):
        result = await service.develop_strategy(StrategyType.RISK_ASSESSMENT, context)
        assert result.id is not None
        assert result.status == "custom"

    @pytest.mark.asyncio
    async def test_create_implementation_plan(self, service, context):
        recommendations = [
            {"title": "Phase 1", "timeline_weeks": 4, "action_statement": "Do phase 1"},
            {"title": "Phase 2", "timeline_weeks": 6, "action_statement": "Do phase 2"},
        ]
        plan = await service._create_implementation_plan(recommendations, context)
        assert len(plan["phases"]) == 2
        assert "timeline" in plan
        assert "milestones" in plan

    @pytest.mark.asyncio
    async def test_define_success_metrics_market_analysis(self, service, context):
        metrics = await service._define_success_metrics(StrategyType.MARKET_ANALYSIS, [], context)
        assert "market_share_percentage" in metrics["quantitative_metrics"]
        assert "brand_perception" in metrics["qualitative_metrics"]

    @pytest.mark.asyncio
    async def test_define_success_metrics_product_strategy(self, service, context):
        metrics = await service._define_success_metrics(StrategyType.PRODUCT_STRATEGY, [], context)
        assert "user_adoption_rate" in metrics["quantitative_metrics"]
        assert "product_market_fit" in metrics["qualitative_metrics"]


class TestStrategyEngineFacade:
    """Test StrategyEngine facade."""

    @pytest.fixture
    def engine(self):
        return StrategyEngine(tenant_id=1)

    @pytest.fixture
    def context(self):
        return StrategicContext(
            organization_goals=["growth"],
            market_conditions={},
            competitive_landscape={},
            internal_capabilities={},
            constraints={},
            time_horizon="12 months",
            success_criteria=["revenue"],
        )

    @pytest.mark.asyncio
    async def test_develop_strategy(self, engine, context):
        result = await engine.develop_strategy(StrategyType.MARKET_ANALYSIS, context)
        assert "id" in result
        assert result["type"] == "market_analysis"
        assert result["id"] in engine.strategies

    @pytest.mark.asyncio
    async def test_add_objective(self, engine):
        obj = StrategicObjective(
            id="test-obj",
            title="Test",
            description="",
            priority=StrategicPriority.HIGH,
            target_date=datetime.now(timezone.utc),
            success_metrics=[],
        )
        await engine.add_objective(obj)
        assert "test-obj" in engine.objectives

    @pytest.mark.asyncio
    async def test_record_insight(self, engine):
        insight = StrategicInsight(
            id="test-insight",
            type=StrategyType.MARKET_ANALYSIS,
            title="Test",
            description="",
            confidence=0.8,
            impact_score=7.0,
            urgency_score=6.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        await engine.record_insight(insight)
        assert "test-insight" in engine.insights

    @pytest.mark.asyncio
    async def test_analyze_strategic_opportunity(self, engine):
        insight = await engine.analyze_strategic_opportunity("New market entry")
        assert insight.type == StrategyType.OPPORTUNITY_ANALYSIS

    def test_get_strategy_status(self, engine, context):
        # Add a strategy directly
        engine.strategies["test-strategy"] = {"id": "test-strategy", "status": "active"}
        status = engine.get_strategy_status("test-strategy")
        assert status["id"] == "test-strategy"

    def test_list_active_strategies(self, engine):
        engine.strategies["active-1"] = {"id": "active-1", "status": "active"}
        engine.strategies["completed-1"] = {"id": "completed-1", "status": "completed"}
        engine.strategies["cancelled-1"] = {"id": "cancelled-1", "status": "cancelled"}

        active = engine.list_active_strategies()
        assert len(active) == 1
        assert active[0]["id"] == "active-1"


class TestRepository:
    """Test repository implementations."""

    @pytest.fixture
    async def repo(self):
        return InMemoryStrategyRepository()

    @pytest.mark.asyncio
    async def test_save_and_get_strategy(self):
        repo = InMemoryStrategyRepository()
        strategy = {"id": "s1", "name": "Test Strategy"}
        await repo.save_strategy(1, strategy)

        retrieved = await repo.get_strategy(1, "s1")
        assert retrieved == strategy

    @pytest.mark.asyncio
    async def test_get_strategies_for_tenant(self):
        repo = InMemoryStrategyRepository()
        await repo.save_strategy(1, {"id": "s1", "name": "S1"})
        await repo.save_strategy(1, {"id": "s2", "name": "S2"})
        await repo.save_strategy(2, {"id": "s3", "name": "S3"})

        tenant1_strategies = await repo.get_strategies(1)
        assert len(tenant1_strategies) == 2

    @pytest.mark.asyncio
    async def test_delete_strategy(self):
        repo = InMemoryStrategyRepository()
        await repo.save_strategy(1, {"id": "s1", "name": "Test"})
        await repo.delete_strategy(1, "s1")

        retrieved = await repo.get_strategy(1, "s1")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_save_and_get_objective(self):
        repo = InMemoryStrategyRepository()
        obj = StrategicObjective(
            id="obj1",
            title="Test",
            description="",
            priority=StrategicPriority.HIGH,
            target_date=datetime.now(timezone.utc),
            success_metrics=[],
        )
        await repo.save_objective(1, obj)

        objectives = await repo.get_active_objectives(1)
        assert len(objectives) == 1

    @pytest.mark.asyncio
    async def test_save_and_get_insight(self):
        repo = InMemoryStrategyRepository()
        insight = StrategicInsight(
            id="i1",
            type=StrategyType.MARKET_ANALYSIS,
            title="Test",
            description="",
            confidence=0.8,
            impact_score=7.0,
            urgency_score=6.0,
            supporting_evidence=[],
            recommended_actions=[],
            risks=[],
            opportunities=[],
        )
        await repo.save_insight(1, insight)

        insights = await repo.get_insights(1)
        assert len(insights) == 1
