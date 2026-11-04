"""
Unhappy Path Tests for Semantic Router.

Tests failure scenarios, edge cases, and error handling.
"""

import pytest
import pytest_asyncio

from src.core.als.enterprise.departments.department_orchestrator import Department


@pytest.mark.asyncio
@pytest.mark.integration
class TestSemanticRouterUnhappyPaths:
    """Test failure and edge case scenarios."""

    async def test_no_match_found(self, guna_router, prana_budgets):
        """
        Unhappy Path: Task doesn't match any known pattern.

        Should return None with fallback flag.
        """
        result = await guna_router.route(
            task="xyz_unknown_task_12345",
            task_description="Completely nonsensical task description",
            available_prana=prana_budgets,
        )

        assert result.department is None
        assert result.guna_used == "none"
        assert result.confidence == 0.0
        assert result.fallback_used is True
        assert "No matching route" in result.reasoning

    async def test_insufficient_prana_all_layers(self, depleted_prana):
        """
        Unhappy Path: Not enough prana for any layer.

        Even with matching patterns, routing should fail.
        """
        from src.core.als.enterprise.departments.deterministic_router import DeterministicRouter
        from src.core.semantic_router.hybrid_router import GunaRouter

        # Create router with mocked embedder to avoid Ollama dependency
        router = GunaRouter(
            tenant_id=1,
            deterministic_router=DeterministicRouter(),
            semantic_router=None,  # Will fail gracefully
        )

        result = await router.route(
            task="invoice_processing",  # Would normally match Finance
            available_prana=depleted_prana,
        )

        # Should fail due to insufficient prana
        assert result.department is None or result.fallback_used is True
        assert result.prana_cost <= 5  # Shouldn't spend much

    async def test_empty_task_string(self, guna_router, prana_budgets):
        """
        Unhappy Path: Empty or whitespace-only task.
        """
        result = await guna_router.route(
            task="", task_description="", available_prana=prana_budgets
        )

        assert result.department is None
        assert result.confidence == 0.0

    async def test_very_long_task_description(self, guna_router, prana_budgets):
        """
        Unhappy Path: Extremely long task description.

        Should handle gracefully without crashing.
        """
        long_description = "Analyze budget " * 1000  # Very long

        result = await guna_router.route(
            task="budget_analysis", task_description=long_description, available_prana=prana_budgets
        )

        # Should still route correctly (or fail gracefully)
        assert result.department is not None or result.fallback_used is True

    async def test_special_characters_in_task(self, guna_router, prana_budgets):
        """
        Unhappy Path: Task with special characters and SQL injection attempts.
        """
        malicious_tasks = [
            "invoice'; DROP TABLE users; --",
            "budget<script>alert('xss')</script>",
            'hiring"; DELETE FROM tenants;',
            "security ../../../etc/passwd",
        ]

        for task in malicious_tasks:
            result = await guna_router.route(task=task, available_prana=prana_budgets)

            # Should not crash, may or may not find match
            assert isinstance(result.confidence, float)
            assert 0 <= result.confidence <= 1

    async def test_ollama_unavailable(self, prana_budgets):
        """
        Unhappy Path: Ollama service unavailable.

        Should fall back to deterministic routing.
        """
        from src.core.als.enterprise.departments.deterministic_router import DeterministicRouter
        from src.core.semantic_router.embedders import OllamaEmbedder
        from src.core.semantic_router.hybrid_router import GunaRouter
        from src.core.semantic_router.router import SanskritiSemanticRouter

        # Create embedder with invalid URL
        embedder = OllamaEmbedder(base_url="http://invalid:99999")

        semantic = SanskritiSemanticRouter(tenant_id=1, embedder=embedder, similarity_threshold=0.7)

        router = GunaRouter(
            tenant_id=1, deterministic_router=DeterministicRouter(), semantic_router=semantic
        )

        # Should still work using Tamasic layer
        result = await router.route(task="invoice_processing", available_prana=prana_budgets)

        # Should use Tamasic fallback
        assert result.department is not None
        assert result.guna_used in ["tamasic", "tamasic (fallback)"]

    async def test_feedback_with_wrong_prediction(self, guna_router, prana_budgets):
        """
        Unhappy Path: Router made wrong prediction, feedback corrects it.
        """
        # Route a task
        result = await guna_router.route(task="data analysis", available_prana=prana_budgets)

        predicted = result.department

        # Report that it was WRONG
        await guna_router.report_outcome(
            task="data analysis",
            predicted_department=predicted,
            actual_department=Department.DATA_AI_GOVERNANCE,  # Correct answer
            guna_used=result.guna_used,
            success=False,  # Wrong!
        )

        # Verify stats track the failure
        stats = guna_router.get_stats()
        assert stats["total_routes"] >= 1

    async def test_concurrent_routing_requests(self, guna_router, prana_budgets):
        """
        Unhappy Path: Many concurrent routing requests.

        Should handle without race conditions.
        """
        import asyncio

        tasks = [
            guna_router.route(task=f"invoice_processing_{i}", available_prana=prana_budgets)
            for i in range(50)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete
        assert len(results) == 50
        # Most should succeed (some might fail due to resource limits)
        successful = sum(1 for r in results if r.department is not None)
        assert successful >= 40  # At least 80% success rate

    async def test_routing_with_none_prana_budget(self, guna_router):
        """
        Unhappy Path: None passed as prana budget.
        """
        result = await guna_router.route(task="invoice_processing", available_prana=None)

        # Should still work (no budget constraints)
        assert result.department is not None

    async def test_routing_with_empty_prana_budget(self, guna_router):
        """
        Unhappy Path: Empty prana budget dict.
        """
        result = await guna_router.route(task="invoice_processing", available_prana={})

        # Should still work (no budget constraints)
        assert result.department is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestSemanticRouterEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_unicode_characters(self, guna_router, prana_budgets):
        """
        Edge Case: Task with Unicode/emojis.
        """
        result = await guna_router.route(
            task="💰 budget analysis 📊",
            task_description="Financial analysis",
            available_prana=prana_budgets,
        )

        # Should handle gracefully
        assert result is not None

    async def test_single_character_task(self, guna_router, prana_budgets):
        """
        Edge Case: Single character task.
        """
        result = await guna_router.route(task="$", available_prana=prana_budgets)

        # Should not crash
        assert isinstance(result.confidence, float)

    async def test_very_high_confidence_threshold(self, ollama_embedder):
        """
        Edge Case: Impossibly high confidence threshold.
        """
        from src.core.semantic_router.router import SanskritiSemanticRouter

        router = SanskritiSemanticRouter(
            tenant_id=1,
            embedder=ollama_embedder,
            similarity_threshold=0.99,  # Very high
        )
        await router.initialize()

        result = await router.route(task="invoice_processing", available_prana={})

        # Should return None or low confidence
        assert result.confidence < 0.99 or result.department is None

    async def test_zero_similarity_threshold(self, ollama_embedder):
        """
        Edge Case: Zero confidence threshold.
        """
        from src.core.semantic_router.router import SanskritiSemanticRouter

        router = SanskritiSemanticRouter(
            tenant_id=1,
            embedder=ollama_embedder,
            similarity_threshold=0.0,  # Accept anything
        )
        await router.initialize()

        result = await router.route(task="completely unknown task xyz 123", available_prana={})

        # Should match something (even if wrong)
        # or return low confidence match
        assert result is not None
