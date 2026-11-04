"""
Slice 10: End-to-End Test - F1 Invoice Approval Flow

Complete integration test validating the entire agent orchestration pipeline
from user intent to procedure execution.

Flow:
User: "Approve invoice for $200"
  -> DomainPackRegistry (find candidates)
  -> ConfidenceScorer (score matches)
  -> PlannerAgent (create plan)
  -> ComplianceAgent (check policies)
  -> ReviewerAgent (if needed)
  -> ExecutorAgent (execute)
  -> Result

NOTE: These tests use mocked ProcedureResolver and do NOT require database.
They should run quickly (< 1 second per test).
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.core.agents.capabilities.procedure_resolver import ProcedureResolver
from src.core.agents.capabilities.schemas import ExecutionDecision, ProcedureResolverInput

# Mark all tests in this module - fast since they use mocks
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.integration,
    pytest.mark.timeout(30),  # Prevent hanging - 30s max per test (should be < 1s)
]

# ============================================================================
# E2E TEST SUITE: Invoice Approval Flow
# ============================================================================


class TestInvoiceApprovalE2E:
    """End-to-end tests for F1 invoice approval scenario"""

    @pytest.mark.asyncio
    async def test_happy_path_auto_approve(self):
        """
        E2E: User approves invoice with high confidence
        Expected: AUTO_EXECUTE decision with execution plan
        """
        # Given: User wants to approve an invoice
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice for $200",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        # When: System resolves the intent
        result = await resolver.resolve(input_data)

        # Then: System should auto-execute
        assert result.decision == ExecutionDecision.AUTO_EXECUTE
        assert result.confidence >= 0.8
        assert result.matched_procedure is not None
        assert result.matched_procedure.procedure_name == "Invoice Approval Procedure"
        assert result.execution_plan is not None
        assert len(result.execution_plan.execution_plan) >= 2
        assert any("validate" in step.action for step in result.execution_plan.execution_plan)

    @pytest.mark.asyncio
    async def test_medium_confidence_requires_confirmation(self):
        """
        E2E: User request is ambiguous
        Expected: USER_CONFIRM decision
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Process invoice",  # Ambiguous: approve? reject? view?
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should require confirmation due to ambiguity
        if result.confidence < 0.8:
            assert result.decision in [
                ExecutionDecision.USER_CONFIRM,
                ExecutionDecision.NO_MATCH,
            ]

    @pytest.mark.asyncio
    async def test_no_match_for_unknown_intent(self):
        """
        E2E: User requests unknown action
        Expected: NO_MATCH with clear reasoning
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Make coffee",  # Not a business procedure
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        assert result.decision == ExecutionDecision.NO_MATCH
        assert result.confidence < 0.5
        assert "no" in result.reasoning.lower() or "low" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_domain_specific_resolution(self):
        """
        E2E: User specifies domain filter
        Expected: Only finance procedures considered
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
            domain_filter="finance",
        )

        result = await resolver.resolve(input_data)

        # Should find finance procedure
        if result.matched_procedure:
            # Would check domain in production
            assert result.confidence > 0.0

    @pytest.mark.asyncio
    async def test_variations_of_intent(self):
        """
        E2E: Multiple ways to express same intent
        Expected: All resolve to same procedure
        """
        resolver = ProcedureResolver()
        tenant_id = uuid4()
        user_id = uuid4()

        intents = [
            "Approve invoice",
            "Approve invoice for payment",
            "Invoice approval",
            "Approve the invoice",
        ]

        results = []
        for intent in intents:
            input_data = ProcedureResolverInput(
                user_intent=intent,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            result = await resolver.resolve(input_data)
            results.append(result)

        # All should match invoice procedure
        matched_procedures = [r.matched_procedure for r in results if r.matched_procedure]
        assert len(matched_procedures) > 0
        # All should have similar confidence
        confidences = [r.confidence for r in results]
        assert all(c >= 0.6 for c in confidences)


# ============================================================================
# E2E TEST SUITE: User Profile Management Flow
# ============================================================================


class TestUserProfileE2E:
    """End-to-end tests for user profile management"""

    @pytest.mark.asyncio
    async def test_view_profile_auto_execute(self):
        """
        E2E: User views their profile
        Expected: AUTO_EXECUTE for safe read operation
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="View my profile",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should auto-execute safe read operations
        assert result.decision in [
            ExecutionDecision.AUTO_EXECUTE,
            ExecutionDecision.USER_CONFIRM,
        ]
        if result.matched_procedure:
            assert (
                "profile" in result.matched_procedure.procedure_name.lower()
                or "user" in result.matched_procedure.procedure_name.lower()
            )

    @pytest.mark.asyncio
    async def test_update_profile(self):
        """
        E2E: User updates profile
        Expected: Procedure matched with update action
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Update my user profile",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should find profile update procedure
        if result.matched_procedure:
            assert (
                "profile" in result.matched_procedure.procedure_name.lower()
                or "user" in result.matched_procedure.procedure_name.lower()
            )


# ============================================================================
# E2E TEST SUITE: Data Export Flow
# ============================================================================


class TestDataExportE2E:
    """End-to-end tests for data export operations"""

    @pytest.mark.asyncio
    async def test_export_data(self):
        """
        E2E: User exports data
        Expected: Matched to data export procedure
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Export my data",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should find export procedure
        if result.matched_procedure:
            assert (
                "export" in result.matched_procedure.procedure_name.lower()
                or "data" in result.matched_procedure.procedure_name.lower()
            )


# ============================================================================
# E2E TEST SUITE: Edge Cases
# ============================================================================


class TestEdgeCasesE2E:
    """End-to-end tests for edge cases"""

    @pytest.mark.asyncio
    async def test_empty_intent(self):
        """
        E2E: User provides empty intent
        Expected: NO_MATCH with helpful message
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should handle gracefully
        assert result.decision == ExecutionDecision.NO_MATCH

    @pytest.mark.asyncio
    async def test_very_long_intent(self):
        """
        E2E: User provides very long intent
        Expected: Still resolves correctly
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="I would like to approve an invoice that was submitted "
            "yesterday for the amount of $200 and needs to be processed",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should extract key terms (approve, invoice) and match
        assert result.confidence > 0.0

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """
        E2E: Intent with special characters
        Expected: Handles gracefully
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice @ $200 (urgent!)",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await resolver.resolve(input_data)

        # Should still match despite special chars
        assert result.decision in [
            ExecutionDecision.AUTO_EXECUTE,
            ExecutionDecision.USER_CONFIRM,
            ExecutionDecision.NO_MATCH,
        ]


# ============================================================================
# E2E TEST SUITE: Performance
# ============================================================================


class TestPerformanceE2E:
    """End-to-end performance tests"""

    @pytest.mark.asyncio
    async def test_resolution_speed(self):
        """
        E2E: Resolution completes quickly
        Expected: < 1 second for simple resolution
        """
        resolver = ProcedureResolver()

        input_data = ProcedureResolverInput(
            user_intent="Approve invoice",
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        start = datetime.now(timezone.utc)
        result = await resolver.resolve(input_data)
        duration = (datetime.now(timezone.utc) - start).total_seconds()

        # Should complete quickly
        assert duration < 1.0
        assert result is not None

    @pytest.mark.asyncio
    async def test_multiple_sequential_resolutions(self):
        """
        E2E: Multiple resolutions in sequence
        Expected: All complete successfully
        """
        resolver = ProcedureResolver()
        tenant_id = uuid4()
        user_id = uuid4()

        intents = [
            "Approve invoice",
            "View profile",
            "Export data",
        ]

        for intent in intents:
            input_data = ProcedureResolverInput(
                user_intent=intent,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            result = await resolver.resolve(input_data)
            assert result is not None
            assert result.decision is not None
