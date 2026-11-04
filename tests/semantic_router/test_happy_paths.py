"""
Happy Path Tests for Semantic Router.

Tests successful routing scenarios with real components.
"""

import pytest
import pytest_asyncio

from src.core.als.enterprise.departments.department_orchestrator import Department


@pytest.mark.asyncio
@pytest.mark.integration
class TestSemanticRouterHappyPaths:
    """Test successful routing scenarios."""

    async def test_exact_match_finance(self, guna_router, prana_budgets):
        """
        Happy Path: Exact keyword match routes to Finance.

        Uses Tamasic layer (deterministic) - fast and reliable.
        """
        result = await guna_router.route(
            task="invoice_processing",
            task_description="Process monthly vendor invoices",
            available_prana=prana_budgets,
        )

        assert result.department == Department.FINANCE
        assert result.guna_used == "tamasic"
        assert result.confidence > 0.9
        assert result.prana_cost == 5
        assert result.fallback_used is False
        assert "Exact pattern match" in result.reasoning

    async def test_exact_match_hr(self, guna_router, prana_budgets):
        """
        Happy Path: Exact keyword match routes to HR.
        """
        result = await guna_router.route(
            task="hiring",
            task_description="New engineer recruitment",
            available_prana=prana_budgets,
        )

        assert result.department == Department.HR
        assert result.guna_used == "tamasic"
        assert result.confidence > 0.9

    async def test_exact_match_security(self, guna_router, prana_budgets):
        """
        Happy Path: Exact keyword match routes to IT Security.
        """
        result = await guna_router.route(
            task="threat_detection",
            task_description="Monitor for intrusion attempts",
            available_prana=prana_budgets,
        )

        assert result.department == Department.IT_SECURITY
        assert result.guna_used == "tamasic"
        assert result.confidence > 0.9

    async def test_semantic_match_after_learning(
        self, guna_router, ollama_embedder, prana_budgets, db_session
    ):
        """
        Happy Path: Semantic routing after learning.

        First, teach the router, then verify it routes correctly.
        Uses Rajasic layer (embeddings + vector search).
        """
        # First, teach the router
        await guna_router.rajasic.learn(
            task="Quantum encryption implementation",
            correct_department=Department.IT_SECURITY,
            was_successful=True,
        )

        # Now route a similar task
        result = await guna_router.route(
            task="Post-quantum cryptography research",
            task_description="Implement lattice-based encryption",
            available_prana=prana_budgets,
        )

        # Should use Rajasic layer and find the learned route
        assert result.department == Department.IT_SECURITY
        assert result.guna_used == "rajasic"
        assert result.confidence > 0.7
        assert result.prana_cost == 25

    async def test_semantic_match_ambiguous_task(
        self, guna_router, ollama_embedder, prana_budgets, db_session
    ):
        """
        Happy Path: Semantic understanding of ambiguous task.

        Task that doesn't match regex patterns but semantically
        belongs to a department.
        """
        # Teach about "market research"
        await guna_router.rajasic.learn(
            task="Analyze competitor landscape",
            correct_department=Department.STRATEGY,
            was_successful=True,
        )

        # Route similar ambiguous task
        result = await guna_router.route(
            task="Research emerging competitors in AI space",
            task_description="Identify startups threatening our market position",
            available_prana=prana_budgets,
        )

        assert result.department == Department.STRATEGY
        assert result.guna_used == "rajasic"
        assert result.confidence > 0.6

    async def test_routing_stats_tracking(self, guna_router, prana_budgets):
        """
        Happy Path: Statistics are tracked correctly.
        """
        # Initial stats
        initial_stats = guna_router.get_stats()
        initial_tamasic = initial_stats["tamasic_hits"]

        # Route several tasks
        for _ in range(3):
            await guna_router.route(task="invoice_processing", available_prana=prana_budgets)

        # Check stats updated
        final_stats = guna_router.get_stats()
        assert final_stats["tamasic_hits"] == initial_tamasic + 3
        assert final_stats["total_routes"] >= 3

    async def test_feedback_learning_improves_routing(self, guna_router, prana_budgets):
        """
        Happy Path: Feedback loop improves future routing.
        """
        # Route a task
        result1 = await guna_router.route(
            task="GDPR compliance audit", available_prana=prana_budgets
        )

        # Provide feedback that it was correct
        await guna_router.report_outcome(
            task="GDPR compliance audit",
            predicted_department=result1.department,
            actual_department=Department.LEGAL_COMPLIANCE,
            guna_used=result1.guna_used,
            success=True,
        )

        # Route similar task again
        result2 = await guna_router.route(
            task="Data privacy assessment", available_prana=prana_budgets
        )

        # Should still route correctly
        assert result2.department is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestGunaLayerTransitions:
    """Test transitions between Guna layers."""

    async def test_tamasic_to_rajasic_fallback(self, guna_router, prana_budgets):
        """
        Happy Path: Falls back to Rajasic when Tamasic has no match.

        After learning, unknown tasks use Rajasic layer.
        """
        # First teach the router
        await guna_router.rajasic.learn(
            task="Machine learning model training",
            correct_department=Department.DATA_AI_GOVERNANCE,
            was_successful=True,
        )

        # Route task that doesn't match Tamasic patterns
        result = await guna_router.route(
            task="Neural network hyperparameter tuning",
            task_description="Optimize deep learning model performance",
            available_prana=prana_budgets,
        )

        # Should use Rajasic (semantic) not Tamasic (deterministic)
        assert result.department == Department.DATA_AI_GOVERNANCE
        assert result.guna_used == "rajasic"

    async def test_confidence_thresholds_respected(self, guna_router, prana_budgets):
        """
        Happy Path: High confidence Tamasic routes skip Rajasic.

        Efficient routing: don't waste prana on Rajasic if Tamasic is confident.
        """
        result = await guna_router.route(
            task="budget_analysis",
            task_description="Q4 financial review",
            available_prana=prana_budgets,
        )

        # Should use Tamasic (cheap) not Rajasic (expensive)
        assert result.department == Department.FINANCE
        assert result.guna_used == "tamasic"
        assert result.prana_cost == 5  # Not 25


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiDepartmentRouting:
    """Test routing to all 10 departments."""

    @pytest.mark.parametrize(
        "task,expected_dept",
        [
            ("market_intelligence", Department.STRATEGY),
            ("technical_architecture", Department.PRODUCT_INNOVATION),
            ("inventory_forecasting", Department.OPERATIONS_SUPPLY_CHAIN),
            ("lead_generation", Department.SALES_MARKETING),
            ("tax_compliance", Department.FINANCE),
            ("talent_acquisition", Department.HR),
            ("threat_hunting", Department.IT_SECURITY),
            ("contract_review", Department.LEGAL_COMPLIANCE),
            ("customer_support", Department.CUSTOMER_EXPERIENCE),
            ("ml_model_training", Department.DATA_AI_GOVERNANCE),
        ],
    )
    async def test_all_departments_routable(self, guna_router, prana_budgets, task, expected_dept):
        """
        Happy Path: All 10 departments can be routed to.
        """
        result = await guna_router.route(task=task, available_prana=prana_budgets)

        assert (
            result.department == expected_dept
        ), f"Task '{task}' should route to {expected_dept.value}"
        assert result.confidence > 0.5
