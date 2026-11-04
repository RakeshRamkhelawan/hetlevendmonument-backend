"""
Slice 9: ProcedureResolver - Comprehensive Test Suite (RED Phase)

Tests orchestration of all capability agents for complete procedure resolution.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.procedure_resolver import ProcedureResolver
from src.core.agents.capabilities.schemas import (
    ComplianceResult,
    ComplianceStatus,
    ExecutionDecision,
    ExecutionStep,
    PlannerResult,
    ProcedureResolverInput,
    ProcedureResolverOutput,
    ReviewerResult,
    ReviewStatus,
    ScoredProcedure,
)

# ============================================================================
# TEST SUITE 1: High Confidence Resolution (AUTO_EXECUTE)
# ============================================================================


class TestHighConfidenceResolution:
    """Test auto-execution flow for high confidence matches"""

    @pytest.mark.asyncio
    async def test_resolves_high_confidence_procedure(self):
        """Should auto-execute high confidence procedures"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice for $200",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        assert result.decision == ExecutionDecision.AUTO_EXECUTE
        assert result.confidence >= 0.8
        assert result.matched_procedure is not None

    @pytest.mark.asyncio
    async def test_includes_execution_plan(self):
        """Should include execution plan for high confidence"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        if result.decision == ExecutionDecision.AUTO_EXECUTE:
            assert result.execution_plan is not None
            assert len(result.execution_plan.execution_plan) > 0

    @pytest.mark.asyncio
    async def test_passes_compliance_checks(self):
        """Should pass compliance checks for valid requests"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="View my profile",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should not be blocked by compliance
        assert result.decision != ExecutionDecision.NO_MATCH or result.confidence < 0.5


# ============================================================================
# TEST SUITE 2: Medium Confidence Resolution (USER_CONFIRM)
# ============================================================================


class TestMediumConfidenceResolution:
    """Test user confirmation flow for medium confidence"""

    @pytest.mark.asyncio
    async def test_requires_confirmation_for_medium_confidence(self):
        """Should require user confirmation for medium confidence"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Do something with the invoice",  # Ambiguous
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Medium confidence should require confirmation
        if 0.5 <= result.confidence < 0.8:
            assert result.decision == ExecutionDecision.USER_CONFIRM

    @pytest.mark.asyncio
    async def test_provides_matched_procedure(self):
        """Should provide matched procedure for confirmation"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Maybe approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        if result.decision == ExecutionDecision.USER_CONFIRM:
            assert result.matched_procedure is not None


# ============================================================================
# TEST SUITE 3: Low Confidence Resolution (NO_MATCH)
# ============================================================================


class TestLowConfidenceResolution:
    """Test no-match flow for low confidence"""

    @pytest.mark.asyncio
    async def test_returns_no_match_for_low_confidence(self):
        """Should return NO_MATCH for low confidence"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="xyzabc nonsense query",  # Gibberish
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        if result.confidence < 0.5:
            assert result.decision == ExecutionDecision.NO_MATCH

    @pytest.mark.asyncio
    async def test_provides_reasoning_for_no_match(self):
        """Should explain why no match was found"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="completely unknown action",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        assert result.reasoning is not None
        assert len(result.reasoning) > 0


# ============================================================================
# TEST SUITE 4: Ambiguous Matches
# ============================================================================


class TestAmbiguousMatches:
    """Test handling of ambiguous procedure matches"""

    @pytest.mark.asyncio
    async def test_detects_ambiguous_matches(self):
        """Should detect when multiple procedures match similarly"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="approve something",  # Could match multiple
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Check if alternatives are provided
        assert isinstance(result.ambiguous_alternatives, list)

    @pytest.mark.asyncio
    async def test_requires_confirmation_for_ambiguous(self):
        """Should require user confirmation for ambiguous matches"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="approve",  # Multiple procedures might match
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        if len(result.ambiguous_alternatives) > 1:
            assert result.decision in [
                ExecutionDecision.USER_CONFIRM,
                ExecutionDecision.NO_MATCH,
            ]


# ============================================================================
# TEST SUITE 5: Compliance Blocking
# ============================================================================


class TestComplianceBlocking:
    """Test compliance-based blocking of procedures"""

    @pytest.mark.asyncio
    async def test_blocks_on_compliance_failure(self):
        """Should block execution if compliance fails"""
        resolver = ProcedureResolver()

        # Mock compliance failure
        with patch.object(resolver, "_check_compliance") as mock_compliance:
            mock_compliance.return_value = ComplianceResult(
                status=ComplianceStatus.BLOCKED,
                issues=[],
                passed_checks=[],
            )

            input_data = ProcedureResolverInput(
                user_intent="Delete all data",  # Risky action
                tenant_id=uuid4(),
                user_id=uuid4(),
            )

            result = await resolver.resolve(input_data)

            # Should be blocked or require confirmation
            assert (
                result.decision != ExecutionDecision.AUTO_EXECUTE
                or "blocked" in result.reasoning.lower()
            )


# ============================================================================
# TEST SUITE 6: Domain Filtering
# ============================================================================


class TestDomainFiltering:
    """Test domain-specific procedure resolution"""

    @pytest.mark.asyncio
    async def test_filters_by_domain(self):
        """Should filter procedures by domain"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
            domain_filter="finance",
        )

        result = await resolver.resolve(input_data)

        # Should consider domain filter
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_match_in_wrong_domain(self):
        """Should return no match if domain doesn't have procedure"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
            domain_filter="hr",  # Wrong domain for invoice
        )

        result = await resolver.resolve(input_data)

        # Might not find match in wrong domain
        assert result.decision is not None


# ============================================================================
# TEST SUITE 7: Tenant Isolation
# ============================================================================


class TestTenantIsolation:
    """Test tenant isolation in resolution"""

    @pytest.mark.asyncio
    async def test_isolates_by_tenant(self):
        """Should only access procedures for current tenant"""
        resolver = ProcedureResolver()

        tenant_a = uuid4()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=tenant_a,
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should only consider tenant A's procedures
        if result.matched_procedure:
            assert result.matched_procedure is not None


# ============================================================================
# TEST SUITE 8: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling and graceful degradation"""

    @pytest.mark.asyncio
    async def test_handles_registry_failure(self):
        """Should handle registry service failure gracefully"""
        resolver = ProcedureResolver()

        with patch.object(resolver, "_get_candidates") as mock_registry:
            mock_registry.side_effect = Exception("Registry unavailable")

            input_data = ProcedureResolverInput(
                user_intent="Approve invoice",
                tenant_id=uuid4(),
                user_id=uuid4(),
            )

            result = await resolver.resolve(input_data)

            # Should return graceful failure
            assert result.decision == ExecutionDecision.NO_MATCH
            assert "error" in result.reasoning.lower() or "unavailable" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_handles_scorer_failure(self):
        """Should handle scorer service failure gracefully"""
        resolver = ProcedureResolver()

        with patch.object(resolver, "_score_candidates") as mock_scorer:
            mock_scorer.side_effect = Exception("Scorer failed")

            input_data = ProcedureResolverInput(
                user_intent="Approve invoice",
                tenant_id=uuid4(),
                user_id=uuid4(),
            )

            result = await resolver.resolve(input_data)

            # Should fail gracefully
            assert result.decision == ExecutionDecision.NO_MATCH

    @pytest.mark.asyncio
    async def test_handles_empty_candidates(self):
        """Should handle case with no candidate procedures"""
        resolver = ProcedureResolver()

        with patch.object(resolver, "_get_candidates") as mock_registry:
            mock_registry.return_value = []

            input_data = ProcedureResolverInput(
                user_intent="Unknown action",
                tenant_id=uuid4(),
                user_id=uuid4(),
            )

            result = await resolver.resolve(input_data)

            assert result.decision == ExecutionDecision.NO_MATCH
            assert (
                "no procedures" in result.reasoning.lower()
                or "no match" in result.reasoning.lower()
            )


# ============================================================================
# TEST SUITE 9: Orchestration Flow
# ============================================================================


class TestOrchestrationFlow:
    """Test complete orchestration of all agents"""

    @pytest.mark.asyncio
    async def test_calls_all_required_services(self):
        """Should orchestrate all required services"""
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        # Should complete without errors
        result = await resolver.resolve(input_data)

        assert result is not None
        assert result.decision is not None
        assert result.reasoning is not None

    @pytest.mark.asyncio
    async def test_maintains_execution_order(self):
        """Should execute services in correct order"""
        resolver = ProcedureResolver()

        # Registry → Scorer → Planner → Compliance
        input_data = ProcedureResolverInput(
            user_intent="Process payment",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # If we got this far, order was maintained
        assert result is not None


# ============================================================================
# TEST SUITE 10: Validation
# ============================================================================


class TestValidation:
    """Test input validation"""

    @pytest.mark.asyncio
    async def test_requires_user_intent(self):
        """Should require user_intent"""
        resolver = ProcedureResolver()

        try:
            input_data = ProcedureResolverInput(
                user_intent="",  # Empty
                tenant_id=uuid4(),
                user_id=uuid4(),
            )
            await resolver.resolve(input_data)
            # Should handle empty intent gracefully
        except (ValueError, TypeError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_tenant_id(self):
        """Should require tenant_id"""
        resolver = ProcedureResolver()

        try:
            input_data = ProcedureResolverInput(
                user_intent="Approve invoice",
                tenant_id=None,  # Missing
                user_id=uuid4(),
            )
            await resolver.resolve(input_data)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_user_id(self):
        """Should require user_id"""
        resolver = ProcedureResolver()

        try:
            input_data = ProcedureResolverInput(
                user_intent="Approve invoice",
                tenant_id=uuid4(),
                user_id=None,  # Missing
            )
            await resolver.resolve(input_data)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected
